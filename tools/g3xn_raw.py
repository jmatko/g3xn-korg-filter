#!/usr/bin/env python3
"""
g3xn_raw.py — G3Xn SysEx client over the RAW ALSA MIDI device (/dev/snd/midiC3D0).

Unlike the ALSA sequencer path (whose RECEIVE is broken in this container),
the raw device gives both working SEND and RECEIVE. Verified: file-list request
returns a real reply.

Protocol (Zoom G Series, mungewell/zoom-zt2):
  framing: F0 52 00 6E <body...> F7

  list start : 60 25 00 00 <name cstr>   (name '*' = 0x2A)
  list next  : 60 26 00 00 <name cstr>
  list end   : 60 27
  list reply : F0 52 00 6E 60 04 25 00 00 <len u14> 00 00 00 <name cstr> ... F7
               (entry-follows flag is body[1]==0x04; name starts at body[11])
  disk       : 60 29 00 00 00 00 00

  file status: 60 25 <name cstr>  then 60 05 00
  open read  : 60 20 02 ... <name cstr>
  read next  : 60 05 00   -> reply 60 04 23 .. <len u14> <data> (0x23=DATA)
  close      : 60 21 40 00 00 00 00
  term       : 60 09

  create     : 60 24 <name cstr>
  open write : 60 20 01 ... <name cstr>
  write blk  : 60 23 40 00 00 00 00 <len u14> 00 00 00 <pack7> <crc5>
  ack        : 60 05 00

Usage:
  python3 g3xn_raw.py list
  python3 g3xn_raw.py disk
  python3 g3xn_raw.py download <name> <out>
  python3 g3xn_raw.py upload <name> <in>
  python3 g3xn_raw.py status <name>
"""
import sys, time, zlib, os

RAW = "/dev/snd/midiC3D0"

# ---- 7-bit packing (high-bit-byte scheme) ----
def pack7(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 7):
        chunk = data[i:i+7]
        high = 0
        for j, b in enumerate(chunk):
            if b & 0x80:
                high |= 0x40 >> j
        out.append(high)
        out.extend(b & 0x7F for b in chunk)
    return bytes(out)

def unpack7(packed: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(packed), 8):
        high = packed[i]
        for j, b in enumerate(packed[i+1:i+8]):
            out.append(b | (0x80 if high & (0x40 >> j) else 0))
    return bytes(out)

