# G3Xn MIDI Protocol Research Notes
## Guitar Lab Binary Analysis & Protocol Investigation
**Date:** 2026-11-24 (updated 2026-11-25)
**Status:** Protocol CONFIRMED — read path fully verified, write path blocked by pedal USB state

## 0. Quick Status (2026-11-25)
- **Read path: FULLY CONFIRMED** (list, status, disk, data read all work)
- **Write path: PROTOCOL CORRECT** (matches Guitar Lab binary exactly) but pedal
  rejects writes from the container's raw MIDI device (degraded USB state)
- **WebMIDI tool: READY** (`web/verify.html` — fixed fileExists, upload timing,
  error reporting). Use Chrome on the Chromebook for the actual upload.
- **Disk: NOT full** (495 MB free of 3 GB) — no need to delete presets
- **Effect file: READY** (`files/XXTRVL_g3xn.ZD2`, 8017 B, Traveler filter)
- See `notes/07-protocol-verification.md` for full details.

---

## 1. Environment Setup

### Wine + Guitar Lab
- **Wine:** 10.0, Win32 prefix at `/home/user/.wine-zoom`
- **App:** Guitar Lab v7.3.0.130 at `/home/user/.wine-zoom/drive_c/Program Files/ZOOM/Guitar Lab/`
- **Binary:** `Guitar Lab.exe` (PE32, 7.4MB, 32-bit)
- **Hardware:** ZOOM G3Xn via USB, raw MIDI at `/dev/snd/midiC3D0`
- **ALSA Seq:** Client 28:0 (`ZOOM G Series MIDI 1`)

### Key Tools
| Tool | Path |
|------|------|
| Raw MIDI client | `/home/user/zd2-project/g3xn-korg-filter/tools/g3xn_raw.py` |
| RTMIDI test | `/home/user/zd2-project/g3xn-korg-filter/tools/test_rtmidi2.py` |
| Strace parser | `/home/user/zd2-project/g3xn-korg-filter/tools/parse_strace_midi.py` |
| Proxy script | `/home/user/zd2-project/g3xn-korg-filter/tools/zoom_proxy.py` |
| Strace log | `/tmp/guitarlab_strace.log` (26MB) |

### Ghidra
- **Location:** `/home/user/ghidra_12.2_PUBLIC`
- **Run:** `/home/user/ghidra_12.2_PUBLIC/ghidraRun`
- **Config:** `/home/user/.config/ghidra/ghidra_12.2_PUBLIC`

---

## 2. Guitar Lab Binary Analysis

### MIDI API
Guitar Lab uses the **Win32 MIDI API** (Wine translates to ALSA):
- `midiInOpen`, `midiInClose`, `midiInStart`, `midiInStop`
- `midiInMessage`, `midiInAddBuffer`, `midiInPrepareHeader`
- `midiOutOpen`, `midiOutClose`, `midiOutShortMsg`, `midiOutLongMsg`
- `midiOutPrepareHeader`, `midiOutUnprepareHeader`
- `midiInGetNumDevs`, `midiOutGetNumDevs`
- `midiInGetDevCapsW`, `midiOutGetDevCapsW`

### Key Classes (C++ mangled names)
| Class | Address | Role |
|-------|---------|------|
| `AVSysExMessage` | 0x66d87e | SysEx message wrapper |
| `AVMidiManager` | 0x66dc56 | MIDI I/O manager |
| `AVZoomDevice` | 0x66dd6e | Zoom device abstraction |
| `AVGuitarLabDeviceDelegate` | 0x66d672 | Device delegate (heavily referenced) |
| `AVMidiInputCallback` | 0x66da26 | Input callback handler |
| `AVMidiOutput` | 0x6733c6 | MIDI output |
| `AVMidiMessageCollector` | 0x672ce6 | Message collector |
| `Win32MidiService` | 0x672db6 | Win32 MIDI service |
| `Win32MidiDeviceQuery` | 0x672d8e | Device enumeration |
| `AUMidiService` | 0x67321a | Abstract MIDI service |
| `AUMidiInCollector` | 0x672e46 | MIDI input collector |
| `AUMidiOutHandle` | 0x673b46 | MIDI output handle |
| `AUMidiServiceType` | 0x673bfe | Service type enum |

