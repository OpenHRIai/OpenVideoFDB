"""Table-1 style summaries over scored run directories (plans/WS5-judge.md).

Inputs per run dir: `<clip>/<bucket>/judge.json` (written by `pipeline.score`) and
`<clip>/<bucket>/timing.json` (WS4), one pair per manifest row = (clip_id, bucket).
`summarise` gives one row per run dir with the three perception axes, Overall (mean
of each row's available axes), TOR-Alignment % and median latency, each with a 95 %
bootstrap CI over rows (1000 resamples, seed 0). `per_dynamic` breaks the same
metrics down by dynamic (paper Table 11). `agreement` compares two judges' cached
per-axis results (% within 1 point). `write` renders markdown + CSV.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable
from pathlib import Path

import numpy as np
import pandas as pd

from ovfdb.schema import Axis, Bucket

N_BOOT = 1000
SEED = 0

#: (axis value, column label) in table order.
AXIS_COLUMNS: list[tuple[str, str]] = [
    (Axis.FLUENCY.value, "Fluency"),
    (Axis.CONVERSATIONAL_FLOW.value, "Conv. Flow"),
    (Axis.SEMANTIC_GROUNDING.value, "Grounding"),
]
METRIC_COLUMNS = [label for _, label in AXIS_COLUMNS] + ["Overall", "TOR-Align %", "Latency ms"]


# --- loading ---------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _axes_from_judge(j: dict | None, judge: str | None) -> tuple[dict[str, float], float | None, str | None]:
    """(axis -> rating, overall, judge name) from a judge.json, optionally selecting a judge in `by_judge`."""
    if not j:
        return {}, None, None
    block = j
    if judge is not None and j.get("judge") != judge:
        block = (j.get("by_judge") or {}).get(judge) or {}
        if not block:
            return {}, None, None
    axes = {a: float(v["rating"]) if isinstance(v, dict) else float(v) for a, v in (block.get("axes") or {}).items()}
    overall = block.get("overall")
    if overall is None and axes:
        overall = sum(axes.values()) / len(axes)
    return axes, overall, block.get("judge", j.get("judge"))


def iter_row_dirs(run_dir: Path):
    """Yield (clip_dir, bucket, row_dir) for every `<clip>/<bucket>/` under `run_dir`, sorted."""
    for d in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        for bucket in Bucket:
            rd = d / bucket.value
            if rd.is_dir():
                yield d, bucket.value, rd


def load_run(run_dir: str | Path, judge: str | None = None) -> dict:
    """{"run", "provider", "mode", "judge", "clips": [{clip_id, bucket, dynamic_type, axes, overall, passed, latency_ms}]}.

    One entry per scored manifest row (`<clip>/<bucket>/`), so a clip present in both buckets
    contributes two entries.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    provider = mode = judge_name = None
    clips: list[dict] = []
    for d, bucket, rd in iter_row_dirs(run_dir):
        j = _read_json(rd / "judge.json")
        t = _read_json(rd / "timing.json")
        if j is None and t is None:
            continue
        src = t or j or {}
        provider = provider or src.get("provider")
        mode = mode or src.get("mode")
        axes, overall, jn = _axes_from_judge(j, judge)
        judge_name = judge_name or jn
        timing = (t or {}).get("timing") or {}
        clips.append({
            "clip_id": src.get("clip_id", d.name),
            "bucket": src.get("bucket", bucket),
            "dynamic_type": src.get("dynamic_type"),
            "axes": axes,
            "overall": overall,
            "passed": timing.get("passed"),
            "latency_ms": timing.get("latency_ms"),
        })
    if provider is None:
        r = _read_json(next(iter(run_dir.glob("*/run.json")), Path("/nonexistent")))
        if r:
            provider, mode = r.get("provider"), r.get("mode")
    return {"run": run_dir.name, "run_dir": str(run_dir), "provider": provider or run_dir.name, "mode": mode or "",
            "judge": judge or judge_name, "clips": clips}


# --- statistics ----------------------------------------------------------------------

