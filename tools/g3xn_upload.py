#!/usr/bin/env python3
"""
g3xn_upload.py — Upload a .ZD2 file to a Zoom G3Xn (fire-and-forget).

Uses the WRITE path from mungewell/zoom-zt2 (verified on G1Four/MS Plus):
  60 24 <name cstr>              create/truncate file
  60 20 01 ... <name cstr>       open for WRITE (mode 0x01)
  60 05 00                       (ack)
  per 512-byte block:
    60 23 40 00 00 00 00 <len u14> 00 00 00 <pack7(data)> <crc5>
    60 05 00                     (ack)
  60 21 40 00 00 00 00           close
  60 09                          terminator

NOTE: This container has SEND working but RECEIVE broken. So this is
fire-and-forget: we send the full sequence and cannot read back the pedal's
replies. Verification must be done on the Chromebook WebMIDI UI (read-back
+ byte compare) or by observing the pedal.

Usage:
  python3 g3xn_upload.py dry-run <zd2_file> [device_name]
  python3 g3xn_upload.py upload <zd2_file> [device_name]
"""
import sys, time, zlib

# --- 7-bit packing (high-bit-byte scheme) ---
def pack7(data: bytes) -> bytes:
    # High-bit-byte scheme, matching mungewell/zoom-zt2 pack():
    # each group of up to 7 bytes -> 1 high-bit byte + the low bytes.
    # The last group is NOT padded (mungewell omits trailing pad).
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
    """Inverted CRC-32 as 5 7-bit bytes, low group first."""
    crc = (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF
    return bytes((crc >> (7*i)) & 0x7F for i in range(5))

def u14(n: int) -> bytes:
    """14-bit little-endian (7+7)."""
    return bytes([n & 0x7F, (n >> 7) & 0x7F])

# --- SysEx framing ---
def sysex(body: bytes) -> bytes:
    return bytes([0xF0, 0x52, 0x00, 0x6E]) + body + bytes([0xF7])

# --- Build the full upload sequence ---
def build_upload_seq(data: bytes, name: str) -> list:
    """Return list of (label, body_bytes) for each message in the upload."""
    msgs = []
    name_b = name.encode() + b'\x00'

    # 1. create/truncate
    msgs.append(("create", bytes([0x60, 0x24]) + name_b))

    # 2. open for write (mode 0x01)
    msgs.append(("open-write", bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + name_b))

    # 3. ack
    msgs.append(("ack", bytes([0x60, 0x05, 0x00])))

    # 4. data blocks (512 bytes each)
    BLOCK = 512
    for off in range(0, len(data), BLOCK):
        chunk = data[off:off+BLOCK]
        body = bytes([0x60, 0x23, 0x40, 0x00, 0x00, 0x00, 0x00]) + u14(len(chunk)) + bytes([0x00, 0x00, 0x00]) + pack7(chunk) + crc5(chunk)
        msgs.append((f"data[{off//BLOCK}]", body))
        msgs.append(("ack", bytes([0x60, 0x05, 0x00])))

    # 5. close
    msgs.append(("close", bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00])))

    # 6. terminator
    msgs.append(("term", bytes([0x60, 0x09])))

    return msgs

def hexdump(b, n=100):
    return " ".join(f"{x:02x}" for x in b[:n]) + ("..." if len(b) > n else "")

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]  # dry-run | upload
    zd2_path = sys.argv[2]
    # device name (on-pedal filename, max 12 bytes)
    name = "XXTRVL.ZD2"  # default
    if len(sys.argv) > 3:
        name = sys.argv[3]

    data = open(zd2_path, 'rb').read()
    print(f"File: {zd2_path} ({len(data)} bytes)")
    print(f"Device name: {name} ({len(name)} chars)")
    print(f"Blocks: {(len(data) + 511) // 512} x 512 bytes")
    print()

    msgs = build_upload_seq(data, name)
    total_bytes = sum(len(m[1]) + 6 for m in msgs)  # +6 for F0 52 00 6E F7
    print(f"Total messages: {len(msgs)}")
    print(f"Total SysEx bytes: {total_bytes}")
    print()

    for i, (label, body) in enumerate(msgs):
        full = sysex(body)
        print(f"  [{i:3d}] {label:12s} {len(full):4d} B  {hexdump(full, 60)}")

    if mode == "dry-run":
        print("\nDRY RUN — no messages sent.")
        # Verify pack7 round-trip on the first block
        chunk = data[:512]
        packed = pack7(chunk)
        unpacked = unpack7(packed)
        assert unpacked == chunk, f"pack7 round-trip FAILED: {len(chunk)} vs {len(unpacked)}"
        print(f"\n[OK] pack7 round-trip verified on first block ({len(chunk)} bytes)")
        # Verify crc5
        c = crc5(chunk)
        print(f"[OK] crc5(first block) = {hexdump(c)}")
    elif mode == "upload":
        print("\nLIVE UPLOAD — sending to pedal...")
        import alsa_midi as am
        c = am.SequencerClient(client_name="g3xn-upload")
        port = c.create_port(name="upload", caps=am.RW_PORT)
        port.connect_to(am.Address(28, 0))
        print("[+] connected to ZOOM G Series (28:0)")
        for i, (label, body) in enumerate(msgs):
            c.event_output(am.SysExEvent(data=sysex(body)))
            c.drain_output()
            print(f"  [{i:3d}] sent {label:12s}")
            time.sleep(0.05)  # small delay between messages
        port.close()
        c.close()
        print("\n[!] Upload sequence sent (fire-and-forget).")
        print("    Verify on Chromebook WebMIDI UI: list files, download XXTRVL.ZD2, byte-compare.")
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

if __name__ == "__main__":
    main()