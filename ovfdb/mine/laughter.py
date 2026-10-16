"""Laughter detector for one participant's audio track.

Seamless transcripts carry no laughter tokens (checked over 80 naturalistic
/test pairs: zero "[laughter]"/"haha" hits), so laughter comes from audio:

* primary (``detect_gemini``): one gemini-2.5-flash call over the whole
  16 kHz track asking for laugh timestamps (~$0.002 / file), snapped to the
  VAD regions they overlap;
* fallback (``detect_dsp``, no API): stretches **inside VAD but without
  transcript words** (the ASR drops non-lexical vocalisations) that look like
  laughter — a train of >= 3 short voiced energy bursts at a 3–8 Hz syllable
  rate with a pitch above the speaker's speaking median. Untuned: no ground
  truth was available on day 1 and the autocorrelation f0 is unreliable on
  the denoised tracks.

Precision of whichever detector is used is measured downstream by the VLM
verification. Pure parts (``burst_features``, ``unlexical_stretches``,
``snap_to_vad``) take arrays/segments so they can be unit-tested.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv()

from ovfdb.data.seamless import Utterance
from ovfdb.mine.dialogue import merge_regions
from ovfdb.schema import Segment

SR = 16000
HOP = 0.010
WIN = 0.025
MIN_UNLEXICAL_S = 0.5       # a wordless stretch inside VAD must be at least this long
MIN_BURSTS = 3
BURST_RATE_HZ = (3.0, 8.5)
MIN_VOICED_FRAC = 0.35
F0_RANGE = (90.0, 700.0)


@dataclass
class LaughFeatures:
    n_bursts: int
    burst_rate_hz: float
    voiced_frac: float
    f0_median: float
    score: float


def _frames(x: np.ndarray, sr: int = SR) -> tuple[np.ndarray, np.ndarray]:
    """Frame energy (dB) and a crude autocorrelation f0 (Hz, 0 = unvoiced) at 10 ms hop."""
    hop, win = int(sr * HOP), int(sr * WIN)
    if len(x) < win:
        return np.zeros(0), np.zeros(0)
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    fr = x[idx] * np.hanning(win)[None, :]
    energy = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-10)
    # f0 by autocorrelation in the lag band for F0_RANGE
    lo, hi = int(sr / F0_RANGE[1]), int(sr / F0_RANGE[0])
    spec = np.fft.rfft(fr, n=2 * win, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, :win]
    ac0 = ac[:, :1] + 1e-9
    band = ac[:, lo:hi] / ac0
    best = band.argmax(axis=1)
    f0 = np.where(band.max(axis=1) > 0.45, sr / (best + lo), 0.0)
    return energy, f0


def burst_features(x: np.ndarray, sr: int = SR, speech_f0: float = 0.0) -> LaughFeatures:
    """Laughter-likeness of one audio stretch (float32 mono)."""
    from scipy.signal import find_peaks

    energy, f0 = _frames(x, sr)
    if len(energy) < 20:
        return LaughFeatures(0, 0.0, 0.0, 0.0, 0.0)
    env = np.convolve(energy, np.ones(3) / 3, mode="same")
    floor = np.percentile(env, 20)
    peaks, _ = find_peaks(env, prominence=4.0, distance=int(0.09 / HOP), height=floor + 6)
    dur = len(energy) * HOP
    n = len(peaks)
    rate = n / dur if dur > 0 else 0.0
    voiced = f0 > 0
    voiced_frac = float(voiced.mean())
    f0_med = float(np.median(f0[voiced])) if voiced.any() else 0.0
    score = 0.0
    if n >= MIN_BURSTS and BURST_RATE_HZ[0] <= rate <= BURST_RATE_HZ[1] and voiced_frac >= MIN_VOICED_FRAC:
        score = min(n, 8) / 8 + voiced_frac
        if speech_f0 > 0 and f0_med > 1.1 * speech_f0:
            score += 0.5
    return LaughFeatures(n, round(rate, 2), round(voiced_frac, 3), round(f0_med, 1), round(score, 3))


def unlexical_stretches(vad: list[Segment], utts: list[Utterance], min_len: float = MIN_UNLEXICAL_S) -> list[tuple[float, float]]:
    """Intervals inside merged VAD runs that no transcript word covers (pure)."""
    words = sorted(((w.start, w.end) for u in utts for w in u.words), key=lambda p: p[0])
    out = []
    for run in merge_regions(vad):
        t, end = run[0].start, run[-1].end
        for ws, we in words:
            if we <= t or ws >= end:
                continue
            if ws - t >= min_len:
                out.append((t, ws))
            t = max(t, we)
        if end - t >= min_len:
            out.append((t, end))
    return out


def laugh_segments(audio: np.ndarray, sr: int, stretches: list[tuple[float, float]], speech_f0: float = 0.0,
                   min_score: float = 1.0) -> list[Segment]:
    """Score each stretch and keep the laughter-like ones as Segments (text="[laughter]")."""
    out = []
    for s, e in stretches:
        x = audio[int(s * sr):int(e * sr)]
        f = burst_features(x, sr, speech_f0)
        if f.score >= min_score:
            out.append(Segment(start=round(s, 3), end=round(e, 3), text="[laughter]", n_words=0))
            out[-1].__dict__["features"] = f  # keep evidence without changing the schema
    return out


def load_audio(path, sr: int = SR) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly

    x, in_sr = sf.read(str(path), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if in_sr != sr:
        from math import gcd
        g = gcd(in_sr, sr)
        x = resample_poly(x, sr // g, in_sr // g).astype(np.float32)
    return x


def speaking_f0(audio: np.ndarray, sr: int, utts: list[Utterance], max_words: int = 300) -> float:
    """Median f0 over the first ``max_words`` transcribed words (the speaker's baseline)."""
    vals = []
    for u in utts:
        for w in u.words[: max(0, max_words - len(vals))]:
            _, f0 = _frames(audio[int(w.start * sr):int(w.end * sr)], sr)
            vals.extend(f0[f0 > 0].tolist())
        if len(vals) >= max_words:
            break
    return float(np.median(vals)) if vals else 0.0


def detect_dsp(wav_path, vad: list[Segment], utts: list[Utterance], min_score: float = 1.0) -> list[Segment]:
    """Laughter segments from the burst heuristic alone (no API)."""
    audio = load_audio(wav_path)
    base = speaking_f0(audio, SR, utts)
    return laugh_segments(audio, SR, unlexical_stretches(vad, utts), base, min_score)


_GEMINI_PROMPT = (
    "This is one participant's close microphone track from a face-to-face conversation (the other person is "
    "faint or inaudible). List EVERY moment this speaker laughs or chuckles audibly, including short laughs "
    "while speaking. Return a JSON list of objects {\"start\": \"MM:SS.s\", \"end\": \"MM:SS.s\", "
    "\"kind\": \"laugh\" | \"chuckle\", \"while_speaking\": bool, \"note\": str}. Timestamps are "
    "minutes:seconds.tenths from the start of the audio (e.g. \"01:23.4\"), as precise as you can. "
    "Return [] if there is no laughter."
)


def parse_ts(v) -> float | None:
    """'MM:SS.s' | 'H:MM:SS' | number of seconds -> seconds (pure)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        if ":" in s:
            parts = [float(x) for x in s.split(":")]
            out = 0.0
            for x in parts:
                out = out * 60 + x
            return out
        return float(s)
    except ValueError:
        return None


def snap_to_vad(laughs: list[Segment], vad: list[Segment], max_shift: float = 1.0) -> list[Segment]:
    """Align approximate (API) laugh times to the VAD: clip each laugh to the
    union of VAD regions it overlaps (extended by up to ``max_shift`` s when
    the laugh fell just outside any region). Pure."""
    out = []
    for lg in laughs:
        hit = [s for s in vad if s.start < lg.end + max_shift and s.end > lg.start - max_shift]
        if not hit:
            continue
        s0 = max(min(s.start for s in hit), lg.start - max_shift)
        s1 = min(max(s.end for s in hit), lg.end + max_shift)
        if s1 - s0 >= 0.3:
            seg = Segment(start=round(s0, 3), end=round(s1, 3), text=lg.text, n_words=lg.n_words)
            seg.__dict__["features"] = lg.__dict__.get("features")
            out.append(seg)
    return out


def detect_gemini(wav_path, vad: list[Segment], cache_dir: Path | str = "data/mining/laughter") -> list[Segment]:
    """Laughter segments via a gemini-2.5-flash audio pass (cached per file).

    ~5.5k input tokens per 170 s track (about $0.002). Timestamps are
    snapped to the VAD regions they overlap.
    """
    import subprocess
    import tempfile

    from ovfdb.mine import gemini as G

    wav_path = Path(wav_path)
    cache = Path(cache_dir) / f"{wav_path.stem}.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
    else:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "a.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(wav_path), "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", str(tmp)], check=True)
            out, usage = G.generate(_GEMINI_PROMPT, tmp, mime="audio/wav")
        raw = {"laughs": out if isinstance(out, list) else [], "usage": usage}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw, indent=1))
    segs = []
    for d in raw["laughs"]:
        s, e = parse_ts(d.get("start", d.get("start_s"))), parse_ts(d.get("end", d.get("end_s")))
        if s is None or e is None:
            continue
        if e <= s:
            e = s + 0.5     # the model often returns a point event; give it a minimal extent
        if e > s:
            seg = Segment(start=s, end=e, text="[laughter]", n_words=0)
            seg.__dict__["features"] = {k: d.get(k) for k in ("kind", "while_speaking", "note")}
            segs.append(seg)
    return snap_to_vad(segs, vad)


def detect(wav_path, vad: list[Segment], utts: list[Utterance], use_api: bool = True) -> list[Segment]:
    """Laughter segments for one participant file (raw file seconds).

    Primary = Gemini audio pass; fallback (``use_api=False`` or no key) = the
    burst heuristic on wordless VAD stretches.
    """
    if use_api and os.environ.get("GOOGLE_API_KEY"):
        return detect_gemini(wav_path, vad)
    return detect_dsp(wav_path, vad, utts)
