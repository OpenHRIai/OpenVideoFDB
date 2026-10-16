"""ovfdb.review.app: decision log, manifest apply, row building (no media, no server)."""

from __future__ import annotations

import json

from ovfdb.review import app as R
from ovfdb.schema import Bucket, DynamicType, Sample, Word, read_manifest, write_manifest


def _sample(cid, bucket=Bucket.PERCEPTION, dyn=DynamicType.PAUSE_HANDLING):
    return Sample(clip_id=cid, conversation_id="x", bucket=bucket, dynamic_type=dyn, dynamic_start_s=4.0,
                  dynamic_end_s=6.0, duration_s=20.0, user_audio_path=f"data/clips_t/{cid}/user.wav",
                  user_video_path=f"data/clips_t/{cid}/user.mp4", user_words=[Word("hi", 1.0, 1.2)],
                  source_meta={"t0": 100.0, "t1": 120.0, "mining_rule": "pause_handling",
                               "evidence": {"rule": "pause_handling", "gap_s": 2.0}})


def test_decisions_latest_wins_and_apply(tmp_path):
    man = tmp_path / "m.jsonl"
    write_manifest([_sample("a"), _sample("b"), _sample("c"), _sample("c", Bucket.GENERATION, DynamicType.LAUGHTER)], man)
    rv = tmp_path / "review.jsonl"
    R.record_decision(rv, "a", "perception", "reject", "partner was already talking")
    R.record_decision(rv, "a", "perception", "accept")                       # overrides
    R.record_decision(rv, "b", "perception", "accept", start_s=4.5, end_s=6.5)
    R.record_decision(rv, "c", "generation", "reject")
    dec = R.load_decisions(rv)
    assert dec[("a", "perception")]["decision"] == "accept" and dec[("b", "perception")]["start_s"] == 4.5
    out = tmp_path / "out.jsonl"
    assert R.apply_decisions(man, rv, out) == (3, 1, 1)                       # c/perception unreviewed, kept
    rows = {(s.clip_id, s.bucket.value): s for s in read_manifest(out)}
    assert set(rows) == {("a", "perception"), ("b", "perception"), ("c", "perception")}
    b = rows[("b", "perception")]
    assert (b.dynamic_start_s, b.dynamic_end_s) == (4.5, 6.5)
    assert b.source_meta["dynamic_start_raw_s"] == 104.5 and b.source_meta["review"]["decision"] == "accept"
    assert "review" not in rows[("c", "perception")].source_meta
    assert R.apply_decisions(man, rv, out, keep_unreviewed=False) == (2, 2, 1)
    try:
        R.record_decision(rv, "a", "perception", "maybe")
    except ValueError:
        pass
    else:
        raise AssertionError("bad decision accepted")


def test_build_rows_without_media(tmp_path):
    man = tmp_path / "m.jsonl"
    write_manifest([_sample("a")], man)
    rows = R.build_rows(man)
    assert len(rows) == 1 and rows[0]["clip_id"] == "a" and rows[0]["sbs"] is False
    assert rows[0]["video"].endswith("data/clips_t/a/user.mp4") and rows[0]["partner_words"] == []
    assert rows[0]["cue"].startswith("Mined cue: the user pauses mid-turn for 2.00s")
    assert rows[0]["user_words"] == [{"t": 1.0, "e": 1.2, "w": "hi"}]
    assert json.dumps(rows[0])                                               # JSON-serialisable
