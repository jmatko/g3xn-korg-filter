# Protocol Verification — Session 3 (2026-11-26)

## Key Findings

### 1. Data is RAW 8-bit, NOT 7-bit packed
The G3Xn sends file data as **raw 8-bit bytes** in the read reply. The
`unpack7()` function in the original `g3xn_raw.py` was corrupting data.

Read reply format:
```
60 04 22 01 00 00 04 00 <raw 8-bit data ...>
```
- 8-byte header
- Data starts at byte 8
- Data detection: `r[3] == 0x01`

### 2. Data reply is ASYNCHRONOUS
The data reply for block N arrives as the reply to block N+1's ack (`60 05 00`),
NOT immediately after the read request. This is a critical protocol detail.

Sequence:
```
send 60 05 00 (ack)  → reply: DATA from previous block (598B)
send 60 22 ... (read) → reply: read ack (17B)
[wait 250ms]
send 60 05 00 (ack)  → reply: DATA from this block (598B)
...
```

Block 0 is special: its ack returns an error (`60 03 00 00 00 00 00`), and
the data arrives with block 1's ack.

### 3. Pedal enters error state after sessions
After a read/write session, the pedal enters an error state where:
- Open requests return `60 03 7f 7f 7f 7f 0f` (all-ones error)
- All subsequent writes fail

This state clears after a power cycle or a fresh connection. The download
function now retries the open request up to 3 times with 1-second delays.

### 4. File size vs actual data
FLST_SEQ.ZT2 reports size 16,950 bytes but only 9,799 bytes of actual data
are returned. The remaining 7,151 bytes appear to be zero-padding or
unused space in the pedal's file system.

### 5. Status reply format
`60 25 00 00 <name cstr>` returns:
```
60 04 25 00 00 17 00 00 00 00 00 46 4c 53 54 5f 53 45 51 2e 5a 54 32 00 00 00 36 42 00 00
```
- Body[11:23]: filename (12 bytes, null-padded)
- Body[26:30]: file size (u32le) = 0x4236 = 16,950

## Working Commands (verified)
| Command | Status | Notes |
|---------|--------|-------|
| `list` | ✅ | 181 files returned |
| `disk` | ✅ | Returns disk usage |
| `status <name>` | ✅ | Returns filename + size |
| `download <name> <out>` | ✅ | Raw 8-bit, async data, 250ms pacing |
| `upload <name> <in>` | ⚠️ | Protocol correct, blocked by pedal error state |
| `raw <hex>` | ✅ | Raw SysEx passthrough |

## Download Function (fixed)
The key changes to `g3xn_raw.py`:
1. **No `unpack7()`** — data is raw 8-bit
2. **Async data handling** — data arrives with next block's ack
3. **250ms pacing** — matches Guitar Lab's timing
4. **Retry on open** — handles pedal error state
5. **Short block detection** — `len(raw) < 500` means end of file
6. **File size check** — stop when `len(data) >= fsize`

## Upload Blocker
The write path is blocked by the pedal's error state. All write commands
(create, open-write, write-block) return `60 03 7f 7f 7f 7f 0f`.

Possible solutions:
1. Power-cycle the pedal before uploading
2. Use the WebMIDI tool (web/verify.html) which runs in a browser
3. Find a SysEx command that resets the pedal's error state

## Files
- `/tmp/FLST_SEQ_ok.ZT2` — 9,799 bytes, verified correct
- `/tmp/FLST_SEQ_fixed.ZT2` — 9,799 bytes, byte-for-byte match
- `tools/g3xn_raw.py` — updated with all fixes