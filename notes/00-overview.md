# ZD2 Traveler Filter Project — Overview & Progress Log

## Goal
Build a custom ZD2 effect for the Zoom G3Xn that emulates the Korg AX1500G
"Traveler" low-pass filter (an emulation of the Keio Traveler F-1, the same
LFO/filter engine Korg used in the MS20 / Polysix era), controllable by the
expression pedal.

## Status — ALL STEPS DONE
- [x] Research: cloned stomphacks, read ZD2 format/ABI/build docs.
- [x] Set up TI C6000 toolchain on Linux (v7.2.11 i386 build at build/ti-cgt-c6000/).
- [x] Verified the reference gain effect builds end-to-end.
- [x] Derived MS20-style Traveler filter math (2-pole resonant LP biquad + LFO sweep).
- [x] Validated the DSP in Python (tools/prototype_ms20.py): stable, correct resonance, smooth sweep.
- [x] Wrote traveler.c kernel + manifest.json.
- [x] Built XXTRVL.ZD2 + XXTRVL.ZIC — REPORT.md passes ALL checks, no failures.
- [x] Made a G3Xn-targeted copy (target 0x91) via tools/set_target.py.
- [x] Wrote upload tooling handoff notes (notes/02-upload-handoff.md).

## Deliverables
- `stomphacks/effects/traveler/traveler.c` — the kernel (clean-room, SAFE-DSP).
- `stomphacks/effects/traveler/manifest.json` — identity + 4 knobs.
- `files/XXTRVL_g3xn.ZD2` — G3Xn-targeted effect (target 0x91), CRC valid.
- `files/XXTRVL_msplus.ZD2` — MS Plus-targeted effect (target 0x90).
- `files/XXTRVL.ZIC` — companion icon.
- `tools/set_target.py` — sets the ZD2 target bitfield + recomputes CRC.
- `tools/prototype_ms20.py` — exact-math reference for the filter.
- `notes/01-filter-design.md` — the DSP design.
- `notes/02-upload-handoff.md` — for the upload collaborator.

## Key technical findings
- The ZD2 format + ABI are fully documented by thammer/stomphacks (clean-room
  build pipeline: manifest + C kernel -> ZD2 + ZIC, no stock Zoom code).
- The C6000 kernel cannot divide or call libm. Solutions used:
  * `_rcpsp()` intrinsic -> hardware RCPSP instruction (no divf call).
  * Taylor series for cos/sin of the cutoff angle (w0 < 1.57 rad).
  * Polynomial for the log cutoff mapping.
- The kernel is register-heavy, so it uses `kernel_section: text` +
  `allow_stack: true` (the documented escape hatch; stock reverbs do this).
- G3Xn uses the ZD2 container (G-series bit 0x0001). NOT yet verified that the
  G3Xn loads DIY ZD2 effects (stomphacks was tested on MS-70CDR+). This is the
  main open risk for the upload collaborator.

## The effect (4 knobs)
| Knob | Range | Maps to |
|------|-------|---------|
| Cutoff | 0..100 | base cutoff 60 Hz .. 8 kHz (log). Assign the expression pedal here. |
| Res    | 0..100 | resonance Q 0.5 .. 18 (the peaky MS20 sound) |
| Sweep  | 0..100 | LFO depth 0 .. ±2500 Hz (the "traveler" wobble) |
| Rate   | 0..100 | LFO rate 0.05 .. 8 Hz |

## Working directory layout
```
/home/user/zd2-project/
  notes/            progress log + design + handoff notes
  files/            final .ZD2/.ZIC deliverables
  tools/            set_target.py, prototype_ms20.py, zipcheck.py, respcheck.py
  build/ti-cgt-c6000/   the Linux TI C6000 compiler (bin/ + include/)
  stomphacks/       the cloned build toolchain + effects/traveler/ source
```