def bootstrap_ci(values: Iterable[float], stat: Callable[[np.ndarray], np.ndarray] | None = None, *,
                 n_boot: int = N_BOOT, seed: int = SEED, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI of `stat` (default mean) over `values`; (nan, nan) when empty."""
    v = np.asarray([x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))], dtype=float)
    if v.size == 0:
        return (math.nan, math.nan)
    if v.size == 1:
        return (float(v[0]), float(v[0]))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, v.size, size=(n_boot, v.size))
    samples = v[idx]
    stats = np.mean(samples, axis=1) if stat is None else stat(samples)
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def _median_rows(a: np.ndarray) -> np.ndarray:
    return np.median(a, axis=1)


def _point(values: list[float], fn=np.mean) -> float:
    v = [x for x in values if x is not None]
    return float(fn(v)) if v else math.nan


def _metrics(clips: list[dict], *, n_boot: int, seed: int) -> dict:
    """Point estimates + CIs for one group of clips (a run or a run × dynamic)."""
    row: dict = {"n": len(clips)}
    for axis, label in AXIS_COLUMNS:
        vals = [c["axes"][axis] for c in clips if axis in c["axes"]]
        row[label] = _point(vals)
        row[f"{label}_lo"], row[f"{label}_hi"] = bootstrap_ci(vals, n_boot=n_boot, seed=seed)
        row[f"{label}_n"] = len(vals)
    ov = [c["overall"] for c in clips if c["overall"] is not None]
    row["Overall"] = _point(ov)
    row["Overall_lo"], row["Overall_hi"] = bootstrap_ci(ov, n_boot=n_boot, seed=seed)
    row["Overall_n"] = len(ov)
    passed = [100.0 * float(c["passed"]) for c in clips if c["passed"] is not None]
    row["TOR-Align %"] = _point(passed)
    row["TOR-Align %_lo"], row["TOR-Align %_hi"] = bootstrap_ci(passed, n_boot=n_boot, seed=seed)
    row["TOR-Align %_n"] = len(passed)
    lat = [float(c["latency_ms"]) for c in clips if c["latency_ms"] is not None]
    row["Latency ms"] = _point(lat, np.median)
    row["Latency ms_lo"], row["Latency ms_hi"] = bootstrap_ci(lat, _median_rows, n_boot=n_boot, seed=seed)
    row["Latency ms_n"] = len(lat)
    return row


# --- public tables ---------------------------------------------------------------------

def summarise(run_dirs: Iterable[str | Path], *, judge: str | None = None, n_boot: int = N_BOOT,
              seed: int = SEED) -> pd.DataFrame:
    """One row per run dir: provider, mode, n, each metric with `<metric>_lo/_hi` 95 % bootstrap CI columns."""
    rows = []
    for rd in run_dirs:
        r = load_run(rd, judge)
        row = {"run": r["run"], "provider": r["provider"], "mode": r["mode"], "judge": r["judge"]}
        row.update(_metrics(r["clips"], n_boot=n_boot, seed=seed))
        rows.append(row)
    return pd.DataFrame(rows)


def per_dynamic(run_dirs: Iterable[str | Path], *, judge: str | None = None, n_boot: int = N_BOOT,
                seed: int = SEED) -> pd.DataFrame:
    """One row per (run dir, dynamic) with the same metric/CI columns as `summarise`."""
    rows = []
    for rd in run_dirs:
        r = load_run(rd, judge)
        by_dyn: dict[str, list[dict]] = {}
        for c in r["clips"]:
            by_dyn.setdefault(c["dynamic_type"] or "?", []).append(c)
        for dyn in sorted(by_dyn):
            row = {"run": r["run"], "provider": r["provider"], "mode": r["mode"], "dynamic_type": dyn}
            row.update(_metrics(by_dyn[dyn], n_boot=n_boot, seed=seed))
            rows.append(row)
    return pd.DataFrame(rows)


def agreement(run_dir: str | Path, judge_a: str, judge_b: str) -> dict:
    """Cross-judge agreement from `<clip>/<bucket>/judge/<axis>_<judge>.json` caches.

    {axis: {"n", "within_1", "exact", "mean_abs_diff", "mean_a", "mean_b"}, "overall": {...}} with
    percentages in [0, 100]. Only rows/axes rated by both judges count.
    """
    run_dir = Path(run_dir)
    diffs: dict[str, list[tuple[float, float]]] = {}
    for _, _, rd in iter_row_dirs(run_dir):
        jd = rd / "judge"
        if not jd.is_dir():
            continue
        for axis, _ in AXIS_COLUMNS:
            a = _read_json(jd / f"{axis}_{judge_a}.json")
            b = _read_json(jd / f"{axis}_{judge_b}.json")
            if a and b and "rating" in a and "rating" in b:
                diffs.setdefault(axis, []).append((float(a["rating"]), float(b["rating"])))
    out: dict = {}
    pooled: list[tuple[float, float]] = []
    for axis, pairs in diffs.items():
        out[axis] = _agree_stats(pairs)
        pooled.extend(pairs)
    out["overall"] = _agree_stats(pooled)
    return out


def _agree_stats(pairs: list[tuple[float, float]]) -> dict:
    n = len(pairs)
    if n == 0:
        return {"n": 0, "within_1": math.nan, "exact": math.nan, "mean_abs_diff": math.nan,
                "mean_a": math.nan, "mean_b": math.nan}
    d = [abs(a - b) for a, b in pairs]
    return {
        "n": n,
        "within_1": 100.0 * sum(x <= 1 for x in d) / n,
        "exact": 100.0 * sum(x == 0 for x in d) / n,
        "mean_abs_diff": sum(d) / n,
        "mean_a": sum(a for a, _ in pairs) / n,
        "mean_b": sum(b for _, b in pairs) / n,
    }


# --- rendering ---------------------------------------------------------------------------

def _fmt(x: float, digits: int) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{digits}f}"


def _cell(row: pd.Series, label: str) -> str:
    digits = 0 if label in ("TOR-Align %", "Latency ms") else 2
    v = row.get(label, math.nan)
    if isinstance(v, float) and math.isnan(v):
        return "—"
    lo, hi = row.get(f"{label}_lo", math.nan), row.get(f"{label}_hi", math.nan)
    return f"{_fmt(v, digits)} [{_fmt(lo, digits)}, {_fmt(hi, digits)}]"


def to_markdown(df: pd.DataFrame, id_cols: list[str]) -> str:
    """Markdown table: id columns + n + each metric as `point [lo, hi]`."""
    if df.empty:
        return "_(no runs)_\n"
    cols = id_cols + ["n"] + METRIC_COLUMNS
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = [str(row.get(c, "")) for c in id_cols] + [str(int(row["n"]))]
        cells += [_cell(row, m) for m in METRIC_COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write(run_dirs: Iterable[str | Path], per_dynamic: bool = False, out: str | Path = "results/summary.md", *,
          judge: str | None = None, n_boot: int = N_BOOT, seed: int = SEED) -> Path:
    """Write `<out>` (markdown) and `<out stem>.csv` (+ `<stem>_per_dynamic.csv` when requested)."""
    run_dirs = [Path(r) for r in run_dirs]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = summarise(run_dirs, judge=judge, n_boot=n_boot, seed=seed)
    df.to_csv(out.with_suffix(".csv"), index=False)
    judges = sorted({str(j) for j in df.get("judge", pd.Series(dtype=object)).dropna()}) if not df.empty else []
    note = (f"Judge: {', '.join(judges) or '—'}. n = manifest rows (clip, bucket) scored. "
            "Overall = mean of each perception row's available judge axes. "
            f"Brackets are 95 % bootstrap CIs over rows ({n_boot} resamples, seed {seed}). "
            "TOR-Align % = fraction of timed rows whose takeover matches the expected class; latency is the median.")
    parts = [
        "# OpenVideoFDB summary",
        "",
        f"Runs: {', '.join(str(r) for r in run_dirs)}  ",
        note,
        "",
        to_markdown(df, ["provider", "mode"]),
    ]
    if per_dynamic:
        pdf = _per_dynamic_table(run_dirs, judge=judge, n_boot=n_boot, seed=seed)
        pdf.to_csv(out.with_name(out.stem + "_per_dynamic.csv"), index=False)
        parts += ["## Per dynamic", "", to_markdown(pdf, ["provider", "mode", "dynamic_type"])]
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


#: `write()` takes a `per_dynamic: bool` flag (CLI contract), so the table builder needs another name there.
_per_dynamic_table = per_dynamic
