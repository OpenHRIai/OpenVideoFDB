"""Unit tests for ovfdb.score.timing / segments / pipeline (WS4).

Each timing class has >= 3 synthetic cases (pass, fail, edge). All synthetic:
no media, no ASR (the pipeline test monkeypatches the ASR step).
"""

import json
from dataclasses import asdict

import pytest

from ovfdb.schema import AgentRun, Bucket, DynamicType, Sample, Segment, TimingClass, Word, write_manifest
from ovfdb.score import asr, pipeline, segments, timing


def seg(start, end, text="hello there friend", n_words=None):
    n = len(text.split()) if n_words is None else n_words
    return Segment(start=start, end=end, text=text, n_words=n)


def ev(segs, cls, ds=5.0, de=8.0, clip_end=20.0, **kw):
    return timing.evaluate(segs, ds=ds, de=de, cls=cls, clip_end=clip_end, **kw)


# --- segments ------------------------------------------------------------------

def test_is_backchannel():
    assert timing.is_backchannel(seg(1.0, 1.5, "mhm"))
    assert not timing.is_backchannel(seg(1.0, 2.5, "mhm"))          # too long
    assert not timing.is_backchannel(seg(1.0, 1.5, "oh yeah"))      # 2 words is not < 2


def test_words_to_segments_merges_on_gap():
    words = [Word("hi", 0.0, 0.2), Word("there", 0.3, 0.5), Word("friend", 1.2, 1.5)]
    segs = segments.words_to_segments(words, gap=0.5)
    assert segs == [Segment(0.0, 0.5, "hi there", 2), Segment(1.2, 1.5, "friend", 1)]


def test_words_to_segments_gap_boundary_and_sorting():
    # gap exactly == 0.5 splits; unsorted input is sorted; blank words dropped
    words = [Word("b", 1.0, 1.4), Word("a", 0.0, 0.5), Word(" ", 0.6, 0.7)]
    segs = segments.words_to_segments(words, gap=0.5)
    assert segs == [Segment(0.0, 0.5, "a", 1), Segment(1.0, 1.4, "b", 1)]
    assert segments.words_to_segments([]) == []
    assert segments.words_to_segments(words, gap=0.6) == [Segment(0.0, 1.4, "a b", 2)]


def test_activity_and_overlaps():
    segs = [seg(2.0, 4.0), seg(7.0, 9.0)]
    assert segments.activity_fraction(segs, 0.0, 10.0) == pytest.approx(0.4)
    assert segments.activity_fraction(segs, 3.0, 8.0) == pytest.approx(0.4)
    assert segments.activity_fraction(segs, 5.0, 5.0) == 0.0
    assert segments.overlaps(segs, 3.0, 8.0) == [(segs[0], pytest.approx(1.0)), (segs[1], pytest.approx(1.0))]
    assert segments.overlaps(segs, 4.0, 7.0) == []     # touching is not overlapping


def test_timing_class_lookup():
    assert timing.timing_class(DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION) is TimingClass.STAY_SILENT
    assert timing.timing_class(DynamicType.LAUGHTER, Bucket.PERCEPTION) is None


# --- derived signal blocks (F.2.3 / F.5.1 wording) ----------------------------

def test_overlap_line_exact_format():
    ov = timing.overlap_summary([seg(3.28, 9.28)], ds=7.28, de=10.0, clip_end=20.0)
    assert ov.line() == ("Agent in-window speech: 2.00s total across 1 segment(s) "
                         "--- [3.28-9.28] overlaps by 2.00s")
    assert ov.total_in_window_s == pytest.approx(2.0)
    assert ov.pre_activity == pytest.approx(4.0 / 7.28)
    assert ov.post_activity == 0.0


