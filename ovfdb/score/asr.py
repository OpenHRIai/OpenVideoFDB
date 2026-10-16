"""Word-timestamped ASR for agent audio.

`transcribe(wav) -> list[Word]` runs faster-whisper (CPU, int8) with
`word_timestamps=True`; `load_or_transcribe` caches the words as
`<stem>.words.json` next to the wav so re-scoring never re-runs the model.
Optional `deepgram` backend is a stub (port of fugubook `DeepgramSTT` to do).
Spec: plans/WS4-scoring-timing.md.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from ovfdb.schema import Word

if TYPE_CHECKING:
    import numpy as np

WHISPER_SR = 16000
DEFAULT_MODEL = "small.en"
DEFAULT_BACKEND = "faster_whisper"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
CACHE_SUFFIX = ".words.json"


def cache_path(wav_path: str | Path) -> Path:
    """`runs/x/clip/agent.wav` -> `runs/x/clip/agent.words.json`."""
    return Path(wav_path).with_suffix(CACHE_SUFFIX)


@lru_cache(maxsize=2)
def _whisper(model: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel  # lazy: heavy import, model download on first use

    return WhisperModel(model, device=device, compute_type=compute_type)


def load_audio_16k(wav_path: str | Path) -> np.ndarray:
    """Mono float32 samples at 16 kHz (faster-whisper's native rate). Resamples if needed.

    Decoded with soundfile rather than faster-whisper's own `decode_audio`, whose PyAV
    call (`av.open(..., metadata_errors=)`) breaks on the PyAV version pinned here.
    """
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != WHISPER_SR:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(WHISPER_SR, sr)
        audio = resample_poly(audio, WHISPER_SR // g, sr // g).astype(np.float32)
    return audio


def _transcribe_faster_whisper(wav_path: Path, model: str, *, device: str, compute_type: str,
                               vad_filter: bool, language: str | None) -> list[Word]:
    wm = _whisper(model, device, compute_type)
    kwargs = {"word_timestamps": True, "vad_filter": vad_filter}
    if language:
        kwargs["language"] = language
    segments, _info = wm.transcribe(load_audio_16k(wav_path), **kwargs)
    words: list[Word] = []
    for seg in segments:                     # generator: transcription happens here
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text=text, start=float(w.start), end=float(w.end)))
    return words


def _transcribe_deepgram(wav_path: Path, model: str) -> list[Word]:
    raise NotImplementedError("deepgram backend not ported yet (fugubook DeepgramSTT)")


def transcribe(wav_path: str | Path, model: str = DEFAULT_MODEL, backend: str = DEFAULT_BACKEND, *,
               device: str = DEFAULT_DEVICE, compute_type: str = DEFAULT_COMPUTE_TYPE,
               vad_filter: bool = True, language: str | None = None) -> list[Word]:
    """Word-timestamped transcript of a 16 kHz mono wav. Times are seconds from sample 0.

    `vad_filter=True` suppresses Whisper's hallucinations on long silence, which agent
    recordings (mostly silence) otherwise trigger.
    """
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(wav_path)
    if backend == "faster_whisper":
        return _transcribe_faster_whisper(wav_path, model, device=device, compute_type=compute_type,
                                          vad_filter=vad_filter, language=language)
    if backend == "deepgram":
        return _transcribe_deepgram(wav_path, model)
    raise ValueError(f"unknown ASR backend {backend!r}")


def save_words(words: list[Word], path: str | Path, *, model: str = "", backend: str = "") -> None:
    payload = {"model": model, "backend": backend,
               "words": [{"text": w.text, "start": w.start, "end": w.end} for w in words]}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=0))


def load_words(path: str | Path) -> list[Word]:
    data = json.loads(Path(path).read_text())
    items = data["words"] if isinstance(data, dict) else data
    return [Word(text=w["text"], start=float(w["start"]), end=float(w["end"])) for w in items]


def load_or_transcribe(wav_path: str | Path, model: str = DEFAULT_MODEL, backend: str = DEFAULT_BACKEND,
                       *, force: bool = False, **kw) -> list[Word]:
    """Return cached words from `<stem>.words.json` if present, else transcribe and cache."""
    wav_path = Path(wav_path)
    cp = cache_path(wav_path)
    if cp.exists() and not force:
        return load_words(cp)
    words = transcribe(wav_path, model=model, backend=backend, **kw)
    save_words(words, cp, model=model, backend=backend)
    return words
