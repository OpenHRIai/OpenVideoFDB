"""WS1 tests. Parser/gate/rebase tests are pure (inline fixtures, no network);
``@pytest.mark.network`` tests hit the public mirror and ffmpeg
(``uv run pytest -m network tests/test_seamless.py``)."""

from __future__ import annotations

import itertools
import json
import shutil

import pytest

from ovfdb.data import seamless as sm
from ovfdb.schema import Bucket, DynamicType, Segment, Word, sample_from_dict, sample_to_dict

USER = "V03_S0503_I00000074_P2454"
PARTNER = "V03_S0503_I00000074_P2455"
MOVEMENT_FILE = "V00_S0062_I00000137_P0092"   # naturalistic/test, has_imitator_movement=1
T0, T1 = 60.0, 100.0


# --- pure ---------------------------------------------------------------------

def test_interaction_key():
    assert sm.interaction_key(USER) == "V03_S0503_I00000074"
    assert sm.interaction_key(USER) == sm.interaction_key(PARTNER)


def test_read_vad(tmp_path):
    p = tmp_path / "vad.jsonl"
    p.write_text('{"start": 5.0, "end": 6.5}\n\n{"start": 1.0, "end": 2.0}\n')
    segs = sm.read_vad(p)
    assert [(s.start, s.end) for s in segs] == [(1.0, 2.0), (5.0, 6.5)]
    assert segs[1].dur == 1.5


