#!/usr/bin/env python3
"""
MIDI SysEx proxy/sniffer for Zoom G3Xn protocol analysis.

Creates a virtual MIDI device that sits between the Wine app and the real
ZOOM G Series pedal. All SysEx traffic is logged with timestamps.

Architecture:
  Wine app --> [proxy_in] --> proxy logs --> [ZOOM pedal]
  ZOOM pedal --> [proxy logs] --> [proxy_out] --> Wine app

Usage:
  python3 midi_proxy_sniffer.py [--zoom-port 28:0] [--output capture.log]
"""

import sys
import time
import threading
import argparse
import os
import subprocess

# Use raw ALSA seq for virtual MIDI ports
# We'll use aconnect to create the virtual pair

def create_virtual_pair(name_prefix="zoomproxy"):
    """Create a virtual MIDI pair using aconnect/alsa.
    Returns (tx_port, rx_port) as (client, port) tuples.
    """
    # Use amidi or a Python approach
    # Actually, the simplest: use two rtmidi virtual ports
    import rtmidi
    # rtmidi doesn't support virtual port creation directly
    # Use ALSA seq via subprocess
    pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom-port", default="28:0", help="ZOOM device CLIENT:PORT")
    parser.add_argument("--output", default="/tmp/zoom_capture.log", help="Capture log file")
    parser.add_argument("--list", action="store_true", help="List MIDI ports")
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

    # Strategy: 
    # 1. Open ZOOM device input (to read pedal responses)
    # 2. Open ZOOM device output (to send commands to pedal)
    # 3. Create a virtual MIDI port for the Wine app to connect to
    # 4. Proxy between virtual port and ZOOM device, logging everything

    # For simplicity, let's use the Midi Through approach:
    # - Wine app connects to Midi Through (14:0)
    # - We forward Midi Through -> ZOOM and ZOOM -> Midi Through
    # - We also read from Midi Through to log

    # Actually, the cleanest approach for Wine:
    # Wine's ALSA driver will see the ZOOM device directly.
    # We just need to tap the traffic.
    
    # Simplest working approach:
    # 1. Open ZOOM input port to read responses
    # 2. Open ZOOM output port to forward app's commands
    # 3. Log everything
    
    # But Wine will connect directly to ZOOM, bypassing us.
    # So we need to intercept.
    
    # Best approach: Use aconnect to route ZOOM through Midi Through,
    # then have Wine connect to Midi Through instead of ZOOM.
    
    print("Setting up MIDI routing...")
    
    # Disconnect existing
    subprocess.run(["aconnect", "-i"], capture_output=True)
    subprocess.run(["aconnect", "-o"], capture_output=True)
    
    # Connect Midi Through (14:0) to ZOOM (28:0)
    r = subprocess.run(["aconnect", "14:0", "28:0"], capture_output=True, text=True)
    print(f"  Midi Through -> ZOOM: {r.returncode}")
    
    # Connect ZOOM (28:0) to Midi Through (14:0)
    r = subprocess.run(["aconnect", "28:0", "14:0"], capture_output=True, text=True)
    print(f"  ZOOM -> Midi Through: {r.returncode}")
    
    # Now: Wine app should connect to Midi Through (14:0)
    # Traffic flow: Wine -> Midi Through -> ZOOM -> Midi Through -> Wine
    # We read from Midi Through to log
    
    # Find Midi Through port
    in_api = rtmidi.MidiIn()
    in_api.set_error_callback(lambda e: None)
    
    mt_port = None
    for n in range(in_api.get_port_count()):
        name = in_api.get_port_name(n)
        if "Midi Through" in name:
            mt_port = n
            print(f"  Midi Through at port {n}: {name}")
            break
    
    if mt_port is None:
        print("ERROR: Midi Through not found!")
        return
    
    in_api.open_port(mt_port, "zoom-sniffer")
    
    # Log file
    log_file = open(args.output, 'w')
    log_file.write(f"# Zoom G3Xn MIDI Capture - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write(f"# Device: ZOOM G Series (28:0) via Midi Through\n")
    log_file.write(f"# Format: [timestamp] DIRECTION length bytes hex\n")
    log_file.flush()
    
    print(f"\nListening on Midi Through ({in_api.get_port_name(mt_port)})...")
    print(f"Logging to: {args.output}")
    print("Wine app should connect to 'Midi Through Port-0' (14:0)")
    print("Press Ctrl+C to stop.\n")
    
    start = time.time()
    msg_count = 0
    sysex_count = 0
    
    try:
        while True:
            msg = in_api.get_message()
            if msg:
                ts, data = msg
                if not data:
                    continue
                t = time.time() - start
                msg_count += 1
                
                if data[0] == 0xF0:
                    sysex_count += 1
                    hexstr = ' '.join(f'{b:02x}' for b in data)
                    line = f"[{t:10.4f}] SYSEX {len(data):4d}B {hexstr}"
                    log_file.write(line + "\n")
                    log_file.flush()
                    
                    # Also print to stderr for live monitoring
                    desc = parse_sysex_desc(data)
                    if desc:
                        print(f"[{t:8.3f}] {desc}", file=sys.stderr)
                else:
                    hexstr = ' '.join(f'{b:02x}' for b in data)
                    line = f"[{t:10.4f}] MIDI  {len(data):4d}B {hexstr}"
                    log_file.write(line + "\n")
                    log_file.flush()
            else:
                time.sleep(0.001)
    except KeyboardInterrupt:
        print(f"\nStopped. {msg_count} messages ({sysex_count} SysEx) captured.")
    finally:
        log_file.close()
        print(f"Capture saved to: {args.output}")


def parse_sysex_desc(data):
    """Return a short description of a Zoom SysEx message."""
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
    if not rest:
        return "zoom:empty"
    if rest[0] != 0x60:
        return f"zoom:non60 {rest[:4].hex(' ')}"
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
    return f"zoom:{name} [{rest.hex(' ')}]"


if __name__ == "__main__":
    main()