def test_overlap_line_none_and_multiple():
    ov = timing.overlap_summary([seg(20.0, 24.0)], ds=37.0, de=46.0, clip_end=61.0)
    assert ov.line() == "Agent in-window speech: 0.00s (no segments overlap [37.00, 46.00])"
    ov = timing.overlap_summary([seg(4.0, 6.0), seg(7.5, 9.0)], ds=5.0, de=8.0, clip_end=20.0)
    assert ov.line() == ("Agent in-window speech: 1.50s total across 2 segment(s) "
                         "--- [4.00-6.00] overlaps by 1.00s, [7.50-9.00] overlaps by 0.50s")


def test_partition_block_matches_paper_example():
    segs = [seg(20.24, 24.32), seg(24.64, 26.88), seg(27.20, 30.88)]
    block = segments.format_partition(segments.partition(segs, 37.0, 46.0, 61.0))
    assert block == (
        "-- PRE-DYNAMIC (0.00 -> 37.00s) -- active 10.00s of 37.00s (27%)\n"
        "[ 20.24, 24.32] 4.08s\n"
        "[ 24.64, 26.88] 2.24s\n"
        "[ 27.20, 30.88] 3.68s\n"
        "-- DYNAMIC WINDOW (37.00 -> 46.00s) -- active 0.00s of 9.00s (0%)\n"
        "(no agent speech overlaps the dynamic window)\n"
        "-- POST-DYNAMIC (46.00 -> 61.00s) -- active 0.00s of 15.00s (0%)"
    )


def test_partition_clips_straddling_segment():
    parts = segments.partition([seg(4.0, 9.0)], 5.0, 8.0, 10.0)
    assert parts.pre.spans == [(4.0, 5.0)]
    assert parts.inside.spans == [(5.0, 8.0)]
    assert parts.post.spans == [(8.0, 9.0)]
    assert parts.inside.activity == pytest.approx(1.0)
    assert parts.post.activity == pytest.approx(0.5)


def test_yield_block_matches_paper_example():
    # ds=5, de=7: agent talks 2.40-9.28, 2.72 s silence, then 12.00-14.56.
    segs = [seg(2.4, 9.28), seg(12.0, 14.56)]
    ya = timing.yield_analysis(segs, ds=5.0, de=7.0, clip_end=30.0)
    assert ya.block() == (
        "Yield analysis:\n"
        "Pre-dynamic agent activity: 52.0% (2.60s of 5.00s)\n"
        "Post-dynamic agent activity: 34.6% (4.84s of 14.00s)\n"
        "Yield moment (end of speech before sustained silence): 9.28s\n"
        "Verdict: AGENT YIELDED with brief late lag. Yield moment: 9.28s (+2.28s after dynamic_end_s). "
        "Activity 52% -> 35% post-dynamic."
    )
    assert ya.yielded and ya.yield_moment_s == pytest.approx(9.28) and ya.lag_s == pytest.approx(2.28)


def test_yield_block_verdicts():
    ya = timing.yield_analysis([seg(2.0, 6.0)], ds=5.0, de=7.0, clip_end=20.0)
    assert ya.yielded and ya.verdict.startswith("AGENT YIELDED. Yield moment: 6.00s (-1.00s after dynamic_end_s).")
    ya = timing.yield_analysis([seg(2.0, 19.5)], ds=5.0, de=7.0, clip_end=20.0)
    assert not ya.yielded and ya.yield_moment_s is None and ya.verdict.startswith("AGENT DID NOT YIELD.")
    ya = timing.yield_analysis([seg(2.0, 11.0)], ds=5.0, de=7.0, clip_end=20.0)   # lag 4 s > 3 s
    assert not ya.yielded and ya.yield_moment_s == 11.0 and ya.verdict.startswith("AGENT DID NOT YIELD.")
    ya = timing.yield_analysis([seg(12.0, 15.0)], ds=5.0, de=7.0, clip_end=20.0)
    assert ya.trivially_silent and ya.verdict.startswith("AGENT WAS NOT SPEAKING (trivially silent).")
    assert "Yield moment (end of speech before sustained silence): none" in ya.block()


# --- stay-silent ----------------------------------------------------------------

