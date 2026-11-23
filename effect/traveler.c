/* effects/traveler/traveler.c - the Traveler low-pass filter.
 *
 * A 2-pole resonant low-pass biquad that emulates the Korg AX1500G "Traveler"
 * expression effect (a Keio Traveler F-1 / MS20-style VCF). The expression
 * pedal sweeps the cutoff (assign it to the Cutoff knob); an optional internal
 * LFO adds the classic "traveler" wobble.
 *
 * The math is a clean-room port of the standard resonant low-pass biquad
 * (see tools/prototype_ms20.py for the exact-math reference used to validate
 * the response, resonance and stability). No Zoom code is involved.
 *
 * C6000 SAFE-DSP rules honoured (docs/building-effects.md):
 *   - leaf function: no calls, no stack, no callee-saved registers
 *   - no divide: the 1/a0 normalisation uses a hardware reciprocal + Newton
 *   - no stdlib math: cos/sin of the (small) cutoff angle use Taylor series;
 *     the log cutoff mapping uses a polynomial
 *   - per-instance state lives in instance[2] (state_bytes = 32)
 *   - guard prologue + output clamp are mandatory (real pedal crashes)
 *
 * The 5 biquad coefficients are recomputed every block (16 samples) from the
 * smoothed cutoff. The cutoff is one-pole smoothed per sample (tau ~ 8 ms), so
 * the coefficients change by a tiny amount each block and the sweep is
 * zipper-free (the same smoothing trick the gain effect uses for level).
 */

#include <stdint.h>
#include "sh_params.h"   /* generated into build/ from manifest.json */

/* C6000 hardware reciprocal intrinsic (emits RCPSP.S1, a hardware
 * instruction). Returns ~1/x with a few bits of error; the caller refines it
 * with Newton steps. Using the intrinsic avoids the __c6xabi_divf runtime
 * call, which the self-contained blob does not link. */
extern float _rcpsp(float);
#define frcip _rcpsp

/* ---- tuning constants --------------------------------------------------- */
#define FC_MIN     60.0f      /* lowest cutoff (Hz)   */
#define FC_MAX     8000.0f    /* highest cutoff (Hz)  */
#define Q_MIN      0.5f       /* lowest resonance     */
#define Q_MAX      18.0f      /* highest resonance (still stable at 44.1k)  */
#define SWEEP_MAX  2500.0f    /* max LFO depth (Hz)   */
#define RATE_MIN   0.05f      /* min LFO rate (Hz)    */
#define RATE_MAX   8.0f       /* max LFO rate (Hz)    */

#define TWO_PI     6.2831853f
#define TWO_PI_FS  0.14247586f   /* 2*pi/44100 : w0 = this * fc */
#define FC_SMOOTH  0.018f        /* one-pole cutoff smoothing (tau ~ 8 ms) */
#define INV2       0.5f
#define INV6       0.16666667f
#define INV24      0.041666667f
#define INV120     0.008333333f
#define INV5040    0.00019841270f
#define INV720     0.0013888889f
#define BLOCK_FS   0.000362812f   /* 16/44100 : LFO phase step per block */

/* state layout in instance[2] (32 bytes = 8 floats):
 *   [0] x1_L  [1] x2_L  [2] y1_L  [3] y2_L   channel A biquad state
 *   [4] x1_R  [5] x2_R  [6] y1_R  [7] y2_R   channel B biquad state
 *   [8] fc_smooth (Hz)
 *   [9] lfo_phase (radians)
 *   word 4 (bytes 16..19) = SH_STATE_GUARD (set by init)
 */