def test_read_transcript(tmp_path):
    p = tmp_path / "transcript.jsonl"
    rows = [
        {"words": [{"word": "The", "start": 7.4, "end": 7.8, "score": 0.5},
                   {"word": "time", "start": 7.8, "end": 8.0, "score": 0.4}],
         "start": 7.4, "end": 8.0, "transcript": "The time"},
        {"words": [{"word": "Thank", "start": 3.5, "end": 3.7, "score": 0.5},
                   {"word": "10,", "start": None, "end": None, "score": 0.0}],   # unaligned word (real data)
         "start": 3.5, "end": 3.7, "transcript": "Thank 10,"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    utts = sm.read_transcript(p)
    assert [u.transcript for u in utts] == ["Thank 10,", "The time"]
    assert [w.text for w in utts[0].words] == ["Thank"]
    assert utts[1].words[0] == Word(text="The", start=7.4, end=7.8)
    words = sm.transcript_words(utts)
    assert [w.text for w in words] == ["Thank", "The", "time"]
    assert all(a.start <= b.start for a, b in itertools.pairwise(words))


def test_read_annotations_is_jsonl(tmp_path):
    p = tmp_path / "3P-V.json"
    p.write_text('{"annotation": "rubs head", "start_ts": 61, "end_ts": 66}\n'
                 '{"annotation": "nods", "start_ts": 10, "end_ts": 12}\n')
    anns = sm.read_annotations(p)
    assert [a.annotation for a in anns] == ["nods", "rubs head"]
    assert (anns[1].start_ts, anns[1].end_ts) == (61.0, 66.0)


def test_words_outside_vad_frac():
    vad = [Segment(1.0, 2.0), Segment(5.0, 6.0)]
    words = [Word("a", 1.1, 1.3), Word("b", 1.9, 2.2),   # inside / overlapping
             Word("c", 3.0, 3.2), Word("d", 7.0, 7.1)]   # outside
    assert sm.words_outside_vad_frac(words, vad) == pytest.approx(0.5)
    assert sm.words_outside_vad_frac([], vad) == 0.0
    assert sm.words_outside_vad_frac(words[:2], vad) == 0.0
    assert sm.words_outside_vad_frac(words, []) == 1.0


def test_rebase_words():
    words = [Word("x", 58.0, 59.0), Word("y", 59.5, 60.5), Word("z", 70.0, 71.0), Word("w", 99.8, 100.4),
             Word("v", 101.0, 102.0)]
    out = sm.rebase_words(words, 60.0, 100.0)
    assert [w.text for w in out] == ["y", "z", "w"]
    assert (out[0].start, out[0].end) == (0.0, 0.5)
    assert (out[1].start, out[1].end) == (10.0, 11.0)
    assert (out[2].start, out[2].end) == pytest.approx((39.8, 40.0))


def test_all_features_pinned():
    assert set(sm.DEFAULT_MOVEMENT_FEATURES) <= set(sm.ALL_FEATURES["movement"])
    assert set(sm.DEFAULT_MOVEMENT_FEATURES) <= set(sm.ALL_FEATURES["movement_v4"])
    assert "is_occluded" in sm.ALL_FEATURES["movement_v4"] and "is_occluded" not in sm.ALL_FEATURES["movement"]
    assert sm.movement_url("F", "FAUValue", "naturalistic", "test") == (
        f"{sm.MIRROR}/naturalistic/test/movement/FAUValue/F.npy")
    with pytest.raises(KeyError):
        sm.fetch_movement(USER, ("not_a_feature",))
    with pytest.raises(KeyError):
        sm.fetch_movement(USER, group="nope")


def test_trim_rejects_bad_window(tmp_path):
    with pytest.raises(ValueError):
        sm.trim(USER, PARTNER, 10.0, 5.0, tmp_path)


# --- network ----------------------------------------------------------------

network = pytest.mark.network
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")


@network
def test_filelist_and_pairs():
    df = sm.load_filelist()
    assert {"file_id", "label", "split", "interaction_key", "participant", "has_imitator_movement"} <= set(df.columns)
    ps = sm.pairs("naturalistic", "test", require_3p=True)
    assert (USER, PARTNER) in ps
    assert all(sm.interaction_key(a) == sm.interaction_key(b) for a, b in ps)


@network
def test_fetch_and_parse():
    got = sm.fetch(USER, ("vad", "transcript", "3P-V"))
    assert set(got) == {"vad", "transcript", "3P-V"}
    vad = sm.read_vad(got["vad"])
    utts = sm.read_transcript(got["transcript"])
    anns = sm.read_annotations(got["3P-V"])
    assert vad and utts and anns
    assert all(a.start <= b.start for a, b in itertools.pairwise(vad))
    assert all(a.start <= b.start for a, b in itertools.pairwise(utts))
    assert all(a.start_ts <= b.start_ts for a, b in itertools.pairwise(anns))
    # absent kinds are skipped (mirror answers 403), not raised
    assert "3P-V" not in sm.fetch(MOVEMENT_FILE, ("3P-V",))


@network
def test_pair_is_consistent():
    assert sm.pair_is_consistent(USER, PARTNER)


@network
def test_fetch_movement():
    import numpy as np

    # The acceptance file has has_imitator_movement=0 -> nothing on the mirror.
    assert not sm.has_movement(USER)
    assert sm.fetch_movement(USER, ("emotion_valence",)) == {}
    assert sm.has_movement(MOVEMENT_FILE)
    got = sm.fetch_movement(MOVEMENT_FILE, ("emotion_valence", "gaze_encodings", "FAUValue"))
    assert set(got) == {"emotion_valence", "gaze_encodings", "FAUValue"}
    arrs = {k: np.load(p, allow_pickle=False) for k, p in got.items()}
    n = arrs["emotion_valence"].shape[0]
    assert n > 1000 and arrs["emotion_valence"].shape == (n, 1)
    assert arrs["gaze_encodings"].shape == (n, 2)
    assert arrs["FAUValue"].shape == (n, 24)
    assert all(a.dtype.kind == "f" for a in arrs.values())
    v4 = sm.fetch_movement(MOVEMENT_FILE, ("emotion_valence",), group="movement_v4")
    assert np.load(v4["emotion_valence"]).shape == (n, 1)


@network
@needs_ffmpeg
def test_trim(tmp_path):
    out = sm.trim(USER, PARTNER, T0, T1, tmp_path / "clip")
    assert set(out) == {"user_wav", "partner_wav", "user_mp4", "partner_mp4"}
    for p in out.values():
        assert p.exists() and p.stat().st_size > 0
        assert sm.media_duration(p) == pytest.approx(T1 - T0, abs=0.1)
    import soundfile as sf
    info = sf.info(out["user_wav"])
    assert (info.samplerate, info.channels, info.subtype) == (16000, 1, "PCM_16")
    import subprocess
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,pix_fmt", "-of", "default=nw=1", str(out["user_mp4"])],
        capture_output=True, text=True, check=True).stdout
    probe = dict(line.split("=", 1) for line in raw.strip().splitlines())
    assert (probe["codec_name"], probe["r_frame_rate"], probe["pix_fmt"]) == ("h264", "30/1", "yuv420p")
    assert min(int(probe["width"]), int(probe["height"])) == 720


@network
@needs_ffmpeg
def test_to_sample(tmp_path):
    s = sm.to_sample(USER, PARTNER, T0, T1, Bucket.PERCEPTION, DynamicType.PAUSE_HANDLING,
                     dynamic_start_s=77.0, dynamic_end_s=83.0, clip_index=3, out_root=tmp_path,
                     system_prompt="be nice", mining_rule="unit-test")
    assert s.clip_id == f"{USER}_c03"
    assert s.conversation_id == "V03_S0503_I00000074"
    assert s.source == "seamless" and s.duration_s == 40.0
    assert (s.dynamic_start_s, s.dynamic_end_s) == (17.0, 23.0)
    assert s.system_prompt == "be nice"
    assert s.source_meta["mining_rule"] == "unit-test"
    assert s.source_meta["user_file_id"] == USER and s.source_meta["t0"] == T0
    assert s.user_words and all(0.0 <= w.start <= w.end <= 40.0 for w in s.user_words)
    assert all(a.start <= b.start for a, b in itertools.pairwise(s.user_words))
    for p in (s.user_audio_path, s.user_video_path, s.partner_audio_path, s.partner_video_path):
        assert p.startswith(str(tmp_path / s.clip_id))
    assert sample_from_dict(sample_to_dict(s)) == s
