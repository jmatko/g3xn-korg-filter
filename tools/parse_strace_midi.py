#!/usr/bin/env python3
"""
Parse strace log to extract MIDI SysEx data from Guitar Lab.

Strategy:
1. Find the ALSA MIDI file descriptor(s) by looking for /dev/snd/seq or similar opens
2. Extract all read/write calls to those FDs
3. Decode the binary data as MIDI SysEx messages
"""

import re
import sys

def parse_strace_log(path):
    """Parse strace log and extract MIDI-related data."""
    
    # Track file descriptors and what they're associated with
    fd_map = {}  # fd -> description
    midi_fds = set()
    
    # Pattern for openat calls
    openat_re = re.compile(
        r'\[pid (\d+)\] openat\([^,]+, "([^"]+)", [^)]+\) = (\d+)'
    )
    
    # Pattern for read/write calls
    rw_re = re.compile(
        r'\[pid (\d+)\] (read|write)\((\d+), "([^"]*)", (\d+)\)'
    )
    
    # Also handle the case where strace shows binary data with \x escapes
    rw_binary_re = re.compile(
        r'\[pid (\d+)\] (read|write)\((\d+), "(.*)", (\d+)\) = (\d+)'
    )
    
    with open(path, 'r', errors='replace') as f:
        for line in f:
            # Track file opens
            m = openat_re.search(line)
            if m:
                pid, path_str, fd = m.group(1), m.group(2), int(m.group(3))
                if fd >= 0:
                    fd_map[(pid, fd)] = path_str
                    # Check if it's a MIDI-related path
                    if any(x in path_str.lower() for x in ['midi', 'seq', 'snd', 'alpcm']):
                        midi_fds.add((pid, fd))
                        print(f"[INFO] MIDI FD: pid={pid} fd={fd} path={path_str}", file=sys.stderr)
    
    # Now do a second pass to find read/write to MIDI FDs
    # But we also need to handle the case where the MIDI data flows through
    # a socket or pipe that we didn't identify
    
    print(f"\n[INFO] Identified MIDI FDs: {midi_fds}", file=sys.stderr)
    print(f"[INFO] Total FDs tracked: {len(fd_map)}", file=sys.stderr)
    
    # Print all FDs for debugging
    print("\n[DEBUG] All tracked FDs:", file=sys.stderr)
    for (pid, fd), path in sorted(fd_map.items()):
        if pid == '16907' or pid == '16897':  # Main Wine process
            print(f"  pid={pid} fd={fd} -> {path}", file=sys.stderr)

def parse_strace_log_v2(path):
    """
    More robust parser that handles strace's binary data representation.
    strace shows binary data as \\xNN sequences or as raw bytes.
    """
    
    midi_events = []
    
    # We need to find the ALSA MIDI FD. In Wine, this is typically:
    # - An fd opened from /dev/snd/seq
    # - Or a socket connected to the ALSA seq daemon
    # - Or an fd from a pipe that connects to the MIDI driver
    
    # Let's look for ALL write() calls and check if the data starts with F0 (SysEx)
    # SysEx format: F0 ... F7
    
    # Pattern for write calls with data
    # strace format: write(FD, "data", length) = length
    # Binary data is shown as \xNN sequences
    
    line_re = re.compile(
        r'\[pid (\d+)\] (read|write)\((\d+), "(.*)", (\d+)\) = (\d+)'
    )
    
    with open(path, 'r', errors='replace') as f:
        for line in f:
            m = line_re.search(line)
            if not m:
                continue
            
            pid, direction, fd, data_str, length, retval = m.groups()
            fd = int(fd)
            length = int(length)
            
            # Decode the data string (handle \xNN escapes)
            try:
                # strace uses C-style escaping
                data = data_str.encode('utf-8').decode('unicode_escape').encode('latin-1')
            except:
                continue
            
            if len(data) == 0:
                continue
            
            # Check if this looks like MIDI SysEx
            # SysEx starts with F0 and ends with F7
            if data[0] == 0xF0:
                # Find the F7 end byte
                end_idx = data.find(0xF7)
                if end_idx > 0:
                    sysex = data[:end_idx+1]
                    midi_events.append({
                        'pid': pid,
                        'direction': direction,
                        'fd': fd,
                        'length': len(sysex),
                        'data': sysex,
                        'line': line.strip()[:200]
                    })
                else:
                    # Might be a partial SysEx (multi-packet)
                    midi_events.append({
                        'pid': pid,
                        'direction': direction,
                        'fd': fd,
                        'length': len(data),
                        'data': data,
                        'line': line.strip()[:200],
                        'partial': True
                    })
            
            # Also check for other MIDI status bytes
            elif data[0] in (0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF):
                midi_events.append({
                    'pid': pid,
                    'direction': direction,
                    'fd': fd,
                    'length': len(data),
                    'data': data,
                    'line': line.strip()[:200],
                    'type': f'sysrealtime_0x{data[0]:02x}'
                })
    
    return midi_events

def main():
    if len(sys.argv) < 2:
        print("Usage: parse_strace_midi.py <strace_log>")
        sys.exit(1)
    
    path = sys.argv[1]
    
    print(f"Scanning {path} for MIDI SysEx data...\n", file=sys.stderr)
    
    events = parse_strace_log_v2(path)
    
    if not events:
        print("No MIDI SysEx data found in strace log.", file=sys.stderr)
        print("This might mean the MIDI data is not captured in this strace session.", file=sys.stderr)
        sys.exit(0)
    
    print(f"Found {len(events)} MIDI events:\n", file=sys.stderr)
    
    # Group by FD to identify the MIDI channel
    from collections import defaultdict
    by_fd = defaultdict(list)
    for e in events:
        by_fd[(e['pid'], e['fd'])].append(e)
    
    for (pid, fd), evts in sorted(by_fd.items()):
        print(f"\n=== pid={pid} fd={fd} ({len(evts)} events) ===", file=sys.stderr)
        for i, e in enumerate(evts[:20]):  # Show first 20
            data = e['data']
            hex_str = ' '.join(f'{b:02x}' for b in data[:64])
            if len(data) > 64:
                hex_str += f'... ({len(data)} bytes total)'
            print(f"  [{i}] {e['direction'].upper()} len={e['length']} {hex_str}", file=sys.stderr)
    
    # Write the full data to a file
    with open('/tmp/midi_sysex_extracted.txt', 'w') as out:
        for i, e in enumerate(events):
            data = e['data']
            hex_str = ' '.join(f'{b:02x}' for b in data)
            out.write(f"[{i}] pid={e['pid']} {e['direction'].upper()} fd={e['fd']} len={e['length']}\n")
            out.write(f"    {hex_str}\n\n")
    
    print(f"\nFull data written to /tmp/midi_sysex_extracted.txt", file=sys.stderr)

if __name__ == '__main__':
    main()