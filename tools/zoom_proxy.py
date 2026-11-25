#!/usr/bin/env python3
"""
MIDI proxy/sniffer using rtmidi virtual ports.

Creates two virtual MIDI ports:
  - "zoom-proxy-IN"  (Wine app sends SysEx here)
  - "zoom-proxy-OUT" (Wine app receives SysEx here)

Forwards all traffic to/from the real ZOOM G Series device,
logging everything with timestamps.

Architecture:
  Wine app --send--> [zoom-proxy-IN] --proxy--> ZOOM pedal
  ZOOM pedal --resp--> [proxy] --> [zoom-proxy-OUT] --send--> Wine app

Usage:
  python3 zoom_proxy.py [--zoom 28:0] [--output /tmp/zoom_capture.log]
"""

import sys
import time
import threading
import argparse
import rtmidi

class ZoomProxy:
    def __init__(self, zoom_port_str="28:0", output_file="/tmp/zoom_capture.log"):
        self.zoom_client, self.zoom_port = map(int, zoom_port_str.split(":"))
        self.output_file = output_file
        self.log_file = None
        self.running = False
        self.msg_count = 0
        self.sysex_count = 0
        self.start_time = time.time()

        # Open ZOOM device
        self.zoom_in = rtmidi.MidiIn()
        self.zoom_in.set_error_callback(self._err_cb)
        self.zoom_out = rtmidi.MidiOut()
        self.zoom_out.set_error_callback(self._err_cb)

        # Find ZOOM ports
        self.zoom_in_port = None
        for n in range(self.zoom_in.get_port_count()):
            name = self.zoom_in.get_port_name(n)
            if "ZOOM" in name.upper() or "G Series" in name:
                self.zoom_in_port = n
                print(f"ZOOM input:  {n} ({name})")
                break

        self.zoom_out_port = None
        for n in range(self.zoom_out.get_port_count()):
            name = self.zoom_out.get_port_name(n)
            if "ZOOM" in name.upper() or "G Series" in name:
                self.zoom_out_port = n
                print(f"ZOOM output: {n} ({name})")
                break

        if self.zoom_in_port is None or self.zoom_out_port is None:
            raise RuntimeError("ZOOM device not found!")

        self.zoom_in.open_port(self.zoom_in_port, "proxy-zoom-in")
        self.zoom_out.open_port(self.zoom_out_port, "proxy-zoom-out")

        # Create virtual ports for the Wine app
        self.app_in = rtmidi.MidiIn()      # Wine app sends here
        self.app_in.set_error_callback(self._err_cb)
        self.app_out = rtmidi.MidiOut()    # Wine app receives here
        self.app_out.set_error_callback(self._err_cb)

        self.app_in.open_virtual_port("zoom-proxy-IN")
        self.app_out.open_virtual_port("zoom-proxy-OUT")
        print("Virtual ports created: zoom-proxy-IN, zoom-proxy-OUT")

    def _err_cb(self, err):
        pass  # Suppress errors

    def log(self, direction, data):
        t = time.time() - self.start_time
        hexstr = ' '.join(f'{b:02x}' for b in data)
        line = f"[{t:10.4f}] {direction:6s} {len(data):4d}B {hexstr}"
        self.log_file.write(line + "\n")
        self.log_file.flush()
        self.msg_count += 1
        if data and data[0] == 0xF0:
            self.sysex_count += 1
            desc = parse_sysex_desc(data)
            if desc:
                print(f"[{t:8.3f}] {direction:6s} {desc}", file=sys.stderr, flush=True)

    def app_to_zoom(self):
        """Read from app virtual port, forward to ZOOM, log."""
        while self.running:
            msg = self.app_in.get_message()
            if msg:
                ts, data = msg
                if data:
                    self.log("APP>ZOOM", data)
                    try:
                        self.zoom_out.send_message(data)
                    except Exception as e:
                        print(f"Error sending to ZOOM: {e}", file=sys.stderr)
            else:
                time.sleep(0.001)

    def zoom_to_app(self):
        """Read from ZOOM, forward to app virtual port, log."""
        while self.running:
            msg = self.zoom_in.get_message()
            if msg:
                ts, data = msg
                if data:
                    self.log("ZOOM>APP", data)
                    try:
                        self.app_out.send_message(data)
                    except Exception as e:
                        print(f"Error sending to app: {e}", file=sys.stderr)
            else:
                time.sleep(0.001)

    def run(self):
        self.log_file = open(self.output_file, 'w')
        self.log_file.write(f"# Zoom G3Xn MIDI Proxy Capture - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.log_file.write(f"# ZOOM device: {self.zoom_client}:{self.zoom_port}\n")
        self.log_file.write(f"# Virtual ports: zoom-proxy-IN (app->zoom), zoom-proxy-OUT (zoom->app)\n")
        self.log_file.write(f"# Format: [timestamp] DIRECTION length hex\n")
        self.log_file.flush()

        self.running = True
        t1 = threading.Thread(target=self.app_to_zoom, daemon=True)
        t2 = threading.Thread(target=self.zoom_to_app, daemon=True)
        t1.start()
        t2.start()

        print(f"\nProxy running. Logging to: {self.output_file}")
        print("Wine app should connect to 'zoom-proxy-IN' (send) and 'zoom-proxy-OUT' (receive)")
        print("Press Ctrl+C to stop.\n")

        try:
            while True:
                time.sleep(1)
                elapsed = time.time() - self.start_time
                print(f"\r  {elapsed:.0f}s: {self.msg_count} msgs ({self.sysex_count} SysEx)", end="", file=sys.stderr, flush=True)
        except KeyboardInterrupt:
            print(f"\nStopped. {self.msg_count} messages ({self.sysex_count} SysEx).")
        finally:
            self.running = False
            self.log_file.close()
            print(f"Capture saved to: {self.output_file}")


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", default="28:0")
    parser.add_argument("--output", default="/tmp/zoom_capture.log")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        print("=== Input Ports ===")
        i = rtmidi.MidiIn()
        for n in range(i.get_port_count()):
            print(f"  {n}: {i.get_port_name(n)}")
        print("=== Output Ports ===")
        o = rtmidi.MidiOut()
        for n in range(o.get_port_count()):
            print(f"  {n}: {o.get_port_name(n)}")
        sys.exit(0)

    proxy = ZoomProxy(args.zoom, args.output)
    proxy.run()