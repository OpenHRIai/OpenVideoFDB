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

#: (axis value, column label) in table order. Labels follow the VideoFDB project page / Table 1
#: (docs/reference/nvidia_project_page_leaderboard.txt): Fluency, Conv. Flow, Vis. Ground., Overall, Timing.
AXIS_COLUMNS: list[tuple[str, str]] = [
    (Axis.FLUENCY.value, "Fluency"),
    (Axis.CONVERSATIONAL_FLOW.value, "Conv. Flow"),
    (Axis.SEMANTIC_GROUNDING.value, "Vis. Ground."),
]
METRIC_COLUMNS = [label for _, label in AXIS_COLUMNS] + ["Overall", "TOR-Align %", "Latency ms"]
#: Paper-style columns: the three axes + Overall, then one "Timing" cell = "TOR-Align % / median latency ms".
PAPER_COLUMNS = [label for _, label in AXIS_COLUMNS] + ["Overall", "Timing"]

# --- naming (paper notation) -----------------------------------------------------------
#: Display name per (provider, model) as the project page spells it; fallback "<provider> <model>".
MODEL_NAMES: dict[tuple[str, str], str] = {
    ("human_gt", ""): "Human reference",
    ("random", ""): "Random baseline (mismatched partner)",
    ("gemini_live", "gemini-3.1-flash-live-preview"): "Gemini 3.1 Flash Live",
    ("gemini_live", "gemini-2.5-flash-native-audio-preview-09-2025"): "Gemini 2.5 Flash Native",
    ("gemini_live", "gemini-2.5-flash-preview-native-audio-dialog"): "Gemini 2.5 Flash Native",
    ("openai_realtime", "gpt-realtime"): "OpenAI gpt-realtime",
    ("openai_realtime", "gpt-realtime-mini"): "OpenAI gpt-realtime-mini",
    ("tavus", ""): "Tavus Griffin Lite",
    ("anam", ""): "Gemini 2.5 + Anam",
}
#: What the agent emits: "A" (audio only) or "AV" (audio + video). The human partner and the
#: mismatched-partner baseline are real people on camera, so AV.
OUTPUT_MODALITY: dict[str, str] = {
    "human_gt": "AV", "random": "AV", "gemini_live": "A", "openai_realtime": "A",
    "tavus": "AV", "anam": "AV", "keyframe": "AV",
}
#: Row-group order and headers as on the project page (Tables 1 and 2).
SETTING_GROUPS: list[tuple[str, str]] = [
    ("REF", "Human reference"),
    ("RANDOM", "Random baseline"),
    ("AV2AV", "Full-duplex AV2AV models"),
    ("AV2A", "Full-duplex speech-vision (AV2A)"),
    ("A2A", "Audio-only baselines (A2A; same agents, video withheld)"),
    ("A2AV", "Cascaded speech-to-avatar (A2AV)"),
]


def model_name(provider: str, model: str | None) -> str:
    model = (model or "").strip()
    return MODEL_NAMES.get((provider, model)) or MODEL_NAMES.get((provider, "")) or f"{provider} {model}".strip()


def setting(provider: str, mode: str) -> str:
    """Paper notation <input>2<output>: input AV when frames were streamed (`mode == "av"`), else A."""
    inp = "AV" if mode == "av" else "A"
    return f"{inp}2{OUTPUT_MODALITY.get(provider, 'A')}"


def setting_group(provider: str, mode: str) -> str:
    if provider == "human_gt":
        return "REF"
    if provider == "random":
        return "RANDOM"
    return setting(provider, mode)


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


