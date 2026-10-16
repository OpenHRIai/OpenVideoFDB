"""WS5 report: summarise / per_dynamic / agreement / write over a tiny synthetic run tree."""

from __future__ import annotations

import json
import math

import pytest

from ovfdb.score import report


def _clip(run_dir, cid, dyn, ratings: dict | None, passed=None, latency=None, judge="gpt-4o", provider="human_gt",
          mode="av", second_judge: dict | None = None, bucket="perception"):
    """One scored manifest row: `<run>/<cid>/<bucket>/{timing.json, judge.json, judge/}`."""
    (run_dir / cid).mkdir(parents=True, exist_ok=True)
    (run_dir / cid / "run.json").write_text(json.dumps({"clip_id": cid, "provider": provider, "mode": mode}))
    d = run_dir / cid / bucket
    d.mkdir(parents=True, exist_ok=True)
    timing = None if passed is None else {"passed": passed, "takeover": 0, "expected_takeover": 0,
                                           "latency_ms": latency, "details": {}}
    (d / "timing.json").write_text(json.dumps({
        "clip_id": cid, "provider": provider, "mode": mode, "bucket": bucket, "dynamic_type": dyn,
        "timing_class": "stay-silent" if timing else None, "timing": timing}))
    if ratings is None:                 # generation row: timing only, no perception judge
        return
    axes = {a: {"rating": r, "analysis": "", "reasoning": ""} for a, r in ratings.items()}
    overall = sum(ratings.values()) / len(ratings)
    block = {"judge": judge, "axes": axes, "overall": overall}
    (d / "judge.json").write_text(json.dumps({"clip_id": cid, "provider": provider, "mode": mode, "bucket": bucket,
                                              "dynamic_type": dyn, **block, "by_judge": {judge: block}}))
    (d / "judge").mkdir(exist_ok=True)
    for a, r in ratings.items():
        (d / "judge" / f"{a}_{judge}.json").write_text(json.dumps({"axis": a, "judge": judge, "rating": r}))
    for a, r in (second_judge or {}).items():
        (d / "judge" / f"{a}_claude-sonnet-4-6.json").write_text(
            json.dumps({"axis": a, "judge": "claude-sonnet-4-6", "rating": r}))


@pytest.fixture
def runs(tmp_path):
    gt = tmp_path / "gt"
    _clip(gt, "a", "Pause Handling", {"fluency": 5, "conversational_flow": 4}, passed=True, latency=None,
          second_judge={"fluency": 4, "conversational_flow": 4})
    _clip(gt, "b", "Pause Handling", {"fluency": 4, "conversational_flow": 5}, passed=True, latency=1200.0,
          second_judge={"fluency": 2, "conversational_flow": 5})
    _clip(gt, "c", "Laughter", {"fluency": 5, "semantic_grounding": 4}, second_judge={"fluency": 5})
    _clip(gt, "d", "Adaptor Handling", {"fluency": 4, "semantic_grounding": 3}, passed=False, latency=None)
    # "c" is also a generation row (same clip dir): timed, not judged
    _clip(gt, "c", "Turn-taking", None, passed=True, latency=250.0, bucket="generation")
    (gt / "a" / "timing.json").write_text("{}")             # stale flat file from the old layout: ignored
    rnd = tmp_path / "random"
    _clip(rnd, "a", "Pause Handling", {"fluency": 2, "conversational_flow": 1}, passed=False, latency=300.0,
          provider="random")
    _clip(rnd, "b", "Pause Handling", {"fluency": 3, "conversational_flow": 2}, passed=True, latency=None,
          provider="random")
    _clip(rnd, "c", "Laughter", {"fluency": 1, "semantic_grounding": 2}, provider="random")
    (rnd / "not_a_clip.txt").write_text("ignored")
    return gt, rnd


def test_summarise(runs):
    gt, rnd = runs
    df = report.summarise([gt, rnd])
    assert list(df["provider"]) == ["human_gt", "random"] and list(df["n"]) == [5, 3]     # n = rows
    g = df.iloc[0]
    assert g["Fluency"] == pytest.approx(4.5) and g["Fluency_n"] == 4 and g["Conv. Flow"] == pytest.approx(4.5)
    assert g["Grounding"] == pytest.approx(3.5) and g["Grounding_n"] == 2
    assert g["Overall"] == pytest.approx((4.5 + 4.5 + 4.5 + 3.5) / 4) and g["Overall_n"] == 4
    assert g["TOR-Align %"] == pytest.approx(300 / 4) and g["TOR-Align %_n"] == 4
    assert g["Latency ms"] == pytest.approx(725.0) and g["Latency ms_n"] == 2
    r = df.iloc[1]
    assert r["Fluency"] == pytest.approx(2.0) and r["TOR-Align %"] == pytest.approx(50.0) and r["Latency ms"] == 300.0
    for col in ("Fluency", "Conv. Flow", "Overall", "TOR-Align %"):
        assert g[f"{col}_lo"] <= g[col] <= g[f"{col}_hi"], col
    assert g["Fluency_lo"] >= 4.0 and g["Fluency_hi"] <= 5.0
    assert g["Fluency_lo"] > r["Fluency_hi"]        # GT > random separation
    assert df["judge"].tolist() == ["gpt-4o", "gpt-4o"]


