# Upload Tooling — Handoff Notes

For the collaborator working on uploading the effect to the G3Xn.

## What's ready
- `files/XXTRVL_g3xn.ZD2` — the Traveler effect, target 0x91 (MS Plus + G-series bits), CRC valid.
- `files/XXTRVL.ZIC` — the companion icon (the pedal shows the icon, not the name field).
- `files/XXTRVL_msplus.ZD2` — same effect, target 0x90 (MS Plus only), for testing on an MS Plus.

The ZD2 + ZIC pair is the upload unit. The ZIC must be uploaded with the same
filename stem as the ZD2 (the pedal associates them by filename).

## How ZD2 install works (from zoom-zt2 + stomphacks)
Installing an effect is NOT just copying the file. It has three parts:
1. Upload the `.ZIC` icon file.
2. Upload the `.ZD2` effect file.
3. Add the effect to the pedal's on-device effect list `FLST_SEQ.ZT2`
   (`add_effect_from_filename`), then re-upload the modified list.

`FLST_SEQ.ZT2` is the file the pedal reads FIRST at boot. A corrupt one can
stop the pedal booting (a brick path). So the list edit must be validated
before any write.

## Existing tooling (reuse these, don't reinvent)
- `stomphacks/zoom-zt2/zoomzt2.py` — the ZD2 parser + the USB-MIDI transfer
  layer (`file_upload`, `add_effect_from_filename`, `remove_effect`,
  `file_delete`). Its `--install` flow does the full install. This is the
  reference for the SysEx command sequences — reuse them exactly.
- `stomphacks/tools-pedal/pedal_diy.py install|uninstall <FILE.ZD2>` — the
  safe installer. It is fail-closed: checks the effect against a stock catalog,
  validates the effect list on the PC before any write, runs the whole transfer
  over one timeout-bounded connection, and reads back every uploaded file to
  byte-compare. **This is the tool to use for the actual install.**
- `stomphacks/tools-pedal/safe_connect.py` — session opener: connects, records
  pedal/firmware identity, turns autosave OFF (the anti-brick invariant), and
  downloads the current patch to confirm it's stock-only. Run this first.
- `stomphacks/tools-pedal/backup_pedal.py` — full backup (every effect, every
  patch slot, FLST_SEQ.ZT2). Run before the first write to the pedal.
- `stomphacks/tools/flst_check.py` — offline validation of FLST_SEQ.ZT2
  (must be exactly 8502 bytes, parse, round-trip byte-for-byte).

## SAFETY (read stomphacks/SAFETY.md fully before touching the pedal)
- A broken effect saved into a patch can brick the pedal PERMANENTLY, no known
  recovery.
- The whole anti-brick model rests on autosave being OFF. `safe_connect.py`
  enforces this and refuses to continue unless the pedal ACKs it.
- Never send the SysEx commands listed in SAFETY.md's never-send list.
- One action per script run; print exactly what was sent/received.
- Fail closed on any unexpected response: stop, print state, exit. No retries.
- Install and audition with the safe wrapper; never save a patch that contains
  the DIY effect until it's confirmed stable.

## G3Xn-specific caveats
- The stomphacks project was hardware-tested on an MS-70CDR+, NOT a G3Xn. The
  ZD2 container format is shared ("the G5-family" per docs/zd2-format.md), and
  the G-series bit is 0x0001, but the G3Xn has NOT been verified to load DIY
  ZD2 effects. This is the main open risk.
- The G3Xn uses a different USB-MIDI file-transfer dialect than the MS Plus in
  some cases (Zoom's G-series multieffects have their own file protocol). The
  zoom-zt2 transfer layer was built for the MS Plus. If `pedal_diy.py` doesn't
  connect to the G3Xn, the file-transfer SysEx may need adaptation to the
  G-series protocol (this is likely where the collaborator's work focuses).
- The target bit 0x0001 (g-series) is set in XXTRVL_g3xn.ZD2. If the G3Xn
  rejects the file, try toggling the target bits (the field is "informational"
  in the parser, but the firmware may check it).

## Rebuilding the effect
- Source: `stomphacks/effects/traveler/` (manifest.json + traveler.c).
- Build: `cd stomphacks && ZOOM_TI_CGT=/home/user/zd2-project/build/ti-cgt-c6000 \
  .venv/bin/python3 tools/zd2_make_effect.py effects/traveler/manifest.json`
- The build outputs to `stomphacks/effects/traveler/build/XXTRVL.ZD2` (target 0x90).
- To make a G3Xn-targeted copy: `python3 tools/set_target.py XXTRVL.ZD2 XXTRVL_g3xn.ZD2 0x91`

## The TI toolchain
- The build needs the TI C6000 compiler. A working Linux build (v7.2.11, i386
  binaries) is at `/home/user/zd2-project/build/ti-cgt-c6000/` (bin/ + include/).
  It's older than the documented 8.5.0 but compiles the kernel fine (the gain
  reference effect builds byte-clean with it).
- Set `ZOOM_TI_CGT=/home/user/zd2-project/build/ti-cgt-c6000` when building.