void SH_AUDIO_FN(void **instance, void **ctx)
{
    const float *coef = (const float *)instance[1];
    float *eff   = (float *)ctx[1];
    float *state = (float *)instance[2];
    int i;

    /* ---- mandatory guard prologue -------------------------------------- */
    unsigned ok = 1;
#ifdef SH_STATE_GUARD
    if (((const uint32_t *)instance[2])[SH_STATE_GUARD_WORD] != SH_STATE_GUARD)
        ok = 0;
#endif
    float fade  = coef[SH_COEFF_BYPASS];
    float tCut  = coef[SH_PARAM_CUTOFF];
    float tRes  = coef[SH_PARAM_RES];
    float tSwp  = coef[SH_PARAM_SWEEP];
    float tRate = coef[SH_PARAM_RATE];
    if (!(fade  >= 0.0f && fade  <= 1.0f)) ok = 0;
    if (!(tCut  >= 0.0f && tCut  <= 1.0f)) ok = 0;
    if (!(tRes  >= 0.0f && tRes  <= 1.0f)) ok = 0;
    if (!(tSwp  >= 0.0f && tSwp  <= 1.0f)) ok = 0;
    if (!(tRate >= 0.0f && tRate <= 1.0f)) ok = 0;

    if (!ok) {
        for (i = 0; i < SH_FRAMES; i++) {
            eff[i]                  = 0.0f;
            eff[i + SH_CH_B_OFFSET] = 0.0f;
        }
        return;
    }

    /* ---- read state ----------------------------------------------------- */
    float x1L = state[0], x2L = state[1], y1L = state[2], y2L = state[3];
    float x1R = state[4], x2R = state[5], y1R = state[6], y2R = state[7];
    float fc  = state[8];
    float ph  = state[9];
    if (!(fc >= 0.0f && fc < 1e6f)) fc = 1000.0f;   /* fail safe */
    if (ph < 0.0f || ph > TWO_PI)   ph = 0.0f;

    /* ---- map knobs to physical values ---------------------------------- */
    /* log cutoff: fc = FC_MIN * (FC_MAX/FC_MIN)^cut  (60 .. 8000 Hz) */
    float u  = tCut * 4.8837755f;        /* cut * ln(8000/60) */
    float u2 = u * u;
    float expu = 1.0f + u
               + u2 * 2.3850746f
               + u2 * u   * 0.3872120f
               + u2 * u2  * 0.0471945f
               + u2 * u2 * u * 0.0045902f;
    float base = FC_MIN * expu;

    float Q    = Q_MIN  + tRes  * (Q_MAX - Q_MIN);
    float swp  = tSwp   * SWEEP_MAX;
    float rate = RATE_MIN + tRate * (RATE_MAX - RATE_MIN);

    /* ---- advance LFO + smooth the cutoff (per block) -------------------- */
    ph += TWO_PI * rate * BLOCK_FS;
    if (ph >= TWO_PI) ph -= TWO_PI;
    /* sin(ph) via 7-term Taylor (ph in [0, 2*pi); ~1e-3 accuracy, enough for
     * a wobble that only nudges the cutoff). */
    float s1 = ph, s2 = s1*s1, s3 = s2*s1, s5 = s3*s2, s7 = s5*s2;
    float lfo = s1 - s3*INV6 + s5*INV120 - s7*INV5040;
    float target = base + swp * lfo;
    if (target < FC_MIN)  target = FC_MIN;
    if (target > FC_MAX)  target = FC_MAX;
    fc += FC_SMOOTH * (target - fc);
    if (fc < 20.0f)     fc = 20.0f;
    if (fc > 11000.0f)  fc = 11000.0f;

    /* ---- biquad coefficients from (fc, Q) ------------------------------- */
    float w0 = TWO_PI_FS * fc;            /* w0 in [0.0028, 1.565] rad */
    float w2 = w0*w0, w3 = w2*w0, w4 = w2*w2, w5 = w4*w0, w6 = w4*w2;
    float cw = 1.0f - w2*INV2 + w4*INV24 - w6*INV720;
    float sw = w0 - w3*INV6 + w5*INV120 - w6*w0*INV5040;
    if (sw < 0.0f) sw = 0.0f;             /* w0 >= 0 -> sin >= 0 */
    float alpha = sw * INV2 * frcip(Q);   /* = sin(w0)/(2Q); 1/Q by FRCIP */

    float b0 = 0.5f * (1.0f - cw);
    float b1 = 1.0f - cw;
    float b2 = b0;                    /* b2 == b0 for this LP biquad */
    float a0 = 1.0f + alpha;
    float a1 = -2.0f * cw;
    float a2 = 1.0f - alpha;

    /* 1/a0 by hardware FRCIP + 2 Newton steps (no divide). */
    float r = frcip(a0);
    r = r * (2.0f - a0 * r);
    r = r * (2.0f - a0 * r);
    b0 *= r; b1 *= r; a1 *= r; a2 *= r;   /* a0 normalised to 1 */

    /* ---- per-sample filter, both channels -------------------------------- */
    for (i = 0; i < SH_FRAMES; i++) {
        float a = eff[i];
        float b = eff[i + SH_CH_B_OFFSET];

        /* channel A */
        float ya = b0*a + b1*x1L + b2*x2L - a1*y1L - a2*y2L;
        x2L = x1L; x1L = a; y2L = y1L; y1L = ya;
        /* channel B */
        float yb = b0*b + b1*x1R + b2*x2R - a1*y1R - a2*y2R;
        x2R = x1R; x1R = b; y2R = y1R; y1R = yb;

        /* bypass crossfade: dry*(1-fade) + wet*fade */
        a = a*(1.0f - fade) + ya*fade;
        b = b*(1.0f - fade) + yb*fade;

        /* mandatory output clamp (scrubs NaN/Inf/garbage) */
        if (!(a > -8.0f && a < 8.0f)) a = 0.0f;
        if (!(b > -8.0f && b < 8.0f)) b = 0.0f;

        eff[i]                  = a;
        eff[i + SH_CH_B_OFFSET] = b;
    }

    /* ---- write state back ----------------------------------------------- */
    state[0] = x1L; state[1] = x2L; state[2] = y1L; state[3] = y2L;
    state[4] = x1R; state[5] = x2R; state[6] = y1R; state[7] = y2R;
    state[8] = fc;
    state[9] = ph;
}
