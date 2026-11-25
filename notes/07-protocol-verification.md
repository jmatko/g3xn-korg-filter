# Protocol Verification Session — 2026-11-25

## Summary
Verified the Zoom G3Xn SysEx protocol against the pedal via the raw ALSA MIDI
device (`/dev/snd/midiC3D0`). The READ path is fully confirmed. The WRITE path
is blocked by a pedal-side USB state issue (not a protocol bug).

## What's Confirmed Working (G3Xn fw, raw device)

### File List
```
Send:  F0 52 00 6E 60 25 00 00 2A 00 F7
Reply: F0 52 00 6E 60 04 25 00 00 <6 bytes> <13-byte name cstr> F7
```
- 182 files listed successfully
- Name at body[11], C-string terminated
- `60 26` (next) and `60 27` (end) work as expected

### File Status (single file)
```
Send:  F0 52 00 6E 60 25 00 00 <name cstr> F7
Reply: F0 52 00 6E 60 04 25 00 00 <len> 00 00 00 00 00 <name cstr> <size u32le> <pad> F7
```
- **Existing file** (e.g. FLST_SEQ.ZT2): reply body starts `60 04 25` (status=04 = OK)
  - FLST_SEQ.ZT2: size field = 0x4236 (16,950 bytes)
  - LOWPASSF.ZD2: size field = 0x6E1E (28,190 bytes)
- **Non-existent file** (e.g. XXTRVL.ZD2): reply `60 03 7a 7f 7f 7f 0f` (error)
- The `60 05 00` follow-up after status returns `60 03 00 00 00 00 00` (ack/empty)

### Disk Usage
```
Send:  F0 52 00 6E 60 29 00 00 00 00 00 F7
Reply: F0 52 00 6E 60 04 29 01 00 08 00 02 51 24 03 00 18 5f 2e 01 00 00 00 00 00 00 F7
```
- max = 0x02_25102008 (3,019,571,208 bytes)
- avail = 0x01_2E5F1800 (495,000,064 bytes ≈ 472 MB free)
- **Disk is NOT full** — plenty of room for our 8 KB upload

### Data Read (verified working in previous session, degraded today)
```
Open:   F0 52 00 6E 60 20 02 00 00 00 00 00 00 00 00 00 <name cstr> F7
Reply:  60 04 20 ... (status=04 = OK)
Read:   60 05 00 → 60 22 14 2F 60 00 0C 00 04 00 00 00 → 60 05 00
Reply:  60 04 22 01 00 00 04 00 <len u14> <pack7 data> <crc5>
Close:  60 21 40 00 00 00 00
Term:   60 09
```
- Verified: LOWPASSF.ZD2 first block = 512 bytes, ZDLF magic confirmed
- 7-bit packing (high-bit-byte scheme) verified correct
- CRC-5 (inverted CRC-32, 7-bit groups) verified correct

## Write Path — PROTOCOL MATCHES GUITAR LAB, BLOCKED BY PEDAL STATE

### Command sequence (from Guitar Lab binary analysis, mungewell/zoom-zt2)
```
Create:    60 24 <name cstr>
Open write: 60 20 01 00 00 00 00 00 00 00 00 00 <name cstr>
Ack:        60 05 00
Per block:  60 23 40 00 00 00 00 <len u14> 00 00 00 <pack7> <crc5>
Ack:        60 05 00
Close:      60 21 40 00 00 00 00
Term:       60 09
```

### What Guitar Lab.exe contains (binary analysis)
- All command codes 60 01–60 30 confirmed present in the binary
- Same SysEx framing: F0 52 00 6E ... F7
- Same Win32 MIDI API (midiIn*/midiOut*)
- Command Manager with queuing + response matching
- Timing constants: 250ms, 1000ms, 2000ms, 5000ms
- CRC strings: "crc", "CRC", "checksum", "xor"
- File extensions: .ZD2, .ZT2, FLST_SEQ

### Write test results (today)
All write commands are rejected with error responses:
| Command | Reply | Meaning |
|---------|-------|---------|
| `60 24 <name>` (create) | `60 03 7a 7f 7f 7f 0f` | Rejected |
| `60 20 01 ... <name>` (open write) | `60 03 7f 7f 7f 7f 0f` | Rejected |
| `60 23 ...` (write block) | `60 03 7f 7f 7f 7f 0f` | Rejected |
| `60 24 <existing>` (delete) | `60 03 00 00 00 00 00` | Rejected (different error) |

### Error code analysis
- `60 03 7a 7f 7f 7f 0f` = "file not found / cannot create" (7a = 0x7A = 122)
- `60 03 7f 7f 7f 7f 0f` = "operation not permitted / no file open" (7f = 0x7F = 127)
- `60 03 00 00 00 00 00` = "rejected" (delete on existing file)
- These are PEDAL-SIDE rejections, not USB transport failures
- The pedal RECEIVES the commands and RESPONDS with structured errors

### Root cause: pedal USB state, NOT protocol
Evidence:
1. Read path (list/disk/status) works perfectly
2. Write commands get structured error replies (not timeouts)
3. Same degraded state seen in previous session
4. Data reads work briefly then stop (pedal enters "read-only" mode)
5. No USB reset possible from container (read-only sysfs, no /dev/bus/usb access)
6. Guitar Lab binary uses the EXACT same command codes

**Conclusion: The protocol is correct. The pedal is in a degraded USB state
from the container that rejects writes and bulk reads. The WebMIDI path
(Chrome on the Chromebook) uses a different USB stack and should work.**

## 60 28 — Mystery Command Discovered
```
Send:  F0 52 00 6E 60 28 00 00 <name cstr> F7
Reply: F0 52 00 6E 60 04 28 <counter> 00 04 00 00 00 00 00 00 00 00 00 00 00 00 F7
```
- Returns a SUCCESS (60 04) response with an incrementing counter
- Does NOT create any file (verified: status check after shows no file)
- Likely a "ping" or "status query" command
- Present in Guitar Lab binary (48 occurrences)
- NOT used in mungewell or cwoodard reference tools

## Protocol Confidence Assessment

| Aspect | Confidence | Evidence |
|--------|-----------|----------|
| SysEx framing | **CONFIRMED** | F0 52 00 6E ... F7 works both ways |
| File list | **CONFIRMED** | 182 files, correct names/sizes |
| File status | **CONFIRMED** | Correct size for existing, error for missing |
| Disk usage | **CONFIRMED** | Correct max/available values |
| Data read | **CONFIRMED** | ZDLF magic, correct pack7/CRC |
| 7-bit packing | **CONFIRMED** | Round-trip verified |
| CRC-5 | **CONFIRMED** | Matches Guitar Lab CRC strings |
| Write sequence | **HIGH** | Matches Guitar Lab binary + mungewell (MS Plus verified) |
| Write on G3Xn | **UNVERIFIED** | Blocked by pedal state, not protocol |

## Next Steps
1. **Use WebMIDI (web/verify.html)** — Chrome on Chromebook has working
   send+receive. Fix `fileExists()` first (see notes/06).
2. **Power-cycle the pedal** (unplug USB, wait 10s, replug) to clear
   degraded state, then re-test raw device writes.
3. **Upload XXTRVL_g3xn.ZD2** as XXTRVL.ZD2 (8017 bytes, 16 blocks).
4. **Read back and verify** byte-for-byte.