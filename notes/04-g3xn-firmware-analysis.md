# G3Xn Firmware / Effect Analysis (2026-11-23)

## Can we get the G3Xn firmware image?
- Zoom's firmware download page is gated (502 / login). No G3Xn firmware image
  (.zup/.bin) is in any public repo.
- The g3xn tool (cwoodard1121) does NOT dump firmware — it dumps PATCHES
  (.zptc) and EFFECT FILES (.ZD2).
- So a full firmware disassembly (Ghidra) is not directly possible without
  obtaining the .zup. BUT the effect-level analysis is already done for us.

## What we CAN analyse (and did): the effect catalog
The g3xn tool's `g3xn/data/effects.json` is the 162-effect catalog extracted
directly from the G3Xn's own .ZD2 files (names, descriptions, knob ranges,
defaults, DSP cost, chain positions). This is the authoritative G3Xn effect
database. Saved at /tmp/g3xn_effects.json (copy into the repo).

## G3Xn effect group bytes (the browser categories)
This is the KEY difference from the MS Plus. The top byte of the effect id =
the category. G3Xn mapping:
    0x01 DYNAMICS (10)   0x02 FILTER (14)     0x03 DRIVE (24)
    0x04 AMP (16)        0x05 CABINET (16)    0x06 MODULATION (23)
    0x07 SFX (4)         0x08 DELAY (17)      0x09 REVERB (15)
    0x0b PEDAL (18)      0x1e RHYTHM (1)      0x1f LOOPER (4)

CONTRAST with the MS Plus (from stomphacks effect-ids.md): there 0x07 = SFX and
the filter group is a DIFFERENT number. So an effect that is "SFX" on the MS
Plus is "FILTER" on the G3Xn under a different byte. THIS is the per-display
difference the user was asking about.

### Implication for our Traveler filter
Our effect is a low-pass FILTER. On the G3Xn it belongs in group 0x02 (FILTER),
NOT 0x07 (which is SFX on the G3Xn). So the G3Xn-ready file needs:
    id = 0x02 << 24 | low16
The closest stock G3Xn filter effects (our design references):
    0x020000a0  LowPassFL  (LOWPASSF.ZD2)  FREQ/Sense/RESO/BAL   dsp=20.3
    0x02000020  Resonance  (RESONANC.ZD2)  Mode/Sense/RESO/VOL   dsp=19.89
    0x020000d0  LFO FLTR   (LFO_FLTR.ZD2)  Depth/Rate/RESO/Wave  dsp=21.53
Our 4-knob design (Cutoff/Res/Sweep/Rate) is a superset of these — it matches
the G3Xn filter idiom exactly.

## G3Xn DSP budget
    DSP_BUDGET = 250.0   (ToneLib "DSP %" = raw/2.5, so 250 = 100%)
    DSP_PROVEN = 231.3   (highest sum actually proven to load)
    MAX_POSITIONS = 7    (chain positions)
CONTRAST: MS Plus budget = 270. So the G3Xn has a SMALLER budget. Our effect
declares dspload 14 (5.6% of 250) — comfortably within range (stock filters
are 12.7-28.5).

## "Two-screen" / "3-window" effects (the user's Q1)
The g3xn catalog has a `slots` field = number of chain positions an effect
occupies. 33 effects have slots=2 ("two-screen effects take two" positions).
Examples: BG MK1/MK3, FD TWNR, Dual DLY, Duo Phase, EG FLTR, Gt GEQ, HoldVerb...
This is almost certainly what the user means by "3-window" / display-dependent
effects: on the G3Xn's multi-effect display, some effects span two windows and
consume two of the 7 chain positions. Our Traveler is a single-position effect
(slots=1), so it's unaffected — but it's a real per-pedal difference to be
aware of when building patches.

## Summary of G3Xn vs MS Plus differences (for the effect)
| Property        | MS Plus (stomphacks) | G3Xn (g3xn catalog) |
|-----------------|----------------------|---------------------|
| DSP budget      | 270                  | 250                 |
| Filter group    | (different byte)     | 0x02                |
| SFX group       | 0x07                 | 0x07 (only 4 fx)    |
| Chain positions | (n/a)                | 7 (two-screen=2)    |
| MIDI port prefix| "ZOOM MS Plus Series"| "ZOOM G"            |
| File cmds       | its own 60 xx        | 60 25/26/20/22/05/21/27/09 |
| Target bit      | 0x0090               | (verify from stock ZD2) |

## Bottom line
- The effect SOUND (biquad) is portable.
- The G3Xn-ready file needs: group byte 0x02 (FILTER), correct target bit,
  dspload tuned to the 250 budget (ours is fine).
- The upload path needs the G3Xn file-WRITE command (not yet known; the g3xn
  tool is read-only for files).