"""ovfdb.score.vad: energy VAD on synthetic audio, Silero on a real GT clip when present,
and the pipeline's VAD -> segments path (with fallback)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ovfdb.schema import AgentRun, Bucket, DynamicType, Sample, Word, write_manifest
from ovfdb.score import asr, pipeline, vad

SR = 16000


def synth(bursts: list[tuple[float, float]], dur: float = 6.0, noise_db: float = -60.0, seed: int = 0) -> np.ndarray:
    """White noise floor plus noise bursts 30 dB louder in each (start, end) window."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(int(dur * SR)).astype(np.float32) * 10 ** (noise_db / 20)
    for s, e in bursts:
        a, b = int(s * SR), int(e * SR)
        x[a:b] += rng.standard_normal(b - a).astype(np.float32) * 10 ** ((noise_db + 30) / 20)
    return x


def test_energy_regions_find_bursts():
    regs = vad.energy_regions(synth([(1.0, 1.8), (3.0, 3.5)]))
    assert len(regs) == 2
    assert regs[0] == pytest.approx((1.0, 1.8), abs=0.05) and regs[1] == pytest.approx((3.0, 3.5), abs=0.05)


def test_energy_regions_min_silence_merges_and_min_speech_drops():
    regs = vad.energy_regions(synth([(1.0, 1.5), (1.7, 2.2)]))             # 0.2 s gap < 0.3 s -> one region
    assert len(regs) == 1 and regs[0] == pytest.approx((1.0, 2.2), abs=0.05)
    regs = vad.energy_regions(synth([(1.0, 1.5), (2.0, 2.5)]))             # 0.5 s gap -> two
    assert len(regs) == 2
    assert vad.energy_regions(synth([(1.0, 1.08)])) == []                    # 80 ms < 150 ms min speech


def test_energy_regions_silence_and_empty():
    assert vad.energy_regions(np.zeros(SR * 2, dtype=np.float32)) == []     # digital silence: abs floor holds
    assert vad.energy_regions(np.zeros(0, dtype=np.float32)) == []
    assert vad.energy_regions(synth([], dur=3.0)) == []                      # noise only: nothing 12 dB above floor


def test_detect_backends_and_fallback(tmp_path, monkeypatch):
    wav = tmp_path / "a.wav"
    sf.write(wav, synth([(1.0, 1.8)]), SR, subtype="PCM_16")
    r = vad.detect(wav, backend="energy")
    assert r.backend == "energy" and len(r.regions) == 1 and r.error == ""
    assert vad.speech_regions(wav, backend="energy") == r.regions

    def boom(*a, **k):
        raise RuntimeError("no onnx")

    monkeypatch.setattr(vad, "silero_regions", boom)
    r = vad.detect(wav, backend="auto")
    assert r.backend == "energy" and "no onnx" in r.error and len(r.regions) == 1
    with pytest.raises(RuntimeError):
        vad.detect(wav, backend="silero")
    with pytest.raises(ValueError):
        vad.detect(wav, backend="nope")
    with pytest.raises(FileNotFoundError):
        vad.detect(tmp_path / "missing.wav")


GT_CLIP = Path("runs/gt/V00_S0314_I00000132_P0421_c04/agent.wav")


@pytest.mark.skipif(not GT_CLIP.exists(), reason="GT run audio not present")
def test_silero_finds_non_lexical_backchannel_in_gt_clip():
    # Verbal Backchanneling GT row: whisper transcribes nothing in [29.72, 30.79] but the partner says "mhm".
    r = vad.detect(GT_CLIP, backend="silero")
    assert r.backend == "silero"
    inside = [(s, e) for s, e in r.regions if s >= 29.72 - 0.25 and e <= 30.79 + 0.25]
    assert len(inside) == 1 and 0.1 <= inside[0][1] - inside[0][0] < 1.1


# --- pipeline wiring -------------------------------------------------------------------------

def _run_dir(tmp_path, audio: np.ndarray | None) -> tuple[Path, Path]:
    manifest = tmp_path / "manifest.jsonl"
    write_manifest([Sample(clip_id="c1", conversation_id="x", bucket=Bucket.GENERATION,
                           dynamic_type=DynamicType.VERBAL_BACKCHANNELING, dynamic_start_s=2.0, dynamic_end_s=3.0,
                           duration_s=6.0, user_audio_path="u.wav", user_video_path="u.mp4")], manifest)
    run_dir = tmp_path / "runs" / "demo"
    d = run_dir / "c1"
    d.mkdir(parents=True)
    if audio is None:
        (d / "agent.wav").write_bytes(b"")
    else:
        sf.write(d / "agent.wav", audio, SR, subtype="PCM_16")
    run = AgentRun(clip_id="c1", provider="fake", mode="av", agent_audio_path=str(d / "agent.wav"),
                   meta={"manifest": str(manifest)})
    (d / "run.json").write_text(json.dumps(asdict(run)))
    return run_dir, manifest


def test_pipeline_uses_vad_segments(tmp_path, monkeypatch):
    # audible at 2.3-2.6 (no words: "mhm") and 4.0-5.0 ("so anyway"); whisper onset lags the burst by 0.2 s
    run_dir, _ = _run_dir(tmp_path, synth([(2.3, 2.6), (4.0, 5.0)]))
    monkeypatch.setattr(asr, "load_or_transcribe", lambda wav, **kw: [Word("so", 4.2, 4.5), Word("anyway", 4.6, 5.1)])
    monkeypatch.setattr(vad, "silero_regions", lambda audio, *a, **k: vad.energy_regions(audio))
    summary = pipeline.score_timing(run_dir)
    t = json.loads((run_dir / "c1" / "generation" / "timing.json").read_text())
    assert t["segments_source"]["source"] == "vad+asr" and t["segments_source"]["n_regions"] == 2
    assert [(round(s["start"], 1), round(s["end"], 1), s["text"], s["n_words"]) for s in t["segments"]] == [
        (2.3, 2.6, "", 0), (4.0, 5.0, "so anyway", 2)]
    assert t["transcript"] == "so anyway"
    assert t["timing"]["passed"] is True and t["timing"]["details"]["n_backchannels"] == 1
    assert summary["aggregate"]["Verbal Backchanneling"]["tor_alignment"] == 1.0


def test_pipeline_falls_back_to_words_when_vad_fails(tmp_path, monkeypatch, caplog):
    run_dir, _ = _run_dir(tmp_path, None)                                   # empty wav: unreadable
    monkeypatch.setattr(asr, "load_or_transcribe", lambda wav, **kw: [Word("mhm", 2.2, 2.5)])
    pipeline.score_timing(run_dir)
    t = json.loads((run_dir / "c1" / "generation" / "timing.json").read_text())
    assert t["segments_source"]["source"] == "asr" and t["segments_source"]["vad_backend"] is None
    assert "error" in t["segments_source"]
    assert t["segments"] == [{"start": 2.2, "end": 2.5, "text": "mhm", "n_words": 1}]
    assert t["timing"]["passed"] is True
