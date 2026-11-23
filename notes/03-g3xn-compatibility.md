# G3Xn Compatibility — Research Findings (2026-11-23)

## The big picture
The G3Xn DOES use the ZD2 container for its effect files (confirmed: a
third-party tool downloads all 162 stock .ZD2 files from a G3Xn). But the
G3Xn is a DIFFERENT family from the MS Plus, and the stomphacks toolchain was
built and hardware-tested ONLY on the MS-70CDR+. So:
- The effect CODE (our biquad) is portable — it's the same C6000 DSP.
- The INSTALL path is NOT proven for the G3Xn. This is the collaborator's job.

## Two different target-bit schemes (important!)
The ZD2 `target` field (offset 12) has a bitfield. There are TWO naming schemes:

1. ZD2 effect file (zoomzt2.py `targets`):
   - 0x0001 = "g-series"
   - 0x0008 = "Seen on B6/G6/G11"
   - 0x0010, 0x0080 (ms-50g+), 0x0100 (ms-200d+), 0x0200 (ms-80ir+)
   - Stock MS Plus effects carry 0x0090 = 0x0080 | 0x0010.

2. PTCF preset file (decode_preset.py `targets`) — DIFFERENT mapping:
   - 0x01 = g5n, 0x02 = g3n, 0x04 = g3xn, 0x08 = b3n, 0x10 = g1four,
     0x20 = g1xfour, 0x40 = b1four, 0x80 = b1xfour, 0x0100 = a1four,
     0x0200 = a1xfour, 0x0400 = g11, 0x0800 = h8, 0x1000 = g6, 0x2000 = b6,
     0x4000 = r20, 0x10000 = b2four

So the G3Xn's ZD2 target bit is NOT clearly established. My file uses 0x91
(0x90 MS Plus | 0x01 g-series). If the G3Xn checks the target bit and wants a
different bit (e.g. 0x08 "B6/G6/G11"), the file may be rejected. The target
bit is marked "Informational, does not rebuild" in the parser, but the firmware
may still check it. The collaborator should dump a STOCK G3Xn ZD2 (easy with
the g3xn tool) and read its target bit to know the right value.

## The G3Xn protocol is DIFFERENT from the MS Plus (confirmed)
A separate, G3Xn-verified tool exists: cwoodard1121/zoom-g3xn-agent-skill
("g3xn"), verified on G3Xn firmware 2.20. Key differences from stomphacks:

- Port prefix: G3Xn = "ZOOM G" (stomphacks looks for "ZOOM MS Plus Series").
- SysEx framing: both use `F0 52 00 6E <cmd> F7` (Zoom, device 0x6E).
- File-system commands (G3Xn): `60 25` (open/list), `60 26` (next),
  `60 05` (read block), `60 20` (open for read), `60 22` (read), `60 21`
  (close), `60 27` (end list), `60 09` (?).
- Patch commands: `44` (info), `45` (write), `46` (read), `64 03` (live edit),
  `64 13` (read edit buffer), `64 02` (screen text).
- Patch storage: 150 slots, 3 patches/bank, CC0=0 + CC32=bank + PC=index.
- 7-bit packing for file data (pack7/unpack7), 5-byte checksum.

CRITICAL: the g3xn tool only READS the file system (list_files, read_file).
It does NOT implement a WRITE/upload of a .ZD2. So the G3Xn upload command
sequence is NOT yet known from that tool. The collaborator needs to find the
G3Xn file-WRITE command (likely a `60 2x` variant, mirroring the read path) —
possibly by reversing Guitar Lab / ToneLib, or by observing what Zoom's
software does.

## Per-model effect differences (Q1)
- The effect-ids doc has a category table for MS Plus models ONLY. The G-series
  (G3Xn, G11, G6) category/group numbering is UNKNOWN — there's no table.
- The id-scheme doc says: "The group byte is set per target pedal... an effect
  that targets several models gets ONE FINISHED FILE PER MODEL. Each file
  carries that model's group byte in its id... A single binary does not run on
  every pedal anyway (the format and ABI differ across families)."
- So YES, there are per-model differences: the group byte (top byte of the
  effect id, which sets the browser category) is different per pedal, and the
  G-series may have a different ABI/format than the MS Plus.
- "3-window" effects: I found NO reference to "3-window" effects in any doc.
  This is not a documented concept in stomphacks. It may refer to the G3Xn's
  3-effect-display UI, or a specific effect class. UNVERIFIED — flag for the
  collaborator to check against a real G3Xn.

## What this means for our build
- Our XXTRVL.ZD2 (target 0x91) is a reasonable first guess but UNVERIFIED on
  the G3Xn.
- To make it G3Xn-correct, the collaborator should:
  1. Use the g3xn tool to dump a stock G3Xn ZD2 (e.g. a filter effect).
  2. Read its target bit + group byte (top byte of id).
  3. Set our file's target bit and group byte to match.
  4. Find the G3Xn file-WRITE SysEx command (reverse Guitar Lab/ToneLib, or
     observe the protocol).
- The DSP code itself (traveler.c) should run unchanged IF the G3Xn's DSP ABI
  matches the MS Plus (likely, since both use ZD2/C6000, but not guaranteed).

## The g3xn tool (cwoodard1121/zoom-g3xn-agent-skill)
- MIT licensed. Verified on G3Xn fw 2.20.
- Reads/writes all 150 patch slots byte-exact. 162-effect catalog.
- Downloads all .ZD2 effect files from the pedal.
- Reads knob ranges/defaults from the embedded C6x ELF (same as stomphacks).
- Built on mungewell/zoom-zt2 (PTCF + ZD2 + file transfer) + shooking/ZoomPedalFun.
- Does NOT upload custom effects (read-only file system).
- This is the best starting point for the G3Xn upload work.