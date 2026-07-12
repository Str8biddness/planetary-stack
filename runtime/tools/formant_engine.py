#!/usr/bin/env python3
"""
SI-native cascade formant synthesizer (Klatt-style source-filter).

HONEST TARGET: INTELLIGIBLE but ROBOTIC speech (classic DECtalk / Hawking /
Klatt formant quality). Recognizable words; NOT natural. Natural voice needs
neural TTS — rejected on purpose under the SI thesis.

Dependencies on the synth path: numpy, scipy, stdlib only.
No pyttsx3/espeak/piper/coqui/WebSpeech/torch/tensorflow.

Source-filter model:
  source = glottal pulse train (voiced) + noise (unvoiced), mixed by voicing
  filter = cascade of 2nd-order formant resonators (F1/F2/F3 + optional F4)
  coarticulation = raised-cosine formant track interpolation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy import signal

# ── Phoneme articulation tables (Hz) ─────────────────────────────────
# F1/F2/F3, BW1/BW2/BW3, duration_s, voicing 0..1, noise_mix 0..1
# Sources: classic average American English formant charts (Peterson/Barney-ish)

@dataclass
class PhoneTarget:
    name: str
    f1: float
    f2: float
    f3: float
    bw1: float = 90.0
    bw2: float = 110.0
    bw3: float = 170.0
    dur: float = 0.08
    voice: float = 1.0
    noise: float = 0.0
    amp: float = 1.0
    # nasal antiformant (Hz) if > 0
    fnz: float = 0.0
    # burst for stops: Hz center, duration
    burst_f: float = 0.0
    burst_dur: float = 0.0
    silence: float = 0.0  # pre-closure silence for stops


# Vowels & diphthong nuclei
_V = dict(
    IY=PhoneTarget("IY", 270, 2290, 3010, 60, 90, 120, 0.11, 1.0, 0.0, 1.0),
    IH=PhoneTarget("IH", 400, 1990, 2550, 70, 100, 140, 0.12, 1.0, 0.0, 1.0),
    EH=PhoneTarget("EH", 530, 1840, 2480, 80, 100, 150, 0.10, 1.0, 0.0, 1.0),
    AE=PhoneTarget("AE", 660, 1720, 2410, 80, 110, 160, 0.11, 1.0, 0.0, 1.0),
    AA=PhoneTarget("AA", 730, 1090, 2440, 80, 100, 150, 0.11, 1.0, 0.0, 1.0),
    AH=PhoneTarget("AH", 640, 1190, 2390, 90, 110, 160, 0.09, 1.0, 0.0, 0.95),
    AO=PhoneTarget("AO", 570, 840, 2410, 80, 100, 150, 0.11, 1.0, 0.0, 1.0),
    UH=PhoneTarget("UH", 440, 1020, 2240, 80, 100, 150, 0.09, 1.0, 0.0, 0.9),
    UW=PhoneTarget("UW", 300, 870, 2240, 70, 90, 140, 0.11, 1.0, 0.0, 1.0),
    ER=PhoneTarget("ER", 490, 1350, 1690, 80, 100, 120, 0.16, 1.0, 0.0, 1.0),
    AX=PhoneTarget("AX", 640, 1190, 2390, 100, 120, 170, 0.07, 1.0, 0.0, 0.85),  # schwa
    EY=PhoneTarget("EY", 480, 1900, 2500, 80, 100, 150, 0.14, 1.0, 0.0, 1.0),  # will glide
    AY=PhoneTarget("AY", 700, 1200, 2400, 80, 100, 150, 0.14, 1.0, 0.0, 1.0),
    OW=PhoneTarget("OW", 500, 900, 2300, 80, 100, 150, 0.14, 1.0, 0.0, 1.0),
    AW=PhoneTarget("AW", 650, 1100, 2400, 80, 100, 150, 0.14, 1.0, 0.0, 1.0),
    OY=PhoneTarget("OY", 500, 900, 2300, 80, 100, 150, 0.14, 1.0, 0.0, 1.0),
)

# Diphthong end targets (second half)
_DIPH_END = {
    "EY": (300, 2200, 3000),
    "AY": (300, 2100, 2950),
    "OW": (350, 800, 2200),
    "AW": (400, 900, 2300),
    "OY": (350, 1900, 2500),
}

# Consonants
_C = dict(
    # stops: silence + burst
    P=PhoneTarget("P", 400, 1100, 2500, 100, 150, 200, 0.05, 0.0, 0.35, 0.95, 0, 1400, 0.018, 0.045),
    B=PhoneTarget("B", 400, 1100, 2500, 100, 150, 200, 0.05, 0.45, 0.25, 0.95, 0, 900, 0.015, 0.04),
    T=PhoneTarget("T", 400, 1600, 2800, 100, 150, 200, 0.05, 0.0, 0.4, 0.95, 0, 3800, 0.02, 0.045),
    D=PhoneTarget("D", 400, 1600, 2800, 100, 150, 200, 0.05, 0.5, 0.25, 0.95, 0, 2800, 0.016, 0.04),
    K=PhoneTarget("K", 400, 1800, 2600, 100, 150, 200, 0.055, 0.0, 0.45, 0.95, 0, 2000, 0.022, 0.05),
    G=PhoneTarget("G", 400, 1800, 2600, 100, 150, 200, 0.055, 0.5, 0.3, 0.95, 0, 1500, 0.018, 0.04),
    # fricatives
    F=PhoneTarget("F", 400, 1400, 2500, 200, 300, 400, 0.10, 0.05, 0.95, 0.85, 0, 0, 0, 0),
    V=PhoneTarget("V", 400, 1400, 2500, 150, 200, 300, 0.09, 0.7, 0.5, 0.85, 0, 0, 0, 0),
    TH=PhoneTarget("TH", 400, 1600, 2800, 200, 300, 400, 0.09, 0.05, 0.95, 0.75, 0, 0, 0, 0),
    DH=PhoneTarget("DH", 400, 1400, 2500, 150, 200, 300, 0.08, 0.65, 0.55, 0.8, 0, 0, 0, 0),
    S=PhoneTarget("S", 500, 1800, 5500, 200, 400, 600, 0.12, 0.0, 1.0, 0.9, 0, 0, 0, 0),
    Z=PhoneTarget("Z", 500, 1800, 4500, 150, 300, 500, 0.10, 0.75, 0.55, 0.85, 0, 0, 0, 0),
    SH=PhoneTarget("SH", 400, 1800, 3500, 200, 300, 500, 0.12, 0.0, 1.0, 0.9, 0, 0, 0, 0),
    ZH=PhoneTarget("ZH", 400, 1800, 3500, 150, 250, 400, 0.10, 0.75, 0.55, 0.85, 0, 0, 0, 0),
    HH=PhoneTarget("HH", 500, 1500, 2500, 300, 400, 500, 0.07, 0.15, 0.85, 0.7, 0, 0, 0, 0),
    # affricates approx
    CH=PhoneTarget("CH", 400, 1800, 2800, 150, 250, 350, 0.08, 0.0, 0.9, 0.7, 0, 2500, 0.02, 0.03),
    JH=PhoneTarget("JH", 400, 1800, 2800, 150, 250, 350, 0.08, 0.6, 0.55, 0.75, 0, 2000, 0.015, 0.025),
    # nasals
    M=PhoneTarget("M", 280, 1000, 2200, 60, 100, 150, 0.07, 1.0, 0.05, 0.85, 750, 0, 0, 0),
    N=PhoneTarget("N", 280, 1400, 2500, 60, 100, 150, 0.07, 1.0, 0.05, 0.85, 1450, 0, 0, 0),
    NG=PhoneTarget("NG", 280, 1800, 2500, 60, 100, 150, 0.08, 1.0, 0.05, 0.85, 1600, 0, 0, 0),
    # liquids / glides
    L=PhoneTarget("L", 400, 1000, 2600, 80, 100, 150, 0.07, 1.0, 0.0, 0.9, 0, 0, 0, 0),
    R=PhoneTarget("R", 400, 1100, 1500, 80, 90, 120, 0.07, 1.0, 0.0, 0.9, 0, 0, 0, 0),
    W=PhoneTarget("W", 300, 700, 2200, 70, 90, 140, 0.06, 1.0, 0.0, 0.9, 0, 0, 0, 0),
    Y=PhoneTarget("Y", 300, 2200, 3000, 70, 90, 140, 0.06, 1.0, 0.0, 0.9, 0, 0, 0, 0),
    # silence
    SIL=PhoneTarget("SIL", 500, 1500, 2500, 100, 100, 100, 0.08, 0.0, 0.0, 0.0, 0, 0, 0, 0),
    SIL_LONG=PhoneTarget("SIL_LONG", 500, 1500, 2500, 100, 100, 100, 0.22, 0.0, 0.0, 0.0, 0, 0, 0, 0),
)

PHONE_DB: dict[str, PhoneTarget] = {**_V, **_C}
# aliases
PHONE_DB["AX"] = _V["AX"]
for k, v in list(PHONE_DB.items()):
    PHONE_DB[k.upper()] = v


def get_phone(name: str) -> PhoneTarget:
    n = name.upper().strip()
    if n in PHONE_DB:
        return PHONE_DB[n]
    # strip stress digits if any
    n2 = re.sub(r"\d", "", n) if (re := __import__("re")) else n
    return PHONE_DB.get(n2, PHONE_DB["AH"])


# ── Resonators ───────────────────────────────────────────────────────

def resonator_ba(f: float, bw: float, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    """Klatt-style digital resonator coefficients (b, a) for lfilter."""
    f = float(np.clip(f, 50.0, fs * 0.45))
    bw = float(np.clip(bw, 40.0, 2000.0))
    r = np.exp(-np.pi * bw / fs)
    theta = 2.0 * np.pi * f / fs
    b1 = 2.0 * r * np.cos(theta)
    b2 = -(r * r)
    # gain so steady-state ~1 near resonance
    a0 = 1.0 - b1 - b2
    if abs(a0) < 1e-8:
        a0 = 1e-8
    b = np.array([a0, 0.0, 0.0], dtype=np.float64)
    a = np.array([1.0, -b1, -b2], dtype=np.float64)
    return b, a


def antiformant_ba(f: float, bw: float, fs: float) -> Tuple[np.ndarray, np.ndarray]:
    """Zero pair (inverse resonator) for nasals."""
    f = float(np.clip(f, 50.0, fs * 0.45))
    bw = float(np.clip(bw, 40.0, 2000.0))
    r = np.exp(-np.pi * bw / fs)
    theta = 2.0 * np.pi * f / fs
    # zeros outside unit circle inverted -> poles of inverse
    b1 = 2.0 * r * np.cos(theta)
    b2 = -(r * r)
    # numerator is resonator denom, denom is (1,0,0) scaled
    g = 1.0
    b = np.array([1.0, -b1, -b2], dtype=np.float64) * g
    a = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    # normalize DC
    dc = np.sum(b) / (np.sum(a) + 1e-12)
    if abs(dc) > 1e-8:
        b = b / dc
    return b, a


def cascade_formants(
    x: np.ndarray,
    f1: float, f2: float, f3: float,
    bw1: float, bw2: float, bw3: float,
    fs: float,
    f4: float = 3500.0,
    bw4: float = 200.0,
    fnz: float = 0.0,
) -> np.ndarray:
    y = np.asarray(x, dtype=np.float64)
    for f, bw in ((f1, bw1), (f2, bw2), (f3, bw3), (f4, bw4)):
        b, a = resonator_ba(f, bw, fs)
        y = signal.lfilter(b, a, y)
    if fnz > 50:
        b, a = antiformant_ba(fnz, 100.0, fs)
        y = signal.lfilter(b, a, y)
    return y


# ── Source ───────────────────────────────────────────────────────────

def glottal_flow_pulse(n: int, f0: float, fs: float, rng: np.random.Generator) -> np.ndarray:
    """LF/Rosenberg-ish glottal flow derivative pulse train."""
    out = np.zeros(n, dtype=np.float64)
    if f0 < 40 or f0 > 500:
        f0 = 120.0
    period = fs / f0
    # open quotient ~0.6
    t = 0.0
    i = 0
    while i < n:
        # start of period
        p_len = period * (1.0 + 0.01 * (rng.random() - 0.5))  # micro jitter
        open_n = int(max(4, p_len * 0.55))
        for k in range(open_n):
            if i + k >= n:
                break
            x = k / max(open_n - 1, 1)
            # Rosenberg: two-polynomial glottal flow, use derivative-like excitation
            if x < 0.6:
                g = np.sin(np.pi * x / 0.6)
            else:
                g = np.sin(np.pi * (1.0 - x) / 0.4)
            # differentiated-ish impulse at closure for spectral tilt
            out[i + k] += g
        # strong negative impulse at glottal closure (high-freq energy)
        close_i = i + open_n
        if close_i < n:
            out[close_i] -= 1.8
        i += max(1, int(round(p_len)))
    # mild lowpass for natural spectral tilt
    b, a = signal.butter(1, min(0.45, 800.0 / (fs / 2)), btype="low")
    out = signal.lfilter(b, a, out)
    # normalize
    m = np.max(np.abs(out)) + 1e-12
    return out / m


def noise_source(n: int, rng: np.random.Generator, bright: float = 1.0) -> np.ndarray:
    x = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    # shape: high-shelf emphasis for fricatives when bright>1
    if bright > 1.01:
        b, a = signal.butter(2, min(0.48, 2500.0 / (22050)), btype="high")
        # fix fs-independent: use normalized
        wn = min(0.48, 0.25 * bright)
        b, a = signal.butter(2, wn, btype="high")
        x = signal.lfilter(b, a, x)
    m = np.max(np.abs(x)) + 1e-12
    return x / m


# ── Track generation ─────────────────────────────────────────────────

@dataclass
class Frame:
    f1: float
    f2: float
    f3: float
    bw1: float
    bw2: float
    bw3: float
    f0: float
    voice: float
    noise: float
    amp: float
    fnz: float = 0.0
    burst_f: float = 0.0
    is_burst: bool = False
    is_silence: bool = False


def _ease(t: float) -> float:
    """Raised-cosine 0..1."""
    t = float(np.clip(t, 0, 1))
    return 0.5 - 0.5 * np.cos(np.pi * t)


def build_frames(
    phone_seq: Sequence[Tuple[str, PhoneTarget, float]],
    fs: float,
    f0_base: float,
    f0_contour: Sequence[float],
    transition_s: float = 0.035,
    frame_ms: float = 5.0,
) -> List[Frame]:
    """phone_seq: list of (name, target, duration_seconds) after prosody scale."""
    hop = max(1, int(fs * frame_ms / 1000.0))
    # expand each phone into steady + transition into next
    segments: List[Tuple[PhoneTarget, PhoneTarget, int, bool]] = []
    # (from_tgt, to_tgt, n_samples, is_transition)
    for i, (name, tgt, dur) in enumerate(phone_seq):
        n = max(1, int(dur * fs))
        if i + 1 < len(phone_seq):
            n_trans = min(int(transition_s * fs), n // 2)
            n_steady = max(1, n - n_trans)
            segments.append((tgt, tgt, n_steady, False))
            nxt = phone_seq[i + 1][1]
            segments.append((tgt, nxt, n_trans, True))
        else:
            segments.append((tgt, tgt, n, False))

    frames: List[Frame] = []
    sample_pos = 0
    total = sum(s[2] for s in segments)
    for a, b, n, is_tr in segments:
        n_frames = max(1, n // hop)
        for fi in range(n_frames):
            t = (fi + 0.5) / n_frames
            e = _ease(t) if is_tr else 0.0
            # diphthong mid-phone glide if same phone and name in diph
            f1 = a.f1 * (1 - e) + b.f1 * e
            f2 = a.f2 * (1 - e) + b.f2 * e
            f3 = a.f3 * (1 - e) + b.f3 * e
            bw1 = a.bw1 * (1 - e) + b.bw1 * e
            bw2 = a.bw2 * (1 - e) + b.bw2 * e
            bw3 = a.bw3 * (1 - e) + b.bw3 * e
            voice = a.voice * (1 - e) + b.voice * e
            noise = a.noise * (1 - e) + b.noise * e
            amp = a.amp * (1 - e) + b.amp * e
            fnz = a.fnz * (1 - e) + b.fnz * e
            # F0 from contour
            idx = int((sample_pos / max(total, 1)) * (len(f0_contour) - 1))
            idx = int(np.clip(idx, 0, len(f0_contour) - 1))
            f0 = float(f0_contour[idx]) * (0.92 + 0.08 * voice)
            is_sil = a.name.startswith("SIL") and b.name.startswith("SIL")
            is_burst = (a.burst_f > 0 and not is_tr and fi == 0)
            frames.append(Frame(
                f1=f1, f2=f2, f3=f3, bw1=bw1, bw2=bw2, bw3=bw3,
                f0=f0, voice=voice, noise=noise, amp=amp, fnz=fnz,
                burst_f=a.burst_f if is_burst else 0.0,
                is_burst=is_burst,
                is_silence=is_sil or (a.amp < 0.05 and b.amp < 0.05 and a.noise < 0.05),
            ))
            sample_pos += hop
    return frames


def _interp_track(frames: List[Frame], attr: str, hop: int, n: int) -> np.ndarray:
    pts = np.array([getattr(f, attr) for f in frames], dtype=np.float64)
    if len(pts) == 0:
        return np.zeros(n)
    xp = (np.arange(len(pts)) + 0.5) * hop
    x = np.arange(n, dtype=np.float64)
    return np.interp(x, xp, pts, left=pts[0], right=pts[-1])


def synthesize_frames(
    frames: List[Frame],
    fs: int,
    rng: Optional[np.random.Generator] = None,
) -> np.ndarray:
    """Continuous-track source-filter (better than OLA for formant continuity)."""
    if rng is None:
        rng = np.random.default_rng(0)
    if not frames:
        return np.zeros(int(0.1 * fs), dtype=np.float64)

    hop = max(1, int(fs * 0.005))
    n = hop * len(frames)
    # parameter tracks
    f1 = _interp_track(frames, "f1", hop, n)
    f2 = _interp_track(frames, "f2", hop, n)
    f3 = _interp_track(frames, "f3", hop, n)
    bw1 = _interp_track(frames, "bw1", hop, n)
    bw2 = _interp_track(frames, "bw2", hop, n)
    bw3 = _interp_track(frames, "bw3", hop, n)
    f0 = _interp_track(frames, "f0", hop, n)
    voice = np.clip(_interp_track(frames, "voice", hop, n), 0, 1)
    noise_a = np.clip(_interp_track(frames, "noise", hop, n), 0, 1)
    amp = np.clip(_interp_track(frames, "amp", hop, n), 0, 2)
    fnz = _interp_track(frames, "fnz", hop, n)

    # time-varying F0 glottal: integrate phase
    phase = np.cumsum(2.0 * np.pi * np.maximum(f0, 60.0) / fs)
    # glottal flow approx: 2nd harmonic rich pulse from phase
    # open phase sinusoid + closure click when phase wraps
    ph = np.mod(phase, 2.0 * np.pi)
    open_mask = ph < (0.6 * 2 * np.pi)
    glot = np.zeros(n, dtype=np.float64)
    glot[open_mask] = np.sin(ph[open_mask] / 0.6)
    # closure impulses
    wrap = np.diff(ph, prepend=ph[0]) < -np.pi
    glot[wrap] -= 2.0
    # spectral tilt
    b_lp, a_lp = signal.butter(1, min(0.4, 900.0 / (fs / 2)), btype="low")
    glot = signal.lfilter(b_lp, a_lp, glot)
    gmax = np.max(np.abs(glot)) + 1e-12
    glot /= gmax

    noi = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    # bright noise for fricatives
    b_hp, a_hp = signal.butter(2, min(0.48, 1800.0 / (fs / 2)), btype="high")
    noi_b = signal.lfilter(b_hp, a_hp, noi)
    noi_b /= np.max(np.abs(noi_b)) + 1e-12

    src = voice * glot + noise_a * (0.55 * noi_b + 0.25 * noi)
    # bursts from frame flags
    for fi, fr in enumerate(frames):
        if fr.is_burst and fr.burst_f > 0:
            i0 = fi * hop
            i1 = min(n, i0 + int(0.012 * fs))
            b, a = resonator_ba(fr.burst_f, 900.0, fs)
            burst = signal.lfilter(b, a, rng.normal(0, 1, i1 - i0))
            burst /= np.max(np.abs(burst)) + 1e-12
            src[i0:i1] = src[i0:i1] * 0.25 + burst * 1.1

    # Piecewise-stationary cascade in short blocks (update coeffs, keep state)
    block = hop  # 5 ms
    out = np.zeros(n, dtype=np.float64)
    # filter states for 4 resonators (order-2) + nasal lowpass (order-1)
    zf = [np.zeros(2) for _ in range(4)]
    z_nas = np.zeros(1)
    for i0 in range(0, n, block):
        i1 = min(n, i0 + block)
        chunk = src[i0:i1].copy()
        mid = (i0 + i1) // 2
        specs = [
            (f1[mid], bw1[mid]),
            (f2[mid], bw2[mid]),
            (f3[mid], bw3[mid]),
            (3500.0, 250.0),
        ]
        for ri, (ff, bb) in enumerate(specs):
            b, a = resonator_ba(ff, bb, fs)
            chunk, zf[ri] = signal.lfilter(b, a, chunk, zi=zf[ri])
        # Nasals: gentle lowpass muffling (stable). Hard zeros killed energy after /n/.
        if fnz[mid] > 50:
            b_n, a_n = signal.butter(1, min(0.35, 1200.0 / (fs / 2)), btype="low")
            chunk, z_nas = signal.lfilter(b_n, a_n, chunk, zi=z_nas)
            chunk *= 0.85
        else:
            z_nas *= 0.5
        out[i0:i1] = chunk * amp[i0:i1]

    # lip radiation (pre-emphasis / differentiator)
    out = signal.lfilter([1.0, -0.95], [1.0], out)
    # silence gate from amp
    out *= (amp > 0.04).astype(np.float64) * 0.15 + 0.85 * np.clip(amp, 0, 1)

    peak = np.max(np.abs(out)) + 1e-12
    out = out / peak * 0.92
    out = signal.lfilter([1, -1], [1, -0.995], out)
    peak = np.max(np.abs(out)) + 1e-12
    out = out / peak * 0.95
    return out.astype(np.float64)


def _synth_phone_chunk(
    tgt: PhoneTarget,
    n: int,
    fs: int,
    f0: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Synthesize one stationary phone chunk (classic cascade formant)."""
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    if tgt.amp < 0.05 and tgt.noise < 0.05 and tgt.voice < 0.05:
        return np.zeros(n, dtype=np.float64)

    # Source
    if tgt.voice >= 0.15:
        glot = glottal_flow_pulse(n + 32, max(70.0, f0), fs, rng)[:n]
    else:
        glot = np.zeros(n)
    noi = noise_source(n, rng, bright=1.0 + 1.5 * tgt.noise)
    src = tgt.voice * glot + tgt.noise * noi * (0.7 if tgt.voice < 0.3 else 0.45)

    if tgt.burst_f > 0 and tgt.burst_dur > 0:
        nb = min(n, max(1, int(tgt.burst_dur * fs)))
        b, a = resonator_ba(tgt.burst_f, 1000.0, fs)
        burst = signal.lfilter(b, a, rng.normal(0, 1, nb))
        burst /= np.max(np.abs(burst)) + 1e-12
        src[:nb] = src[:nb] * 0.2 + burst * 1.2

    # Cascade formants (fixed for this phone) + parallel F2/F3 for clarity
    y = cascade_formants(
        src, tgt.f1, tgt.f2, tgt.f3, tgt.bw1, tgt.bw2, tgt.bw3, fs,
        f4=3200.0 if tgt.voice > 0.4 else 4500.0,
        bw4=200.0,
        fnz=0.0,  # nasal via F1 already low
    )
    # Parallel branch (Klatt-style): boost F2/F3 peaks for vowel intelligibility
    if tgt.voice > 0.35 and tgt.noise < 0.5:
        b2, a2 = resonator_ba(tgt.f2, tgt.bw2 * 0.9, fs)
        b3, a3 = resonator_ba(tgt.f3, tgt.bw3 * 0.9, fs)
        p2 = signal.lfilter(b2, a2, src)
        p3 = signal.lfilter(b3, a3, src)
        y = y * 0.72 + p2 * 0.22 + p3 * 0.10
    if tgt.fnz > 50:
        b_n, a_n = signal.butter(1, min(0.4, 1400.0 / (fs / 2)), btype="low")
        y = signal.lfilter(b_n, a_n, y) * 0.9

    # Lip radiation
    y = signal.lfilter([1.0, -0.97], [1.0], y)
    # Envelope: fade in/out 3ms
    fade = max(1, int(0.003 * fs))
    if len(y) > 2 * fade:
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
    y *= tgt.amp
    # prevent denormals
    peak = np.max(np.abs(y)) + 1e-12
    y = y / peak * min(1.0, 0.5 + 0.5 * tgt.amp)
    return y.astype(np.float64)


