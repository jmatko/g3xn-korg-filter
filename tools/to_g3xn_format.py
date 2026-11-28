#!/usr/bin/env python3
"""
Convert a stomphacks (MS Plus layout) ZD2 into the layout of a stock Zoom
G3Xn *Pedal-group* effect.

Derived by diffing PDL_REV.ZD2 and PDL_BITC.ZD2 (downloaded from a real G3Xn)
against the MS Plus build.  The ELF (DATA chunk) is NOT touched.

What changes
  header   target 0x07; the 73-byte block at offsets 16..88 (non-zero on every
           stock G3Xn effect, all zeros in an MS Plus build); version; group
           byte 0x0b; id top byte 0x0b; group name "PEDAL"
  ICON     MS Plus raw 936-byte screen frame  ->  23x30 1-bit BMP (182 bytes),
           as on every stock G3Xn effect
  INFO     adds badge "PDL" + group name "PEDAL" (stock layout:
           4 zero bytes | badge[3] | group[9] | float32 dsp-load)
  PRMJ/PRME  first parameter gets "pedal":true (what stock pedal effects have)
  CRC      recomputed over data[12:-16]

NOT reproduced: the 16-byte trailer.  Stock files carry 16 non-zero bytes that
match no MD5 of any part of the file; this tool leaves it zero, as MS Plus
builds do.  If the pedal checks it, this is the first thing to suspect.

Usage: to_g3xn_format.py IN.ZD2 OUT.ZD2 [--version 1.40] [--badge PDL] [--no-pedal-flag]
"""
import sys, struct, zlib, argparse, re

HDR_BLOCK = bytes.fromhex(   # stock G3Xn bytes 16..88 (identical in PDL_REV and PDL_BITC)
 "01000100000000008000000000000000000000000000000080000000000000000000000000000000"
 "000000000000000000000000000000000000000000000000000000000000000001")
assert len(HDR_BLOCK) == 73

# 3x5 glyphs for the icon label
FONT = {'T':["111","010","010","010","010"],'R':["110","101","110","101","101"],
        'V':["101","101","101","101","010"],'L':["100","100","100","100","111"],
        'F':["111","100","110","100","100"],'W':["101","101","101","111","101"],
        'A':["010","101","111","101","101"],'H':["101","101","111","101","101"]}

def make_icon_bmp(label="TRVL"):
    """23x30 1bpp BMP in the stock style: rounded body outline + label."""
    W, H = 23, 30
    px = [[0]*W for _ in range(H)]          # 1 = black
    def box(x0,y0,x1,y1):
        for x in range(x0,x1+1): px[y0][x]=1; px[y1][x]=1
        for y in range(y0,y1+1): px[y][x0]=1; px[y][x1]=1
    box(0,1,22,29)                          # body
    for x in range(3,20): px[4][x]=1        # display strip
    for x in range(5,18): px[25][x]=1       # footswitch bar
    x = 5
    for ch in label[:4]:                    # label, 3x5 glyphs, 1px gap
        g = FONT.get(ch.upper())
        if g:
            for r,row in enumerate(g):
                for c,v in enumerate(row):
                    if v == '1': px[8+r][x+c] = 1
        x += 4
    stride = 4
    pix = bytearray()
    for y in range(H-1,-1,-1):              # bottom-up rows
        row = bytearray(stride)
        for xx in range(W):
            if not px[y][xx]: row[xx//8] |= 0x80 >> (xx%8)   # palette: 0=black, 1=white
        pix += row
    hdr = struct.pack('<2sIHHI', b'BM', 62+len(pix), 0, 0, 62)
    dib = struct.pack('<IiiHHIIiiII', 40, W, H, 1, 1, 0, len(pix), 2835, 2835, 0, 0)
    pal = bytes([0,0,0,0, 255,255,255,0])
    out = hdr + dib + pal + bytes(pix)
    assert len(out) == 182, len(out)
    return out

def read_chunks(d):
    o, out = 128, []
    while o + 8 <= len(d) - 16:
        tag = d[o:o+4]
        if not re.fullmatch(rb'[A-Z0-9]{4}', tag): break
        ln = struct.unpack_from('<I', d, o+4)[0]
        out.append([tag.decode(), d[o+8:o+8+ln]]); o += 8 + ln
    if o != len(d) - 16: raise SystemExit(f"unexpected layout: chunks end at {o}, trailer at {len(d)-16}")
    return out

def set_first_pedal(b):
    t = b.decode('latin-1')
    t2 = re.sub(r'("pedal"\s*:\s*)false', r'\1true', t, count=1)
    return t2.encode('latin-1')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--version', default='1.40')
    ap.add_argument('--badge', default='PDL')
    ap.add_argument('--label', default='TRVL')
    ap.add_argument('--no-pedal-flag', action='store_true')
    a = ap.parse_args()
    d = bytearray(open(a.src, 'rb').read())
    if d[:4] != b'ZDLF': raise SystemExit('not a ZD2')
    chunks = read_chunks(bytes(d))
    # ---- header ----
    d[12:16] = struct.pack('<I', 0x07)
    d[16:89] = HDR_BLOCK
    d[89:93] = a.version.encode().ljust(4, b'\0')[:4]
    d[95] = 0x0b; d[99] = 0x0b                       # group byte, id top byte (LE)
    d[111:122] = b'PEDAL'.ljust(11, b'\0')
    # ---- chunks ----
    for c in chunks:
        if c[0] == 'ICON': c[1] = make_icon_bmp(a.label)
        elif c[0] == 'INFO':
            dsp = c[1][-4:]
            c[1] = b'\0\0\0\0' + a.badge.encode().ljust(3, b'\0')[:3] + b'PEDAL'.ljust(9, b'\0') + dsp
            assert len(c[1]) == 20
        elif c[0] in ('PRMJ', 'PRME') and not a.no_pedal_flag:
            c[1] = set_first_pedal(c[1])
    body = b''.join(t.encode() + struct.pack('<I', len(p)) + p for t, p in chunks)
    out = bytearray(d[:128]) + body + bytes(16)       # trailer left zero (unknown)
    crc = (zlib.crc32(bytes(out[12:-16])) & 0xffffffff) ^ 0xffffffff
    out[8:12] = struct.pack('<I', crc)
    open(a.dst, 'wb').write(out)
    print(f"wrote {a.dst}: {len(out)} B, chunks " + ', '.join(f"{t}={len(p)}" for t, p in chunks) + f", crc 0x{crc:08x}")

if __name__ == '__main__':
    main()
