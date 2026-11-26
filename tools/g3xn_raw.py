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


def download(g, name, outp, verbose=False):
    """Download a file from the G3Xn.

    CRITICAL: the G3Xn sends file data as RAW 8-bit bytes in the read reply,
    NOT 7-bit packed (unlike the MS Plus). The read reply format is:
      60 04 22 01 00 00 04 00 <raw data ...>
    (8-byte header, then raw data). Data detection: r[3] == 0x01.
    """
    nb = name.encode() + b"\x00"
    # status → file size at reply[26:30] (u32le)
    st = g.request(bytes([0x60, 0x25, 0x00, 0x00]) + nb, 2.0)
    fsize = None
    if st and len(st) >= 30:
        fsize = int.from_bytes(st[26:30], "little")
    if verbose:
        print(f"  file size: {fsize}", file=sys.stderr)

    # Open for read (mode 0x02). Retry if the pedal is in an error state
    # (returns 60 03 7f 7f 7f 7f 0f) — this happens after a previous session
    # left the pedal in a bad state. A fresh connection or a short pause
    # usually clears it.
    open_body = bytes([0x60, 0x20, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + nb
    open_r = None
    for attempt in range(3):
        g.send(open_body)
        open_r = g.read_reply(2.0)
        # success: 60 04 20 ... ; error: 60 03 ...
        if open_r and len(open_r) >= 3 and open_r[1] == 0x04:
            break
        if verbose:
            print(f"  open attempt {attempt+1}: {hexdump(open_r, 20) if open_r else 'none'}", file=sys.stderr)
        time.sleep(1.0)
        g._flush(0.5)
    if verbose:
        print(f"  open: {hexdump(open_r, 20) if open_r else 'none'}", file=sys.stderr)

    data = bytearray()
    # The G3Xn's data reply is ASYNCHRONOUS: the data for block N arrives
    # as the reply to block N+1's ack (60 05 00). So the pattern is:
    #   send ack → read_reply (gets DATA from previous block)
    #   send read → read_reply (gets read ack, 17B)
    #   [data arrives with next ack]
    #
    # Block 0: ack → error(7B), read → ack(17B), [data arrives with block 1's ack]
    # Block 1: ack → DATA(598B), read → ack(17B), [data arrives with block 2's ack]
    # ...
    # Last block: ack → DATA(short), read → ack, [no more data]
    prev_data = None  # data received from previous iteration
    for blk in range(5000):
        # Send ack; the reply contains the data for the PREVIOUS block
        g.send(bytes([0x60, 0x05, 0x00]))
        r = g.read_reply(3.0)
        if r and len(r) >= 8 and r[0] == 0x60 and r[3] == 0x01:
            raw = r[8:]
            data.extend(raw)
            if verbose:
                print(f"  blk{blk}: got {len(raw)}B total={len(data)}/{fsize}", file=sys.stderr)
            if len(raw) < 500:  # short block → end of file
                break
            if fsize and len(data) >= fsize:
                break
        elif blk == 0 and r and len(r) >= 3 and r[1] == 0x03:
            pass  # block 0 ack always returns error (expected)
        else:
            if verbose: print(f"  blk{blk}: unexpected ack reply {hexdump(r,10) if r else 'none'}", file=sys.stderr)
            break
        # Send read request; the reply is the read ack (17B)
        g.send(bytes([0x60, 0x22, 0x14, 0x2F, 0x60, 0x00, 0x0C, 0x00, 0x04, 0x00, 0x00, 0x00]))
        g.read_reply(1.0)
        time.sleep(0.25)
    # close + term
    g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
    g.read_reply(1.0)
    g.send(bytes([0x60, 0x09]))
    g.read_reply(1.0)
    with open(outp, "wb") as f:
        f.write(data)
    return len(data)


def upload(g, name, data: bytes, verbose=True):
    """Upload a file to the G3Xn.

    NOTE: the G3Xn write path may be blocked when the pedal is in a degraded
    state (all writes return 60 03 errors). Reads work fine in that state.
    The write data is RAW 8-bit (no pack7/crc5), matching the read format.
    """
    nb = name.encode() + b"\x00"
    # create (retry if pedal is in error state: 60 03 7f 7f 7f 7f 0f)
    create_body = bytes([0x60, 0x24]) + nb
    r = None
    for attempt in range(3):
        g.send(create_body)
        r = g.read_reply(2.0)
        # success: 60 04 24 ... ; error: 60 03 ...
        if r and len(r) >= 3 and r[1] == 0x04:
            break
        if verbose: print(f"create attempt {attempt+1}:", hexdump(r, 40), file=sys.stderr)
        time.sleep(1.0)
        g._flush(0.5)
    if verbose: print("create:", hexdump(r, 40), file=sys.stderr)
    # open write (mode 0x01)
    g.send(bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + nb)
    r = g.read_reply(2.0)
    if verbose: print("open-write:", hexdump(r, 40), file=sys.stderr)
    # ack
    g.send(bytes([0x60, 0x05, 0x00]))
    r = g.read_reply(2.0)
    if verbose: print("ack:", hexdump(r, 40), file=sys.stderr)
    # data blocks (RAW 8-bit, 512-byte chunks)
    BLOCK = 512
    for off in range(0, len(data), BLOCK):
        chunk = data[off:off+BLOCK]
        body = (bytes([0x60, 0x23, 0x40, 0x00, 0x00, 0x00, 0x00])
                + u14(len(chunk)) + bytes([0x00, 0x00, 0x00])
                + chunk)
        g.send(body)
        r = g.read_reply(2.0)
        # ack
        g.send(bytes([0x60, 0x05, 0x00]))
        r2 = g.read_reply(2.0)
        if verbose and (off // BLOCK) % 8 == 0:
            print(f"  block {off//BLOCK}: send-ack={hexdump(r,24)} read-ack={hexdump(r2,24)}", file=sys.stderr)
        time.sleep(0.25)  # pace like Guitar Lab
    # close
    g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
    r = g.read_reply(2.0)
    if verbose: print("close:", hexdump(r, 40), file=sys.stderr)
    # term
    g.send(bytes([0x60, 0x09]))
    r = g.read_reply(2.0)
    if verbose: print("term:", hexdump(r, 40), file=sys.stderr)


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
            n = download(g, sys.argv[2], sys.argv[3], verbose=True)
            print(f"downloaded {n} bytes -> {sys.argv[3]}")
        elif cmd == "upload":
            data = open(sys.argv[3], "rb").read()
            print(f"uploading {len(data)} bytes as {sys.argv[2]}", file=sys.stderr)
            upload(g, sys.argv[2], data)
            print("upload sequence done")
        elif cmd == "status":
            nb = sys.argv[2].encode() + b"\x00"
            r = g.request(bytes([0x60, 0x25, 0x00, 0x00]) + nb, 2.0)
            if r and len(r) >= 30:
                fsize = int.from_bytes(r[26:30], "little")
                fname = r[11:23].split(b"\x00")[0].decode("ascii", "replace")
                print(f"{fname}  size={fsize}")
            else:
                print("status:", hexdump(r))
        elif cmd == "raw":
            r = g.request(bytes.fromhex(sys.argv[2]))
            print("reply:", hexdump(r))
    finally:
        g.close()


if __name__ == "__main__":
    main()