def crc5(data: bytes) -> bytes:
    crc = (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF
    return bytes((crc >> (7*i)) & 0x7F for i in range(5))

def u14(n: int) -> bytes:
    return bytes([n & 0x7F, (n >> 7) & 0x7F])

def sysex(body: bytes) -> bytes:
    return bytes([0xF0, 0x52, 0x00, 0x6E]) + body + bytes([0xF7])

def hexdump(b, n=100):
    return " ".join(f"{x:02x}" for x in b[:n]) + ("..." if len(b) > n else "")


class RawG3Xn:
    def __init__(self):
        self.fd = os.open(RAW, os.O_RDWR | os.O_NONBLOCK)
        self._flush()

    def _flush(self, t=0.4):
        end = time.time() + t
        while time.time() < end:
            try:
                os.read(self.fd, 4096)
            except BlockingIOError:
                break

    def send(self, body: bytes):
        os.write(self.fd, sysex(body))

    def read_reply(self, timeout=3.0):
        """Read one complete SysEx (F0..F7). Returns body bytes (without F0 52 00 6E / F7)."""
        end = time.time() + timeout
        buf = bytearray()
        started = False
        while time.time() < end:
            try:
                d = os.read(self.fd, 4096)
            except BlockingIOError:
                time.sleep(0.002)
                continue
            for b in d:
                if not started:
                    if b == 0xF0:
                        buf.append(b); started = True
                    continue
                buf.append(b)
                if b == 0xF7:
                    # strip F0 52 00 6E prefix and F7
                    return bytes(buf[4:-1])
            # if we got an incomplete one and buffer is huge, keep going
        return bytes(buf)

    def request(self, body: bytes, timeout=3.0):
        self.send(body)
        return self.read_reply(timeout)

    def close(self):
        try:
            os.close(self.fd)
        except Exception:
            pass


def list_files(g, maxn=400):
    files = []
    r = g.request(bytes([0x60, 0x25, 0x00, 0x00, 0x2A, 0x00]))
    files.extend(_parse_list(r))
    for _ in range(maxn):
        r = g.request(bytes([0x60, 0x26, 0x00, 0x00, 0x2A, 0x00]))
        more = _parse_list(r)
        if not more:
            break
        files.extend(more)
    g.send(bytes([0x60, 0x27]))
    g.read_reply(1.0)
    return files

def _parse_list(r):
    out = []
    if not r or len(r) < 11:
        return out
    if r[0] != 0x60:
        return out
    if r[1] != 0x04:  # entry-follows indicator
        return out
    # name at body[11], cstr
    name = r[11:].split(b"\x00")[0].decode("ascii", "replace")
    if name:
        out.append(name)
    return out


def download(g, name, outp):
    nb = name.encode() + b"\x00"
    # status (informational; G3Xn returns a size reply like 60 03 <size>, not 60 05 00,
    # so we do NOT gate on it — the open-for-read reply is the real existence check)
    g.send(bytes([0x60, 0x25, 0x00, 0x00]) + nb)
    g.read_reply(2.0)
    g.send(bytes([0x60, 0x05, 0x00]))
    g.read_reply(2.0)
    # open for read (mode 0x02)
    g.send(bytes([0x60, 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + nb)
    open_r = g.read_reply(2.0)
    # open-for-read ack: 60 04 20 ... ; if we get 60 03 .. the file likely doesn't exist
    data = bytearray()
    for _ in range(5000):
        g.send(bytes([0x60, 0x05, 0x00]))
        g.read_reply(1.0)
        g.send(bytes([0x60, 0x22, 0x14, 0x2F, 0x60, 0x00, 0x0C, 0x00, 0x04, 0x00, 0x00, 0x00]))
        g.read_reply(1.0)
        r = g.read_reply(2.0)
        if not r or len(r) < 10 or r[0] != 0x60:
            break
        if r[4] != 0x04:  # no data entry (r[4] is the status byte)
            break
        ln = r[8] | (r[9] << 7)
        if ln == 0:
            break
        packed = r[10:10 + ln + (ln + 6) // 7]
        data.extend(unpack7(packed, ln))
    # close
    g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
    g.read_reply(1.0)
    g.send(bytes([0x60, 0x09]))
    g.read_reply(1.0)
    with open(outp, "wb") as f:
        f.write(data)
    return len(data)


def upload(g, name, data: bytes):
    nb = name.encode() + b"\x00"
    # create
    g.send(bytes([0x60, 0x24]) + nb)
    r = g.read_reply(2.0); print("create:", hexdump(r, 40), file=sys.stderr)
    # open write (mode 0x01)
    g.send(bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + nb)
    r = g.read_reply(2.0); print("open-write:", hexdump(r, 40), file=sys.stderr)
    # ack
    g.send(bytes([0x60, 0x05, 0x00]))
    r = g.read_reply(2.0); print("ack:", hexdump(r, 40), file=sys.stderr)
    # data blocks
    BLOCK = 512
    for off in range(0, len(data), BLOCK):
        chunk = data[off:off+BLOCK]
        body = (bytes([0x60, 0x23, 0x40, 0x00, 0x00, 0x00, 0x00])
                + u14(len(chunk)) + bytes([0x00, 0x00, 0x00])
                + pack7(chunk) + crc5(chunk))
        g.send(body)
        r = g.read_reply(2.0)
        # ack
        g.send(bytes([0x60, 0x05, 0x00]))
        r2 = g.read_reply(2.0)
        if (off // BLOCK) % 8 == 0:
            print(f"  block {off//BLOCK}: send-ack={hexdump(r,24)} read-ack={hexdump(r2,24)}", file=sys.stderr)
    # close
    g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
    r = g.read_reply(2.0); print("close:", hexdump(r, 40), file=sys.stderr)
    # term
    g.send(bytes([0x60, 0x09]))
    r = g.read_reply(2.0); print("term:", hexdump(r, 40), file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    g = RawG3Xn()
    try:
        if cmd == "list":
            files = list_files(g)
            print(f"{len(files)} files:")
            for f in files:
                print("  " + f)
        elif cmd == "disk":
            r = g.request(bytes([0x60, 0x29, 0x00, 0x00, 0x00, 0x00, 0x00]))
            print("DISK:", hexdump(r))
        elif cmd == "download":
            n = download(g, sys.argv[2], sys.argv[3])
            print(f"downloaded {n} bytes -> {sys.argv[3]}")
        elif cmd == "upload":
            data = open(sys.argv[3], "rb").read()
            print(f"uploading {len(data)} bytes as {sys.argv[2]}", file=sys.stderr)
            upload(g, sys.argv[2], data)
            print("upload sequence done")
        elif cmd == "status":
            nb = sys.argv[2].encode() + b"\x00"
            g.send(bytes([0x60, 0x25]) + nb); g.read_reply(2.0)
            g.send(bytes([0x60, 0x05, 0x00])); r = g.read_reply(2.0)
            print("status:", hexdump(r))
        elif cmd == "raw":
            r = g.request(bytes.fromhex(sys.argv[2]))
            print("reply:", hexdump(r))
    finally:
        g.close()


if __name__ == "__main__":
    main()