def phones_to_audio(
    phones: Sequence[str],
    fs: int = 22050,
    f0_base: float = 140.0,
    f0_end: Optional[float] = None,
    dur_scale: float = 1.0,
    f2_stretch: float = 1.0,
    amp: float = 1.0,
    transition: float = 0.035,
    seed: int = 0,
) -> np.ndarray:
    """Render a phoneme list to mono float64 audio -1..1.

    Uses per-phone stationary cascade segments + crossfade coarticulation
    (clearer than sample-rate track interpolation for intelligibility).
    """
    rng = np.random.default_rng(seed)
    seq: List[Tuple[str, PhoneTarget, float]] = []
    for p in phones:
        tgt = get_phone(p)
        t = PhoneTarget(
            name=tgt.name,
            f1=tgt.f1,
            f2=tgt.f2 * f2_stretch if tgt.voice > 0.5 and tgt.noise < 0.3 else tgt.f2,
            f3=tgt.f3,
            bw1=tgt.bw1,
            bw2=tgt.bw2 * (1.0 + 0.15 * max(0.0, f2_stretch - 1.0)),
            bw3=tgt.bw3,
            dur=max(0.03, tgt.dur * dur_scale),
            voice=tgt.voice,
            noise=tgt.noise,
            amp=tgt.amp * amp,
            fnz=tgt.fnz,
            burst_f=tgt.burst_f,
            burst_dur=tgt.burst_dur,
            silence=tgt.silence,
        )
        if t.silence > 0.01:
            seq.append((
                "SIL",
                PhoneTarget(
                    name="SIL", f1=500, f2=1500, f3=2500,
                    bw1=100, bw2=100, bw3=100,
                    dur=t.silence * dur_scale, voice=0.0, noise=0.0, amp=0.0,
                ),
                max(0.015, t.silence * dur_scale),
            ))
        if t.name in _DIPH_END:
            e1, e2, e3 = _DIPH_END[t.name]
            d1 = t.dur * 0.45
            d2 = t.dur * 0.55
            t1 = PhoneTarget(
                t.name, t.f1, t.f2, t.f3, t.bw1, t.bw2, t.bw3, d1,
                t.voice, t.noise, t.amp, t.fnz,
            )
            t2 = PhoneTarget(
                t.name + "2", e1, e2 * f2_stretch, e3, t.bw1, t.bw2, t.bw3, d2,
                t.voice, t.noise, t.amp, t.fnz,
            )
            seq.append((t.name, t1, d1))
            seq.append((t.name + "2", t2, d2))
        else:
            seq.append((t.name, t, t.dur))

    if not seq:
        return np.zeros(int(0.1 * fs), dtype=np.float64)

    total_dur = sum(s[2] for s in seq)
    f0_end = f0_base if f0_end is None else f0_end
    xfade = max(1, int(transition * fs))

    chunks: List[np.ndarray] = []
    t_pos = 0.0
    for i, (name, tgt, dur) in enumerate(seq):
        n = max(1, int(dur * fs))
        # F0 contour over utterance
        t_frac = t_pos / max(total_dur, 1e-6)
        f0 = f0_base * (1.0 - 0.06 * t_frac) + (f0_end - f0_base * 0.94) * (t_frac ** 1.4)
        f0 *= 1.0 + 0.01 * np.sin(2 * np.pi * 4.5 * t_pos)
        chunk = _synth_phone_chunk(tgt, n, fs, float(f0), rng)
        chunks.append(chunk)
        t_pos += dur

    # Crossfade concatenate
    out = chunks[0]
    for nxt in chunks[1:]:
        if len(out) == 0:
            out = nxt
            continue
        if len(nxt) == 0:
            continue
        xf = min(xfade, len(out) // 2, len(nxt) // 2, max(1, len(nxt) // 3))
        if xf < 2:
            out = np.concatenate([out, nxt])
            continue
        fade_out = np.linspace(1, 0, xf)
        fade_in = np.linspace(0, 1, xf)
        mid = out[-xf:] * fade_out + nxt[:xf] * fade_in
        out = np.concatenate([out[:-xf], mid, nxt[xf:]])

    # final normalize
    peak = np.max(np.abs(out)) + 1e-12
    out = out / peak * 0.95
    # light highpass to reduce boom
    b, a = signal.butter(1, 80.0 / (fs / 2), btype="high")
    out = signal.lfilter(b, a, out)
    peak = np.max(np.abs(out)) + 1e-12
    out = out / peak * 0.95
    return out.astype(np.float64)


def spectral_formant_summary(audio: np.ndarray, fs: int) -> dict:
    """Proof helper: STFT peak/mean ratio + rough F1/F2 band energy."""
    if len(audio) < fs // 10:
        return {"error": "audio too short", "peak_mean_ratio": 0.0}
    # mono
    x = np.asarray(audio, dtype=np.float64)
    x = x / (np.max(np.abs(x)) + 1e-12)
    nper = 512
    f, t, z = signal.stft(x, fs=fs, nperseg=nper, noverlap=nper // 2)
    mag = np.abs(z)
    # peak/mean over spectrum (tones >> formant speech)
    flat = mag.mean(axis=1) + 1e-12
    peak_mean = float(flat.max() / flat.mean())
    # energy in vowel formant bands
    def band_e(lo, hi):
        m = (f >= lo) & (f <= hi)
        return float(mag[m, :].mean()) if m.any() else 0.0
    e_f1 = band_e(200, 900)
    e_f2 = band_e(900, 2500)
    e_f3 = band_e(2500, 4000)
    e_hi = band_e(4000, min(8000, fs // 2 - 1))
    return {
        "peak_mean_ratio": round(peak_mean, 2),
        "band_energy": {
            "F1_200_900": round(e_f1, 5),
            "F2_900_2500": round(e_f2, 5),
            "F3_2500_4000": round(e_f3, 5),
            "hi_4000_plus": round(e_hi, 5),
        },
        "note": "formant speech: moderate peak/mean (<< 1000 tone spikes); energy across F1-F3",
    }
