#!/usr/bin/env python3
"""Minimal G3Xn SysEx client over ALSA (alsa-midi package).

Usage:
    python3 g3xn_client.py list
    python3 g3xn_client.py disk
    python3 g3xn_client.py download FLST_SEQ.ZT2 out.bin
    python3 g3xn_client.py raw <hexbody>
"""
import sys, time
import alsa_midi as am

PEDAL_CLIENT = 28
PEDAL_PORT = 0

def hexdump(b, n=90):
    return " ".join(f"{x:02x}" for x in b[:n])


class G3Xn:
    def __init__(self):
        self.client = am.SequencerClient(client_name="g3xn-tool")
        self.port = self.client.create_port(name="g3xn", caps=am.RW_PORT)
        self.port.connect_to(am.Address(PEDAL_CLIENT, PEDAL_PORT))
        print(f"[+] connected to ZOOM G Series ({PEDAL_CLIENT}:{PEDAL_PORT})", file=sys.stderr)

    def send(self, body: bytes):
        msg = bytes([0xF0, 0x52, 0x00, 0x6E]) + body + bytes([0xF7])
        ev = am.SysExEvent(data=msg)
        self.client.event_output(ev)
        self.client.drain_output()

    def read_reply(self, timeout=3.0):
        """Read SysEx events until F7 (or timeout). Returns concatenated body bytes."""
        deadline = time.time() + timeout
        buf = bytearray()
        while time.time() < deadline:
            ev = self.client.event_input()  # blocking until an event or None
            if ev is None:
                time.sleep(0.005)
                continue
            if ev.type == am.EventType.SYSTEM_EXCLUSIVE:
                buf.extend(ev.data)
                if len(buf) >= 2 and buf[-1] == 0xF7:
                    return bytes(buf)
            # else: ignore (note/CC/echo)
        return bytes(buf)

    def close(self):
        try:
            self.port.close()
        except Exception:
            pass
        self.client.close()


def main():
    g = G3Xn()
    try:
        cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
        if cmd == "list":
            g.send(bytes([0x60, 0x25, 0x00, 0x00, 0x2A, 0x00]))  # list first, '*'
            r = g.read_reply(2.0)
            print("LIST first reply:", hexdump(r))
            for i in range(300):
                g.send(bytes([0x60, 0x26, 0x00, 0x00, 0x2A, 0x00]))  # next
                r = g.read_reply(1.5)
                if len(r) > 14 and r[5] == 0x04:
                    name = bytes(r[14:27]).split(b"\x00")[0].decode("ascii", "replace")
                    print(f"  {name}")
                else:
                    break
            g.send(bytes([0x60, 0x27]))  # end list
            g.read_reply(1.0)
        elif cmd == "disk":
            g.send(bytes([0x60, 0x29, 0x00, 0x00, 0x00, 0x00, 0x00]))
            r = g.read_reply(2.0)
            print("DISK reply:", hexdump(r))
        elif cmd == "download":
            fname = sys.argv[2].encode()
            outp = sys.argv[3]
            g.send(bytes([0x60, 0x05, 0x00]))
            r = g.read_reply(2.0)
            print("status:", hexdump(r))
            g.send(bytes([0x60, 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + fname + b"\x00")
            r = g.read_reply(2.0)
            print("open:", hexdump(r))
            data = bytearray()
            for _ in range(5000):
                g.send(bytes([0x60, 0x05, 0x00]))  # ack / read next
                r = g.read_reply(2.0)
                if not r or len(r) < 12:
                    break
                if r[5] != 0x04:  # no data
                    break
                ln = r[8] | (r[9] << 7)
                if ln == 0:
                    break
                data.extend(r[10:10 + ln])
            print(f"downloaded {len(data)} bytes -> {outp}")
            with open(outp, "wb") as f:
                f.write(data)
            g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
            g.read_reply(1.0)
        elif cmd == "raw":
            body = bytes.fromhex(sys.argv[2])
            g.send(body)
            r = g.read_reply(2.5)
            print("reply:", hexdump(r))
    finally:
        g.close()


if __name__ == "__main__":
    main()