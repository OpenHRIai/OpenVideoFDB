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
    assert g["Vis. Ground."] == pytest.approx(3.5) and g["Vis. Ground._n"] == 2
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
    assert math.isnan(ph["Vis. Ground."])
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
    assert md.startswith("# OpenVideoFDB summary") and "# Perception (project page Table 1)" in md
    # paper-notation table first: grouped rows, Model | Setting | n | axes | Overall | Timing
    assert "| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |" in md
    assert "| **Human reference** |" in md and "| Human reference | AV2AV | 5 | 4.50 | 4.50 | 3.50 |" in md
    assert "| **Random baseline** |" in md and "| Random baseline (mismatched partner) | AV2AV | 3 | 2.00 |" in md
    assert "| 75% / 725 ms |" in md                      # Timing = TOR-Align % / median latency
    # CI table second
    assert "## With 95 % bootstrap CIs" in md and "| Model | Setting | n | Fluency |" in md
    assert "| Human reference | AV2AV | 5 | 4.50 [" in md and "725 [250, 1200]" in md and "—" in md
    assert "## Per dynamic" in md and "| Human reference | AV2AV | Pause Handling | 2 |" in md
    assert (tmp_path / "results" / "summary.csv").exists()
    assert (tmp_path / "results" / "summary_per_dynamic.csv").exists()
    assert report.to_markdown(report.summarise([]), ["Model"]).startswith("_(no runs)_")
    assert report.to_paper_markdown(report.summarise([])).startswith("_(no runs)_")


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
    assert df.iloc[0]["Fluency_n"] == 2 and df.iloc[0]["Vis. Ground._n"] == 0
    out = report.write([gt, rnd], per_dynamic=True, out=tmp_path / "s.md", manifest=manifest, rows=2)
    text = out.read_text()
    assert f"Rows restricted to the first 2 rows of {manifest}." in text
    assert "Laughter" not in text.split("## Per dynamic")[1]


def test_paper_notation_names_and_settings():
    assert report.model_name("gemini_live", "gemini-3.1-flash-live-preview") == "Gemini 3.1 Flash Live"
    assert report.model_name("openai_realtime", "gpt-realtime") == "OpenAI gpt-realtime"
    assert report.model_name("openai_realtime", "gpt-realtime-mini") == "OpenAI gpt-realtime-mini"
    assert report.model_name("human_gt", "") == "Human reference"
    assert report.model_name("newprov", "model-x") == "newprov model-x"
    assert report.setting("gemini_live", "av") == "AV2A" and report.setting("gemini_live", "a2a") == "A2A"
    assert report.setting("human_gt", "av") == "AV2AV" and report.setting("tavus", "av") == "AV2AV"
    assert report.setting("anam", "a2a") == "A2AV"
    assert report.setting_group("human_gt", "av") == "REF" and report.setting_group("random", "av") == "RANDOM"
    assert report.setting_group("openai_realtime", "a2a") == "A2A"


def test_row_filter_matches_per_bucket_run_dirs(tmp_path):
    # NVIDIA-style dual-bucket clip: run dirs <clip>__perception / <clip>__generation, clip_id stored inside
    run = tmp_path / "r"
    _clip(run, "x__perception", "Laughter", {"fluency": 4, "semantic_grounding": 4})
    _clip(run, "x__generation", "Laughter", None, passed=True, latency=100.0, bucket="generation")
    for sub in ("x__perception/perception", "x__generation/generation"):
        for f in ("timing.json", "judge.json"):
            p = run / sub / f
            if p.exists():
                d = json.loads(p.read_text()); d["clip_id"] = "x"; p.write_text(json.dumps(d))
    manifest = tmp_path / "m.jsonl"
    manifest.write_text(json.dumps({"clip_id": "x", "bucket": "perception"}) + "\n" + json.dumps({"clip_id": "x", "bucket": "generation"}) + "\n")
    df = report.summarise([run], keep=report.row_filter(manifest))
    assert list(df["n"]) == [2] and df.iloc[0]["Fluency_n"] == 1 and df.iloc[0]["TOR-Align %_n"] == 1


def test_write_lists_generation_only_runs_in_generation_tables_only(runs, tmp_path):
    """Avatar runs carry generation judge axes only; an incidental perception row (same clip dir, timing only)
    must not put them in the perception table as a row of dashes. A timing-only run (no judge yet) stays."""
    gt, rnd = runs
    av = tmp_path / "heygen_a2av"
    gen = {"generation_fluency": 4, "affect_match": 2, "cue_appropriateness": 0}
    _clip(av, "c", "Turn-taking", gen, passed=True, latency=1800.0, provider="heygen", mode="a2a",
          bucket="generation")
    _clip(av, "c", "Laughter", None, provider="heygen", mode="a2a")        # incidental perception row
    timed = tmp_path / "timed_only"
    _clip(timed, "a", "Pause Handling", None, passed=True, latency=400.0, provider="random")

    df = report.summarise([gt, rnd, av, timed])
    assert report.generation_only_runs(df, [gt, rnd, av, timed]) == {"heygen_a2av"}

    out = report.write([gt, rnd, av, timed], per_dynamic=True, out=tmp_path / "r" / "s.md")
    md = out.read_text()
    top, gen_part = md.split("# Generation (project page Table 2)", 1)
    assert "HeyGen" not in top and "heygen_a2av" in top              # named in the note, not as a row
    assert "listed in the Generation tables only" in top
    assert "| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | 1 | 4.00 | 2.00 | 0.00 | 2.00 |" in gen_part
    csv = (tmp_path / "r" / "s.csv").read_text()
    assert "heygen_a2av" not in csv and "timed_only" in csv           # timing-only run kept in Table 1
    assert "heygen_a2av" not in (tmp_path / "r" / "s_per_dynamic.csv").read_text()


def test_write_lists_only_generation_judged_runs_in_generation_tables(runs, tmp_path):
    """Audio-out runs (perception judge only) have generation rows with timing but no generation axes: they stay
    in the perception table and are named, not listed, in the Generation tables (mirror of the avatar rule)."""
    gt, rnd = runs
    _clip(gt, "e", "Laughter", {"generation_fluency": 5, "affect_match": 3, "cue_appropriateness": 4},
          bucket="generation")
    api = tmp_path / "gemini_live_av"
    _clip(api, "a", "Pause Handling", {"fluency": 3, "conversational_flow": 3}, passed=True, latency=900.0,
          provider="gemini_live")
    _clip(api, "c", "Turn-taking", None, passed=True, latency=1100.0, provider="gemini_live", bucket="generation")

    out = report.write([gt, rnd, api], per_dynamic=True, out=tmp_path / "r" / "s.md")
    top, gen_part = out.read_text().split("# Generation (project page Table 2)", 1)
    assert "gemini_live_av" in (tmp_path / "r" / "s.csv").read_text()      # still in the perception table
    assert "without generation judge scores" not in top
    assert "without generation judge scores (gemini_live_av" in gen_part and "random" in gen_part
    assert "| Human reference | AV2AV | 2 |" in gen_part
    for csv in ("s_generation.csv", "s_generation_per_dynamic.csv"):
        assert "gemini_live_av" not in (tmp_path / "r" / csv).read_text()
