#!/usr/bin/env python3
"""
Retarget a stomphacks (MS Plus) ZD2 so the Zoom G3Xn accepts it and files it
under the PEDAL category.

Facts taken from the 162 stock G3Xn effects (zoom-zt2/zoom_fx_AllZDL7/G3Xn):
  * target field (offset 12): 0x07 on nearly all effects (0x05 on a few).
    MS Plus builds carry 0x90/0x91, which Effect Manager greys out.
  * group byte / id top byte: 0x0b = PEDAL (PDL Vol, wahs, PDL Pitch ...),
    0x02 = FILTER.  Stock pedal ids are 0x0b0000x0; ours becomes 0x0b00XXXX.

Patched in the header: target (12), group byte (95), id top byte (99),
group name string (11-byte padded field right after the effect name).
The CRC (over data[12:-16]) is recomputed.

Usage: retarget_g3xn.py IN.ZD2 OUT.ZD2 [--target 0x07] [--group 0x0b] [--groupname PEDAL]
"""
import sys, struct, zlib, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--target", type=lambda x: int(x, 0), default=0x07)
    ap.add_argument("--group", type=lambda x: int(x, 0), default=0x0b)
    ap.add_argument("--groupname", default="PEDAL")
    a = ap.parse_args()
    d = bytearray(open(a.src, "rb").read())
    if d[:4] != b"ZDLF":
        sys.exit("not a ZD2")
    # layout: ... version(4) 00 00 group(1) id(4) name(11, NUL padded) groupname(11)
    g = 95
    if d[93:95] != b"\x00\x00":
        sys.exit("unexpected header layout (version padding not at 93)")
    old_group = d[g]; old_id = struct.unpack_from("<I", d, g + 1)[0]
    name_end = d.index(b"\x00", g + 5)           # end of effect name
    gn = g + 5 + 11                               # groupname field start
    old_gn = bytes(d[gn:gn + 11]).split(b"\x00")[0].decode()
    if len(a.groupname) > 10: sys.exit("groupname max 10 chars")
    old_tgt = struct.unpack_from("<I", d, 12)[0]
    d[12:16] = struct.pack("<I", a.target)
    d[g] = a.group
    d[g + 4] = a.group                            # top byte of LE id
    d[gn:gn + 11] = a.groupname.encode().ljust(11, b"\x00")
    crc = (zlib.crc32(bytes(d[12:-16])) & 0xffffffff) ^ 0xffffffff
    d[8:12] = struct.pack("<I", crc)
    open(a.dst, "wb").write(d)
    print(f"target 0x{old_tgt:x} -> 0x{a.target:x}")
    print(f"group 0x{old_group:02x} -> 0x{a.group:02x}, id 0x{old_id:08x} -> 0x{struct.unpack_from('<I', d, g+1)[0]:08x}")
    print(f"groupname {old_gn} -> {a.groupname}; crc 0x{crc:08x}; {len(d)} bytes")

if __name__ == "__main__":
    main()