def test_bootstrap_ci_deterministic():
    v = [1, 2, 3, 4, 5, 6, 7, 8]
    a, b = report.bootstrap_ci(v), report.bootstrap_ci(v)
    assert a == b and a[0] < 4.5 < a[1]
    assert report.bootstrap_ci(v, seed=1) != a
    assert report.bootstrap_ci([]) == (math.nan, math.nan) or all(math.isnan(x) for x in report.bootstrap_ci([]))
    assert report.bootstrap_ci([3.0]) == (3.0, 3.0)
    lo, hi = report.bootstrap_ci([100.0, 0.0, 100.0, 0.0, 100.0], report._median_rows)
    assert lo == 0.0 and hi == 100.0


def test_per_dynamic(runs):
    gt, rnd = runs
    df = report.per_dynamic([gt, rnd])
    assert df["dynamic_type"].tolist() == ["Adaptor Handling", "Laughter", "Pause Handling", "Turn-taking",
                                           "Laughter", "Pause Handling"]
    ph = df[(df["run"] == "gt") & (df["dynamic_type"] == "Pause Handling")].iloc[0]
    assert ph["n"] == 2 and ph["Conv. Flow"] == pytest.approx(4.5) and ph["TOR-Align %"] == 100.0
    assert math.isnan(ph["Grounding"])
    tt = df[(df["run"] == "gt") & (df["dynamic_type"] == "Turn-taking")].iloc[0]
    assert tt["n"] == 1 and math.isnan(tt["Fluency"]) and tt["TOR-Align %"] == 100.0 and tt["Latency ms"] == 250.0


def test_agreement(runs):
    gt, _ = runs
    a = report.agreement(gt, "gpt-4o", "claude-sonnet-4-6")
    assert a["fluency"]["n"] == 3 and a["fluency"]["within_1"] == pytest.approx(200 / 3)
    assert a["fluency"]["exact"] == pytest.approx(100 / 3) and a["fluency"]["mean_abs_diff"] == pytest.approx(1.0)
    assert a["conversational_flow"] == {"n": 2, "within_1": 100.0, "exact": 100.0, "mean_abs_diff": 0.0,
                                        "mean_a": 4.5, "mean_b": 4.5}
    assert "semantic_grounding" not in a and a["overall"]["n"] == 5 and a["overall"]["within_1"] == 80.0
    assert report.agreement(gt, "gpt-4o", "nobody")["overall"]["n"] == 0


def test_write_markdown_and_csv(runs, tmp_path):
    gt, rnd = runs
    out = report.write([gt, rnd], per_dynamic=True, out=tmp_path / "results" / "summary.md")
    md = out.read_text()
    assert md.startswith("# OpenVideoFDB summary") and "| provider | mode | n | Fluency |" in md
    assert "| human_gt | av | 5 | 4.50 [" in md and "| random | av | 3 | 2.00 [" in md
    assert "## Per dynamic" in md and "| human_gt | av | Pause Handling | 2 |" in md
    assert "725 [250, 1200]" in md and "—" in md           # latency CI; missing Grounding for pause-only
    assert (tmp_path / "results" / "summary.csv").exists()
    assert (tmp_path / "results" / "summary_per_dynamic.csv").exists()
    assert report.to_markdown(report.summarise([]), ["provider"]).startswith("_(no runs)_")


def test_load_run_selects_judge(runs):
    gt, _ = runs
    r = report.load_run(gt, judge="claude-sonnet-4-6")
    assert r["judge"] == "claude-sonnet-4-6" and all(c["axes"] == {} for c in r["clips"])
    assert [(c["clip_id"], c["bucket"]) for c in r["clips"]] == [
        ("a", "perception"), ("b", "perception"), ("c", "perception"), ("c", "generation"), ("d", "perception")]
    with pytest.raises(FileNotFoundError):
        report.load_run(gt / "missing")


def test_row_filter_restricts_runs_to_common_rows(runs, tmp_path):
    gt, rnd = runs
    manifest = tmp_path / "m.jsonl"
    manifest.write_text("\n".join(json.dumps(r) for r in [
        {"clip_id": "a", "bucket": "perception"}, {"clip_id": "c", "bucket": "generation"},
        {"clip_id": "b", "bucket": "perception"}, {"clip_id": "zzz", "bucket": "perception"}]) + "\n")
    keep = report.row_filter(manifest)
    assert keep == {("a", "perception"), ("c", "generation"), ("b", "perception"), ("zzz", "perception")}
    assert report.row_filter(manifest, rows=2) == {("a", "perception"), ("c", "generation")}
    assert report.row_filter(None) is None and report.row_filter("") is None
    df = report.summarise([gt, rnd], keep=keep)
    assert list(df["n"]) == [3, 2]                                   # gt: a, b, c/generation; random: a, b
    assert df.iloc[0]["Fluency_n"] == 2 and df.iloc[0]["Grounding_n"] == 0
    out = report.write([gt, rnd], per_dynamic=True, out=tmp_path / "s.md", manifest=manifest, rows=2)
    text = out.read_text()
    assert f"Rows restricted to the first 2 rows of {manifest}." in text
    assert "Laughter" not in text.split("## Per dynamic")[1]
