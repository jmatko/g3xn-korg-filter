#!/usr/bin/env python3
"""
g3xn_inspect.py — connect to a G3Xn over USB-MIDI, dump its stock .ZD2 effect
files, and inspect the target bit + group byte so you can match a custom effect
to the pedal exactly.

READ-ONLY: it only lists and reads files. It never writes to the pedal.

Protocol source: cwoodard1121/zoom-g3xn-agent-skill (verified on G3Xn fw 2.20).
File-system SysEx (inner bytes after F0 52 00 6E):
    60 25 00 00 <cstr>   open/list (first)
    60 26 00 00 <cstr>   next entry
    60 05 00             read block
    60 20 02 ... <cstr>  open file for read
    60 22 14 2F 60 00 0C 00 04 00 00 00   read
    60 21 40 00 00 00 00 close
    60 27                end list
    60 09                (terminator)
Data is 7-bit packed; each block carries a 5-byte checksum.

Usage:
    python3 g3xn_inspect.py                 # list all files
    python3 g3xn_inspect.py LOWPASSF.ZD2    # dump+inspect one named file
    python3 g3xn_inspect.py --save DIR      # dump every .ZD2 into DIR/

Requirements: pip install mido
The pedal must be the only process holding the "ZOOM G" MIDI port (close
ToneLib / Guitar Lab / any browser tab first).
"""
import sys, struct, time, argparse

ZOOM = (0x52, 0x00, 0x6E)
PORT_PREFIX = "ZOOM G"


def pack7(data: bytes) -> bytes:
    """Pack bytes into 7-bit groups (MSB first), padding the final group."""
    out = bytearray()
    for i in range(0, len(data), 7):
        chunk = data[i:i + 7]
        byte = 0
        for b in chunk:
            byte = (byte << 1) | (b & 0x7F)
        for _ in range(7 - len(chunk)):
            byte <<= 1
        out.append(byte & 0xFF)
    return bytes(out)


def unpack7(packed: bytes) -> bytes:
    out = bytearray()
    for byte in packed:
        for i in range(7, 0, -1):
            out.append((byte >> (i - 1)) & 0x7F)
    return bytes(out)


class Pedal:
    def __init__(self, timeout=2.0):
        import mido
        self.mido = mido
        ins = [p for p in mido.get_input_names() if p.startswith(PORT_PREFIX)]
        outs = [p for p in mido.get_output_names() if p.startswith(PORT_PREFIX)]
        if not ins or not outs:
            raise SystemExit(
                f"no G3Xn MIDI port (looking for {PORT_PREFIX!r}).\n"
                f"inputs:  {mido.get_input_names()}\n"
                f"outputs: {mido.get_output_names()}")
        self.inp = mido.open_input(ins[0])
        self.out = mido.open_output(outs[0])
        self.timeout = timeout
        print(f"connected: in={ins[0]!r}  out={outs[0]!r}")

    def _send(self, inner: bytes):
        self.out.send(self.mido.Message("sysex", data=list(ZOOM) + list(inner)))

    def _wait(self, expect: bytes = None, timeout=None):
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            m = self.inp.poll()
            if m is None:
                time.sleep(0.001)
            elif m.type == "sysex":
                d = bytes(m.data)
                if expect is None or d.startswith(bytes(expect)):
                    return d
        return None

    def _req(self, inner: bytes, expect: bytes = None):
        self._send(inner)
        r = self._wait(expect)
        if r is None:
            raise RuntimeError(f"no reply to {inner.hex()}")
        return r

    def list_files(self):
        names, first = [], True
        while True:
            c = b"*" + b"\x00"
            inner = bytes([0x60, 0x25 if first else 0x26, 0, 0]) + c
            r = self._req(inner)
            first = False
            if len(r) < 14 or r[4] != 4:
                break
            name = bytes(r[14:]).split(b"\x00")[0].decode("ascii", "replace")
            if not name or name in names:
                break
            names.append(name)
        self._send(bytes([0x60, 0x27]))
        return names

    def read_file(self, name: str) -> bytes:
        c = name.encode() + b"\x00"
        self._send(bytes([0x60, 0x25, 0, 0]) + c)
        found = self._req(bytes([0x60, 0x05, 0]))[-5:] == bytes(5)
        self._send(bytes([0x60, 0x27]))
        if not found:
            raise FileNotFoundError(name)
        self._send(bytes([0x60, 0x20, 0x02]) + bytes(9) + c)
        data = bytearray()
        while True:
            self._req(bytes([0x60, 0x05, 0]))
            self._send(bytes([0x60, 0x22, 0x14, 0x2F, 0x60, 0, 0x0C, 0, 0x04, 0, 0, 0]))
            r = self._req(bytes([0x60, 0x05, 0]))
            if len(r) < 10:
                break
            n = (r[9] << 7) | r[8]
            if r[4] != 4 or n == 0:
                break
            block = unpack7(r[10:10 + n + n // 7 + 1])[:n]
            data += block
        self._send(bytes([0x60, 0x21, 0x40, 0, 0, 0, 0]))
        self._send(bytes([0x60, 0x09]))
        return bytes(data)


def inspect_zd2(name: str, data: bytes):
    if data[:4] != b"ZDLF":
        print(f"  {name}: NOT a ZDLF container (magic {data[:4]!r})")
        return
    length = struct.unpack_from("<I", data, 4)[0]
    checksum = struct.unpack_from("<I", data, 8)[0]
    target = struct.unpack_from("<I", data, 12)[0]
    bits = [hex(1 << i) for i in range(32) if target & (1 << i)]
    print(f"  {name}: len={length} target=0x{target:04x} bits={bits} checksum=0x{checksum:08x}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="a .ZD2 filename to dump+inspect")
    ap.add_argument("--save", metavar="DIR", help="dump every .ZD2 into DIR/")
    a = ap.parse_args()

    import os
    p = Pedal()
    names = p.list_files()
    zd2s = [n for n in names if n.upper().endswith(".ZD2")]
    print(f"\n{len(names)} files on the pedal ({len(zd2s)} are .ZD2):")
    for n in names:
        print(f"   {n}{'  <ZD2>' if n in zd2s else ''}")

    if a.save:
        os.makedirs(a.save, exist_ok=True)
        print(f"\nSaving {len(zd2s)} .ZD2 files to {a.save}/ ...")
        for n in zd2s:
            try:
                d = p.read_file(n)
                open(os.path.join(a.save, n), "wb").write(d)
                inspect_zd2(n, d)
            except Exception as e:
                print(f"  {n}: FAILED ({e})")
    elif a.file:
        d = p.read_file(a.file)
        print(f"\n{a.file}: {len(d)} bytes")
        inspect_zd2(a.file, d)
    else:
        print("\n(pass a .ZD2 name to dump+inspect one, or --save DIR to dump all)")

    p.inp.close()
    p.out.close()


if __name__ == "__main__":
    main()