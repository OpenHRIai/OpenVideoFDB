"""Scoring pipeline over a run directory.

`score_timing(run_dir)`: for every `runs/<name>/<clip_id>/` holding `run.json`
(an `AgentRun`) and `agent.wav`, run ASR -> segments -> overlap / yield /
timing, write `timing.json` per clip and `timing_summary.json` at the run root.
`score(...)` (WS5) adds the LLM judge on top; it is a stub here.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from ovfdb.schema import AgentRole, AgentRun, Sample, TimingClass, read_manifest
from ovfdb.score import asr
from ovfdb.score.segments import format_partition, partition, words_to_segments
from ovfdb.score.timing import TimingResult, aggregate, evaluate, overlap_summary, yield_analysis


@lru_cache(maxsize=8)
def _samples_by_id(manifest: str) -> dict[str, Sample]:
    return {s.clip_id: s for s in read_manifest(manifest)}


def _load_run(path: Path) -> AgentRun:
    d = json.loads(path.read_text())
    known = AgentRun.__dataclass_fields__
    return AgentRun(**{k: v for k, v in d.items() if k in known})


def _resolve(p: str | None, base: Path, default: str) -> Path:
    if not p:
        return base / default
    q = Path(p)
    if q.is_absolute() or q.exists():
        return q
    if (base / q.name).exists():
        return base / q.name
    return q


def score_clip(clip_dir: Path, sample: Sample, run: AgentRun, *, asr_model: str = asr.DEFAULT_MODEL,
               asr_backend: str = asr.DEFAULT_BACKEND) -> dict:
    """ASR + derived signals + timing for one clip. Returns the timing.json payload."""
    wav = _resolve(run.agent_audio_path, clip_dir, "agent.wav")
    words = asr.load_or_transcribe(wav, model=asr_model, backend=asr_backend)
    segs = words_to_segments(words)
    ds, de, end = sample.dynamic_start_s, sample.dynamic_end_s, sample.duration_s
    ov = overlap_summary(segs, ds, de, end)
    parts = partition(segs, ds, de, end)
    out: dict = {
        "clip_id": sample.clip_id,
        "provider": run.provider,
        "mode": run.mode,
        "bucket": sample.bucket.value,
        "dynamic_type": sample.dynamic_type.value,
        "dynamic_start_s": ds,
        "dynamic_end_s": de,
        "duration_s": end,
        "agent_role": sample.agent_role.value,
        "asr": {"model": asr_model, "backend": asr_backend, "n_words": len(words)},
        "segments": [asdict(s) for s in segs],
        "transcript": " ".join(s.text for s in segs) or "[no speech]",
        "overlap_line": ov.line(),
        "overlap": {
            "total_in_window_s": round(ov.total_in_window_s, 3),
            "pre_activity": round(ov.pre_activity, 4),
            "in_activity": round(ov.in_activity, 4),
            "post_activity": round(ov.post_activity, 4),
        },
        "partition_block": format_partition(parts),
        "yield_block": None,
        "timing_class": None,
        "timing": None,
    }
    if sample.agent_role is AgentRole.YIELDING:
        ya = yield_analysis(segs, ds, de, end)
        out["yield_block"] = ya.block()
        out["yield"] = asdict(ya)
    cls = sample.timing_class
    if cls is not None:
        r = evaluate(segs, ds, de, cls, agent_speaks_first=sample.agent_speaks_first, clip_end=end)
        out["timing_class"] = cls.value
        out["timing"] = {
            "passed": r.passed,
            "takeover": r.takeover,
            "expected_takeover": r.expected_takeover,
            "latency_ms": r.latency_ms,
            "details": r.details,
        }
    return out


def _result_from_payload(p: dict) -> TimingResult:
    t = p["timing"]
    return TimingResult(timing_class=TimingClass(p["timing_class"]), passed=t["passed"], takeover=t["takeover"],
                        expected_takeover=t["expected_takeover"], latency_ms=t["latency_ms"],
                        details=t.get("details", {}))


def iter_clip_dirs(run_dir: Path):
    for d in sorted(run_dir.iterdir()):
        if d.is_dir() and (d / "run.json").exists():
            yield d


def score_timing(run_dir: str | Path, manifest: str | None = None, *, asr_model: str = asr.DEFAULT_MODEL,
                 asr_backend: str = asr.DEFAULT_BACKEND, force: bool = False) -> dict:
    """ASR + timing metrics for every clip in `run_dir`; writes timing.json + timing_summary.json.

    The Sample for each clip comes from the manifest path stored in `run.json` meta
    (`meta["manifest"]`), falling back to `manifest`. Clips without a timing class still
    get a timing.json (segments, overlap line, partition) with `timing: null`.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    per_clip: list[dict] = []
    by_dynamic: dict[str, list[TimingResult]] = {}
    skipped: list[dict] = []
    for clip_dir in iter_clip_dirs(run_dir):
        out_path = clip_dir / "timing.json"
        run = _load_run(clip_dir / "run.json")
        man = run.meta.get("manifest") or manifest
        if not man or not Path(man).exists():
            skipped.append({"clip_id": run.clip_id, "reason": f"manifest not found: {man!r}"})
            continue
        sample = _samples_by_id(str(man)).get(run.clip_id)
        if sample is None:
            skipped.append({"clip_id": run.clip_id, "reason": f"clip not in manifest {man}"})
            continue
        if out_path.exists() and not force:
            payload = json.loads(out_path.read_text())
        else:
            payload = score_clip(clip_dir, sample, run, asr_model=asr_model, asr_backend=asr_backend)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        per_clip.append(payload)
        if payload.get("timing"):
            by_dynamic.setdefault(payload["dynamic_type"], []).append(_result_from_payload(payload))
    summary = {
        "run_dir": str(run_dir),
        "n_clips": len(per_clip),
        "n_timed": sum(1 for p in per_clip if p.get("timing")),
        "skipped": skipped,
        "aggregate": aggregate(by_dynamic),
        "clips": [
            {"clip_id": p["clip_id"], "dynamic_type": p["dynamic_type"], "timing_class": p["timing_class"],
             "passed": p["timing"]["passed"] if p.get("timing") else None,
             "latency_ms": p["timing"]["latency_ms"] if p.get("timing") else None}
            for p in per_clip
        ],
    }
    (run_dir / "timing_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def score(run_dir: str | Path, judge: str = "gpt-4o", axes: str = "all", manifest: str | None = None) -> dict:
    """WS5: timing + LLM judge. Timing part runs; the judge is not implemented yet."""
    score_timing(run_dir, manifest=manifest)
    raise NotImplementedError("WS5 judge")
