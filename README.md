# Zoom G3Xn "Traveler" Filter — Custom ZD2 Effect

A custom ZD2 effect for the **Zoom G3Xn** that emulates the **Korg AX1500G
"Traveler"** low-pass filter (an emulation of the Keio Traveler F-1, the same
LFO/filter engine Korg used in the MS20 / Polysix era). The cutoff is
expression-pedal controllable, with resonance and an LFO "sweep."

Built with the [thammer/stomphacks](https://github.com/thammer/stomphacks)
clean-room toolchain (manifest + C kernel → ZD2 + ZIC). The DSP is a 2-pole
resonant low-pass biquad (MS20 VCF character) with an optional LFO wobble.

> **Status:** the effect *sound* is built and validated. The G3Xn *install*
> path is not yet proven — see [notes/03-g3xn-compatibility.md](notes/03-g3xn-compatibility.md)
> and [notes/02-upload-handoff.md](notes/02-upload-handoff.md). The target bit
> and upload command need to be confirmed against a real G3Xn.

## The effect (4 knobs)

| Knob   | Range  | Maps to |
|--------|--------|---------|
| Cutoff | 0..100 | base cutoff 60 Hz .. 8 kHz (log). **Assign the expression pedal here.** |
| Res    | 0..100 | resonance Q 0.5 .. 18 (the peaky MS20 sound) |
| Sweep  | 0..100 | LFO depth 0 .. ±2500 Hz (the "traveler" wobble) |
| Rate   | 0..100 | LFO rate 0.05 .. 8 Hz |

## Repository layout

```
effect/     traveler.c (the C6000 kernel) + manifest.msplus.json + manifest.g3xn.json
files/      built .ZD2/.ZIC deliverables (G3Xn + MS Plus)
tools/      set_target.py, g3xn_inspect.py, prototype_ms20.py
notes/      design + G3Xn compatibility + upload handoff + G3Xn effect catalog
build.sh    builds both variants into files/
```

## Quick start (Linux / Crostini)

### 1. Get the toolchain
```bash
git clone https://github.com/thammer/stomphacks stomphacks
cd stomphacks
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. Get the TI C6000 compiler
The build needs the TI C6000 Code Generation Tools. On Linux an i386 build
works (v7.2.11 or 8.5.0). Set `ZOOM_TI_CGT` to the directory containing
`bin/cl6x` and `include/`.
```bash
export ZOOM_TI_CGT=/path/to/ti-cgt-c6000
```
(If you don't have it, the working copy used for this project is an i386
v7.2.11 build. Ask the original author, or install the TI C6000 CGT for Linux.)

### 3. Build
```bash
./build.sh
```
This produces `files/g3xn/XXTRVL.ZD2` (G3Xn, retargeted to PEDAL group 0x0b)
and `files/msplus/XXTRVL.ZD2` (MS Plus).

## Inspecting a real G3Xn (to confirm the target bit)

Before uploading, confirm the G3Xn's expected target bit + group byte by
dumping a stock filter effect (read-only, safe):
```bash
pip install mido
python3 tools/g3xn_inspect.py LOWPASSF.ZD2     # dump+inspect one stock filter
python3 tools/g3xn_inspect.py --save dump/     # dump all 162 .ZD2 files
```
Match our file's target bit + group byte to what the stock files show, then
rebuild/re-`set_target.py` as needed.

## Uploading to the G3Xn (collaborator's task)

The G3Xn file-WRITE SysEx command is **not yet known** (the g3xn tool is
read-only for files). See [notes/02-upload-handoff.md](notes/02-upload-handoff.md)
for the full handoff, including the safe MS Plus install tools (stomphacks
`tools-pedal/pedal_diy.py`) and the G3Xn protocol reference
([cwoodard1121/zoom-g3xn-agent-skill](https://github.com/cwoodard1121/zoom-g3xn-agent-skill)).

**⚠️ SAFETY:** a broken effect saved into a patch can permanently brick the
pedal. Read [stomphacks/SAFETY.md](https://github.com/thammer/stomphacks/blob/main/SAFETY.md)
and `notes/02-upload-handoff.md` before any write. Autosave must be OFF.

## Key G3Xn vs MS Plus differences (summary)

| Property        | MS Plus | G3Xn |
|-----------------|---------|------|
| DSP budget      | 270     | 250  |
| Filter group byte | (different) | 0x02 |
| Chain positions | —       | 7 (two-screen effects take 2) |
| MIDI port prefix| "ZOOM MS Plus Series" | "ZOOM G" |
| File cmds       | its own | 60 25/26/20/22/05/21/27/09 |

Full detail in [notes/04-g3xn-firmware-analysis.md](notes/04-g3xn-firmware-analysis.md).

## Notes

- `notes/00-overview.md` — project overview + progress log
- `notes/01-filter-design.md` — the DSP design (biquad + LFO)
- `notes/02-upload-handoff.md` — upload tooling handoff
- `notes/03-g3xn-compatibility.md` — G3Xn compatibility research
- `notes/04-g3xn-firmware-analysis.md` — G3Xn effect catalog analysis
- `notes/g3xn_effects_catalog.json` — the 162-effect G3Xn catalog (from the g3xn tool)

## License
The effect source (traveler.c) is clean-room, written for this project. The
toolchain is thammer/stomphacks (see its LICENSE). The G3Xn protocol reference
is cwoodard1121/zoom-g3xn-agent-skill (MIT).