def test_stay_silent_pass_on_silence():
    r = ev([seg(12.0, 15.0)], TimingClass.STAY_SILENT)
    assert r.passed and r.takeover == 0 and r.expected_takeover == 0 and r.latency_ms is None


def test_stay_silent_fail_on_floor_take():
    r = ev([seg(5.5, 8.0)], TimingClass.STAY_SILENT)
    assert not r.passed and r.takeover == 1 and r.latency_ms == pytest.approx(500.0)


def test_stay_silent_pass_backchannel_only_overlap():
    # 1.8 s of in-window speech (> 1 s) but every overlapping segment is a backchannel
    r = ev([seg(5.2, 6.1, "mhm"), seg(7.0, 7.9, "yeah")], TimingClass.STAY_SILENT)
    assert r.passed and r.takeover == 0 and r.latency_ms == pytest.approx(200.0)
    assert r.details["all_backchannel"] is True


def test_stay_silent_short_non_backchannel_passes_but_takes_over():
    r = ev([seg(5.2, 6.0, "oh yeah")], TimingClass.STAY_SILENT)        # 0.8 s <= 1 s
    assert r.passed and r.takeover == 1
    r = ev([seg(3.0, 5.5)], TimingClass.STAY_SILENT)                   # already speaking at ds, 0.5 s in-window
    assert r.passed and r.latency_ms == 0.0


# --- continue-speaking ----------------------------------------------------------

def test_continue_speaking_pass():
    r = ev([seg(0.0, 10.0)], TimingClass.CONTINUE_SPEAKING)
    assert r.passed and r.takeover == 1 and r.expected_takeover == 1 and r.latency_ms is None
    assert r.details["vacuous"] is False and r.details["in_activity"] == pytest.approx(1.0)


def test_continue_speaking_fail_on_yield():
    r = ev([seg(0.0, 5.5)], TimingClass.CONTINUE_SPEAKING)
    assert not r.passed and r.details["pre_activity"] == pytest.approx(1.0)
    assert r.details["in_activity"] == pytest.approx(0.5 / 3)


def test_continue_speaking_vacuous_pass():
    r = ev([seg(0.0, 1.0)], TimingClass.CONTINUE_SPEAKING)
    assert r.passed and r.details["vacuous"] is True and r.takeover == 0
    r = ev([], TimingClass.CONTINUE_SPEAKING)
    assert r.passed and r.details["vacuous"] is True


def test_continue_speaking_thresholds():
    # pre 1.0/3 >= 30 % -> in-window exactly 50 % passes
    r = ev([seg(2.0, 3.0), seg(5.0, 6.5)], TimingClass.CONTINUE_SPEAKING)
    assert r.passed and r.details["vacuous"] is False
    r = ev([seg(2.0, 3.0), seg(5.0, 6.4)], TimingClass.CONTINUE_SPEAKING)
    assert not r.passed
    # ds < 3 s: pre-window clipped at 0
    r = ev([seg(0.0, 1.0)], TimingClass.CONTINUE_SPEAKING, ds=2.0, de=4.0)
    assert r.details["pre_activity"] == pytest.approx(0.5) and not r.passed


# --- yield-required -------------------------------------------------------------

def test_yield_required_latency():
    r = ev([seg(2.0, 6.0)], TimingClass.YIELD_REQUIRED, de=7.0)
    assert r.passed and r.latency_ms == pytest.approx(1000.0) and r.takeover == 1
    assert r.details["yielded"] is True and r.details["trivially_silent"] is False


def test_yield_required_fail_keeps_talking():
    r = ev([seg(2.0, 19.5)], TimingClass.YIELD_REQUIRED, de=7.0)
    assert not r.passed and r.latency_ms == pytest.approx(14500.0)
    assert r.details["verdict"].startswith("AGENT DID NOT YIELD")


