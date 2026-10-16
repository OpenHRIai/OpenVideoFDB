"""Scoring pipeline over a run directory.

The benchmark unit is a manifest ROW = (clip_id, bucket); a clip can appear in both
buckets (e.g. Laughter perception + generation) and then shares one
`runs/<name>/<clip_id>/` directory (same `run.json`, same `agent.wav`). Scoring
therefore iterates manifest rows, not directories, and writes per-row outputs under
a per-bucket subdirectory:

    runs/<name>/<clip_id>/agent.wav                 (shared by both rows)
    runs/<name>/<clip_id>/agent.words.json          (ASR cache, clip level)
    runs/<name>/<clip_id>/<bucket>/timing.json
    runs/<name>/<clip_id>/<bucket>/judge.json
    runs/<name>/<clip_id>/<bucket>/judge/<axis>_<judge>.json

`score_timing(run_dir)`: ASR -> segments -> overlap / yield / timing for every row
whose clip dir exists; writes `timing_summary.json` at the run root (n = rows).
`score(run_dir, judge, axes)` (WS5) runs `score_timing` then the perception LLM
judge over every perception row, writing `judge_summary.json` (n = rows).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from statistics import mean, stdev

from ovfdb.schema import AgentRole, AgentRun, Axis, Bucket, Sample, TimingClass, read_manifest
from ovfdb.score import asr
from ovfdb.score import judge as judge_mod
from ovfdb.score.segments import format_partition, partition, words_to_segments
from ovfdb.score.timing import TimingResult, aggregate, evaluate, overlap_summary, yield_analysis

log = logging.getLogger(__name__)
DEFAULT_MANIFEST = "manifest/ovfdb_v0.jsonl"


@lru_cache(maxsize=8)
def _samples(manifest: str) -> tuple[Sample, ...]:
    return tuple(read_manifest(manifest))


def row_dir(clip_dir: Path, bucket: Bucket | str) -> Path:
    """`runs/<name>/<clip_id>/<bucket>/` — per-row output directory."""
    return Path(clip_dir) / Bucket(bucket).value


def row_key(sample: Sample) -> str:
    return f"{sample.clip_id}/{sample.bucket.value}"


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


def iter_rows(run_dir: Path, manifest: str) -> tuple[list[tuple[Sample, Path, AgentRun]], list[dict]]:
    """Manifest rows with an existing clip dir, in manifest order, plus `skipped` notes.

    Returns ([(sample, clip_dir, run), ...], skipped). Rows whose `runs/<name>/<clip_id>/run.json`
    is missing are not listed (the run never produced them); run dirs absent from the manifest are
    reported in `skipped`.
    """
    rows: list[tuple[Sample, Path, AgentRun]] = []
    seen: set[str] = set()
    runs: dict[str, AgentRun] = {}
    for sample in _samples(manifest):
        clip_dir = run_dir / sample.clip_id
        if not (clip_dir / "run.json").exists():
            continue
        if sample.clip_id not in runs:
            runs[sample.clip_id] = _load_run(clip_dir / "run.json")
        rows.append((sample, clip_dir, runs[sample.clip_id]))
        seen.add(sample.clip_id)
    skipped = [{"clip_id": d.name, "bucket": None, "reason": f"clip not in manifest {manifest}"}
               for d in iter_clip_dirs(run_dir) if d.name not in seen]
    return rows, skipped


def score_timing(run_dir: str | Path, manifest: str | None = None, *, asr_model: str = asr.DEFAULT_MODEL,
                 asr_backend: str = asr.DEFAULT_BACKEND, force: bool = False) -> dict:
    """ASR + timing metrics for every manifest row in `run_dir`; writes `<clip>/<bucket>/timing.json`
    and `timing_summary.json` (n = rows, keyed by (clip_id, bucket)).

    The manifest is `manifest` if given, else the path stored in `run.json` meta (`meta["manifest"]`),
    else `<run_dir>/manifest.jsonl`, else `manifest/ovfdb_v0.jsonl`. Rows without a timing class
    still get a timing.json (segments, overlap line, partition) with `timing: null`. ASR runs once
    per clip (cached in `agent.words.json`) even when the clip has rows in both buckets.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    man = _resolve_manifest(run_dir, manifest)
    if not man or not Path(man).exists():
        raise FileNotFoundError(f"manifest not found: {man!r}")
    rows, skipped = iter_rows(run_dir, man)
    per_row: list[dict] = []
    by_dynamic: dict[str, list[TimingResult]] = {}
    for sample, clip_dir, run in rows:
        out_dir = row_dir(clip_dir, sample.bucket)
        out_path = out_dir / "timing.json"
        if out_path.exists() and not force:
            payload = json.loads(out_path.read_text())
        else:
            payload = score_clip(clip_dir, sample, run, asr_model=asr_model, asr_backend=asr_backend)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        per_row.append(payload)
        if payload.get("timing"):
            by_dynamic.setdefault(payload["dynamic_type"], []).append(_result_from_payload(payload))
    summary = {
        "run_dir": str(run_dir),
        "manifest": man,
        "n_rows": len(per_row),
        "n_clips": len({p["clip_id"] for p in per_row}),
        "n_timed": sum(1 for p in per_row if p.get("timing")),
        "skipped": skipped,
        "aggregate": aggregate(by_dynamic),
        "rows": [
            {"clip_id": p["clip_id"], "bucket": p["bucket"], "dynamic_type": p["dynamic_type"],
             "timing_class": p["timing_class"],
             "passed": p["timing"]["passed"] if p.get("timing") else None,
             "latency_ms": p["timing"]["latency_ms"] if p.get("timing") else None}
            for p in per_row
        ],
    }
    (run_dir / "timing_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def _resolve_manifest(run_dir: Path, manifest: str | None) -> str | None:
    """Explicit arg -> run.json meta -> <run_dir>/manifest.jsonl -> manifest/ovfdb_v0.jsonl."""
    if manifest and Path(manifest).exists():
        return str(manifest)
    for clip_dir in iter_clip_dirs(run_dir):
        m = _load_run(clip_dir / "run.json").meta.get("manifest")
        if m and Path(m).exists():
            return str(m)
        break
    for cand in (run_dir / "manifest.jsonl", Path(DEFAULT_MANIFEST)):
        if cand.exists():
            return str(cand)
    return manifest


def _parse_axes(axes: str | None) -> set[Axis] | None:
    if axes in (None, "", "all"):
        return None
    return {Axis(a.strip()) for a in str(axes).split(",") if a.strip()}


def _stats(values: list[float]) -> dict:
    n = len(values)
    return {"mean": mean(values) if n else None, "sd": stdev(values) if n > 1 else (0.0 if n else None), "n": n}


def _clip_judge_payload(sample: Sample, run: AgentRun, judge: str, results: dict[str, judge_mod.JudgeResult],
                        skipped_axes: list[str], existing: dict | None) -> dict:
    axes = {a: {"rating": r.rating, "analysis": r.analysis, "reasoning": r.reasoning, "rubric": r.rubric,
                "cached": r.cached, "usage": r.usage} for a, r in results.items()}
    overall = mean(r.rating for r in results.values()) if results else None
    block = {"judge": judge, "axes": axes, "overall": overall, "skipped_axes": skipped_axes}
    by_judge = dict((existing or {}).get("by_judge") or {})
    by_judge[judge] = block
    return {
        "clip_id": sample.clip_id, "provider": run.provider, "mode": run.mode, "bucket": sample.bucket.value,
        "dynamic_type": sample.dynamic_type.value, "agent_role": sample.agent_role.value,
        "has_caption": bool((sample.av_caption or "").strip()),
        **block, "by_judge": by_judge,
    }


def score(run_dir: str | Path, judge: str = judge_mod.DEFAULT_JUDGE, axes: str = "all",
          manifest: str | None = None, *, force: bool = False) -> dict:
    """WS5: `score_timing` (reuses `<bucket>/timing.json`) + perception judge on every perception row.

    `axes` is "all" or a comma list of axis values (e.g. "fluency,conversational_flow"); generation
    axes and generation-bucket rows are skipped with a note. Writes `<clip>/<bucket>/judge.json`
    (results of this judge at top level, every judge so far under `by_judge`) and
    `<run_dir>/judge_summary.json`: per-axis mean/sd/n per dynamic and overall (n = rows), per-row
    `overall` = mean of its axes, token usage.
    """
    run_dir = Path(run_dir)
    manifest = _resolve_manifest(run_dir, manifest)
    timing_summary = score_timing(run_dir, manifest=manifest)
    manifest = timing_summary["manifest"]
    wanted = _parse_axes(axes)
    rows_out: list[dict] = []
    skipped: list[dict] = list(timing_summary.get("skipped", []))
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "n_calls": 0, "n_cached": 0}
    rows, _ = iter_rows(run_dir, manifest)
    for sample, clip_dir, run in rows:
        out_dir = row_dir(clip_dir, sample.bucket)
        tpath = out_dir / "timing.json"
        if not tpath.exists():
            continue                      # score_timing already recorded why it was skipped
        if sample.bucket is not Bucket.PERCEPTION:
            skipped.append({"clip_id": sample.clip_id, "bucket": sample.bucket.value,
                            "reason": f"{sample.bucket.value} bucket: perception judge n/a"})
            continue
        timing_json = json.loads(tpath.read_text())
        sel = [a for a in sample.axes if wanted is None or a in wanted]
        skipped_axes = [a.value for a in sample.axes if a not in judge_mod.PERCEPTION_AXES]
        results = judge_mod.score_sample(sample, timing_json, judge, axes=sel, cache_dir=out_dir / "judge",
                                         force=force)
        for r in results.values():
            if r.cached:
                usage["n_cached"] += 1
            else:
                for k in ("prompt_tokens", "completion_tokens", "n_calls"):
                    usage[k] += int(r.usage.get(k, 0) or 0)
        jpath = out_dir / "judge.json"
        existing = json.loads(jpath.read_text()) if jpath.exists() else None
        payload = _clip_judge_payload(sample, run, judge, results, skipped_axes, existing)
        jpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        rows_out.append(payload)

    axis_names = sorted({a for c in rows_out for a in c["axes"]})
    per_dynamic: dict[str, dict] = {}
    for dyn in sorted({c["dynamic_type"] for c in rows_out}):
        cs = [c for c in rows_out if c["dynamic_type"] == dyn]
        per_dynamic[dyn] = {a: _stats([c["axes"][a]["rating"] for c in cs if a in c["axes"]]) for a in axis_names
                            if any(a in c["axes"] for c in cs)}
        per_dynamic[dyn]["overall"] = _stats([c["overall"] for c in cs if c["overall"] is not None])
    summary = {
        "run_dir": str(run_dir),
        "judge": judge,
        "manifest": manifest,
        "n_rows": timing_summary.get("n_rows", 0),
        "n_clips": timing_summary.get("n_clips", 0),
        "n_judged": len(rows_out),
        "skipped": skipped,
        "per_axis": {a: _stats([c["axes"][a]["rating"] for c in rows_out if a in c["axes"]]) for a in axis_names},
        "overall": _stats([c["overall"] for c in rows_out if c["overall"] is not None]),
        "per_dynamic": per_dynamic,
        "usage": {**usage, "est_cost_usd": judge_mod.estimate_cost_usd(usage, judge)},
        "timing": timing_summary.get("aggregate", {}),
        "rows": [{"clip_id": c["clip_id"], "bucket": c["bucket"], "dynamic_type": c["dynamic_type"],
                  "overall": c["overall"], "axes": {a: v["rating"] for a, v in c["axes"].items()}}
                 for c in rows_out],
    }
    (run_dir / "judge_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    log.info("judged %d/%d rows with %s; overall %s", len(rows_out), summary["n_rows"], judge, summary["overall"])
    return summary
