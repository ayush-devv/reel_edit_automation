"""Procedural SFX we synthesise ourselves (fully owned, no licence): ffmpeg lavfi graphs — seeded noise
(`anoisesrc`), sample-exact tone/envelope expressions (`aevalsrc`), a time-varying band-pass
(`afftfilt` driven by the frame time) for whooshes and risers, saturation and short echoes for
weight and space. ffmpeg renders float32; numpy peak-normalises to −1 dBFS and adds a 10 ms
de-click tail; soundfile writes 48 kHz / 24-bit WAV with a fixed header — so the same ffmpeg
build re-creates byte-identical files (fixed seeds, single-threaded filtering).

Each recipe is `<category>_<variant>` so `library.sfx_category` files it under that category.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reel import config

SR = 48_000
PEAK_DBFS = -1.0
TAIL_FADE_S = 0.010


# ------------------------------------------------------------------ expression helpers (ffmpeg eval syntax)


def _env(t0: float, att: float, dec: float) -> str:
    """Attack/decay envelope starting at t0: (1 − e^(−x/att)) · e^(−x/dec), 0 before t0.
    x is clamped at 0 so exp() never overflows before the onset (inf · 0 = NaN)."""
    x = f"max(0,t-{t0})"
    return f"gte(t,{t0})*(1-exp(-{x}/{att}))*exp(-{x}/{dec})"


def _glide(f0: float, f1: float, tau: float, t0: float = 0.0) -> str:
    """Phase of a tone gliding exponentially from f0 to f1 (time constant tau), starting at t0."""
    x = f"max(0,t-{t0})"
    return f"2*PI*({f1}*{x}+({f0 - f1})*{tau}*(1-exp(-{x}/{tau})))"


def _sweep_phase(f0: float, ratio: float, dur: float) -> str:
    """Phase of an exponential sweep f0 → f0·ratio over dur."""
    return f"2*PI*{f0}*{dur}/log({ratio})*(pow({ratio},t/{dur})-1)"


def _hash(n: str, seed: float) -> str:
    """Deterministic pseudo-random 0..1 from an integer expression (classic sin hash)."""
    v = f"sin(({n})*12.9898+{seed})*43758.5453"
    return f"({v}-floor({v}))"


def _partials(parts: list[tuple[float, float, float]], t0: float, att: float = 0.002, detune: float = 1.0) -> str:
    """Sum of decaying sine partials (freq, amp, decay) starting at t0."""
    return "+".join(f"{a}*sin(2*PI*{f * detune:.3f}*(t-{t0}))*{_env(t0, att, d)}" for f, a, d in parts)


# ------------------------------------------------------------------ graph builder


class _Graph:
    def __init__(self, dur: float):
        self.d = dur
        self.parts: list[str] = []
        self.n = 0

    def add(self, spec: str, *inputs: str) -> str:
        self.n += 1
        label = f"n{self.n}"
        self.parts.append("".join(f"[{i}]" for i in inputs) + spec + f"[{label}]")
        return label

    def noise(self, color: str, seed: int, filters: str = "") -> str:
        """Decorrelated stereo noise (two seeds), optionally filtered."""
        chans = []
        for s in (seed, seed + 1):
            src = f"anoisesrc=d={self.d}:c={color}:r={SR}:a=0.8:s={s}"
            chans.append(self.add(src + (f",{filters}" if filters else "")))
        return self.add("join=inputs=2:channel_layout=stereo", *chans)

    def expr(self, left: str, right: str | None = None) -> str:
        return self.add(f"aevalsrc=exprs='{left}|{right or left}':s={SR}:d={self.d}")

    def mul(self, a: str, b: str) -> str:
        return self.add("amultiply", a, b)

    def fx(self, a: str, filters: str) -> str:
        return self.add(filters, a)

    def mix(self, *pairs: tuple[str, float]) -> str:
        if len(pairs) == 1:
            label, w = pairs[0]
            return self.add(f"volume={w}", label)
        weights = " ".join(str(w) for _, w in pairs)
        return self.add(f"amix=inputs={len(pairs)}:normalize=0:duration=longest:weights='{weights}'", *(p for p, _ in pairs))

    def render(self, out: str) -> str:
        return ";".join(self.parts + [f"[{out}]aformat=sample_fmts=flt:channel_layouts=stereo[out]"])


def _band(fc: str, width: float) -> str:
    """afftfilt band-pass, Gaussian in log-frequency around fc (an expression of T = seconds)."""
    fc_t = fc.replace("T", "(pts/sr)")
    gain = f"exp(-pow(log((b+1)*sr/(2*nb)/({fc_t})),2)/{2 * width * width:.4f})"
    return f"afftfilt=real='re*{gain}':imag='im*{gain}':win_size=1024:overlap=0.75"


def _bell(var: str, dur: float, peak: float, w_in: float, w_out: float) -> str:
    """Asymmetric bell 0..1 peaking at `peak` (fraction of dur)."""
    x = f"({var}/{dur})"
    return f"exp(-pow(({x}-{peak})/if(lt({x},{peak}),{w_in},{w_out}),2))"


# ------------------------------------------------------------------ recipes


def whoosh(dur: float, *, color: str = "pink", lo: float = 300, hi: float = 3000, peak: float = 0.6, w_in: float = 0.28,
           w_out: float = 0.18, width: float = 0.55, pan: tuple[float, float] = (0.2, 0.8), seed: int = 11, body: float = 0.0) -> str:
    g = _Graph(dur)
    shape_f = _bell("T", dur, peak, w_in * 1.2, w_out * 1.2)
    band = g.fx(g.noise(color, seed, "highpass=f=60"), _band(f"{lo}*pow({hi / lo},{shape_f})", width))
    amp = _bell("t", dur, peak, w_in, w_out)
    p = f"({pan[0]}+{pan[1] - pan[0]}*t/{dur})"
    sig = g.mul(band, g.expr(f"{amp}*sqrt(1-{p})", f"{amp}*sqrt({p})"))
    if body:
        low = g.mul(g.noise("brown", seed + 7, "lowpass=f=260,highpass=f=40"), g.expr(amp))
        sig = g.mix((sig, 1.0), (low, body))
    return g.render(sig)


def riser(dur: float, *, f0: float = 110, octaves: float = 2.0, tonal: float = 0.6, noise: float = 1.0, trem: tuple[float, float] = (4, 14),
          lo: float = 300, hi: float = 9000, seed: int = 21, cymbal: bool = False) -> str:
    g = _Graph(dur)
    rise = f"pow(t/{dur},2.2)"
    layers: list[tuple[str, float]] = []
    if cymbal:
        n = g.noise("white", seed, "highpass=f=3500,lowpass=f=15000")
        layers.append((g.mul(n, g.expr(f"pow(t/{dur},3.2)")), noise))
    else:
        n = g.fx(g.noise("white", seed, "highpass=f=80"), _band(f"{lo}*pow({hi / lo},pow(T/{dur},1.4))", 0.8))
        layers.append((g.mul(n, g.expr(rise)), noise))
    if tonal:
        r = 2 ** octaves
        a, b = trem
        tr = f"(0.72+0.28*sin(2*PI*({a}*t+{(b - a) / (2 * dur):.4f}*t*t)))"
        saw = lambda det: "+".join(f"sin({k}*{_sweep_phase(f0 * det, r, dur)})/{k}" for k in range(1, 7))  # noqa: E731
        layers.append((g.expr(f"{rise}*{tr}*({saw(1.0)})", f"{rise}*{tr}*({saw(1.004)})"), tonal * 0.5))
    return g.render(g.fx(g.mix(*layers), "lowpass=f=14000"))


def boom(dur: float, *, f0: float = 90, f1: float = 34, pitch_tau: float = 0.35, amp_tau: float = 0.6, noise: float = 0.5,
         noise_lp: float = 400, drive_db: float = 9, tail: bool = False, seed: int = 31) -> str:
    g = _Graph(dur)
    sub = g.expr(f"sin({_glide(f0, f1, pitch_tau)})*{_env(0, 0.004, amp_tau)}")
    burst = g.mul(g.noise("pink", seed, f"lowpass=f={noise_lp}"), g.expr(_env(0, 0.002, 0.11)))
    sig = g.fx(g.mix((sub, 1.0), (burst, noise)), f"volume={drive_db}dB,asoftclip=type=atan,highpass=f=25")
    if tail:
        sig = g.fx(sig, "aecho=0.8:0.55:70|130|210:0.35|0.25|0.15")
    return g.render(g.fx(sig, "lowpass=f=7000"))


def hit(dur: float, *, f0: float = 170, f1: float = 55, body_tau: float = 0.16, crack: float = 1400, crack_tau: float = 0.035,
        snap: float = 0.5, drive_db: float = 8, tail: bool = False, seed: int = 41) -> str:
    g = _Graph(dur)
    body = g.expr(f"sin({_glide(f0, f1, 0.035)})*{_env(0, 0.0015, body_tau)}")
    crk = g.mul(g.noise("white", seed, f"bandpass=f={crack}:width_type=q:w=0.9"), g.expr(_env(0, 0.0008, crack_tau)))
    trn = g.mul(g.noise("white", seed + 3, "highpass=f=2500"), g.expr(_env(0, 0.0003, 0.008)))
    sig = g.fx(g.mix((body, 1.0), (crk, 0.8), (trn, snap)), f"volume={drive_db}dB,asoftclip=type=tanh,highpass=f=30")
    if tail:
        sig = g.fx(sig, "aecho=0.8:0.5:55|95|160:0.3|0.22|0.14")
    return g.render(sig)


def pop(dur: float, *, f0: float = 320, f1: float = 900, glide_tau: float = 0.012, amp_tau: float = 0.035, click: float = 0.15, seed: int = 51) -> str:
    g = _Graph(dur)
    ph = _glide(f0, f1, glide_tau)
    tone = g.expr(f"(sin({ph})+0.18*sin(2*{ph}))*{_env(0, 0.0015, amp_tau)}")
    clk = g.mul(g.noise("white", seed, "highpass=f=3000"), g.expr(_env(0, 0.0002, 0.003)))
    return g.render(g.mix((tone, 1.0), (clk, click)))


def click(dur: float, *, f: float = 2400, tau: float = 0.004, noise_f: float = 4000, second: float = 0.0, wood: bool = False, seed: int = 61) -> str:
    g = _Graph(dur)
    onsets = [(0.0, 1.0)] + ([(second, 0.6)] if second else [])
    tone = "+".join(f"{a}*sin(2*PI*{f}*(t-{t0}))*{_env(t0, 0.0003, tau)}" for t0, a in onsets)
    if wood:
        tone += "+" + "+".join(f"{0.8 * a}*sin(2*PI*{f * 0.37:.1f}*(t-{t0}))*{_env(t0, 0.0005, tau * 2.5)}" for t0, a in onsets)
    nenv = "+".join(f"{a}*{_env(t0, 0.0002, tau * 0.6)}" for t0, a in onsets)
    nz = g.mul(g.noise("white", seed, f"bandpass=f={noise_f}:width_type=q:w=0.8"), g.expr(nenv))
    return g.render(g.fx(g.mix((g.expr(tone), 1.0), (nz, 1.4)), "highpass=f=150"))


def ding(dur: float, notes: list[tuple[float, float]], *, ratios=((1, 1, 1.0), (2.0, 0.35, 0.55), (2.76, 0.28, 0.4), (5.4, 0.1, 0.2)),
         decay: float = 1.0, space: bool = True) -> str:
    """Bell partials per note (start s, fundamental Hz); `ratios` = (ratio, amp, decay factor)."""
    g = _Graph(dur)
    left = "+".join(_partials([(f * r, a, decay * d) for r, a, d in ratios], t0) for t0, f in notes)
    right = "+".join(_partials([(f * r, a, decay * d) for r, a, d in ratios], t0, detune=1.001) for t0, f in notes)  # slight width, mono-safe
    sig = g.expr(left, right)
    if space:
        sig = g.fx(sig, "aecho=0.8:0.45:47|83:0.22|0.14")
    return g.render(sig)


def glitch(dur: float, *, rate: float = 28, lo: float = 180, hi: float = 2200, gate: float = 0.35, bits: int = 6, data: bool = False, seed: int = 71) -> str:
    g = _Graph(dur)
    k = f"floor(t*{rate})"
    fade = f"min(1,({dur}-t)/0.04)"
    f = f"({lo}+{hi - lo}*{_hash(k, seed)})"

    def tone(gate_seed: int) -> str:
        on = f"gt({_hash(k, gate_seed)},{gate})*{fade}"
        if data:  # fast sine blips on random pitches (data chatter)
            return f"0.8*sin(2*PI*{f}*t)*lt(t*{rate}-{k},0.55)*{on}"
        return f"0.55*(2*gt(sin(2*PI*{f}*t),0)-1)*{on}"  # stuttered square tones

    sq = g.expr(tone(seed + 2), tone(seed + 5))
    nz = g.mul(g.noise("white", seed, "highpass=f=400"), g.expr(f"gt({_hash(k, seed + 9)},0.55)*{fade}"))
    return g.render(g.fx(g.mix((sq, 1.0), (nz, 0.45)), f"acrusher=bits={bits}:samples=6:mix=0.85,highpass=f=120"))


def typing(dur: float, *, rate: float = 11, seed: int = 81) -> str:
    g = _Graph(dur)
    k = f"floor(t*{rate})"
    u = f"(t-{k}/{rate}-0.45*{_hash(k, seed)}*gt({k},0)/{rate})"  # first key lands at 0, the rest jitter in their slot
    on = f"gte({u},0)*max(eq({k},0),gt({_hash(k, seed + 2)},0.12))*(0.55+0.45*{_hash(k, seed + 1)})"
    fade = f"min(1,({dur}-t)/0.03)"
    key = g.mul(g.noise("white", seed, "bandpass=f=3200:width_type=q:w=0.7"), g.expr(f"{on}*exp(-{u}/0.006)*{fade}"))
    thock = g.expr(f"{on}*sin(2*PI*(140+90*{_hash(k, seed + 3)})*{u})*exp(-{u}/0.014)*{fade}")
    return g.render(g.fx(g.mix((key, 1.0), (thock, 0.5)), "aecho=0.8:0.3:23|41:0.2|0.12,highpass=f=90"))


def camera(dur: float, *, onsets=(0.0, 0.085), whirr: tuple[float, float] | None = None, seed: int = 91) -> str:
    g = _Graph(dur)
    nenv = "+".join(_env(t0, 0.0003, 0.006) for t0 in onsets)
    mech = "+".join(f"sin(2*PI*{720 - 140 * i}*(t-{t0}))*{_env(t0, 0.0008, 0.018)}" for i, t0 in enumerate(onsets))
    layers = [(g.mul(g.noise("white", seed, "bandpass=f=3000:width_type=q:w=0.9"), g.expr(nenv)), 1.0), (g.expr(mech), 0.5)]
    if whirr:
        a, b = whirr
        buzz = f"between(t,{a},{b})*min(1,(t-{a})/0.02)*min(1,({b}-t)/0.03)*(0.6+0.4*sin(2*PI*95*t))"
        layers.append((g.mul(g.noise("pink", seed + 4, "bandpass=f=1400:width_type=q:w=1.2"), g.expr(buzz)), 0.35))
    return g.render(g.fx(g.mix(*layers), "aecho=0.8:0.25:17|29:0.15|0.1,highpass=f=200"))


_COIN = ((1.0, 1.0, 0.5), (1.53, 0.55, 0.35), (2.27, 0.35, 0.25), (2.9, 0.2, 0.18))


def cash(dur: float, *, register: bool = False, hits: int = 1, f0: float = 3100, spread: float = 0.0, seed: int = 101) -> str:
    g = _Graph(dur)
    layers = []
    tone_l, tone_r = [], []
    t_ching = 0.0
    if register:  # "ka": drawer latch + thud, then the bell "ching"
        latch = g.mul(g.noise("white", seed, "bandpass=f=1500:width_type=q:w=1.0"), g.expr(_env(0, 0.0005, 0.018)))
        layers += [(latch, 0.9), (g.expr(f"sin({_glide(180, 95, 0.03)})*{_env(0, 0.002, 0.05)}"), 0.6)]
        t_ching = 0.085
        bell = [(2637, 1.0, 0.9), (3951, 0.55, 0.7), (5274, 0.35, 0.5), (6590, 0.2, 0.35)]
        tone_l.append(_partials(bell, t_ching))
        tone_r.append(_partials(bell, t_ching, detune=1.004))
    for i in range(hits):  # coins: inharmonic metallic partials; bounces (decaying, closer together) or a spill
        r1, r2 = _pyhash(10 * seed + i, 7.1), _pyhash(10 * seed + i, 3.3)
        if spread:
            t0, amp = t_ching + 0.05 + spread * i / max(1, hits - 1) + 0.02 * r1, 0.9 * (0.6 + 0.4 * r1)
        else:
            t0, amp = 0.11 * i * (1 - 0.15 * i), 0.9 * 0.7 ** i
        f = round(f0 * (0.85 + 0.3 * r2), 1)
        parts = [(round(f * r, 1), round(amp * a, 4), d * (0.6 if spread else 1.0)) for r, a, d in _COIN]
        t0 = round(t0, 4)
        tone_l.append(_partials(parts, t0, att=0.0006))
        tone_r.append(_partials(parts, t0, att=0.0006, detune=1.003))
    layers.append((g.expr("+".join(tone_l), "+".join(tone_r)), 0.8))
    return g.render(g.fx(g.mix(*layers), "aecho=0.8:0.35:31|53:0.18|0.1,highpass=f=120"))


def _pyhash(n: int, seed: float) -> float:
    v = math.sin(n * 12.9898 + seed) * 43758.5453
    return v - math.floor(v)


# ------------------------------------------------------------------ the library

@dataclass(frozen=True)
class Recipe:
    name: str  # <category>_<variant>
    category: str
    dur: float
    graph: str


def _r(name: str, dur: float, graph: str) -> Recipe:
    return Recipe(name, name.split("_")[0], dur, graph)


def recipes() -> list[Recipe]:
    C6, E6, G6, A5, E5 = 1046.5, 1318.5, 1568.0, 880.0, 659.3
    return [
        # whoosh: band-passed noise flying past (pitch and level peak together, panned across)
        _r("whoosh_soft", 0.8, whoosh(0.8, lo=280, hi=2600, seed=11)),
        _r("whoosh_fast", 0.45, whoosh(0.45, color="white", lo=600, hi=5200, peak=0.55, w_in=0.25, w_out=0.16, pan=(0.75, 0.25), seed=13)),
        _r("whoosh_heavy", 1.0, whoosh(1.0, lo=160, hi=1700, width=0.6, w_in=0.3, w_out=0.2, seed=15, body=0.7)),
        _r("whoosh_air", 0.7, whoosh(0.7, color="white", lo=1200, hi=8000, width=0.45, pan=(0.8, 0.2), seed=17)),
        _r("whoosh_reverse", 0.9, whoosh(0.9, lo=250, hi=4200, peak=0.94, w_in=0.42, w_out=0.035, seed=19)),
        # swipe: short, bright, one-directional
        _r("swipe_right", 0.32, whoosh(0.32, color="white", lo=1500, hi=6500, peak=0.45, w_in=0.22, w_out=0.2, width=0.5, pan=(0.1, 0.9), seed=23)),
        _r("swipe_left", 0.32, whoosh(0.32, color="white", lo=1500, hi=6500, peak=0.45, w_in=0.22, w_out=0.2, width=0.5, pan=(0.9, 0.1), seed=25)),
        _r("swipe_soft", 0.42, whoosh(0.42, lo=900, hi=4200, peak=0.5, w_in=0.25, w_out=0.22, width=0.55, pan=(0.35, 0.65), seed=27)),
        # riser: rising noise band + gliding saw with accelerating tremolo; stops dead on the cut
        _r("riser_noise", 2.0, riser(2.0, tonal=0.0, seed=31)),
        _r("riser_tension", 2.5, riser(2.5, f0=82, octaves=2.0, tonal=0.8, seed=33)),
        _r("riser_short", 1.5, riser(1.5, f0=147, octaves=1.5, tonal=0.6, trem=(6, 18), seed=35)),
        _r("riser_long", 3.0, riser(3.0, f0=65, octaves=2.5, tonal=0.7, trem=(3, 16), lo=200, hi=10000, seed=37)),
        _r("riser_reverse_cymbal", 1.8, riser(1.8, tonal=0.0, cymbal=True, seed=39)),
        # boom / sub drop: falling sine + noise burst, saturated so phones hear the harmonics
        _r("boom_subdrop", 1.5, boom(1.5, f0=95, f1=32, pitch_tau=0.4, amp_tau=0.55, seed=41)),
        _r("boom_cinematic", 2.0, boom(2.0, f0=80, f1=36, pitch_tau=0.25, amp_tau=0.7, noise=0.9, noise_lp=1800, tail=True, seed=43)),
        _r("boom_short", 0.8, boom(0.8, f0=120, f1=45, pitch_tau=0.12, amp_tau=0.22, noise=0.6, seed=45)),
        _r("boom_deep", 1.8, boom(1.8, f0=70, f1=28, pitch_tau=0.6, amp_tau=0.8, noise=0.3, drive_db=12, seed=47)),
        # hit / impact: transient + crack + pitched body
        _r("hit_punch", 0.5, hit(0.5, seed=51)),
        _r("hit_heavy", 0.9, hit(0.9, f0=130, f1=42, body_tau=0.3, crack=900, crack_tau=0.06, drive_db=10, seed=53)),
        _r("hit_snap", 0.35, hit(0.35, f0=260, f1=110, body_tau=0.06, crack=2600, crack_tau=0.02, snap=0.9, seed=55)),
        _r("hit_cinematic", 1.2, hit(1.2, f0=150, f1=40, body_tau=0.35, crack=1100, crack_tau=0.08, drive_db=11, tail=True, seed=57)),
        # pop: quick upward pitch blip
        _r("pop_bubble", 0.18, pop(0.18, f0=320, f1=900, seed=61)),
        _r("pop_high", 0.15, pop(0.15, f0=650, f1=1500, glide_tau=0.008, amp_tau=0.025, seed=63)),
        _r("pop_low", 0.22, pop(0.22, f0=170, f1=430, glide_tau=0.015, amp_tau=0.045, click=0.1, seed=65)),
        _r("pop_soft", 0.25, pop(0.25, f0=420, f1=780, glide_tau=0.02, amp_tau=0.06, click=0.0, seed=67)),
        # click: UI / mouse / wood
        _r("click_soft", 0.1, click(0.1, f=1800, tau=0.005, noise_f=2500, seed=71)),
        _r("click_sharp", 0.08, click(0.08, f=3200, tau=0.003, noise_f=5500, seed=73)),
        _r("click_double", 0.15, click(0.15, f=2600, tau=0.0035, noise_f=4200, second=0.055, seed=75)),
        _r("click_wood", 0.12, click(0.12, f=2100, tau=0.006, noise_f=1600, wood=True, seed=77)),
        # ding / chime: bell partials with natural decay
        _r("ding_bell", 1.5, ding(1.5, [(0.0, E6)], decay=1.1)),
        _r("ding_notification", 1.2, ding(1.2, [(0.0, A5), (0.12, E6)], decay=0.8)),
        _r("ding_success", 1.3, ding(1.3, [(0.0, C6), (0.08, E6), (0.16, G6)], decay=0.7)),
        _r("ding_chime_bright", 1.4, ding(1.4, [(0.0, 2093.0)], ratios=((1, 1, 1.0), (2.4, 0.4, 0.6), (3.9, 0.25, 0.4), (6.1, 0.12, 0.25)), decay=1.0)),
        _r("ding_soft", 1.0, ding(1.0, [(0.0, E5)], ratios=((1, 1, 1.0), (2.0, 0.25, 0.6), (3.0, 0.08, 0.35)), decay=0.8, space=False)),
        # glitch: bit-crushed stutter / data chatter
        _r("glitch_stutter", 0.5, glitch(0.5, seed=81)),
        _r("glitch_digital", 0.6, glitch(0.6, rate=40, lo=300, hi=3500, gate=0.45, bits=5, seed=83)),
        _r("glitch_short", 0.25, glitch(0.25, rate=48, gate=0.3, bits=7, seed=85)),
        _r("glitch_data", 0.6, glitch(0.6, rate=60, lo=900, hi=4200, gate=0.25, bits=8, data=True, seed=87)),
        # typing: irregular key strikes (click + thock)
        _r("typing_fast", 1.5, typing(1.5, rate=12, seed=91)),
        _r("typing_slow", 2.0, typing(2.0, rate=6.5, seed=93)),
        _r("typing_short", 0.8, typing(0.8, rate=11, seed=95)),
        # camera: shutter curtain clicks, film wind
        _r("camera_shutter", 0.3, camera(0.3, seed=101)),
        _r("camera_shutter_burst", 0.6, camera(0.6, onsets=(0.0, 0.07, 0.19, 0.26, 0.38, 0.45), seed=103)),
        _r("camera_film", 0.7, camera(0.7, onsets=(0.0, 0.08), whirr=(0.16, 0.62), seed=105)),
        # cash / coin: register "ka-ching", coin bounce, coin spill
        _r("cash_register", 1.3, cash(1.3, register=True, hits=3, spread=0.35, seed=111)),
        _r("cash_coin", 0.8, cash(0.8, hits=3, f0=3100, seed=113)),
        _r("cash_coins_spill", 1.1, cash(1.1, hits=9, f0=3600, spread=0.7, seed=115)),
    ]


# ------------------------------------------------------------------ render


def synth(recipe: Recipe) -> np.ndarray:
    """Float32 (n, 2) at 48 kHz, peak at −1 dBFS, 10 ms de-click fade at the end."""
    cmd = [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-filter_complex_threads", "1",
           "-filter_complex", recipe.graph, "-map", "[out]", "-f", "f32le", "-ac", "2", "-ar", str(SR), "pipe:1"]
    res = subprocess.run(cmd, capture_output=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {recipe.name}: {res.stderr.decode(errors='replace')[-600:]}")
    y = np.frombuffer(res.stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64)
    if not np.isfinite(y).all():
        raise RuntimeError(f"{recipe.name} rendered non-finite samples")
    n = int(round(recipe.dur * SR))
    y = y[:n] if y.shape[0] >= n else np.vstack([y, np.zeros((n - y.shape[0], 2))])
    tail = int(TAIL_FADE_S * SR)
    y[-tail:] *= np.linspace(1.0, 0.0, tail)[:, None]
    return normalise_peak(y, recipe.name)


def normalise_peak(y: np.ndarray, name: str = "audio", dbfs: float = PEAK_DBFS) -> np.ndarray:
    peak = float(np.abs(y).max()) if y.size else 0.0
    if peak < 1e-6:
        raise RuntimeError(f"{name} is silent")
    return (y.astype(np.float64) * (10 ** (dbfs / 20) / peak)).astype(np.float32)


def decode(path: Path) -> np.ndarray:
    """Any audio file → float32 (n, 2) at 48 kHz (pinned ffmpeg; its resampler is deterministic)."""
    cmd = [str(config.ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path), "-map", "0:a:0",
           "-f", "f32le", "-ac", "2", "-ar", str(SR), "pipe:1"]
    res = subprocess.run(cmd, capture_output=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode {path.name}: {res.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(res.stdout, dtype=np.float32).reshape(-1, 2)


def ffmpeg_version() -> str:
    res = subprocess.run([str(config.ffmpeg_path()), "-hide_banner", "-version"], capture_output=True, check=False)
    first = res.stdout.decode(errors="replace").splitlines()[:1]
    return first[0].split(" Copyright")[0] if first else "ffmpeg"


def write_wav(path: Path, y: np.ndarray) -> Path:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.wav")
    sf.write(str(tmp), y, SR, subtype="PCM_24", format="WAV")
    tmp.replace(path)
    return path


def render_all(out_dir: Path, only: list[str] | None = None) -> list[Path]:
    """(Re)generate every recipe into out_dir/<name>.wav; removes stale procedural files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rs = [r for r in recipes() if not only or r.name in only]
    paths = [write_wav(out_dir / f"{r.name}.wav", synth(r)) for r in rs]
    if not only:
        keep = {p.name for p in paths}
        for old in out_dir.glob("*.wav"):
            if old.name not in keep:
                old.unlink()
    return paths
