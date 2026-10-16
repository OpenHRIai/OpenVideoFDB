"""ovfdb.data.nvidia: transcript parsing (pure) and, when the snapshot exists, loading the validation split."""

from __future__ import annotations

from pathlib import Path

import pytest

from ovfdb.data import nvidia as N
from ovfdb.schema import Bucket, Word


def test_parse_transcript_chunks_pairs_and_points():
    raw = '[{"text": " Hello", "timestamp": [0.0, 0.4]}, {"text": "there", "timestamp": [0.5, 0.9]}]'
    assert N.parse_transcript_chunks(raw) == [Word("Hello", 0.0, 0.4), Word("there", 0.5, 0.9)]
    # point timestamps: a word ends where the next begins; the last gets +0.3 s
    pts = [{"text": "a", "timestamp": 1.0}, {"text": "b", "timestamp": 1.5}, {"text": "c", "timestamp": 2.0}]
    assert N.parse_transcript_chunks(pts) == [Word("a", 1.0, 1.5), Word("b", 1.5, 2.0), Word("c", 2.0, 2.3)]
    # start/end keys, missing end, junk entries
    mixed = [{"word": "x", "start": 0.0, "end": None}, {"text": "", "timestamp": [1, 2]}, "junk", {"text": "y", "timestamp": [3.0, 3.5]}]
    assert N.parse_transcript_chunks(mixed) == [Word("x", 0.0, 3.0), Word("y", 3.0, 3.5)]
    assert N.parse_transcript_chunks("") == N.parse_transcript_chunks(None) == N.parse_transcript_chunks("not json") == []
    assert N.parse_transcript_chunks({"chunks": [{"text": "z", "timestamp": [0, 1]}]}) == [Word("z", 0.0, 1.0)]


def test_partner_paths_only_when_shipped(tmp_path):
    d = tmp_path / "conv" / "clip"
    d.mkdir(parents=True)
    for n in ("speaker1.wav", "speaker1.mp4", "speaker2.wav"):
        (d / n).write_bytes(b"")
    a, v = N._partner_paths(d / "speaker1.wav", d / "speaker1.mp4")
    assert a == str(d / "speaker2.wav") and v is None
    assert N._partner_paths(d / "other.wav", d / "other.mp4") == (None, None)


@pytest.mark.skipif(not (Path(N.ROOT) / "0_metadata_validation.parquet").exists(), reason="NVIDIA snapshot not present")
def test_load_validation_split():
    rows = N.load("validation")
    assert len(rows) == 11 and len({r.clip_id for r in rows}) == 8
    assert {r.bucket for r in rows} == {Bucket.PERCEPTION, Bucket.GENERATION}
    for r in rows:
        assert r.source == "nvidia" and r.av_caption and r.system_prompt and r.duration_s > 0
        assert 0 <= r.dynamic_start_s <= r.dynamic_end_s <= r.duration_s + 0.5
        assert Path(r.user_audio_path).exists() and Path(r.user_video_path).exists()
        assert all(w.end >= w.start for w in r.user_words)
    # the user is speaker1 or speaker2 per row; the other channel ships for only some validation clips
    with_partner = [r for r in rows if r.partner_audio_path]
    assert with_partner and all(Path(r.partner_audio_path).exists() for r in with_partner)


def _sample(cid, bucket=Bucket.PERCEPTION):
    from ovfdb.schema import DynamicType, Sample
    return Sample(clip_id=cid, conversation_id="x", bucket=bucket, dynamic_type=DynamicType.LAUGHTER, dynamic_start_s=1.0,
                  dynamic_end_s=2.0, duration_s=10.0, user_audio_path=f"data/clips_t/{cid}/speaker1.wav",
                  user_video_path=f"data/clips_t/{cid}/speaker1.mp4")


def test_run_dir_names_split_dual_bucket_clips_that_swap_the_user():
    from ovfdb.schema import run_dir_names
    a_p = _sample("a"); a_g = _sample("a", Bucket.GENERATION)                 # same user channel: shared dir
    b_p = _sample("b"); b_g = _sample("b", Bucket.GENERATION)
    b_g.user_audio_path = "data/clips_t/b/speaker2.wav"                      # NVIDIA-style swap: own dirs
    names = run_dir_names([a_p, a_g, b_p, b_g, _sample("c")])
    assert names[("a", "perception")] == names[("a", "generation")] == "a"
    assert names[("b", "perception")] == "b__perception" and names[("b", "generation")] == "b__generation"
    assert names[("c", "perception")] == "c"
