"""Speech-activity regions on agent audio (VAD), independent of what ASR transcribes.

Why: faster-whisper drops non-lexical backchannels ("mhm", a chuckle) entirely and its
word onsets lag the acoustic onset by 100-400 ms, which made human ground truth fail the
backchannel-produced and smooth-handoff rules (STATUS.md "Calibration findings").
Segments are therefore built from VAD regions and ASR words are attached to them
(`ovfdb.score.segments.merge_vad_and_words`).

Backends
- `silero`: the Silero VAD ONNX model that faster-whisper already bundles
  (`faster_whisper.vad`, runs on onnxruntime). No torch, no new dependency.
- `energy`: RMS-energy VAD with a noise-floor-relative threshold (20 ms frames, speech =
  >= 12 dB above the 10th-percentile frame level, min speech 150 ms, min silence 300 ms).
  Used when the Silero backend cannot be imported or fails (`backend="auto"`).

`speech_regions(wav_path) -> [(start_s, end_s), ...]`; `detect()` also reports which
backend produced the regions so the pipeline can record it in timing.json.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ovfdb.score.asr import WHISPER_SR, load_audio_16k
from ovfdb.score.segments import merge_regions

log = logging.getLogger(__name__)

#: Silero speech-probability threshold (its "lazy" default).
SILERO_THRESHOLD = 0.5
#: Shortest region kept. 100 ms for Silero (a clipped "mhm" is ~150 ms of >0.5 probability).
SILERO_MIN_SPEECH_S = 0.10
#: Pad each Silero region by this much on both sides. Silero fires a frame or two late;
#: the default 400 ms would turn every 0.5 s "yeah" into a >1 s non-backchannel.
SILERO_PAD_S = 0.06
#: Silence shorter than this does not split a region (both backends).
MIN_SILENCE_S = 0.30
#: Energy backend: frame length, threshold above the noise floor, shortest region kept.
ENERGY_FRAME_S = 0.02
ENERGY_DB_ABOVE_FLOOR = 12.0
ENERGY_MIN_SPEECH_S = 0.15
#: Energy backend never fires below this absolute level (dBFS), so digital silence stays silent.
ENERGY_ABS_MIN_DB = -55.0


@dataclass
class VadResult:
    regions: list[tuple[float, float]] = field(default_factory=list)
    backend: str = ""
    error: str = ""              # why the preferred backend was not used (auto mode)


# --- backends ----------------------------------------------------------------

def silero_regions(audio: np.ndarray, sr: int = WHISPER_SR, *, threshold: float = SILERO_THRESHOLD,
                   min_speech_s: float = SILERO_MIN_SPEECH_S, min_silence_s: float = MIN_SILENCE_S,
                   pad_s: float = SILERO_PAD_S) -> list[tuple[float, float]]:
    """Silero VAD via faster-whisper's bundled ONNX model. Mono float32 audio at 16 kHz."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps  # lazy: loads onnxruntime

    if len(audio) == 0:
        return []
    opts = VadOptions(threshold=threshold, min_speech_duration_ms=round(min_speech_s * 1000),
                      min_silence_duration_ms=round(min_silence_s * 1000),
                      speech_pad_ms=round(pad_s * 1000))
    stamps = get_speech_timestamps(np.asarray(audio, dtype=np.float32), opts, sampling_rate=sr)
    return [(float(t["start"]) / sr, float(t["end"]) / sr) for t in stamps]


def energy_regions(audio: np.ndarray, sr: int = WHISPER_SR, *, frame_s: float = ENERGY_FRAME_S,
                   db_above_floor: float = ENERGY_DB_ABOVE_FLOOR, min_speech_s: float = ENERGY_MIN_SPEECH_S,
                   min_silence_s: float = MIN_SILENCE_S, abs_min_db: float = ENERGY_ABS_MIN_DB
                   ) -> list[tuple[float, float]]:
    """RMS-energy VAD: a frame is speech when its level exceeds the noise floor (10th percentile of
    frame levels) by `db_above_floor` dB and `abs_min_db`; runs are then smoothed by the min
    silence / min speech rules."""
    n = max(1, round(frame_s * sr))
    nf = len(audio) // n
    if nf == 0:
        return []
    frames = np.asarray(audio[: nf * n], dtype=np.float32).reshape(nf, n)
    level_db = 20.0 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9)
    floor = float(np.percentile(level_db, 10))
    thr = max(floor + db_above_floor, abs_min_db)
    active = level_db > thr
    runs: list[tuple[int, int]] = []
    start = None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, nf))
    regions = [(s * n / sr, e * n / sr) for s, e in runs]
    regions = merge_regions(regions, min_silence_s)
    return [(s, e) for s, e in regions if e - s >= min_speech_s]


# --- entry points -------------------------------------------------------------

def detect(wav_path: str | Path, backend: str = "auto") -> VadResult:
    """Speech regions of a wav. `backend` is "silero", "energy" or "auto" (silero, else energy)."""
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(wav_path)
    audio = load_audio_16k(wav_path)
    if backend == "energy":
        return VadResult(energy_regions(audio), "energy")
    if backend not in ("auto", "silero"):
        raise ValueError(f"unknown VAD backend {backend!r}")
    try:
        return VadResult(silero_regions(audio), "silero")
    except Exception as e:  # any import/runtime failure falls back in auto mode
        if backend == "silero":
            raise
        log.warning("%s: silero VAD unavailable (%s); using energy VAD", wav_path.name, e)
        return VadResult(energy_regions(audio), "energy", error=f"{type(e).__name__}: {e}")


def speech_regions(wav_path: str | Path, backend: str = "auto") -> list[tuple[float, float]]:
    """`[(start_s, end_s), ...]` of speech-like activity in `wav_path` (seconds from sample 0)."""
    return detect(wav_path, backend).regions
