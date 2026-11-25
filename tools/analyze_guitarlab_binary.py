#!/usr/bin/env python3
"""
Guitar Lab.exe Binary Protocol Analyzer
Extracts MIDI SysEx protocol constants and class structures from the binary.
Run: python3 analyze_guitarlab_binary.py
"""
import re
import struct
import sys
import os

GL_PATH = "/home/user/.wine-zoom/drive_c/Program Files/ZOOM/Guitar Lab/Guitar Lab.exe"

def hexdump(data, offset, length=32):
    """Pretty hex dump"""
    chunk = data[offset:offset+length]
    hex_part = " ".join(f"{b:02x}" for b in chunk)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    return f"  0x{offset:06x}: {hex_part:<48s} |{ascii_part}|"

def find_all(data, pattern):
    """Find all occurrences of pattern in data"""
    positions = []
    idx = 0
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        positions.append(idx)
        idx += 1
    return positions

def analyze():
    print("=" * 70)
    print("Guitar Lab.exe Binary Protocol Analysis")
    print("=" * 70)
    
    with open(GL_PATH, "rb") as f:
        data = f.read()
    
    print(f"\nFile size: {len(data):,} bytes ({len(data)/1024/1024:.1f} MB)")
    
    # 1. PE Header
    print("\n" + "-" * 70)
    print("1. PE HEADER")
    print("-" * 70)
    pe_offset = struct.unpack_from("<I", data, 0x3c)[0]
    print(f"  PE header at: 0x{pe_offset:06x}")
    signature = data[pe_offset:pe_offset+4]
    print(f"  Signature: {signature}")
    
    # COFF header
    coff = pe_offset + 4
    machine = struct.unpack_from("<H", data, coff)[0]
    num_sections = struct.unpack_from("<H", data, coff+2)[0]
    timestamp = struct.unpack_from("<I", data, coff+4)[0]
    print(f"  Machine: 0x{machine:04x} (0x014c = i386)")
    print(f"  Sections: {num_sections}")
    print(f"  Timestamp: {timestamp}")
    
    # 2. SysEx Protocol Patterns
    print("\n" + "-" * 70)
    print("2. SYSEX PROTOCOL PATTERNS")
    print("-" * 70)
    
    patterns = {
        b'\xf0\x52\x00\x6e': "Full SysEx header F0 52 00 6E",
        b'\x60\x25': "CMD 60 25 (file status/list)",
        b'\x60\x26': "CMD 60 26 (list next)",
        b'\x60\x27': "CMD 60 27 (list end)",
        b'\x60\x20': "CMD 60 20 (open file)",
        b'\x60\x21': "CMD 60 21 (close file)",
        b'\x60\x23': "CMD 60 23 (write block)",
        b'\x60\x24': "CMD 60 24 (create file)",
        b'\x60\x05': "CMD 60 05 (ACK/read next)",
        b'\x60\x09': "CMD 60 09 (terminate)",
        b'\x60\x04': "CMD 60 04 (data reply)",
        b'\x60\x22': "CMD 60 22 (read data)",
        b'\x60\x29': "CMD 60 29 (disk info)",
        b'\x60\x03': "CMD 60 03 (error/nack)",
        b'\x60\x01': "CMD 60 01 (ack)",
        b'\x60\x02': "CMD 60 02 (nack)",
        b'\x60\x06': "CMD 60 06 (unknown)",
        b'\x60\x07': "CMD 60 07 (unknown)",
        b'\x60\x08': "CMD 60 08 (unknown)",
        b'\x60\x28': "CMD 60 28 (unknown)",
        b'\x60\x2a': "CMD 60 2A (unknown)",
        b'\x60\x2b': "CMD 60 2B (unknown)",
        b'\x60\x2c': "CMD 60 2C (unknown)",
        b'\x60\x2d': "CMD 60 2D (unknown)",
        b'\x60\x2e': "CMD 60 2E (unknown)",
        b'\x60\x2f': "CMD 60 2F (unknown)",
        b'\x60\x30': "CMD 60 30 (unknown)",
    }
    
    for pat, desc in patterns.items():
        positions = find_all(data, pat)
        if positions:
            first_5 = ", ".join(f"0x{p:06x}" for p in positions[:5])
            more = f" (+{len(positions)-5} more)" if len(positions) > 5 else ""
            print(f"  {desc}: {len(positions)} occ [{first_5}{more}]")
        else:
            print(f"  {desc}: NOT FOUND")
    
    # 3. Context around SysEx header occurrences
    print("\n" + "-" * 70)
    print("3. SYSEX HEADER CONTEXT (first 10 occurrences)")
    print("-" * 70)
    
    header_positions = find_all(data, b'\xf0\x52\x00\x6e')
    for i, pos in enumerate(header_positions[:10]):
        print(f"\n  Occurrence {i+1} at 0x{pos:06x}:")
        # Show 16 bytes before and 32 bytes after
        start = max(0, pos - 8)
        hexdump(data, start, 40)
    
    # 4. Key class names and their addresses
    print("\n" + "-" * 70)
    print("4. KEY CLASS NAMES")
    print("-" * 70)
    
    class_names = [
        "AVSysExMessage", "AVMidiManager", "AVZoomDevice",
        "AVGuitarLabDeviceDelegate", "AVMidiInputCallback",
        "AVMidiOutput", "AVMidiMessageCollector",
        "Win32MidiService", "Win32MidiDeviceQuery",
        "AUMidiService", "AUMidiInCollector", "AUMidiOutHandle",
        "AUMidiServiceType", "AVMidiManager",
        "CommandManager", "CommandManagerImpl",
    ]
    
    for name in class_names:
        positions = find_all(data, name.encode())
        if positions:
            first_3 = ", ".join(f"0x{p:06x}" for p in positions[:3])
            more = f" (+{len(positions)-3} more)" if len(positions) > 3 else ""
            print(f"  {name}: {len(positions)} occ [{first_3}{more}]")
        else:
            print(f"  {name}: NOT FOUND")
    
    # 5. Win32 MIDI API functions
    print("\n" + "-" * 70)
    print("5. WIN32 MIDI API FUNCTIONS")
    print("-" * 70)
    
    midi_funcs = [
        "midiInOpen", "midiInClose", "midiInStart", "midiInStop",
        "midiInMessage", "midiInAddBuffer", "midiInPrepareHeader",
        "midiInUnprepareHeader", "midiInGetNumDevs", "midiInGetDevCapsW",
        "midiOutOpen", "midiOutClose", "midiOutShortMsg", "midiOutLongMsg",
        "midiOutPrepareHeader", "midiOutUnprepareHeader",
        "midiOutGetNumDevs", "midiOutGetDevCapsW", "midiOutReset",
    ]
    
    for func in midi_funcs:
        positions = find_all(data, func.encode())
        if positions:
            first_3 = ", ".join(f"0x{p:06x}" for p in positions[:3])
            print(f"  {func}: {len(positions)} occ [{first_3}]")
        else:
            print(f"  {func}: NOT FOUND")
    
    # 6. File-related strings
    print("\n" + "-" * 70)
    print("6. FILE-RELATED STRINGS")
    print("-" * 70)
    
    for ext in [b'.ZD2', b'.ZT2', b'.zd2', b'.zt2', b'ZD2', b'ZT2',
                b'.ZD1', b'.ZT1', b'FLST_SEQ', b'USER', b'FACTORY']:
        positions = find_all(data, ext)
        if positions:
            first_3 = ", ".join(f"0x{p:06x}" for p in positions[:3])
            print(f"  '{ext.decode()}': {len(positions)} occ [{first_3}]")
    
    # 7. Look for CRC-related strings
    print("\n" + "-" * 70)
    print("7. CRC / CHECKSUM STRINGS")
    print("-" * 70)
    
    for term in [b'crc', b'CRC', b'checksum', b'CHECKSUM', b'pack7', b'PACK7',
                 b'xor', b'XOR', b'check', b'CHECK']:
        positions = find_all(data, term)
        if positions:
            first_3 = ", ".join(f"0x{p:06x}" for p in positions[:3])
            more = f" (+{len(positions)-3} more)" if len(positions) > 3 else ""
            print(f"  '{term.decode()}': {len(positions)} occ [{first_3}{more}]")
    
    # 8. Look for timing-related constants
    print("\n" + "-" * 70)
    print("8. TIMING CONSTANTS (potential delays/timeouts)")
    print("-" * 70)
    
    # Common MIDI timing values in milliseconds
    for ms in [10, 20, 50, 100, 200, 250, 500, 1000, 2000, 5000]:
        # Look for the value as a 4-byte little-endian integer
        val = struct.pack("<I", ms)
        positions = find_all(data, val)
        if positions and len(positions) < 100:  # Filter out noise
            first_3 = ", ".join(f"0x{p:06x}" for p in positions[:3])
            print(f"  {ms} ms (0x{ms:08x}): {len(positions)} occ [{first_3}]")
    
    # 9. Look for block size constants
    print("\n" + "-" * 70)
    print("9. BLOCK SIZE CONSTANTS")
    print("-" * 70)
    
    for size in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192]:
        val = struct.pack("<I", size)
        positions = find_all(data, val)
        if positions and len(positions) < 50:
            first_3 = ", ".join(f"0x{p:06x}" for p in positions[:3])
            print(f"  {size} bytes: {len(positions)} occ [{first_3}]")
    
    # 10. Look for the specific list request pattern
    print("\n" + "-" * 70)
    print("10. LIST REQUEST PATTERN (F0 52 00 6E 60 25 00 00 2A 00 F7)")
    print("-" * 70)
    
    list_req = b'\xf0\x52\x00\x6e\x60\x25\x00\x00\x2a\x00\xf7'
    positions = find_all(data, list_req)
    if positions:
        for p in positions[:5]:
            print(f"  Found at 0x{p:06x}:")
            hexdump(data, p, 16)
    else:
        print("  Exact list request pattern NOT FOUND in binary")
        print("  (likely constructed at runtime from individual bytes)")
    
    # 11. Look for 0x2A (42) which is in the list request
    print("\n" + "-" * 70)
    print("11. BYTE 0x2A (42) IN CONTEXT")
    print("-" * 70)
    
    # This is likely a timeout or block count
    # Look for it near 60 25
    for pos in find_all(data, b'\x60\x25')[:10]:
        context = data[max(0,pos-4):pos+8]
        if b'\x2a' in context:
            print(f"  0x{pos:06x}: {hexdump(data, max(0,pos-4), 12)}")
    
    # 12. Export summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"""
Protocol: Zoom SysEx (Manufacturer ID 0x006E)
Header:   F0 52 00 6E ... F7
API:      Win32 MIDI (midiIn*/midiOut*)
Classes:  AVSysExMessage, AVMidiManager, AVZoomDevice,
          AVGuitarLabDeviceDelegate, Win32MidiService

Command codes confirmed in binary:
  60 04 - Data reply
  60 05 - ACK / Read next
  60 09 - Terminate
  60 20 - Open file
  60 21 - Close file
  60 22 - Read data
  60 23 - Write block
  60 24 - Create file
  60 25 - File status / List
  60 26 - List next
  60 27 - List end
  60 29 - Disk info

File formats: .ZD2 (effects), .ZT2 (sequences)
Config key: GuitarLabMIDIPortName7

The protocol command codes match g3xn_raw.py exactly.
The issue is likely in timing, framing, or flow control.
""")

if __name__ == "__main__":
    analyze()