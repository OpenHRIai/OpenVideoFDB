"""WS6c generation judge: frame plan, consistency rules, payload text, rubric dispatch, video resolution,
message assembly, ffmpeg composite round-trip (synthetic lavfi media), pipeline wiring with a stubbed judge.

No network: the judge call is monkeypatched. The media tests need ffmpeg/ffprobe on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from ovfdb.schema import AXES, AgentRun, Axis, Bucket, DynamicType, Sample, Segment, Word, write_manifest
from ovfdb.score import judge as J
from ovfdb.score import judge_generation as G
from ovfdb.score import pipeline, report

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not on PATH")

CAPTION = "0.0s - 3.0s: The user tells a story and bursts out laughing at 3s. 3.0s - 6.0s: She keeps smiling."


def make_sample(dynamic=DynamicType.LAUGHTER, **kw) -> Sample:
    words = [Word("so", 0.0, 0.2), Word("that", 0.3, 0.5), Word("happened", 0.6, 1.0), Word("ha", 3.0, 3.4),
             Word("yeah", 5.0, 5.3)]
    d = {"clip_id": "g1", "conversation_id": "x", "bucket": Bucket.GENERATION, "dynamic_type": dynamic,
         "dynamic_start_s": 3.0, "dynamic_end_s": 4.0, "duration_s": 6.0, "user_audio_path": "u.wav",
         "user_video_path": "u.mp4", "av_caption": CAPTION, "user_words": words, "source": "nvidia"}
    d.update(kw)
    return Sample(**d)


def make_timing(segments=None, transcript="Oh no, haha.") -> dict:
    segs = [{"start": 4.5, "end": 5.2, "text": "Oh no, haha.", "n_words": 3}] if segments is None else segments
    return {"agent_role": "EXCHANGING", "segments": segs, "transcript": transcript,
            "overlap_line": "Agent in-window speech: 0.00s (no segments overlap [3.00, 4.00])",
            "partition_block": "-- PRE-DYNAMIC --", "yield_block": None}


# --- frame plan ------------------------------------------------------------------------------

def test_frame_times_fps_and_cap():
    t = G.frame_times(57.0)
    assert len(t) == 456 and t[0] == 0.0 and t[1] == pytest.approx(0.125) and t[-1] == pytest.approx(455 / 8)
    assert G.effective_fps(57.0) == 8.0
    t = G.frame_times(100.0)                                   # 800 nominal -> capped, spread uniformly
    assert len(t) == 600 and G.effective_fps(100.0) == pytest.approx(6.0) and t[-1] == pytest.approx(599 / 6)
    assert t == sorted(t) and len(set(t)) == len(t)
    assert len(G.frame_times(2.0, fps=8, max_frames=600)) == 16
    assert len(G.frame_times(2.0, fps=4, max_frames=5)) == 5 and G.effective_fps(2.0, 4, 5) == pytest.approx(2.5)
    assert G.frame_times(0.0) == [] and G.frame_times(5.0, fps=0) == [] and G.frame_times(5.0, max_frames=0) == []
    assert len(G.frame_times(0.05)) == 1                       # a clip shorter than one frame period still gets a frame


def test_thin_indices():
    assert G.thin_indices(10, 20) == list(range(10)) and G.thin_indices(0, 5) == [] and G.thin_indices(5, 0) == []
    idx = G.thin_indices(600, 500)
    assert len(idx) == 500 and idx[0] == 0 and idx[-1] == 599 and idx == sorted(set(idx))
    assert G.thin_indices(7, 1) == [0] and G.thin_indices(7, 2) == [0, 6]


# --- decomposed schema ---------------------------------------------------------------------------

def test_parse_decomposed_and_consistency():
    raw = '```json\n{"analysis": "AGENT pane smiles at 3.2s", "cue_produced": 1, "cue_timing": "During", ' \
          '"cue_appropriateness": "4", "reasoning": "ok"}\n```'
    d = G.parse_decomposed(raw)
    assert d == {"analysis": "AGENT pane smiles at 3.2s", "cue_produced": 1, "cue_timing": "during",
                 "cue_appropriateness": 4, "reasoning": "ok"}
    assert G.enforce_consistency(d) == (d, [])
    # cue_produced=0 forces absent / 0
    d0 = {"analysis": "", "cue_produced": 0, "cue_timing": "late", "cue_appropriateness": 3, "reasoning": ""}
    fixed, fixes = G.enforce_consistency(d0)
    assert fixed["cue_timing"] == "absent" and fixed["cue_appropriateness"] == 0 and len(fixes) == 2
    assert d0["cue_timing"] == "late"                           # input untouched
    # produced but 'absent': appropriateness 0 -> not produced; otherwise -> late
    fixed, fixes = G.enforce_consistency({**d0, "cue_produced": 1, "cue_timing": "absent", "cue_appropriateness": 0})
    assert fixed["cue_produced"] == 0 and fixed["cue_timing"] == "absent" and len(fixes) == 1
    fixed, fixes = G.enforce_consistency({**d0, "cue_produced": 1, "cue_timing": "absent", "cue_appropriateness": 4})
    assert fixed["cue_produced"] == 1 and fixed["cue_timing"] == "late" and fixed["cue_appropriateness"] == 4
    for bad in ('{"cue_produced": 1, "cue_timing": "soon", "cue_appropriateness": 4}',
                '{"cue_produced": 2, "cue_timing": "late", "cue_appropriateness": 4}',
                '{"cue_produced": 1, "cue_timing": "late", "cue_appropriateness": 6}',
                '{"cue_produced": 1, "cue_timing": "late"}', "not json at all"):
        with pytest.raises(J.JudgeParseError):
            G.parse_decomposed(bad)


# --- system prompt / dispatch --------------------------------------------------------------------

def test_system_prompt_dispatch_all_generation_dynamics():
    gen_dynamics = sorted({d for d, b in AXES if b is Bucket.GENERATION}, key=lambda d: d.value)
    assert len(gen_dynamics) == 7
    preamble = J.load_rubric("generation_preamble")
    for dyn in gen_dynamics:
        s = make_sample(dyn)
        cue = G.build_system_prompt(Axis.CUE_APPROPRIATENESS, s)
        assert cue.startswith(preamble) and "CATEGORY: (G)" in cue and '"cue_produced": 0 or 1' in cue
        assert "Internal-consistency rules" in cue
        flu = G.build_system_prompt(Axis.GEN_FLUENCY, s)
        assert "UNIVERSAL AXIS: Generation Fluency" in flu and '"rating": integer 0-5' in flu and "cue_produced" not in flu
    assert G.rubric_name(Axis.AFFECT_MATCH, DynamicType.TURN_TAKING) == "generation_affect_match"
    assert G.rubric_name(Axis.CUE_APPROPRIATENESS, DynamicType.EMOTION_MATCHING) == "generation_face_emotion_display"
    assert "Affect Match" in J.load_rubric("generation_affect_match") and "caps at score 3" in J.load_rubric("generation_affect_match")
    with pytest.raises(ValueError):
        G.rubric_name(Axis.FLUENCY, DynamicType.LAUGHTER)
    with pytest.raises(ValueError):
        G.rubric_name(Axis.CUE_APPROPRIATENESS, DynamicType.PAUSE_HANDLING)


# --- payload text -------------------------------------------------------------------------------

def test_overlap_signal():
    user = [Segment(0.0, 5.0, "a b c d", 4), Segment(6.0, 8.0, "e f g", 3)]
    agent = [Segment(4.0, 7.0, "x", 1), Segment(7.5, 7.8, "y", 1), Segment(9.0, 10.0, "z", 1)]
    sig = G.overlap_signal(user, agent)
    assert sig["n_user_turns"] == 2 and sig["total_s"] == pytest.approx(2.3) and sig["n_events"] == 2
    assert sig["max_event_s"] == pytest.approx(2.0) and sig["events_over"] == {"1": 1, "1.5": 1, "4": 0}
    line = G.overlap_line(sig)
    assert line.startswith("Agent--user overlap: 2 substantive user turns; total 2.30s; 1 events > 1s; 1 events > 1.5s; 0 events > 4s.")
    assert G.overlap_signal([], agent)["total_s"] == 0.0
    s = make_sample()
    subs = G.substantive_user_segments(s)
    assert [(x.start, x.end) for x in subs] == [(0.0, 1.0)]     # "ha" and "yeah" are too short to be turns


def test_build_user_text_sections():
    s = make_sample()
    plan = {"n": 48, "fps": 8.0, "width": 256}
    txt = G.build_user_text(s, make_timing(), plan)
    lines = txt.split("\n")
    assert lines[0] == G.FRAMING_NOTE
    assert lines[1].startswith("Frames: 48 JPEG frames sampled uniformly at 8.00 fps from t=0.00s to t=5.88s")
    assert "Category: Laughter\nDynamic event (user stimulus): t=3.00s to t=4.00s\nClip duration: 6.00s\n" in txt
    assert "\nAnnotated cue: the user laughs during their own turn" in txt
    assert txt.index("USER STIMULUS (for context only --- do not grade this):") < txt.index("=== AGENT OUTPUT --- GRADE THIS ===")
    assert '"""\n' + CAPTION + '\n"""' in txt and "[0.00-1.00s] so that happened" in txt
    assert "Dynamic window: 3.00-4.00s\nAgent was SILENT during the dynamic window --- no segments overlap.\n" in txt
    assert "Pre-window agent audio: none\nPost-window agent audio: [4.50-5.20s] (+0.50s post)" in txt
    assert "Agent--user overlap: 1 substantive user turns; total 0.00s;" in txt
    assert f"Agent visual caption: {G.NOT_AVAILABLE}" in txt and f"Agent audio caption: {G.NOT_AVAILABLE}" in txt
    assert "Agent speech segments: [4.50-5.20s]\n" in txt and "[4.50-5.20s] Oh no, haha." in txt
    assert txt.endswith('Agent speech transcript:\n"""\nOh no, haha.\n"""\nUse the right half of each frame (and right-channel '
                        "audio) to grade the agent on the 0-5 scale per the rubric above.")
    # in-window agent audio, wordless VAD span, no plan line without a plan
    t2 = make_timing(segments=[{"start": 2.8, "end": 3.5, "text": "", "n_words": 0},
                               {"start": 1.0, "end": 1.4, "text": "mm", "n_words": 1}], transcript="mm")
    txt2 = G.build_user_text(s, t2)
    assert "Frames:" not in txt2
    assert "Agent audio overlapping the dynamic window: [2.80-3.50s] (0.50s in window)" in txt2
    assert "Pre-window agent audio: [1.00-1.40s] (1.60s pre)" in txt2 and "Post-window agent audio: none" in txt2
    assert "Agent speech segments: [1.00-1.40s], [2.80-3.50s]" in txt2 and f"[2.80-3.50s] {J.NO_LEXICAL}" in txt2
    txt3 = G.build_user_text(make_sample(av_caption=""), make_timing(segments=[], transcript=""))
    assert J.NO_CAPTION in txt3 and "Agent speech segments: none (agent produced no audible speech)" in txt3
    assert f'Agent speech transcript:\n"""\n{J.NO_SPEECH}\n"""' in txt3


# --- agent video resolution ---------------------------------------------------------------------

def test_resolve_agent_video(tmp_path):
    clip = tmp_path / "clip"
    clip.mkdir()
    s = make_sample(partner_video_path=str(tmp_path / "partner.mp4"))
    run = AgentRun(clip_id="g1", provider="human_gt", mode="av", agent_audio_path=str(clip / "agent.wav"))
    p, how = G.resolve_agent_video(s, run, clip)
    assert p is None and "partner video" in how
    (tmp_path / "partner.mp4").write_bytes(b"x")
    p, how = G.resolve_agent_video(s, run, clip)
    assert p == tmp_path / "partner.mp4" and how.startswith("human partner video")
    # explicit agent_video_path wins; a stale stored path falls back to <clip_dir>/<name> or <clip_dir>/agent.mp4
    run2 = AgentRun(clip_id="g1", provider="tavus_cvi", mode="av", agent_audio_path="", agent_video_path="/stale/agent.mp4")
    p, how = G.resolve_agent_video(s, run2, clip)
    assert p is None and "does not exist" in how
    (clip / "agent.mp4").write_bytes(b"x")
    assert G.resolve_agent_video(s, run2, clip) == (clip / "agent.mp4", "run.json agent_video_path")
    run3 = AgentRun(clip_id="g1", provider="tavus_cvi", mode="av", agent_audio_path="", agent_video_path="/stale/x.mp4")
    assert G.resolve_agent_video(s, run3, clip) == (clip / "agent.mp4", "run.json agent_video_path")
    # random: the mp4 next to the partner wav in run.json meta
    (tmp_path / "other.wav").write_bytes(b"x")
    run4 = AgentRun(clip_id="g1", provider="random", mode="av", agent_audio_path="", meta={"partner_wav": str(tmp_path / "other.wav")})
    assert G.resolve_agent_video(s, run4, clip)[0] is None
    (tmp_path / "other.mp4").write_bytes(b"x")
    assert G.resolve_agent_video(s, run4, clip)[0] == tmp_path / "other.mp4"
    run5 = AgentRun(clip_id="g1", provider="gemini_live", mode="av", agent_audio_path="")
    p, how = G.resolve_agent_video(s, run5, clip)
    assert p is None and "audio-only" in how


# --- message assembly -----------------------------------------------------------------------------

def test_message_content_shapes_and_backend_caps(tmp_path):
    frames = []
    for i in range(3):
        f = tmp_path / f"{i:05d}.jpg"
        f.write_bytes(b"\xff\xd8\xff" + bytes([i]))
        frames.append(f)
    oc = G.openai_content(frames, "TEXT")
    assert len(oc) == 4 and oc[-1] == {"type": "text", "text": "TEXT"}
    assert oc[0]["type"] == "image_url" and oc[0]["image_url"]["detail"] == "low"
    assert oc[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    ac = G.anthropic_content(frames, "TEXT")
    assert ac[0]["type"] == "image" and ac[0]["source"]["media_type"] == "image/jpeg" and ac[-1]["type"] == "text"
    many = [frames[i % 3] for i in range(600)]
    assert len(G.frames_for_backend(many, "gpt-4o")) == 500
    assert len(G.frames_for_backend(many, "claude-sonnet-4-6")) == 100
    assert len(G.frames_for_backend(many, "gemini-2.5-pro")) == 600
    assert G.frames_for_backend(frames, "gpt-4o") == frames
    assert G.frames_digest(frames) != G.frames_digest(frames[:2]) and len(G.frames_digest(frames)) == 64


# --- media (ffmpeg) -------------------------------------------------------------------------------

def _lavfi_video(path, size: str, seconds: float, rate: int = 25, color="testsrc"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{color}=size={size}:rate={rate}",
                    "-t", f"{seconds}", "-pix_fmt", "yuv420p", str(path)], check=True)


def _lavfi_wav(path, seconds: float, freq: int):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=16000",
                    "-t", f"{seconds}", "-ac", "1", str(path)], check=True)


@pytest.fixture
def media(tmp_path):
    u, a = tmp_path / "user.mp4", tmp_path / "agent.mp4"
    _lavfi_video(u, "320x240", 2.0)
    _lavfi_video(a, "640x360", 1.0)                   # shorter agent video: last frame is held
    uw, aw = tmp_path / "user.wav", tmp_path / "agent.wav"
    _lavfi_wav(uw, 2.0, 440)
    _lavfi_wav(aw, 1.0, 880)
    return u, a, uw, aw


@needs_ffmpeg
def test_composite_and_frames_roundtrip(tmp_path, media):
    u, a, uw, aw = media
    sbs = G.build_composite(u, a, tmp_path / "gen" / "sbs.mp4", 2.0, user_audio=uw, agent_audio=aw, pane_h=120)
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,channels",
                          "-of", "csv=p=0", str(sbs)], capture_output=True, text=True, check=True).stdout
    assert "video,374,120" in out                      # 4:3 user pane 160 wide + 16:9 agent pane 214 wide, 120 high
    assert ",2" in out                                                          # stereo
    m = G.extract_frames(sbs, tmp_path / "gen" / "frames", 2.0, fps=8, max_frames=600, width=256)
    assert m["n"] == 16 and m["fps"] == 8.0 and len(m["files"]) == 16 and m["times"][1] == pytest.approx(0.125)
    from PIL import Image
    with Image.open(tmp_path / "gen" / "frames" / m["files"][0]) as im:
        assert im.size[0] == 256 and im.mode == "RGB"
    assert json.loads((tmp_path / "gen" / "frames" / "frames.json").read_text())["n"] == 16
    m2 = G.extract_frames(sbs, tmp_path / "gen" / "frames2", 2.0, fps=8, max_frames=5, width=128)
    assert m2["n"] == 5 and m2["fps"] == pytest.approx(2.5)


@needs_ffmpeg
def test_prepare_frames_caches(tmp_path, media):
    u, a, uw, aw = media
    clip = tmp_path / "clip"
    clip.mkdir()
    s = make_sample(duration_s=2.0, user_video_path=str(u), user_audio_path=str(uw), partner_video_path=str(a))
    run = AgentRun(clip_id="g1", provider="human_gt", mode="av", agent_audio_path=str(aw))
    gen = clip / "generation" / "gen"
    m = G.prepare_frames(s, run, clip, gen, fps=8, max_frames=600, width=256)
    assert m["n"] == 16 and m["source"].startswith("human partner video") and (gen / "sbs.mp4").exists()
    stamp = (gen / "sbs.mp4").stat().st_mtime_ns, (gen / "frames" / m["files"][0]).stat().st_mtime_ns
    m2 = G.prepare_frames(s, run, clip, gen, fps=8, max_frames=600, width=256)
    assert m2["files"] == m["files"]
    assert ((gen / "sbs.mp4").stat().st_mtime_ns, (gen / "frames" / m["files"][0]).stat().st_mtime_ns) == stamp
    m3 = G.prepare_frames(s, run, clip, gen, fps=4, max_frames=600, width=256)      # new plan -> new frames
    assert m3["n"] == 8 and (gen / "sbs.mp4").stat().st_mtime_ns == stamp[0]
    with pytest.raises(G.GenerationJudgeError):
        G.prepare_frames(s, AgentRun(clip_id="g1", provider="gemini_live", mode="av", agent_audio_path=str(aw)), clip, gen)


# --- pipeline with a stubbed judge ---------------------------------------------------------------

@needs_ffmpeg
def test_score_generation_pipeline(tmp_path, media, monkeypatch):
    u, a, uw, aw = media
    run_dir = tmp_path / "runs" / "gt"
    s1 = make_sample(clip_id="g1", duration_s=2.0, user_video_path=str(u), user_audio_path=str(uw), partner_video_path=str(a))
    s2 = make_sample(clip_id="g2", dynamic_type=DynamicType.TURN_TAKING, duration_s=2.0, user_video_path=str(u),
                     user_audio_path=str(uw), partner_video_path=None)            # no agent video -> skipped
    s3 = make_sample(clip_id="g3", bucket=Bucket.PERCEPTION, dynamic_type=DynamicType.LAUGHTER, duration_s=2.0,
                     user_video_path=str(u), user_audio_path=str(uw))              # perception row: ignored here
    man = tmp_path / "m.jsonl"
    write_manifest([s1, s2, s3], man)
    for s in (s1, s2, s3):
        d = run_dir / s.clip_id
        d.mkdir(parents=True)
        shutil.copy(aw, d / "agent.wav")
        json.dump({"clip_id": s.clip_id, "provider": "human_gt", "mode": "av", "agent_audio_path": str(d / "agent.wav"),
                   "meta": {}}, (d / "run.json").open("w"))
        rd = d / s.bucket.value
        rd.mkdir()
        (rd / "timing.json").write_text(json.dumps({"clip_id": s.clip_id, "provider": "human_gt", "mode": "av",
                                                    "bucket": s.bucket.value, "dynamic_type": s.dynamic_type.value,
                                                    "timing_class": None, "timing": None, **make_timing()}))
    calls: list[tuple[str, int]] = []

    def fake_call(judge, system, text, frames):
        axis = "cue" if "cue_produced" in system else ("affect" if "Affect Match" in system else "fluency")
        calls.append((axis, len(frames)))
        assert text.startswith(G.FRAMING_NOTE) and 0 < len(frames) <= 16
        if axis == "cue":
            return json.dumps({"analysis": "a", "cue_produced": 1, "cue_timing": "absent", "cue_appropriateness": 4,
                               "reasoning": "r"}), {"prompt_tokens": 1000, "completion_tokens": 10}
        return json.dumps({"analysis": "a", "rating": 5 if axis == "fluency" else 3, "reasoning": "r"}), \
            {"prompt_tokens": 1000, "completion_tokens": 10}

    monkeypatch.setattr(G, "_call", fake_call)
    summary = pipeline.score_generation(run_dir, judge="gpt-4o", manifest=str(man))
    assert summary["n_generation_rows"] == 2 and summary["n_judged"] == 1 and len(calls) == 3
    assert summary["skipped"] == [{"clip_id": "g2", "bucket": "generation", "reason": "human_gt row without a partner video"}]
    row = summary["rows"][0]
    assert row["axes"] == {"generation_fluency": 5, "affect_match": 3, "cue_appropriateness": 4}
    assert row["cue_produced"] == 1 and row["cue_timing"] == "late" and row["overall"] == pytest.approx(4.0)
    assert row["n_frames"] == 16 and row["usage"] == {"prompt_tokens": 3000, "completion_tokens": 30}
    assert summary["usage"]["n_calls"] == 3 and summary["usage"]["est_cost_usd"] == pytest.approx((3000 * 2.5 + 30 * 10) / 1e6)
    assert summary["usage"]["est_cost_per_fresh_row_usd"] == pytest.approx(summary["usage"]["est_cost_usd"])
    assert summary["cue"] == {"n": 1, "produced_rate": 1.0, "timing": {"during": 0, "late": 1, "absent": 0}, "n_consistency_fixes": 1}
    j = json.loads((run_dir / "g1" / "generation" / "judge.json").read_text())
    assert j["judge"] == "gpt-4o" and j["bucket"] == "generation" and j["overall"] == pytest.approx(4.0)
    assert j["axes"]["cue_appropriateness"]["consistency_fixes"] == ["cue_produced=1 with timing 'absent': cue_timing -> 'late'"]
    assert j["frames"]["n"] == 16 and j["by_judge"]["gpt-4o"]["axes"].keys() == j["axes"].keys()
    assert (run_dir / "g1" / "generation" / "judge" / "cue_appropriateness_gpt-4o.json").exists()
    assert (run_dir / "judge_summary_generation.json").exists() and not (run_dir / "judge_summary.json").exists()
    # second run: judge.json already complete -> no calls, counted as cached
    s2nd = pipeline.score_generation(run_dir, judge="gpt-4o", manifest=str(man))
    assert len(calls) == 3 and s2nd["usage"]["n_calls"] == 0 and s2nd["usage"]["n_cached"] == 3 and s2nd["n_judged"] == 1
    assert s2nd["rows"][0]["axes"] == row["axes"]
    # --force re-judges (cache bypassed)
    pipeline.score_generation(run_dir, judge="gpt-4o", manifest=str(man), force=True)
    assert len(calls) == 6
    # report: generation table with the project-page columns; perception table untouched
    out = report.write([run_dir], per_dynamic=True, out=tmp_path / "res" / "s.md", manifest=str(man))
    md = out.read_text()
    assert "# Generation" in md
    assert "| Model | Setting | n | Fluency ↑ | Dyadic Affect ↑ | NV Cue Approp. ↑ | Overall ↑ | Timing ↑ |" in md
    assert "| Human reference | AV2AV | 2 | 5.00 | 3.00 | 4.00 | 4.00 | — |" in md     # n = generation rows (g2 timing-only)
    assert "## Generation per dynamic" in md and "| Human reference | AV2AV | Laughter | 1 | 5.00 | 3.00 | 4.00 | 4.00 |" in md
    assert (tmp_path / "res" / "s_generation.csv").exists()
    gdf = report.summarise([run_dir], bucket="generation")
    assert gdf.iloc[0]["n"] == 2 and gdf.iloc[0]["NV Cue Approp."] == 4.0 and gdf.iloc[0]["NV Cue Approp._n"] == 1
    assert gdf.iloc[0]["Overall"] == 4.0 and gdf.iloc[0]["Overall_n"] == 1
    pdf = report.summarise([run_dir])                      # default table: perception axes, Overall ignores gen rows
    assert pdf.iloc[0]["n"] == 3 and pdf.iloc[0]["Overall_n"] == 0           # g1 gen, g2 gen (timing only), g3 perception
