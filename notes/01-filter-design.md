# Traveler Filter — DSP Design

## What it is
A 2-pole resonant low-pass biquad (the MS20 / Keio Traveler F-1 VCF character)
with an expression-pedal-controlled cutoff sweep and an optional internal LFO
that adds the classic "traveler" wobble to the cutoff.

## Control model (manifest knobs)
| Knob | Range | Maps to |
|------|-------|---------|
| Cutoff | 0..100 | base cutoff frequency (log scale 60 Hz .. 8 kHz) |
| Res    | 0..100 | resonance Q (0.5 .. ~18, the peaky MS20 sound) |
| Sweep  | 0..100 | LFO depth in Hz (0 = no wobble, 100 = ±2500 Hz) |
| Rate   | 0..100 | LFO rate 0.05 .. 8 Hz |

The EXPRESSION PEDAL is the G3Xn's global expression input. In a patch it is
assigned to a knob (typically Cutoff) via the pedal's assignment screen — the
effect just reads the knob value. So the expression pedal sweeps the cutoff,
which is exactly the AX1500G Traveler behavior.

## The biquad (RBJ / classic resonant LP)
    w0    = 2*pi*fc/fs
    cw    = cos(w0)
    alpha = sin(w0)/(2*Q)
    b0=(1-cw)/2 ; b1=1-cw ; b2=(1-cw)/2
    a0=1+alpha  ; a1=-2*cw ; a2=1-alpha
    y = (b0/a0)x0 + (b1/a0)x1 + (b2/a0)x2 - (a1/a0)y1 - (a2/a0)y2

Unconditionally stable for Q < ~100 at 44.1 kHz. Resonant peak gain = Q
(Q=5 -> 5x peak at cutoff), which is the MS20 "peaky" character.

## C6000 constraints (no divide, no cos/sin, no calls)
The kernel recomputes the 5 biquad coefficients EVERY BLOCK (16 samples) from
the smoothed cutoff, using:
  * A 6-term Taylor series for cos(w0) and sin(w0) (w0 = 2*pi*fc/fs, fc in
    [60,8000] -> w0 in [0.0085, 1.135 rad], so the series converges fast and
    is accurate to ~1e-4).
  * Reciprocal Newton iteration (2 steps) instead of divide:
        r = 1.0/a0;  r = r*(2.0 - a0*r)  (2x)
  * Per-sample one-pole smoothing of the cutoff (tau ~ 8 ms) to kill zipper.

State (per instance, in instance[2], 32 bytes):
  [0] x1_L  [1] x2_L  [2] y1_L  [3] y2_L   (channel A biquad state)
  [4] x1_R  [5] x2_R  [6] y1_R  [7] y2_R   (channel B biquad state)
  [8] fc_smooth (Hz)
  [9] lfo_phase (radians)
  word 4 (bytes 16-19) = the guard word (SH_STATE_GUARD)

## Why per-block coefficient recompute is fine
The cutoff is smoothed per-sample, so the coefficients change by a tiny amount
each block. Updating 5 coefficients per block (16 samples) is zipper-free — the
same smoothing trick the gain effect uses for its level knob. Verified in the
Python prototype: the magnitude response is a smooth curve as cutoff sweeps
(the only "bump" is the resonant peak passing through, which is the desired
effect).

## DSP load
A biquad per channel = ~8 MACs/sample + the per-block coefficient math (amortized
to ~0.5 MACs/sample). Total well under a stock filter's budget. Declare dspload
~14 (a stock 2-pole filter declares ~10-15).

## Reference prototype
tools/prototype_ms20.py — exact-math version used to validate the response,
resonance, and stability. The C kernel is a fixed-point-safe port of this.