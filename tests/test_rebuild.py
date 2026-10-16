"""ovfdb.data.seamless.rebuild_from_manifest: skip/limit bookkeeping without touching the network."""

from __future__ import annotations

from ovfdb.data import seamless as sm
from ovfdb.schema import Bucket, DynamicType, Sample, write_manifest


def _row(tmp_path, cid, exists):
    d = tmp_path / "clips" / cid
    if exists:
        d.mkdir(parents=True, exist_ok=True)
        (d / "user.wav").write_bytes(b"")
        (d / "user.mp4").write_bytes(b"")
    return Sample(clip_id=cid, conversation_id="c", bucket=Bucket.PERCEPTION, dynamic_type=DynamicType.PAUSE_HANDLING,
                  dynamic_start_s=1.0, dynamic_end_s=2.0, duration_s=10.0, user_audio_path=str(d / "user.wav"),
                  user_video_path=str(d / "user.mp4"),
                  source_meta={"user_file_id": "V00_X_P1", "partner_file_id": "V00_X_P2", "t0": 5.0, "t1": 15.0})


def test_rebuild_skips_existing_and_counts_failures(tmp_path, monkeypatch):
    rows = [_row(tmp_path, "a", True), _row(tmp_path, "a", True), _row(tmp_path, "b", False)]
    rows[1].bucket = Bucket.GENERATION                     # same clip in two buckets: one rebuild
    man = tmp_path / "m.jsonl"
    write_manifest(rows, man)
    calls = []

    def fake_trim(user_id, partner_id, t0, t1, out_dir, video=True):
        calls.append((user_id, partner_id, t0, t1, str(out_dir), video))
        raise FileNotFoundError("mirror has no video")       # no network in tests

    monkeypatch.setattr(sm, "trim", fake_trim)
    c = sm.rebuild_from_manifest(man)
    assert c == {"rows": 3, "clips": 2, "built": 0, "skipped": 1, "failed": 1}
    assert calls == [("V00_X_P1", "V00_X_P2", 5.0, 15.0, str(tmp_path / "clips" / "b"), True)]
    assert sm.rebuild_from_manifest(man, limit=1)["failed"] == 0        # limit reached after the skipped clip