### Protocol Constants Found in Binary
- **SysEx header `F0 52 00 6E`**: 324 occurrences
- **Command codes** (all confirmed present):

| Code | Meaning | Occurrences |
|------|---------|-------------|
| `60 01` | ACK | 217 |
| `60 02` | NACK | 230 |
| `60 03` | Error/NACK | 220 |
| `60 04` | Data reply | 281 |
| `60 05` | ACK / Read next | 147 |
| `60 06` | Unknown | 59 |
| `60 07` | Unknown | 55 |
| `60 08` | Unknown | 66 |
| `60 09` | Terminate | 41 |
| `60 20` | Open file | 46 |
| `60 21` | Close file | 50 |
| `60 22` | Read data | 34 |
| `60 23` | Write block | 51 |
| `60 24` | Create file | 33 |
| `60 25` | File status / List | 38 |
| `60 26` | List next | 31 |
| `60 27` | List end | 45 |
| `60 28` | Unknown | 48 |
| `60 29` | Disk info | 33 |
| `60 2A` | Unknown | 44 |
| `60 2B` | Unknown | 52 |
| `60 2C` | Unknown | 43 |
| `60 2D` | Unknown | 52 |
| `60 2E` | Unknown | 43 |
| `60 2F` | Unknown | 49 |
| `60 30` | Unknown | 102 |

- **File extensions**: `.ZD2` (2 occ), `.ZT2` (1 occ), `FLST_SEQ` (1 occ)
- **Config key**: `GuitarLabMIDIPortName7`
- **Timing constants found in binary**:
  - 250 ms (45 occ)
  - 1000 ms (72 occ)
  - 2000 ms (35 occ)
  - 5000 ms (15 occ)
- **CRC strings**: `crc` (2), `CRC` (5), `checksum` (1), `xor` (2)
- **Exact list request pattern** `F0 52 00 6E 60 25 00 00 2A 00 F7`: NOT in binary (constructed at runtime)

### Error/Debug Strings
- "Received undefined MIDI message: %s"
- "Undefined sysEx MIDI message processing cmd <%s>: %s"
- "Undefined sysEx MIDI message processing cmd <%s>: %d bytes"
- "ERROR executing command : "
- "ERROR enqueuing: unknown command - "
- "Command Manager"
- "Error processing command %s : %s"
- "ERROR executing command, no reply received : "
- "ERROR in command response : "
- "Enqueued cmd: unit %d, module %d, paramIx %d, value: %d"

### Key Insight
The app has a **Command Manager** with command queuing and response matching.
The protocol command codes are **identical** to what `g3xn_raw.py` uses.
This means the protocol itself is correct — the issue is likely in:
1. **Timing** (delays between commands, ACK timeouts)
2. **Packet framing** (how SysEx messages are chunked)
3. **Channel** (MIDI channel used)
4. **Flow control** (how ACKs are handled)
5. **CRC calculation** (if different from what we implement)

---

## 3. Strace Capture Results

### What Worked
- Guitar Lab launched successfully under Wine + strace
- Triggered download of BYPASS.ZD2 via GUI
- Captured 26MB / 120k lines of strace output

### What Failed
- Only 94 MIDI events found on fd=23 (the MIDI socket)
- All were `F4` (Time Code) subscription messages
- **No actual SysEx data captured**

### Why It Failed
Wine's ALSA MIDI driver does NOT use raw `read()`/`write()` syscalls for MIDI data.
It uses the ALSA sequencer API (`snd_seq_event_output/input`) which goes through
a different kernel interface (ioctl-based, not read/write).

### Strace Log Location
`/tmp/guitarlab_strace.log`