def test_yield_required_trivially_silent():
    r = ev([seg(12.0, 15.0)], TimingClass.YIELD_REQUIRED, de=7.0)
    assert not r.passed and r.details["trivially_silent"] is True and r.latency_ms is None
    r = ev([], TimingClass.YIELD_REQUIRED, de=7.0)
    assert not r.passed and r.details["trivially_silent"] is True
    r = ev([seg(2.0, 3.5)], TimingClass.YIELD_REQUIRED, de=7.0)        # ended 1.5 s before ds: not "immediately preceding"
    assert not r.passed and r.details["trivially_silent"] is True


def test_yield_required_immediately_preceding_segment():
    r = ev([seg(2.0, 4.6)], TimingClass.YIELD_REQUIRED, de=7.0)
    assert r.passed and r.latency_ms == 0.0 and r.details["stop_offset_s"] == pytest.approx(-0.4)
    r = ev([seg(2.0, 6.5)], TimingClass.YIELD_REQUIRED, de=7.0)       # exactly 1.5 s
    assert r.passed and r.latency_ms == pytest.approx(1500.0)
    r = ev([seg(2.0, 6.6)], TimingClass.YIELD_REQUIRED, de=7.0)
    assert not r.passed


# --- smooth-handoff -------------------------------------------------------------

def test_smooth_handoff_pass():
    r = ev([seg(6.0, 9.0)], TimingClass.SMOOTH_HANDOFF)
    assert r.passed and r.latency_ms == pytest.approx(1000.0) and r.takeover == 1
    r = ev([seg(8.0, 10.0)], TimingClass.SMOOTH_HANDOFF)              # onset exactly at de
    assert r.passed and r.latency_ms == pytest.approx(3000.0)


def test_smooth_handoff_fail():
    r = ev([seg(9.0, 12.0)], TimingClass.SMOOTH_HANDOFF)
    assert not r.passed and r.latency_ms == pytest.approx(4000.0) and r.takeover == 0
    r = ev([], TimingClass.SMOOTH_HANDOFF)
    assert not r.passed and r.latency_ms is None and r.details["no_onset"] is True


def test_smooth_handoff_already_speaking_at_ds():
    r = ev([seg(3.0, 9.0)], TimingClass.SMOOTH_HANDOFF, agent_speaks_first=True)
    assert r.passed and r.latency_ms == 0.0 and r.details["already_speaking_at_ds"] is True
    assert r.details["agent_speaks_first"] is True


# --- backchannel-produced -------------------------------------------------------

def test_backchannel_produced_pass():
    r = ev([seg(5.5, 6.0, "mhm")], TimingClass.BACKCHANNEL_PRODUCED)
    assert r.passed and r.takeover == 0 and r.latency_ms == pytest.approx(500.0)
    r = ev([seg(5.5, 6.0, "mhm"), seg(7.0, 7.4, "yeah")], TimingClass.BACKCHANNEL_PRODUCED)
    assert r.passed and r.details["n_backchannels"] == 2


def test_backchannel_produced_fail_floor_take():
    r = ev([seg(5.5, 7.5, "yeah I totally agree")], TimingClass.BACKCHANNEL_PRODUCED)
    assert not r.passed and r.takeover == 1 and r.latency_ms is None
    r = ev([], TimingClass.BACKCHANNEL_PRODUCED)
    assert not r.passed and r.takeover == 0 and r.latency_ms is None


def test_backchannel_produced_mixed_fails():
    r = ev([seg(5.5, 6.0, "mhm"), seg(6.5, 7.9, "yeah I agree")], TimingClass.BACKCHANNEL_PRODUCED)
    assert not r.passed and r.takeover == 1 and r.latency_ms == pytest.approx(500.0)
    assert r.details["n_floor_takes"] == 1


# --- aggregate ------------------------------------------------------------------

