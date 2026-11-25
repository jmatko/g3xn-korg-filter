# Direct MIDI session — 2026-11-24 (user offline ~8h)

Goal: test FLST_SEQ.ZT2 backup/modification over MIDI, then upload XXTRVL_g3xn.ZD2.
User said: use direct MIDI device access, forget git for now.

## What works from this container
- **RAW device `/dev/snd/midiC3D0`** gives working SEND + RECEIVE (ALSA sequencer
  RECEIVE is broken — 0 events). New tool: **`tools/g3xn_raw.py`**
  (`RawG3Xn`: list / download / upload / status / disk / raw).
  The raw device is EXCLUSIVE — opening it blocks the sequencer connect, so use
  raw for both directions.
- Verified working: **file list (182 files, first = FLST_SEQ.ZT2)**, disk usage,
  file status, open-for-read (`60 20 02` → `60 04 20 ...`).

## Protocol corrections found
1. **read-next** is NOT `60 05 00`. Working triple:
   - `60 05 00` (ack)
   - `60 22 14 2F 60 00 0C 00 04 00 00 00` (read-block request)
   - `60 05 00` → **DATA reply** `60 04 22 01 00 00 04 00 <len u14 @8-9> <pack7 @10..> <crc5>`
   (matches `web/verify.html` downloadFile). Old `tools/g3xn_client.py` used the
   wrong read-next → 0 bytes.
2. **file status** `60 25 00 00 <name>` + `60 05 00` returns `60 03 <5 size bytes>`
   (FLST_SEQ.ZT2 → `60 03 7a 7f 7f 7f 0f`), NOT `60 05 00`. So `web/verify.html`
   `fileExists()` is WRONG for G3Xn → returns false even when the file exists.
   **This is the root cause of the "file not found on pedal: FLST_SEQ.ZT2" errors**
   in the Backup and Manage-effects buttons. Fix: treat `60 03 <size>` as exists,
   or attempt open-for-read and check reply `60 04 20`.

## BLOCKER: pedal in degraded state (unresolved)
After the pedal was reconnected to Open Terminal:
- **Reads work** (list/disk/status).
- **All WRITES rejected**: create `60 24` → `60 03 7a 7f 7f 7f 0f`;
  open-write / data block → `60 03 7f 7f 7f 7f 0f`.
- **Data READ (read-next) returns 0 bytes** (worked exactly once, then stopped).
- Does NOT recover after 3–20 s waits.

This blocks both the FLST_SEQ modification test AND the XXTRVL_g3xn.ZD2 upload.
Most likely a USB-MIDI link issue from the container (control traffic works,
bulk data/writes don't).

## Next steps (when user is back)
1. **Easiest:** use the Chromebook WebMIDI web tool (`web/verify.html`) — it has
   working send+receive. First fix `fileExists()` (see above) so Backup /
   Manage-effects stop saying "file not found", and add a file-picker trigger
   for the Upload button (the `#uploadfile` input is display:none and the Upload
   button doesn't call `.click()`).
2. OR re-seat the USB cable / power-cycle the pedal, then re-test
   `python3 tools/g3xn_raw.py download FLST_SEQ.ZT2 out.ZT2` and the upload.
3. Disk is ~full (max 3,019,571,208 B; available ≈ 495,000 B). Free space before
   the real upload if the web-tool "manage effects" (uninstall) is used.

## Local effect file (confirmed)
`files/XXTRVL_g3xn.ZD2` — 8017 B, magic ZDLF, group 0x02 (FILTER),
id 0x02001010, name "Traveler". Upload target name: `XXTRVL.ZD2` (12-char limit).