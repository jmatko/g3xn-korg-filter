#!/usr/bin/env python3
"""
Traveler filter - final reference prototype.

Models the Korg AX1500G "Traveler" LPF (a Keio Traveler F-1 / MS20-style
resonant low-pass with a sweeping cutoff).

Control model (matching the AX1500G Traveler expression effect):
  * EXPRESSION PEDAL  -> base cutoff (the main "travel" sweep)
  * CUTOFF knob       -> where in the sweep range the base sits
  * RES knob          -> resonance (Q)
  * LFO (internal)    -> optional wobble added to the cutoff (the classic
                         "traveler" self-oscillating sweep). Depth + rate knobs.

The filter is a 2-pole resonant low-pass biquad (the MS20 VCF character).
Coefficients are recomputed every block (16 samples) from the smoothed
cutoff. The kernel (C6000) cannot divide or call cos/sin, so the C kernel
uses a polynomial approximation for the biquad coefficients; this Python
version uses the exact math to define the target behavior.

Coefficient update strategy:
  - The biquad coefficients change as the cutoff sweeps. Updating all 5
    coefficients every block (16 samples) with a smoothly-changing cutoff is
    zipper-free because the cutoff itself is smoothed (one-pole). This is the
    same trick the gain effect uses for its level knob.
"""
import math

fs = 44100.0
BLOCK = 16

def biquad_lp(fc, Q):
    fc = min(max(fc, 40.0), 10000.0)
    Q  = min(max(Q, 0.4), 18.0)
    w0 = 2.0*math.pi*fc/fs
    cw = math.cos(w0); sw = math.sin(w0)
    alpha = sw/(2.0*Q)
    b0=(1-cw)/2; b1=1-cw; b2=(1-cw)/2
    a0=1+alpha; a1=-2*cw; a2=1-alpha
    return (b0/a0, b1/a0, b2/a0, a1/a0, a2/a0)

class Traveler:
    def __init__(self):
        # per-channel biquad state (stereo: L and R independent)
        self.st = [[0,0,0,0] for _ in range(2)]
        self.fc_smooth = 800.0
        self.lfo_phase = 0.0
        self.coef = biquad_lp(800.0, 1.0)
    def process_block(self, block, base_cut, Q, lfo_depth, lfo_rate):
        # block: list of 32 floats (16 L + 16 R)
        out = [0.0]*32
        # update smoothed cutoff + LFO once per block
        target = base_cut
        self.lfo_phase += (2*math.pi*lfo_rate/fs)*BLOCK
        target += lfo_depth*math.sin(self.lfo_phase)
        # one-pole smooth the cutoff (tau ~ 10ms)
        self.fc_smooth += (1 - math.exp(-BLOCK/(0.010*fs)))*(target - self.fc_smooth)
        self.coef = biquad_lp(self.fc_smooth, Q)
        b0,b1,b2,a1,a2 = self.coef
        for ch in range(2):
            s = self.st[ch]
            # state s = [x1, x2, y1, y2]
            for i in range(16):
                x = block[ch*16 + i]
                y = b0*x + b1*s[0] + b2*s[1] - a1*s[2] - a2*s[3]
                s[1]=s[0]; s[0]=x   # x2=x1, x1=x
                s[3]=s[2]; s[2]=y   # y2=y1, y1=y
                out[ch*16+i]=y
            self.st[ch]=s
        return out

def demo():
    t = Traveler()
    print("=== 2-second expression sweep (cutoff 200 -> 6000 -> 200 Hz), Q=4, LFO on ===")
    import random; random.seed(3)
    nsec=2
    nb = int(fs*nsec/BLOCK)
    # feed a guitar-ish broadband signal (sawtooth 110 Hz + harmonics)
    peaks=[]
    for b in range(nb):
        tsec = b*BLOCK/fs
        block=[0.0]*32
        for i in range(16):
            tt = tsec + i/fs
            x = 0.5*math.sin(2*math.pi*110*tt) + 0.25*math.sin(2*math.pi*220*tt) + 0.12*math.sin(2*math.pi*330*tt)
            block[i]=x; block[16+i]=x
        # expression pedal: slow triangle sweep
        expr = 0.5 - 0.5*math.cos(2*math.pi*0.5*tsec)   # 0..1..0 over 2s
        base = 200 + expr*(6000-200)
        out = t.process_block(block, base, 4.0, lfo_depth=300, lfo_rate=0.7)
        peaks.append(max(abs(v) for v in out))
    print(f"  output peak over 2s: {max(peaks):.3f}  (input peak ~0.87)")
    print(f"  (resonant peaks should appear as the cutoff sweeps over the harmonics)")

def zip_test():
    """Check for zipper noise: rapidly sweep cutoff, measure output smoothness."""
    t=Traveler()
    prev=None; jumps=0
    for b in range(int(fs/BLOCK)):  # 1 second
        block=[math.sin(2*math.pi*200*b*BLOCK/fs) for _ in range(32)]
        base = 200 + 5800*(0.5+0.5*math.sin(2*math.pi*5*b*BLOCK/fs))  # fast 5Hz sweep
        out=t.process_block(block, base, 6.0, 0, 0)
        for v in out:
            if prev is not None and abs(v-prev)>0.5: jumps+=1
            prev=v
    print(f"=== Zipper test (fast 5Hz cutoff sweep, Q=6): {jumps} big jumps (want ~0) ===")

if __name__=="__main__":
    demo()
    zip_test()