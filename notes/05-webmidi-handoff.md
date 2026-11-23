# WebMIDI Upload/Download Tool — Protocol Findings & Build Plan (2026-11-23)

Handoff note: this session pivoted from Crostini USB-MIDI (dead end — the G3Xn is
not visible to Crostini) to a **Chrome WebMIDI web UI**. Chrome CAN see the pedal.
This document contains the complete protocol research done this session so the
web UI can be built without re-fetching anything.

## 1. Why a web UI
- G3Xn USB device does not appear in Crostini (VM); no /dev/midi*, no "ZOOM G" port.
- ChromeOS USB sharing does not expose it (not even in chrome://usb-internals).
- Chrome DOES see it via WebMIDI (confirmed by user: arachsys/webmidi sysex.html
  demo page can list/send/receive SysEx).
- Therefore: build a self-contained HTML/JS tool that runs in Chrome and does
  file download (known protocol) and upload (write protocol found this session).

## 2. THE G3Xn FILE PROTOCOL (complete, byte-exact)

Framing: every message is `F0 52 00 6E <body> F7`. WebMIDI delivers full SysEx
including F0/F7. All bodies below are the <body> bytes.

### 2.1 File READ path (G3Xn-verified on fw 2.20 — cwoodard1121 tool)

```
60 25 00 00 <name cstr>    list/check file (first entry)
                           reply: 52 00 6E 60 04 25 00 00 <6 bytes> <13-byte name> 00
                           (reply[4]==0x04 means "entry follows"; name at reply[14..26])
60 26 00 00 <name cstr>    next list entry (same reply shape, echoes 60 04 26)
60 27                     end of list
60 05 00                  status read; reply's LAST 5 BYTES all-zero == file exists
60 20 02 00 00 00 00 00 00 00 00 00 <name cstr>
                           open file for READ (mode byte 0x02)
--- read loop (repeat until status!=4 or len==0) ---
60 05 00                  step 1 (ack)
60 22 14 2F 60 00 0C 00 04 00 00 00   step 2 (read block request; 10 fixed param bytes)
60 05 00                  step 3 -> DATA reply:
                           52 00 6E 60 04 <echo> 00 00 <len u14 @8-9> <packed data @10..> <crc5>
                           n = reply[9]<<7 | reply[8]; stop when reply[4]!=4 or n==0
60 21 40 00 00 00 00      close file
60 09                     terminator
```

### 2.2 File WRITE path (mungewell/zoom-zt2; verified on G1Four/MS Plus,
### NOT yet verified on G3Xn — first upload is the risk point)

```
60 24 <name cstr>         create/truncate file
60 20 01 00 00 00 00 00 00 00 00 00 <name cstr>
                           open file for WRITE (mode byte 0x01)
60 05 00                  (ack)
--- per 512-byte block ---
60 23 40 00 00 00 00 <len u14> 00 00 00 <pack7(data)> <crc5>
60 05 00                  (ack)
60 21 40 00 00 00 00      close
60 09                     terminator
```

`crc5` = inverted CRC-32 of the RAW 8-bit block, as 5 7-bit bytes, low group first:
`crc = (crc32(data) ^ 0xFFFFFFFF); bytes i = (crc >> (7*i)) & 0x7F, i=0..4`.

### 2.3 Misc
```
60 29 00 00 00 00 00      disk usage; reply: 52 00 6E 60 04 29 01 00
                           <max u35le @10-14> <available u35le @15-19>
                           (u35le: b0 + b1*128 + b2*128^2 + b3*128^3 + b4*128^4)
```

### 2.4 Patch commands (cwoodard, G3Xn-verified — for later, not needed for files)
```
44                          patch storage info (reply 43 ... count, size, bank size)
46 00 00 bk bk lc lc        read stored patch (reply 47 ... len u14 <7-bit> crc5)
45 00 00 bk bk lc lc len u14 <7-bit> crc5   write stored patch (reply 00 00)
64 13                       read edit buffer (reply 64 12 01 len u14 <7-bit> crc5)
64 03 00 <slot> <param> <v0..v4>   live edit (values = 5 7-bit groups, low first)
64 02 00 <first> <last>     screen text (reply 64 01 ...)
33                          current patch (CC0, CC32 bank, Program Change)
50 / 51                     editor mode on / off
64 0B / 64 0C               tuner on / off
Patch select: CC0=0, CC32=bank, PC=index (3 patches/bank, 150 slots)
```

## 3. 7-BIT PACKING — CORRECT SCHEME (both reference tools agree)

**High-bit-byte scheme**: for each group of up to 7 bytes, emit ONE header byte
(bit j of header = bit 7 of byte j, i.e. header |= 0x40>>j) followed by the 7
low bytes (b & 0x7F). 7 bytes -> 8 packed bytes. Packed length = ceil(n/7)*8.

```python
def pack7(data):
    out = bytearray()
    for i in range(0, len(data), 7):
        chunk = data[i:i+7]
        high = 0
        for j, b in enumerate(chunk):
            if b & 0x80: high |= 0x40 >> j
        out.append(high)
        out.extend(b & 0x7F for b in chunk)
    return bytes(out)

def unpack7(packed):
    out = bytearray()
    for i in range(0, len(packed), 8):
        high = packed[i]
        for j, b in enumerate(packed[i+1:i+8]):
            out.append(b | (0x80 if high & (0x40 >> j) else 0))
    return bytes(out)
```

### BUG FOUND: tools/g3xn_inspect.py has the WRONG pack7/unpack7
It implements pure 7-bit bit-packing (8 bytes -> 7 bytes, MSB-first) instead of
the high-bit-byte scheme above. Its read_file() will produce garbage. Fix before
the Python path is ever used. (The docstring cites cwoodard's protocol.py, whose
pack7 IS the high-bit scheme — the previous session wrote its own and got it wrong.)

## 4. ZD2 CONTAINER LAYOUT (verified against files/XXTRVL_g3xn.ZD2)

```
0x00  magic "ZDLF"
0x04  length  u32le   *** NOT the file size *** (XXTRVL_g3xn.ZD2: 120 vs 8017 bytes;
                      semantics unknown — open question)
0x08  checksum u32le
0x0C  target  u32le   bitfield: 0x01 g-series, 0x08 B6/G6/G11, 0x10, 0x20,
                      0x80 MS50G+/MS60B+/MS70CDR+, 0x100 MS200D+, 0x200 MS80IR+
0x10  unknown (73 bytes)
0x59  version (4 ASCII, padded)
0x5D  00 00
0x5F  group   u8      (browser category; G3Xn: 0x02 = FILTER)
0x60  id      u32le   (top byte == group)
0x64  name    (11 bytes)
0x6D  groupname (11 bytes)
0x76  unknown4 (3 bytes)
0x79  00 00 00
0x7C  chunks: ICON, TXJ1, TXE1, INFO, [DATA, INF2, CCOE, PRMJ, PRME]
      each chunk: 4-byte tag + u32le length + data
      (INFO chunk: length covers data + trailing Float32le dspload)
last  unknown5 (16 bytes)
```

XXTRVL_g3xn.ZD2 observed: length-field=0x78, target=0x91, version "1.00",
group=0x02, id=0x02001010, name "Traveler", groupname "FILTER", ICON@0x7C len 936.

## 5. ZT2 / FLST_SEQ FORMAT (verified against mungewell EMPTY.ZT2, 8502 bytes)

```
Total: 8502 bytes, zero-padded.
Header (78 bytes):
  0x00  ">>>\0"
  0x04  pad 22
  0x18  file name (12 bytes, e.g. "FLST_SEQ")
  0x24  pad 6
  0x2A  0x01
  0x2B  pad 7
  0x32  "<<<\0"
  0x36  pad 22
Groups (repeated):
  ">>>\0" + group u8 + pad 21                    (26 bytes)
  effect entries (26 bytes each):
      filename (12) + 00 + version (4 ASCII) + 00 + installed u8 (1=normal,
      0="Guitar Lab additional") + id u32le + 00 00 00
      (id top byte MUST equal the group byte)
  "<<<\0" + group u8 (== group) + pad 21         (26 bytes)
```

### FLST_SEQ edit algorithm (mungewell add_effect, battle-tested on MS Plus)
1. Parse ZT2 into header + groups.
2. group_new = (id >> 24) & 0xFF.
3. If a group with that number exists: delete any entry with the same filename,
   append new entry {filename, version, id, installed=1}.
4. Else: create the group containing the new entry.
5. Rebuild: header + groups, zero-pad to exactly 8502 bytes.
Remove = same but without append.

## 6. WEB UI DESIGN (to be built next)

Single self-contained file `web/index.html` (inline CSS+JS, no modules — so it
works from file:// with no CORS issues). Fallback: `python3 -m http.server`.

API:
- `navigator.requestMIDIAccess({sysex: true, sysexAccess: true})` (pass both keys;
  sysexAccess is the modern name). Requires secure context — Chrome treats file://
  as secure (verify on first run; if not, serve over localhost).
- Port names: G3Xn exposes input+output named "ZOOM G" (may show as "ZOOM G3Xn").
  List all ports, auto-suggest ones containing "ZOOM", user confirms.
- `port.open()`, `port.onmidimessage` (e.data = full SysEx Uint8Array),
  `port.send(uint8array)`. Handle `midiAccess.onstatechange` for hot-plug.

Transport:
- request(): send F0 52 00 6E <body> F7; await NEXT sysex starting
  F0 52 00 6E 60 (file family); check reply[4]==0x04 (status OK) where it matters;
  3-4s timeout; log every message to a hex console.
- Protocol is strictly request/response (one outstanding request) — same model
  both reference tools use.

Features, phased (read first!):
1. Read-only (default): connect, list files (60 25/26/27), download one file,
   download all (backup), disk usage (60 29).
2. Upload (behind a Read-only toggle, OFF by default): pick .ZD2/.ZT2 -> show
   parsed summary (id/group/target/name/version) -> confirm dialog ->
   60 24 + 60 20 01 + 60 23 blocks + 60 21/60 09 -> READ BACK and byte-compare.
3. FLST_SEQ editor: download -> table of groups/effects -> add effect (from a
   ZD2 in session) / remove (checkboxes) -> auto-backup current FLST_SEQ to a
   .bak download before uploading modified one -> upload -> read-back verify.

Safety (non-negotiable):
- Read-only mode ON by default; writes disabled until user flips toggle.
- Confirm dialog with filename+size before every write.
- Read-back verification after every upload (byte compare, report result).
- Auto-backup before any FLST_SEQ modification.
- Full SysEx hex console with Copy button (for sharing logs when something fails).
- First upload test should be a known-good STOCK file: download X, upload X,
  compare. Then try custom XXTRVL_g3xn.ZD2.

## 7. OFFLINE TEST PLAN (do before any pedal interaction)

Node v20 is available in Crostini. Extract the pure logic (crc32, pack7/unpack7,
ZD2 header parse, ZT2 parse/rebuild) and test:
- pack7/unpack7 round-trip on random + XXTRVL_g3xn.ZD2 data.
- crc32 against known vectors.
- ZD2 header parse on files/XXTRVL_g3xn.ZD2 (expect: target 0x91, group 0x02,
  id 0x02001010, name "Traveler").
- ZT2 parse -> rebuild on mungewell EMPTY.ZT2 must be BYTE-IDENTICAL (8502 bytes).
- ZT2 add_effect/remove_effect round-trip on a synthetic FLST_SEQ.

## 8. OPEN QUESTIONS
1. G3Xn write path (60 24 / 60 20 01 / 60 23) is unverified on the G3Xn — it is
   MS Plus/G1Four-verified only. First live upload is the experiment.
2. ZD2 "length" field semantics (120 in our file vs 8017 actual size).
3. Exact echo byte in the 60 05 data reply (matcher accepts any 60-family reply
   + status check; log will reveal it on first run).
4. The 6 bytes between status and name in list replies (likely size/flags).
5. Whether the G3Xn tolerates FLST_SEQ modifications (stomphacks SAFETY.md warns
   of bricking on MS Plus; G3Xn behavior unknown).
6. file:// WebMIDI in this Chrome build (expected to work).

## 9. SOURCES

- cwoodard1121/zoom-g3xn-agent-skill (MIT, G3Xn-verified fw 2.20):
  g3xn/protocol.py (all commands + correct pack7/checksum), g3xn/pedal.py
  (list_files/read_file). https://github.com/cwoodard1121/zoom-g3xn-agent-skill
- mungewell/zoom-zt2 (MIT, G1Four/MS Plus): zoomzt2.py — pack()/unpack(),
  file_check/file_wild/file_download/file_upload/file_close/disk_usage,
  add_effect/add_effect_from_filename/remove_effect, ZT2+ZD2 construct defs
  (lines ~14-203). https://github.com/mungewell/zoom-zt2
- thammer/stomphacks: tools/zd2_cleanroom.py, tools/flst_check.py, SAFETY.md
  (anti-bricking rules). https://github.com/thammer/stomphacks
- Local copies downloaded this session (in /tmp/zoom-ref/, may not survive reboot):
  cwoodard-pedal.py, mungewell-zoomzt2.py, mungewell-readme.md, EMPTY.ZT2,
  stomphacks-zd2_cleanroom.py, cwoodard-tree.json, stomphacks-tools.json
- Repo: files/XXTRVL_g3xn.ZD2 (8017 B, our Traveler filter, target 0x91, group 0x02),
  files/XXTRVL_msplus.ZD2, files/XXTRVL.ZIC, notes/03 + notes/04 (earlier research).

## 10. NEXT STEPS (ordered)
1. Fix pack7/unpack7 in tools/g3xn_inspect.py (section 3).
2. Build web/index.html per section 6.
3. Run Node offline tests (section 7).
4. User opens web/index.html in Chrome with pedal connected:
   verify port list, list files, download one stock .ZD2 + FLST_SEQ.ZT2.
5. Compare downloaded stock LOWPASSF.ZD2 target bit/group byte vs our XXTRVL
   (answers the notes/03 open question about the correct G3Xn target bit).
6. Upload test: stock file round-trip first, then XXTRVL_g3xn.ZD2.
7. If upload works: FLST_SEQ add-effect, then load the Traveler in a patch and
   audition. Uninstall at end of session (stomphacks safety rule).