def test_aggregate():
    results = {
        "Pause Handling": [ev([seg(12.0, 15.0)], TimingClass.STAY_SILENT), ev([seg(5.5, 8.0)], TimingClass.STAY_SILENT)],
        "Turn-taking": [ev([seg(6.0, 9.0)], TimingClass.SMOOTH_HANDOFF), ev([seg(3.0, 9.0)], TimingClass.SMOOTH_HANDOFF),
                        ev([seg(9.0, 12.0)], TimingClass.SMOOTH_HANDOFF)],
    }
    agg = timing.aggregate(results)
    assert agg["Pause Handling"]["tor_alignment"] == pytest.approx(0.5)
    assert agg["Pause Handling"]["median_latency_ms"] == pytest.approx(500.0)
    assert agg["Pause Handling"]["timing_class"] == "stay-silent"
    assert agg["Turn-taking"]["tor_alignment"] == pytest.approx(2 / 3)
    assert agg["Turn-taking"]["median_latency_ms"] == pytest.approx(1000.0)
    assert agg["Turn-taking"]["takeover_rate"] == pytest.approx(2 / 3)
    assert agg["overall"] == {"n": 5, "n_pass": 3, "tor_alignment": pytest.approx(0.6),
                              "takeover_rate": pytest.approx(0.6), "median_latency_ms": pytest.approx(750.0)}
    assert timing.aggregate({})["overall"]["tor_alignment"] is None


# --- pipeline (no media: ASR monkeypatched) ------------------------------------

def test_score_timing_pipeline(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.jsonl"
    samples = [
        Sample(clip_id="c1", conversation_id="x", bucket=Bucket.PERCEPTION, dynamic_type=DynamicType.NONVERBAL_INTERRUPTION,
               dynamic_start_s=5.0, dynamic_end_s=7.0, duration_s=20.0, user_audio_path="u.wav", user_video_path="u.mp4"),
        Sample(clip_id="c2", conversation_id="x", bucket=Bucket.PERCEPTION, dynamic_type=DynamicType.LAUGHTER,
               dynamic_start_s=5.0, dynamic_end_s=7.0, duration_s=20.0, user_audio_path="u.wav", user_video_path="u.mp4"),
    ]
    write_manifest(samples, manifest)
    run_dir = tmp_path / "runs" / "demo"
    for cid in ("c1", "c2"):
        d = run_dir / cid
        d.mkdir(parents=True)
        (d / "agent.wav").write_bytes(b"")
        run = AgentRun(clip_id=cid, provider="fake", mode="av", agent_audio_path=str(d / "agent.wav"),
                       meta={"manifest": str(manifest)})
        (d / "run.json").write_text(json.dumps(asdict(run)))
    words = [Word("so", 2.0, 2.3), Word("anyway", 2.4, 3.0), Word("I", 3.1, 3.2), Word("think", 3.3, 6.0)]
    monkeypatch.setattr(asr, "load_or_transcribe", lambda wav, **kw: words)

    summary = pipeline.score_timing(run_dir)
    assert summary["n_clips"] == 2 and summary["n_timed"] == 1 and summary["skipped"] == []
    assert summary["aggregate"]["Nonverbal Interruption"]["tor_alignment"] == 1.0
    assert summary["aggregate"]["Nonverbal Interruption"]["median_latency_ms"] == pytest.approx(1000.0)
    t1 = json.loads((run_dir / "c1" / "timing.json").read_text())
    assert t1["timing_class"] == "yield-required" and t1["timing"]["passed"] is True
    assert t1["transcript"] == "so anyway I think" and len(t1["segments"]) == 1
    assert t1["overlap_line"].startswith("Agent in-window speech: 1.00s total across 1 segment(s)")
    assert t1["yield_block"].startswith("Yield analysis:\n") and t1["agent_role"] == "YIELDING"
    t2 = json.loads((run_dir / "c2" / "timing.json").read_text())
    assert t2["timing_class"] is None and t2["timing"] is None and t2["yield_block"] is None
    assert "-- PRE-DYNAMIC (0.00 -> 5.00s) --" in t2["partition_block"]
    assert json.loads((run_dir / "timing_summary.json").read_text())["n_clips"] == 2

    with pytest.raises(NotImplementedError, match="WS5"):
        pipeline.score(run_dir)
