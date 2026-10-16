"""WS3 acceptance: real-time streamer + recorder with a fake echo agent and the
offline HumanGT / RandomPartner providers. Runs in real time (a few seconds)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import av
import numpy as np
import pytest
import soundfile as sf
from PIL import Image

from ovfdb.harness.base import AUDIO_CHUNK_S, AUDIO_SR, AudioOut
from ovfdb.harness.providers.human_gt import HumanGT, RandomPartner, pick_other
from ovfdb.harness.recorder import Recorder, resample_pcm16
from ovfdb.harness.streamer import decode_frames, stream_sample
from ovfdb.schema import Bucket, DynamicType, Sample

# --- fixtures -------------------------------------------------------------------

def _sine_wav(path: Path, dur: float, sr: int = AUDIO_SR, f: float = 440.0, start: float = 0.0,
              amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(dur * sr)) / sr
    x = amp * np.sin(2 * np.pi * f * t)
    x[t < start] = 0.0
    pcm = (x * 32767).astype(np.int16)
    sf.write(str(path), pcm, sr, subtype="PCM_16")
    return pcm


def _tiny_mp4(path: Path, dur: float, fps: int = 10, size: int = 64) -> None:
    with av.open(str(path), "w") as c:
        s = c.add_stream("mpeg4", rate=fps)
        s.width = s.height = size
        s.pix_fmt = "yuv420p"
        for i in range(int(dur * fps)):
            arr = np.zeros((size, size, 3), dtype=np.uint8)
            arr[..., 0] = (i * 7) % 256
            frame = av.VideoFrame.from_image(Image.fromarray(arr))
            for pkt in s.encode(frame):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)


def _sample(tmp: Path, clip_id: str, dur: float, partner_start: float | None = None,
            conversation_id: str | None = None) -> Sample:
    wav = tmp / f"{clip_id}_user.wav"
    mp4 = tmp / f"{clip_id}_user.mp4"
    _sine_wav(wav, dur)
    _tiny_mp4(mp4, dur)
    partner = None
    if partner_start is not None:
        partner = tmp / f"{clip_id}_partner.wav"
        _sine_wav(partner, dur, f=660.0, start=partner_start)
    return Sample(clip_id=clip_id, conversation_id=conversation_id or clip_id, bucket=Bucket.PERCEPTION,
                  dynamic_type=DynamicType.PAUSE_HANDLING, dynamic_start_s=1.0, dynamic_end_s=2.0,
                  duration_s=dur, user_audio_path=str(wav), user_video_path=str(mp4),
                  partner_audio_path=str(partner) if partner else None)


def _onset_s(x: np.ndarray, thresh: int = 1000) -> float:
    idx = np.flatnonzero(np.abs(x.astype(np.int32)) > thresh)
    return float(idx[0]) / AUDIO_SR if len(idx) else float("nan")


# --- fake agent -----------------------------------------------------------------

class FakeEchoAgent:
    """Re-emits every pushed audio chunk `delay` seconds later."""

    name = "fake_echo"

    def __init__(self, delay: float = 0.3) -> None:
        self.delay = delay
        self.out: asyncio.Queue[AudioOut] = asyncio.Queue()
        self.frames: list[float] = []
        self.audio_ts: list[float] = []
        self._t0: float | None = None
        self._tasks: set[asyncio.Task] = set()
        self.started = False
        self.stopped = False

    async def start(self, system_prompt: str, mode: str, *, agent_speaks_first: bool = False) -> None:
        self.started = True

    async def push_audio(self, pcm16k: bytes, t: float) -> None:
        if self._t0 is None:
            self._t0 = time.monotonic()
        self.audio_ts.append(t)
        task = asyncio.create_task(self._echo(pcm16k))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _echo(self, pcm: bytes) -> None:
        await asyncio.sleep(self.delay)
        await self.out.put(AudioOut(pcm, time.monotonic() - self._t0))

    async def push_frame(self, jpeg: bytes, t: float) -> None:
        assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI
        self.frames.append(t)

    async def stop(self) -> None:
        self.stopped = True
        for task in list(self._tasks):
            task.cancel()


# --- tests ----------------------------------------------------------------------

def test_resample_pcm16_roundtrip_length():
    x = (np.sin(np.arange(24_000) / 24_000 * 2 * np.pi * 440) * 10_000).astype(np.int16)
    y = np.frombuffer(resample_pcm16(x.tobytes(), 24_000, 16_000), dtype=np.int16)
    assert len(y) == 16_000
    assert 8_000 < np.abs(y).max() < 11_000
    assert resample_pcm16(b"", 24_000, 16_000) == b""


def test_recorder_queue_semantics_and_flush():
    rec = Recorder(AUDIO_SR)
    chunk = b"\x01\x00" * 640  # 40 ms
    assert rec.place(chunk, 1.0) == pytest.approx(1.0)
    # burst: second chunk "received" at the same time is butted against the head
    assert rec.place(chunk, 1.0) == pytest.approx(1.04)
    # tiny jitter (< snap) is snapped to the head
    assert rec.place(chunk, 1.085) == pytest.approx(1.08)
    # real gap is honoured
    assert rec.place(chunk, 2.0) == pytest.approx(2.0)
    assert rec.play_head_s == pytest.approx(2.04)
    assert rec.flush(2.01) == pytest.approx(0.03)
    assert rec.play_head_s == pytest.approx(2.01)
    audio = rec.audio(3.0)
    assert len(audio) == 3 * AUDIO_SR
    assert audio[int(2.0 * AUDIO_SR)] == 1 and audio[int(2.02 * AUDIO_SR)] == 0
    rec2 = Recorder(AUDIO_SR, overlap="sum")
    rec2.place(chunk, 0.0)
    rec2.place(chunk, 0.02)
    a = rec2.audio()
    assert a[0] == 1 and a[int(0.03 * AUDIO_SR)] == 2


def test_decode_frames_at_1fps(tmp_path: Path):
    mp4 = tmp_path / "v.mp4"
    _tiny_mp4(mp4, 3.0)
    frames = decode_frames(mp4, fps=1.0)
    ts = [t for t, _ in frames]
    assert len(frames) == 3
    assert ts == pytest.approx([0.0, 1.0, 2.0], abs=0.11)
    img = Image.open(__import__("io").BytesIO(frames[0][1]))
    assert img.format == "JPEG" and img.size == (64, 64)


async def test_echo_agent_onset_length_drift(tmp_path: Path):
    dur, tail = 3.0, 1.0
    s = _sample(tmp_path, "echo_c00", dur)
    agent = FakeEchoAgent(delay=0.3)
    out = tmp_path / "run"
    run = await stream_sample(s, agent, "av", fps=1.0, tail_s=tail, out_dir=out)

    assert agent.started and agent.stopped
    assert run.errors == []
    assert run.provider == "fake_echo" and run.mode == "av"
    assert len(agent.audio_ts) == int((dur + tail) / AUDIO_CHUNK_S)
    assert len(agent.frames) == 3 and agent.frames == pytest.approx([0.0, 1.0, 2.0], abs=0.11)
    assert abs(run.drift_ms) < 100, run.drift_ms
    assert run.meta["max_drift_ms"] < 100

    x, sr = sf.read(run.agent_audio_path, dtype="int16")
    assert sr == AUDIO_SR
    assert len(x) == int((dur + tail) * AUDIO_SR)        # recording window = clip + tail
    onset = _onset_s(x)
    assert onset == pytest.approx(0.3, abs=0.06), onset
    # echo is still present near the end of the clip (3.0 + 0.3)
    assert np.abs(x[int(3.1 * AUDIO_SR):int(3.25 * AUDIO_SR)].astype(np.int32)).max() > 1000

    events = [json.loads(line) for line in Path(run.events_path).read_text().splitlines()]
    recv_t = [e["t"] for e in events if e["type"] == "recv"]
    assert recv_t == sorted(recv_t) and len(recv_t) > 50
    assert {"start", "send_frame", "send_audio", "send_silence", "recv", "stop"} <= {e["type"] for e in events}
    run_json = json.loads((out / "run.json").read_text())
    assert run_json["clip_id"] == "echo_c00" and run_json["agent_audio_path"] == run.agent_audio_path


async def test_human_gt_reproduces_partner_at_offset(tmp_path: Path):
    dur, tail, p_start = 3.0, 0.5, 1.0
    s = _sample(tmp_path, "hgt_c00", dur, partner_start=p_start)
    agent = HumanGT(s)
    run = await stream_sample(s, agent, "a2a", tail_s=tail, out_dir=tmp_path / "run")
    assert run.errors == [] and run.provider == "human_gt"
    assert run.meta["partner_clip_id"] == "hgt_c00"
    x, _ = sf.read(run.agent_audio_path, dtype="int16")
    assert len(x) == int((dur + tail) * AUDIO_SR)
    onset = _onset_s(x)
    assert onset == pytest.approx(p_start, abs=0.06), onset
    # the sine itself is reproduced (same frequency: compare a 100 ms window by correlation)
    ref, _ = sf.read(s.partner_audio_path, dtype="int16")
    i0, i1 = int(1.5 * AUDIO_SR), int(1.6 * AUDIO_SR)
    a = x[i0 - 800:i1 + 800].astype(np.float64)
    b = ref[i0:i1].astype(np.float64)
    corr = np.correlate(a, b, mode="valid")
    peak = corr.max() / (np.linalg.norm(b) ** 2)
    assert peak > 0.9, peak
    # the partner stops when the user clip does: silence in the tail
    assert np.abs(x[int(3.1 * AUDIO_SR):].astype(np.int32)).max() < 50


async def test_random_partner_picks_other_clip_deterministically(tmp_path: Path):
    a = _sample(tmp_path, "a_c00", 1.0, partner_start=0.0, conversation_id="conv_a")
    b = _sample(tmp_path, "b_c00", 1.0, partner_start=0.2, conversation_id="conv_b")
    c = _sample(tmp_path, "c_c00", 1.0, partner_start=0.4, conversation_id="conv_c")
    manifest = [a, b, c]
    picks = {pick_other(a, manifest, seed=0).clip_id for _ in range(5)}
    assert len(picks) == 1 and "a_c00" not in picks
    assert pick_other(a, manifest, seed=0).clip_id == pick_other(a, manifest, seed=0).clip_id
    agent = RandomPartner(a, manifest, seed=0)
    assert agent.meta["partner_clip_id"] in {"b_c00", "c_c00"}
    assert agent.wav_path == next(s for s in manifest if s.clip_id == agent.meta["partner_clip_id"]).partner_audio_path
    run = await stream_sample(a, agent, "a2a", tail_s=0.2, out_dir=tmp_path / "run")
    assert run.errors == [] and run.provider == "random"
    assert run.meta["partner_clip_id"] == agent.meta["partner_clip_id"]
    x, _ = sf.read(run.agent_audio_path, dtype="int16")
    assert len(x) == int(1.2 * AUDIO_SR)
    assert np.abs(x.astype(np.int32)).max() > 1000
