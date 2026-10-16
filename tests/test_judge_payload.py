"""WS5 perception judge: payload template, rubric dispatch, parsing, caching, pipeline wiring.

Everything is synthetic (no media, no ASR). The one real gpt-4o call is marked `network`.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

import pytest

from ovfdb.schema import AXES, AgentRole, AgentRun, Axis, Bucket, DynamicType, Sample, Word, write_manifest
from ovfdb.score import asr, judge, pipeline

CAPTION = ("0.0s - 4.0s: The user, a man in a grey sweater, is mid-story and looks at the camera. "
           "4.0s - 7.0s: He stops speaking, looks up and to the side, and holds his breath as if searching for a word. "
           "7.0s - 10.0s: He looks back and finishes the sentence with a small smile.")


def make_sample(dynamic=DynamicType.PAUSE_HANDLING, bucket=Bucket.PERCEPTION, caption=CAPTION, **kw) -> Sample:
    words = [Word("so", 0.0, 0.2), Word("the", 0.3, 0.4), Word("thing", 0.5, 0.9), Word("is", 1.0, 1.2),
             Word("I", 7.2, 7.3), Word("forgot", 7.4, 7.9)]
    d = {"clip_id": "c1", "conversation_id": "x", "bucket": bucket, "dynamic_type": dynamic,
         "dynamic_start_s": 4.0, "dynamic_end_s": 7.0, "duration_s": 10.0, "user_audio_path": "u.wav",
         "user_video_path": "u.mp4", "av_caption": caption, "user_words": words}
    d.update(kw)
    return Sample(**d)


def make_timing(role="SILENT", transcript="Oh, no worries, take your time.", yield_block=None) -> dict:
    return {
        "agent_role": role,
        "transcript": transcript,
        "overlap_line": "Agent in-window speech: 0.00s (no segments overlap [4.00, 7.00])",
        "partition_block": ("-- PRE-DYNAMIC (0.00 -> 4.00s) -- active 0.00s of 4.00s (0%)\n"
                            "-- DYNAMIC WINDOW (4.00 -> 7.00s) -- active 0.00s of 3.00s (0%)\n"
                            "(no agent speech overlaps the dynamic window)\n"
                            "-- POST-DYNAMIC (7.00 -> 10.00s) -- active 1.50s of 3.00s (50%)\n"
                            "[  8.00, 9.50] 1.50s"),
        "yield_block": yield_block,
    }


YIELD_BLOCK = ("Yield analysis:\nPre-dynamic agent activity: 52.0% (2.60s of 5.00s)\n"
               "Post-dynamic agent activity: 34.6% (4.84s of 14.00s)\n"
               "Yield moment (end of speech before sustained silence): 9.28s\n"
               "Verdict: AGENT YIELDED with brief late lag.")


# --- payload ------------------------------------------------------------------------

def test_payload_has_role_overlap_partition_caption():
    msg = judge.build_user_message(make_sample(), make_timing())
    assert msg.startswith("Category: Pause Handling\nBucket: perception\nAgent role: SILENT. ")
    assert judge.role_description(AgentRole.SILENT) in msg
    assert "Dynamic event: t=4.00s to t=7.00s\nClip duration: 10.00s\n" in msg
    assert "\nAgent in-window speech: 0.00s (no segments overlap [4.00, 7.00])\n" in msg
    assert "-- DYNAMIC WINDOW (4.00 -> 7.00s) --" in msg and "-- PRE-DYNAMIC" in msg and "-- POST-DYNAMIC" in msg
    assert f'AV caption (covers full clip including the dynamic event):\n"""\n{CAPTION}\n"""' in msg
    assert 'Agent speech transcript:\n"""\nOh, no worries, take your time.\n"""' in msg
    assert msg.endswith("Rate on the 0-5 scale per the rubric above.")
    assert "Yield analysis:" not in msg


def test_user_speech_grouped_into_utterances():
    msg = judge.build_user_message(make_sample(), make_timing())
    assert 'User speech (with timestamps):\n"""\n[0.00-1.20s] so the thing is\n[7.20-7.90s] I forgot\n"""' in msg
    assert judge.format_user_speech(make_sample(user_words=[])) == "[no user speech]"


def test_yield_block_only_for_yielding_roles():
    s = make_sample(dynamic=DynamicType.NONVERBAL_INTERRUPTION)
    assert s.agent_role is AgentRole.YIELDING
    msg = judge.build_user_message(s, make_timing(role="YIELDING", yield_block=YIELD_BLOCK))
    assert "Agent in-window speech: 0.00s (no segments overlap [4.00, 7.00])\n" + YIELD_BLOCK + "\nAV caption" in msg
    # a yield block handed in for a non-yielding role is dropped
    msg2 = judge.build_user_message(make_sample(), make_timing(role="SILENT", yield_block=YIELD_BLOCK))
    assert "Yield analysis:" not in msg2
    # no block available for a yielding role -> payload still well-formed (the role text may *mention* the block)
    msg3 = judge.build_user_message(s, make_timing(role="YIELDING", yield_block=None))
    assert "Yield analysis:" not in msg3 and "Agent role: YIELDING." in msg3


def test_no_speech_and_no_caption_placeholders():
    msg = judge.build_user_message(make_sample(caption=""), make_timing(transcript=""))
    assert 'Agent speech transcript:\n"""\n[no speech]\n"""' in msg
    assert '"""\n[no caption available]\n"""' in msg
    msg2 = judge.build_user_message(make_sample(), make_timing(transcript="[no speech]"))
    assert msg2.count("[no speech]") == 1


# --- rubric dispatch ------------------------------------------------------------------

def test_category_axes_cover_every_perception_pair():
    for (dyn, bucket), axes in AXES.items():
        if bucket is not Bucket.PERCEPTION:
            continue
        for axis in axes:
            name = judge.rubric_name(axis, dyn)
            assert (judge.RUBRIC_DIR / f"{name}.txt").exists(), (dyn, axis, name)
            if axis is not Axis.FLUENCY:
                assert axis in judge.CATEGORY_AXES[dyn]
    assert judge.rubric_name(Axis.SEMANTIC_GROUNDING, DynamicType.EMOTION_MATCHING) == "face_emotion_display"
    assert judge.rubric_name(Axis.CONVERSATIONAL_FLOW, DynamicType.NONVERBAL_INTERRUPTION) == "nonverbal_interruption_flow"
    with pytest.raises(ValueError):
        judge.rubric_name(Axis.SEMANTIC_GROUNDING, DynamicType.PAUSE_HANDLING)
    with pytest.raises(ValueError):
        judge.rubric_name(Axis.AFFECT_MATCH, DynamicType.LAUGHTER)


def test_rubric_files_verbatim_markers():
    names = ["fluency", "pause_handling", "gaze_avoidance_with_pause", "nonverbal_backchanneling",
             "nonverbal_interruption_flow", "nonverbal_interruption_grounding", "face_emotion_display",
             "laughter", "adaptor_handling"]
    for n in names:
        text = judge.load_rubric(n)
        assert text and "Rate on 0-5" in text, n
        assert "‘‘" not in text and "\\to" not in text and "> >" not in text, n
    pre = judge.load_rubric("perception_preamble")
    assert pre.startswith("You are a judge for VideoFDB") and '"rating": integer 0-5' in pre
    for n in names:
        if n != "fluency":
            assert judge.load_rubric(n).startswith("CATEGORY: (P) ")
    assert judge.load_rubric("fluency").startswith("UNIVERSAL AXIS: Conversational Fluency.")


def test_system_prompt_composition():
    s = make_sample()
    sp = judge.build_system_prompt(Axis.CONVERSATIONAL_FLOW, s)
    assert sp.startswith(judge.load_rubric("perception_preamble"))
    assert "\n\nCATEGORY: (P) Pause Handling." in sp and sp.endswith(judge.OUTPUT_SCHEMA)
    assert "UNIVERSAL AXIS" not in sp
    assert "UNIVERSAL AXIS: Conversational Fluency." in judge.build_system_prompt("fluency", s)
    for role in AgentRole:
        assert len(judge.role_description(role).split()) > 30


# --- parsing / caching ------------------------------------------------------------------

def test_parse_response():
    ok = judge.parse_response('{"analysis": "a", "rating": 4, "reasoning": "r"}')
    assert ok == {"analysis": "a", "rating": 4, "reasoning": "r"}
    assert judge.parse_response('```json\n{"analysis":"a","rating":"3","reasoning":"r"}\n```')["rating"] == 3
    assert judge.parse_response('Sure: {"rating": 5.0, "analysis": "", "reasoning": ""} done')["rating"] == 5
    for bad in ("nope", '{"analysis": "a"}', '{"rating": 7}', '{"rating": 3.5}', '{"rating": true}', "[1,2]"):
        with pytest.raises(judge.JudgeParseError):
            judge.parse_response(bad)


def test_score_axis_caches_and_retries(monkeypatch, tmp_path):
    calls: list[tuple[str, str, str]] = []
    replies = iter(["garbage", '{"analysis": "x", "rating": 4, "reasoning": "y"}'])

    def fake_call(j, system, user):
        calls.append((j, system, user))
        return next(replies), {"prompt_tokens": 100, "completion_tokens": 10}

    monkeypatch.setattr(judge, "_call", fake_call)
    s, t = make_sample(), make_timing()
    r = judge.score_axis(s, t, Axis.CONVERSATIONAL_FLOW, "gpt-4o", cache_dir=tmp_path)
    assert r.rating == 4 and r.cached is False and r.usage == {"prompt_tokens": 200, "completion_tokens": 20, "n_calls": 2}
    assert len(calls) == 2 and calls[1][2].endswith("Return ONLY the JSON object described in the system prompt.")
    assert calls[0][1] == judge.build_system_prompt(Axis.CONVERSATIONAL_FLOW, s)
    f = tmp_path / "conversational_flow_gpt-4o.json"
    saved = json.loads(f.read_text())
    assert saved["rating"] == 4 and saved["key"] == judge.cache_key(calls[0][1], calls[0][2], "gpt-4o")
    assert saved["user_message"] == calls[0][2]
    # cache hit: no call
    r2 = judge.score_axis(s, t, "conversational_flow", "gpt-4o", cache_dir=tmp_path)
    assert r2.cached is True and r2.rating == 4 and len(calls) == 2
    # another judge name -> new key -> new call
    monkeypatch.setattr(judge, "_call", lambda j, sy, u: ('{"analysis":"","rating":2,"reasoning":""}', {}))
    r3 = judge.score_axis(s, t, Axis.CONVERSATIONAL_FLOW, "claude-sonnet-4-6", cache_dir=tmp_path)
    assert r3.rating == 2 and (tmp_path / "conversational_flow_claude-sonnet-4-6.json").exists()
    # payload change invalidates the cache
    r4 = judge.score_axis(make_sample(caption="different"), t, Axis.CONVERSATIONAL_FLOW, "gpt-4o", cache_dir=tmp_path)
    assert r4.cached is False and r4.rating == 2


def test_score_axis_gives_up_after_two_bad_replies(monkeypatch):
    monkeypatch.setattr(judge, "_call", lambda j, s, u: ("not json", {}))
    with pytest.raises(judge.JudgeParseError):
        judge.score_axis(make_sample(), make_timing(), Axis.FLUENCY, "gpt-4o")
    with pytest.raises(ValueError, match="generation axis"):
        judge.score_axis(make_sample(), make_timing(), Axis.AFFECT_MATCH, "gpt-4o")


def test_score_sample_axes_and_skips(monkeypatch, caplog):
    monkeypatch.setattr(judge, "_call", lambda j, s, u: ('{"analysis":"","rating":4,"reasoning":""}', {}))
    res = judge.score_sample(make_sample(), make_timing(), "gpt-4o")
    assert set(res) == {"fluency", "conversational_flow"}
    res = judge.score_sample(make_sample(dynamic=DynamicType.NONVERBAL_INTERRUPTION),
                             make_timing(role="YIELDING"), "gpt-4o", axes=["fluency", "affect_match"])
    assert set(res) == {"fluency"}
    gen = make_sample(dynamic=DynamicType.LAUGHTER, bucket=Bucket.GENERATION)
    assert judge.score_sample(gen, make_timing(role="EXCHANGING"), "gpt-4o") == {}
    with caplog.at_level("WARNING"):
        judge.score_sample(make_sample(caption=""), make_timing(), "gpt-4o")
    assert "av_caption is empty" in caplog.text


def test_unknown_judge_and_missing_key(monkeypatch):
    with pytest.raises(judge.JudgeUnavailable):
        judge.backend_for("llama-3")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    judge._client.cache_clear()
    with pytest.raises(judge.JudgeUnavailable, match="ANTHROPIC_API_KEY"):
        judge._client("anthropic", "claude-sonnet-4-6")


# --- pipeline wiring ----------------------------------------------------------------------

def test_pipeline_score_writes_judge_files(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.jsonl"
    samples = [
        make_sample(clip_id="c1", dynamic=DynamicType.NONVERBAL_INTERRUPTION, dynamic_start_s=5.0, dynamic_end_s=7.0,
                    duration_s=20.0),
        make_sample(clip_id="c2", dynamic=DynamicType.LAUGHTER, dynamic_start_s=5.0, dynamic_end_s=7.0, duration_s=20.0),
        make_sample(clip_id="c3", dynamic=DynamicType.LAUGHTER, bucket=Bucket.GENERATION, dynamic_start_s=5.0,
                    dynamic_end_s=7.0, duration_s=20.0),
    ]
    write_manifest(samples, manifest)
    run_dir = tmp_path / "runs" / "demo"
    for cid in ("c1", "c2", "c3"):
        d = run_dir / cid
        d.mkdir(parents=True)
        (d / "agent.wav").write_bytes(b"")
        run = AgentRun(clip_id=cid, provider="fake", mode="av", agent_audio_path=str(d / "agent.wav"),
                       meta={"manifest": str(manifest)})
        (d / "run.json").write_text(json.dumps(asdict(run)))
    words = [Word("so", 2.0, 2.3), Word("anyway", 2.4, 3.0), Word("I", 3.1, 3.2), Word("think", 3.3, 6.0)]
    monkeypatch.setattr(asr, "load_or_transcribe", lambda wav, **kw: words)
    seen: list[str] = []

    def fake_call(j, system, user):
        seen.append(user)
        rating = 5 if "Nonverbal Interruption" in user else 3
        return json.dumps({"analysis": "a", "rating": rating, "reasoning": "r"}), {"prompt_tokens": 1000,
                                                                                    "completion_tokens": 50}

    monkeypatch.setattr(judge, "_call", fake_call)
    summary = pipeline.score(run_dir, judge="gpt-4o")
    assert summary["n_clips"] == 3 and summary["n_judged"] == 2
    assert [s["clip_id"] for s in summary["skipped"]] == ["c3"]
    assert summary["per_axis"]["fluency"] == {"mean": 4.0, "sd": pytest.approx(1.4142, abs=1e-3), "n": 2}
    assert summary["per_axis"]["semantic_grounding"]["n"] == 2 and summary["per_axis"]["conversational_flow"]["n"] == 1
    assert summary["per_dynamic"]["Laughter"]["overall"] == {"mean": 3.0, "sd": 0.0, "n": 1}
    assert summary["overall"]["mean"] == 4.0 and summary["usage"]["n_calls"] == 5
    assert summary["usage"]["est_cost_usd"] == pytest.approx(5 * (1000 * 2.5 + 50 * 10) / 1e6)
    j1 = json.loads((run_dir / "c1" / "judge.json").read_text())
    assert j1["judge"] == "gpt-4o" and j1["overall"] == 5.0 and set(j1["axes"]) == {
        "fluency", "conversational_flow", "semantic_grounding"}
    assert "Yield analysis:" in seen[0] and "Agent role: YIELDING." in seen[0]
    assert (run_dir / "c1" / "judge" / "semantic_grounding_gpt-4o.json").exists()
    assert not (run_dir / "c3" / "judge.json").exists()
    # second run is fully cached; a second judge is kept side by side in by_judge
    n_before = len(seen)
    s2 = pipeline.score(run_dir, judge="gpt-4o")
    assert len(seen) == n_before and s2["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "n_calls": 0,
                                                      "n_cached": 5, "est_cost_usd": 0.0}
    pipeline.score(run_dir, judge="claude-sonnet-4-6", axes="fluency")
    j1 = json.loads((run_dir / "c1" / "judge.json").read_text())
    assert j1["judge"] == "claude-sonnet-4-6" and set(j1["axes"]) == {"fluency"}
    assert set(j1["by_judge"]) == {"gpt-4o", "claude-sonnet-4-6"} and j1["by_judge"]["gpt-4o"]["overall"] == 5.0
    assert json.loads((run_dir / "judge_summary.json").read_text())["judge"] == "claude-sonnet-4-6"


# --- one real gpt-4o call -----------------------------------------------------------------

GOOD_TIMING = {
    "agent_role": "SILENT",
    "transcript": "Oh, that is such a familiar feeling. What did it turn out to be?",
    "overlap_line": "Agent in-window speech: 0.00s (no segments overlap [4.00, 7.00])",
    "partition_block": ("-- PRE-DYNAMIC (0.00 -> 4.00s) -- active 0.00s of 4.00s (0%)\n"
                        "-- DYNAMIC WINDOW (4.00 -> 7.00s) -- active 0.00s of 3.00s (0%)\n"
                        "(no agent speech overlaps the dynamic window)\n"
                        "-- POST-DYNAMIC (7.00 -> 10.00s) -- active 2.40s of 3.00s (80%)\n"
                        "[  8.40, 10.80] 2.40s"),
    "yield_block": None,
}
BAD_TIMING = {
    "agent_role": "SILENT",
    "transcript": "Right, so what I would say about that is that it really depends on the situation and",
    "overlap_line": "Agent in-window speech: 2.70s total across 1 segment(s) --- [4.30-8.10] overlaps by 2.70s",
    "partition_block": ("-- PRE-DYNAMIC (0.00 -> 4.00s) -- active 0.00s of 4.00s (0%)\n"
                        "-- DYNAMIC WINDOW (4.00 -> 7.00s) -- active 2.70s of 3.00s (90%)\n"
                        "[  4.30, 7.00] 2.70s\n"
                        "-- POST-DYNAMIC (7.00 -> 10.00s) -- active 1.10s of 3.00s (37%)\n"
                        "[  7.00, 8.10] 1.10s"),
    "yield_block": None,
}


@pytest.mark.network
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
def test_gpt4o_separates_good_from_bad_pause_handling(tmp_path, capsys):
    s = make_sample()
    good = judge.score_axis(s, GOOD_TIMING, Axis.CONVERSATIONAL_FLOW, "gpt-4o", cache_dir=tmp_path / "good")
    bad = judge.score_axis(s, BAD_TIMING, Axis.CONVERSATIONAL_FLOW, "gpt-4o", cache_dir=tmp_path / "bad")
    for r in (good, bad):
        assert 0 <= r.rating <= 5 and r.analysis and r.reasoning and r.cached is False
    with capsys.disabled():
        for name, r in (("good", good), ("bad", bad)):
            print(f"\n[gpt-4o conversational_flow/{name}] rating={r.rating} usage={r.usage} "
                  f"cost=${judge.estimate_cost_usd(r.usage, 'gpt-4o'):.4f}\n  reasoning: {r.reasoning}")
    assert good.rating > bad.rating
