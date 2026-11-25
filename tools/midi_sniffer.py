#!/usr/bin/env python3
"""
midi_sniffer.py — Capture ALL MIDI traffic from the G3Xn raw device.

Logs every SysEx message (both directions) with timestamps to a log file.
Run this BEFORE starting Guitar Lab or any other MIDI tool.

Usage:
  python3 midi_sniffer.py [output.log] [duration_seconds]

Then in another terminal, run the tool that talks to the pedal.
When done, Ctrl+C the sniffer.
"""
import sys, os, time, json

RAW = "/dev/snd/midiC3D0"

def hexdump(b, n=80):
    return " ".join(f"{x:02x}" for x in b[:n]) + ("..." if len(b) > n else "")

class Sniffer:
    def __init__(self, logfile):
        self.logf = open(logfile, "w")
        self.fd = os.open(RAW, os.O_RDWR | os.O_NONBLOCK)
        self._flush()
        self.log("=== Sniffer started ===")
        self.count = 0

    def _flush(self, t=0.5):
        end = time.time() + t
        while time.time() < end:
            try:
                os.read(self.fd, 4096)
            except (BlockingIOError, OSError):
                break

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        self.logf.write(line + "\n")
        self.logf.flush()

    def parse_sysex(self, buf):
        """Extract complete SysEx messages from a buffer. Yields (is_reply, body)."""
        i = 0
        while i < len(buf):
            if buf[i] == 0xF0:
                # Find F7
                j = i + 1
                while j < len(buf) and buf[j] != 0xF7:
                    j += 1
                if j < len(buf):
                    msg = buf[i:j+1]
                    # Check if it's a Zoom SysEx
                    if len(msg) >= 6 and msg[1] == 0x52 and msg[2] == 0x00 and msg[3] == 0x6E:
                        body = msg[4:-1]
                        yield body
                    i = j + 1
                    continue
            i += 1

    def run(self, duration=0):
        end = time.time() + duration if duration > 0 else None
        buf = bytearray()
        while True:
            if end and time.time() > end:
                break
            try:
                d = os.read(self.fd, 4096)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            except OSError as e:
                self.log(f"DEVICE ERROR: {e}")
                break
            buf.extend(d)
            # Try to extract SysEx messages
            remaining = bytearray()
            i = 0
            while i < len(buf):
                if buf[i] == 0xF0:
                    j = i + 1
                    while j < len(buf) and buf[j] != 0xF7:
                        j += 1
                    if j < len(buf):
                        msg = bytes(buf[i:j+1])
                        if len(msg) >= 6 and msg[1] == 0x52 and msg[2] == 0x00 and msg[3] == 0x6E:
                            body = msg[4:-1]
                            self.count += 1
                            self.log(f"  RX #{self.count}: {hexdump(body, 100)}")
                        i = j + 1
                        continue
                else:
                    # Non-SysEx MIDI byte (could be a regular MIDI message)
                    # Collect until next F0
                    j = i + 1
                    while j < len(buf) and buf[j] != 0xF0:
                        j += 1
                    chunk = bytes(buf[i:j])
                    if len(chunk) > 0:
                        self.log(f"  RX raw: {hexdump(chunk, 40)}")
                    i = j
                    continue
                i += 1

    def close(self):
        self.log("=== Sniffer stopped ===")
        self.logf.close()
        try:
            os.close(self.fd)
        except:
            pass


def main():
    logfile = sys.argv[1] if len(sys.argv) > 1 else "midi_capture.log"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    print(f"Sniffing {RAW} -> {logfile}")
    print("Ctrl+C to stop.\n")
    s = Sniffer(logfile)
    try:
        s.run(duration)
    except KeyboardInterrupt:
        pass
    finally:
        s.close()
    print(f"\nDone. {s.count} SysEx messages captured.")


if __name__ == "__main__":
    main()