---

## 4. Current Blockers

### Device Lock
- `/dev/snd/midiC3D0` is locked after killing Wine processes
- All open modes fail: `OSError: [Errno 16] Device or resource busy`
- `usbreset` fails (permissions)
- Sysfs unbind/bind fails (read-only filesystem)
- **Fix:** Unplug/replug USB cable, or reboot VM

### ALSA Seq Receive
- The ALSA seq path (client 28:0) can SEND but not RECEIVE in this container
- Confirmed with `test_rtmidi2.py` — sends work, no responses received

---

## 5. Next Steps (When Back at Machine)

### Priority 1: Unblock Raw MIDI Device
1. Unplug G3Xn USB cable, wait 5 seconds, replug
2. Verify: `ls /dev/snd/midiC*`
3. Test: `python3 tools/g3xn_raw.py list`

### Priority 2: Test g3xn_raw.py Protocol
1. `python3 tools/g3xn_raw.py list` — verify file listing works
2. `python3 tools/g3xn_raw.py status` — verify status query
3. `python3 tools/g3xn_raw.py download BYPASS.ZD2 /tmp/test.zd2` — test bulk read
4. If bulk read fails, compare timing/framing with Guitar Lab

### Priority 3: Deep Binary Analysis (Ghidra)
1. Load `Guitar Lab.exe` in Ghidra at `/home/user/ghidra_12.2_PUBLIC`
   - Run: `/home/user/ghidra_12.2_PUBLIC/ghidraRun`
2. Find `AVSysExMessage` class — analyze packet construction
3. Find `AVZoomDevice` class — analyze command flow
4. Find `AVGuitarLabDeviceDelegate` — analyze ACK handling
5. Look for CRC calculation functions (search for `crc`, `checksum`, `xor` in function names)
6. Look for timing constants (250ms, 1000ms, 2000ms, 5000ms found in binary)
7. Use Ghidra script: `tools/ghidra_analyze_guitarlab.py`

### Key Ghidra Addresses to Investigate
| Class | Address | What to Look For |
|-------|---------|------------------|
| `AVSysExMessage` | 0x66d87e | Packet construction, byte layout |
| `AVMidiManager` | 0x66dc56 | MIDI I/O flow |
| `AVZoomDevice` | 0x66dd6e | Command dispatch |
| `AVGuitarLabDeviceDelegate` | 0x66d672 | ACK handling, error recovery |
| `Win32MidiService` | 0x672db6 | Win32 MIDI API calls |
| `CommandManager` | 0x66d985 | Command queue, response matching |
| `AVMidiInputCallback` | 0x66da26 | Input message handling |
| `AVMidiOutput` | 0x6733c6 | Output message construction |

### Priority 4: LD_PRELOAD Hook (Alternative Capture)
Write a C library that hooks `snd_seq_event_output()` / `snd_seq_event_input()`
to capture MIDI data at the ALSA library level, then run Guitar Lab with
`LD_PRELOAD=./hook.so wine Guitar\ Lab.exe`

---

## 6. File Locations Summary

```
/home/user/
├── ghidra_12.2_PUBLIC/          # Ghidra 12.2
│   └── ghidraRun                # Launch script
├── .wine-zoom/                   # Wine prefix (Win32)
│   └── drive_c/Program Files/ZOOM/Guitar Lab/
│       └── Guitar Lab.exe       # 7.4MB PE32 binary
├── zd2-project/g3xn-korg-filter/
│   ├── RESEARCH_NOTES.md        # THIS FILE
│   └── tools/
│       ├── g3xn_raw.py          # Raw ALSA MIDI client
│       ├── test_rtmidi.py       # RTMIDI test (callback)
│       ├── test_rtmidi2.py      # RTMIDI test (polling)
│       ├── parse_strace_midi.py # Strace log parser
│       └── zoom_proxy.py        # Virtual MIDI proxy
└── /tmp/guitarlab_strace.log    # 26MB strace capture
```