def row_filter(manifest: str | Path | None, rows: int = 0) -> set[tuple[str, str]] | None:
    """{(clip_id, bucket)} of the first `rows` manifest rows (all when 0); None without a manifest.

    Lets a report compare runs on a common row set when one run dir also holds clips the others
    lack (e.g. the a2a runs hold 10 nonverbal clips that gt/random do not).
    """
    if not manifest:
        return None
    keys: set[tuple[str, str]] = set()
    with open(manifest, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if rows and i >= rows:
                break
            if line.strip():
                d = json.loads(line)
                keys.add((d["clip_id"], d["bucket"]))
    return keys


def load_run(run_dir: str | Path, judge: str | None = None,
             keep: set[tuple[str, str]] | None = None) -> dict:
    """{"run", "provider", "mode", "judge", "clips": [{clip_id, bucket, dynamic_type, axes, overall, passed, latency_ms}]}.

    One entry per scored manifest row (`<clip>/<bucket>/`), so a clip present in both buckets
    contributes two entries. `keep` (from `row_filter`) restricts the rows to those (clip_id, bucket).
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    provider = mode = judge_name = model = None
    clips: list[dict] = []
    for d, bucket, rd in iter_row_dirs(run_dir):
        j = _read_json(rd / "judge.json")
        t = _read_json(rd / "timing.json")
        if j is None and t is None:
            continue
        src = t or j or {}
        # run dirs are <clip_id> or <clip_id>__<bucket> (schema.run_dir_names): filter on the stored clip_id
        if keep is not None and (src.get("clip_id", d.name.split("__")[0]), bucket) not in keep:
            continue
        provider = provider or src.get("provider")
        mode = mode or src.get("mode")
        if model is None:
            r = _read_json(d / "run.json")
            model = (r or {}).get("model") or ""
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
            provider, mode, model = r.get("provider"), r.get("mode"), r.get("model")
    provider, mode = provider or run_dir.name, mode or ""
    return {"run": run_dir.name, "run_dir": str(run_dir), "provider": provider, "mode": mode, "model": model or "",
            "Model": model_name(provider, model), "Setting": setting(provider, mode),
            "group": setting_group(provider, mode), "judge": judge or judge_name, "clips": clips}


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
              seed: int = SEED, keep: set[tuple[str, str]] | None = None) -> pd.DataFrame:
    """One row per run dir: provider, mode, n, each metric with `<metric>_lo/_hi` 95 % bootstrap CI columns."""
    rows = []
    for rd in run_dirs:
        r = load_run(rd, judge, keep)
        row = {"run": r["run"], "Model": r["Model"], "Setting": r["Setting"], "group": r["group"],
               "provider": r["provider"], "mode": r["mode"], "model": r["model"], "judge": r["judge"]}
        row.update(_metrics(r["clips"], n_boot=n_boot, seed=seed))
        rows.append(row)
    return _paper_order(pd.DataFrame(rows))


def _paper_order(df: pd.DataFrame) -> pd.DataFrame:
    """Stable sort into the project page's group order (reference, random, AV2AV, AV2A, A2A, A2AV)."""
    if df.empty or "group" not in df:
        return df
    rank = {g: i for i, (g, _) in enumerate(SETTING_GROUPS)}
    key = df["group"].map(lambda g: rank.get(g, len(rank)))
    return df.assign(_k=key).sort_values("_k", kind="stable").drop(columns="_k").reset_index(drop=True)


def per_dynamic(run_dirs: Iterable[str | Path], *, judge: str | None = None, n_boot: int = N_BOOT,
                seed: int = SEED, keep: set[tuple[str, str]] | None = None) -> pd.DataFrame:
    """One row per (run dir, dynamic) with the same metric/CI columns as `summarise`."""
    rows = []
    for rd in run_dirs:
        r = load_run(rd, judge, keep)
        by_dyn: dict[str, list[dict]] = {}
        for c in r["clips"]:
            by_dyn.setdefault(c["dynamic_type"] or "?", []).append(c)
        for dyn in sorted(by_dyn):
            row = {"run": r["run"], "Model": r["Model"], "Setting": r["Setting"], "group": r["group"],
                   "provider": r["provider"], "mode": r["mode"], "model": r["model"], "dynamic_type": dyn}
            row.update(_metrics(by_dyn[dyn], n_boot=n_boot, seed=seed))
            rows.append(row)
    return _paper_order(pd.DataFrame(rows))


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
    """Markdown table with CIs: id columns + n + each metric as `point [lo, hi]`."""
    if df.empty:
        return "_(no runs)_\n"
    cols = id_cols + ["n"] + METRIC_COLUMNS
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = [str(row.get(c, "")) for c in id_cols] + [str(int(row["n"]))]
        cells += [_cell(row, m) for m in METRIC_COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _timing_cell(row: pd.Series) -> str:
    tor, lat = row.get("TOR-Align %", math.nan), row.get("Latency ms", math.nan)
    if isinstance(tor, float) and math.isnan(tor):
        return "—"
    return f"{_fmt(tor, 0)}% / {_fmt(lat, 0)} ms" if not (isinstance(lat, float) and math.isnan(lat)) else f"{_fmt(tor, 0)}% / —"


def to_paper_markdown(df: pd.DataFrame, extra_cols: list[str] | None = None) -> str:
    """Project-page layout: rows grouped under setting headers; Model | [extra] | n | axes | Overall | Timing.

    Point estimates only (the CI table is `to_markdown`); Timing = "TOR-Align % / median latency ms",
    as in the page's Table 1 ("90% / 1400 ms").
    """
    if df.empty:
        return "_(no runs)_\n"
    extra = extra_cols or []
    cols = ["Model"] + extra + ["n"] + [f"{c} ↑" for c in PAPER_COLUMNS]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for g, header in SETTING_GROUPS:
        sub = df[df["group"] == g] if "group" in df else df.iloc[0:0]
        if sub.empty:
            continue
        lines.append("| **" + header + "** |" + " |" * (len(cols) - 1))
        for _, row in sub.iterrows():
            cells = [str(row["Model"])] + [str(row.get(c, "")) for c in extra] + [str(int(row["n"]))]
            cells += [_fmt(row.get(m, math.nan), 2) for m in PAPER_COLUMNS if m != "Timing"] + [_timing_cell(row)]
            lines.append("| " + " | ".join(cells) + " |")
    rest = df[~df["group"].isin([g for g, _ in SETTING_GROUPS])] if "group" in df else df.iloc[0:0]
    for _, row in rest.iterrows():
        cells = [str(row["Model"])] + [str(row.get(c, "")) for c in extra] + [str(int(row["n"]))]
        cells += [_fmt(row.get(m, math.nan), 2) for m in PAPER_COLUMNS if m != "Timing"] + [_timing_cell(row)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def write(run_dirs: Iterable[str | Path], per_dynamic: bool = False, out: str | Path = "results/summary.md", *,
          judge: str | None = None, n_boot: int = N_BOOT, seed: int = SEED,
          manifest: str | Path | None = None, rows: int = 0) -> Path:
    """Write `<out>` (markdown) and `<out stem>.csv` (+ `<stem>_per_dynamic.csv` when requested).

    `manifest` (+ `rows` = first N rows) restricts every run to that common row set.
    """
    run_dirs = [Path(r) for r in run_dirs]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    keep = row_filter(manifest, rows)
    df = summarise(run_dirs, judge=judge, n_boot=n_boot, seed=seed, keep=keep)
    df.to_csv(out.with_suffix(".csv"), index=False)
    judges = sorted({str(j) for j in df.get("judge", pd.Series(dtype=object)).dropna()}) if not df.empty else []
    scope = (f" Rows restricted to {'the first ' + str(rows) + ' rows of ' if rows else ''}{manifest}."
             if manifest else "")
    note = (f"Judge: {', '.join(judges) or '—'}. n = manifest rows (clip, bucket) scored.{scope} "
            "Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality "
            "(AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). "
            "Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's "
            "available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) "
            f"/ median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, "
            "so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows "
            f"({n_boot} resamples, seed {seed}).")
    parts = [
        "# OpenVideoFDB summary",
        "",
        f"Runs: {', '.join(str(r) for r in run_dirs)}  ",
        note,
        "",
        to_paper_markdown(df, ["Setting"]),
        "## With 95 % bootstrap CIs",
        "",
        to_markdown(df, ["Model", "Setting"]),
    ]
    if per_dynamic:
        pdf = _per_dynamic_table(run_dirs, judge=judge, n_boot=n_boot, seed=seed, keep=keep)
        pdf.to_csv(out.with_name(out.stem + "_per_dynamic.csv"), index=False)
        parts += ["## Per dynamic", "", to_paper_markdown(pdf, ["Setting", "dynamic_type"]),
                  "## Per dynamic with 95 % bootstrap CIs", "",
                  to_markdown(pdf, ["Model", "Setting", "dynamic_type"])]
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


#: `write()` takes a `per_dynamic: bool` flag (CLI contract), so the table builder needs another name there.
_per_dynamic_table = per_dynamic
