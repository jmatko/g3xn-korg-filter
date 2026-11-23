#!/usr/bin/env python3
"""
Set the ZD2 "target" bitfield (offset 12) and recompute the CRC32 checksum.

The stomphacks build ships target 0x0090 (MS Plus family bits). The Zoom G3Xn
is a G-series multi-effects unit that also uses the ZD2 container, but its
target bit is 0x0001 ("g-series" in zoomzt2.py). This tool ORs in the G-series
bit (or any target you pass) and recomputes the CRC so the file stays valid.

Usage:
    python3 set_target.py INPUT.ZD2 [OUTPUT.ZD2] [TARGET_HEX]

    TARGET_HEX defaults to 0x91 (0x90 MS Plus  |  0x01 G-series), which keeps
    the file loadable on both the MS Plus family and the G3Xn.

The CRC recipe (from docs/zd2-format.md): CRC32, poly 0x104c11db7 reflected,
init 0x00000000, xorOut 0xFFFFFFFF, over data[12:-16] (everything after the
12-byte magic+length+checksum prefix, excluding the 16-byte trailer). The
stored value equals crc ^ 0xffffffff.
"""
import sys, struct, zlib

def crc32_zoom(data: bytes) -> int:
    # zlib.crc32 is the standard reflected CRC32 (poly 0x04c11db7, init 0,
    # xorout 0xffffffff) -- exactly the recipe the ZD2 format uses.
    return zlib.crc32(data) & 0xffffffff

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    target = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x91

    d = bytearray(open(src, "rb").read())
    if d[:4] != b"ZDLF":
        print(f"error: {src} is not a ZD2 (magic {d[:4]!r})"); sys.exit(2)

    old_target = struct.unpack_from("<I", d, 12)[0]
    d[12:16] = struct.pack("<I", target)

    # recompute CRC over data[12:-16]
    crc = crc32_zoom(bytes(d[12:-16])) ^ 0xffffffff
    d[8:12] = struct.pack("<I", crc)

    open(dst, "wb").write(d)
    print(f"target: 0x{old_target:04x} -> 0x{target:04x}")
    print(f"checksum recomputed: 0x{crc:08x}")
    print(f"wrote {dst} ({len(d)} bytes)")
    # self-check: re-read and verify
    v = open(dst, "rb").read()
    stored = struct.unpack_from("<I", v, 8)[0]
    calc = crc32_zoom(v[12:-16]) ^ 0xffffffff
    print(f"verify: stored 0x{stored:08x} calc 0x{calc:08x} -> {'OK' if stored==calc else 'MISMATCH'}")

if __name__ == "__main__":
    main()