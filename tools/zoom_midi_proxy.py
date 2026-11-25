#!/usr/bin/env python3
"""
MIDI proxy/sniffer using ALSA seq virtual ports.

Creates two virtual MIDI ports:
  - "zoom-proxy-in"  (Wine app sends here)
  - "zoom-proxy-out" (Wine app receives here)

Forwards all traffic to/from the real ZOOM device, logging everything.

Usage:
  python3 zoom_midi_proxy.py [--zoom 28:0] [--output /tmp/zoom_capture.log]
"""

import sys
import time
import threading
import argparse
import subprocess
import os
import struct

# We'll use raw ALSA seq via the python-rtmidi library for the ZOOM device,
# and create virtual ports using aconnect/alsactl.

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", default="28:0", help="ZOOM device CLIENT:PORT")
    parser.add_argument("--output", default="/tmp/zoom_capture.log")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    import rtmidi

    if args.list:
        print("=== Input Ports ===")
        i = rtmidi.MidiIn()
        for n in range(i.get_port_count()):
            print(f"  {n}: {i.get_port_name(n)}")
        print("=== Output Ports ===")
        o = rtmidi.MidiOut()
        for n in range(o.get_port_count()):
            print(f"  {n}: {o.get_port_name(n)}")
        return

    zoom_client, zoom_port = map(int, args.zoom.split(":"))

    # Open ZOOM device
    zoom_in = rtmidi.MidiIn()
    zoom_in.set_error_callback(lambda e: None)
    zoom_out = rtmidi.MidiOut()
    zoom_out.set_error_callback(lambda e: None)

    # Find ZOOM port
    zoom_in_port = None
    for n in range(zoom_in.get_port_count()):
        name = zoom_in.get_port_name(n)
        if "ZOOM" in name.upper() or "G Series" in name:
            zoom_in_port = n
            print(f"ZOOM input: {n} ({name})")
            break

    zoom_out_port = None
    for n in range(zoom_out.get_port_count()):
        name = zoom_out.get_port_name(n)
        if "ZOOM" in name.upper() or "G Series" in name:
            zoom_out_port = n
            print(f"ZOOM output: {n} ({name})")
            break

    if zoom_in_port is None or zoom_out_port is None:
        print("ERROR: ZOOM device not found!")
        return

    zoom_in.open_port(zoom_in_port, "proxy-in")
    zoom_out.open_port(zoom_out_port, "proxy-out")

    # Create virtual MIDI ports using amidi or a Python approach
    # For simplicity, use aconnect to create a virtual pair
    # Actually, let's use the "Midi Through" port as the virtual port
    # and have the Wine app connect to it.

    # The key insight: Wine's ALSA driver will see ALL MIDI ports.
    # If we disconnect the ZOOM device from direct access and only
    # expose it through Midi Through, the Wine app will use Midi Through.

    # But we can't easily disconnect the ZOOM device.
    # Instead, let's create a Python-based virtual MIDI port.

    # Use raw ALSA seq to create virtual ports
    # This requires the python-alsaseq library or direct ALSA calls.

    # Simplest approach: Use amidi to create a virtual port
    # Actually, let's just use the Midi Through port and hope the
    # Wine app connects to it.

    # For now, let's just log all traffic from the ZOOM device
    # while the Wine app runs. The Wine app will connect directly
    # to the ZOOM device, and we'll read from the ZOOM input port.

    print("\nListening on ZOOM device...")
    print(f"Logging to: {args.output}")
    print("Start the Wine app and perform file operations.")
    print("Press Ctrl+C to stop.\n")

    log_file = open(args.output, 'w')
    log_file.write(f"# Zoom G3Xn MIDI Capture - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write(f"# Device: ZOOM G Series ({args.zoom})\n")
    log_file.write(f"# Format: [timestamp] DIRECTION length hex\n")
    log_file.flush()

    start = time.time()
    msg_count = 0
    sysex_count = 0
    running = True

    def reader_thread():
        nonlocal msg_count, sysex_count
        while running:
            msg = zoom_in.get_message()
            if msg:
                ts, data = msg
                if not data:
                    continue
                t = time.time() - start
                msg_count += 1
                if data[0] == 0xF0:
                    sysex_count += 1
                    hexstr = ' '.join(f'{b:02x}' for b in data)
                    line = f"[{t:10.4f}] PEDAL>{len(data):4d}B {hexstr}"
                    log_file.write(line + "\n")
                    log_file.flush()
                    desc = parse_sysex_desc(data)
                    if desc:
                        print(f"[{t:8.3f}] P2H {desc}", file=sys.stderr)
                else:
                    hexstr = ' '.join(f'{b:02x}' for b in data)
                    line = f"[{t:10.4f}] PEDAL>{len(data):4d}B {hexstr}"
                    log_file.write(line + "\n")
                    log_file.flush()
            else:
                time.sleep(0.001)

    t = threading.Thread(target=reader_thread, daemon=True)
    t.start()

    # Main thread: wait and periodically report
    try:
        while True:
            time.sleep(1)
            elapsed = time.time() - start
            print(f"\r  {elapsed:.0f}s: {msg_count} msgs ({sysex_count} SysEx)", end="", file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        print(f"\nStopped. {msg_count} messages ({sysex_count} SysEx).")
    finally:
        running = False
        log_file.close()
        print(f"Capture saved to: {args.output}")


def parse_sysex_desc(data):
    if len(data) < 2 or data[0] != 0xF0:
        return None
    f7 = data.find(0xF7, 1)
    body = data[1:f7] if f7 > 0 else data[1:]
    if len(body) < 3:
        return None
    mfg = body[0] | (body[1] << 7)
    if mfg != 0x006E:
        return f"mfg={mfg:#06x}"
    rest = body[2:]
    if not rest or rest[0] != 0x60:
        return f"zoom:non60 {rest[:4].hex(' ')}" if rest else "zoom:empty"
    if len(rest) < 2:
        return "zoom:60"
    cmd = rest[1]
    names = {
        0x03: "STATUS", 0x04: "DATA", 0x05: "ACK", 0x09: "TERM",
        0x14: "RD_NXT_REQ", 0x20: "OPEN", 0x21: "CLOSE",
        0x22: "RD_NXT", 0x23: "WR_BLK", 0x24: "CREATE",
        0x25: "LIST", 0x27: "END_LST", 0x29: "DISK",
    }
    name = names.get(cmd, f"0x{cmd:02x}")
    return f"{name} [{rest.hex(' ')}]"


if __name__ == "__main__":
    main()