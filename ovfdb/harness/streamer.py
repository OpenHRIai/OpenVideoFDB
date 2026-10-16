"""Real-time pacing of a Sample's user audio (40 ms chunks) and frames (~1 fps) into an
Agent; drains `Agent.out` into the Recorder; emits an AgentRun.

Clock: t0 = `time.monotonic()` immediately before the first `push_audio`. Chunk i is
pushed no earlier than t0 + i*AUDIO_CHUNK_S; frames are pushed just before the first
audio chunk whose time ≥ the frame's timestamp. After the clip, `tail_s` of silence is
streamed the same way so late responses are captured, then `agent.stop()`.

The recording window is exactly [0, duration + tail_s]: agent.wav is padded or
truncated to that length so every run of a clip has the same shape.

Spec: plans/WS3-harness.md.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import logging
import math
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

from ovfdb.harness.base import (
    AUDIO_CHUNK_S,
    AUDIO_SR,
    DEFAULT_FRAME_FPS,
    DEFAULT_TAIL_S,
    Agent,
    AudioOut,
    Mode,
)
from ovfdb.harness.recorder import Recorder, resample_pcm16
from ovfdb.schema import AgentRun, Sample, _to_jsonable, read_manifest, run_dir_names

log = logging.getLogger(__name__)

CHUNK_SAMPLES = int(AUDIO_SR * AUDIO_CHUNK_S)
CHUNK_BYTES = CHUNK_SAMPLES * 2
SILENCE_CHUNK = b"\x00" * CHUNK_BYTES
MAX_FRAME_WIDTH = 512
JPEG_QUALITY = 80
TRUST_AGENT_STAMP_S = 2.0   # max drain lag under which the provider's t_received is used


# --- media decoding -----------------------------------------------------------

def load_pcm16k(path: str | Path) -> bytes:
    """Read any wav/flac/... → 16 kHz mono int16 bytes."""
    data, sr = sf.read(str(path), dtype="int16", always_2d=True)
    if data.shape[1] > 1:
        data = np.rint(data.astype(np.float32).mean(axis=1)).astype(np.int16)
    else:
        data = data[:, 0]
    return resample_pcm16(np.ascontiguousarray(data).tobytes(), sr, AUDIO_SR)


def decode_frames(path: str | Path, fps: float = DEFAULT_FRAME_FPS,
                  max_width: int = MAX_FRAME_WIDTH) -> list[tuple[float, bytes]]:
    """Decode `path` with PyAV, sampling one frame per 1/fps seconds → [(t, jpeg_bytes)].

    The first frame at or after each target time t_k = k/fps is taken (k = 0, 1, ...),
    so the returned timestamps are the decoded frames' own times, not the targets.
    """
    import av

    out: list[tuple[float, bytes]] = []
    step = 1.0 / fps
    next_target = 0.0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            t = frame.time
            if t is None:
                t = len(out) * step  # no pts: assume regular sampling
            if t + 1e-6 < next_target:
                continue
            img = frame.to_image()
            if img.width > max_width:
                img = img.resize((max_width, max(1, round(img.height * max_width / img.width))))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
            out.append((float(t), buf.getvalue()))
            next_target = math.floor(t / step + 1e-6) * step + step
    return out


def _chunks(pcm: bytes) -> list[bytes]:
    n = math.ceil(len(pcm) / CHUNK_BYTES)
    pad = n * CHUNK_BYTES - len(pcm)
    pcm = pcm + b"\x00" * pad
    return [pcm[i * CHUNK_BYTES:(i + 1) * CHUNK_BYTES] for i in range(n)]


# --- streaming ----------------------------------------------------------------

async def stream_sample(sample: Sample, agent: Agent, mode: Mode, fps: float = DEFAULT_FRAME_FPS,
                        tail_s: float = DEFAULT_TAIL_S, out_dir: str | Path | None = None,
                        extra_meta: dict | None = None) -> AgentRun:
    """Stream one Sample through `agent` in real time and return the AgentRun.

    If `out_dir` is given, writes `<out_dir>/agent.wav` and `<out_dir>/events.jsonl`
    (and `run.json`). Errors from the agent are collected in `AgentRun.errors`; the
    streamer always tries to call `agent.stop()`.
    """
    errors: list[str] = []
    rec = Recorder(AUDIO_SR)
    started_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")

    pcm = await asyncio.to_thread(load_pcm16k, sample.user_audio_path)
    clip_s = len(pcm) / 2 / AUDIO_SR
    chunks = _chunks(pcm)
    n_clip = len(chunks)
    n_tail = math.ceil(tail_s / AUDIO_CHUNK_S)
    frames: list[tuple[float, bytes]] = []
    if mode == "av" and sample.user_video_path and Path(sample.user_video_path).exists():
        try:
            frames = await asyncio.to_thread(decode_frames, sample.user_video_path, fps)
        except Exception as e:
            errors.append(f"decode_frames: {e!r}")
            log.exception("frame decoding failed for %s", sample.clip_id)
    elif mode == "av":
        errors.append(f"no video at {sample.user_video_path!r}; ran without frames")

    rec.log("start", 0.0, mode=mode, provider=agent.name, clip_s=round(clip_s, 3), n_frames=len(frames))
    try:
        await agent.start(sample.system_prompt, mode, agent_speaks_first=sample.agent_speaks_first)
    except Exception as e:
        errors.append(f"start: {e!r}")
        log.exception("agent.start failed for %s", sample.clip_id)
        return _finish(sample, agent, mode, rec, clip_s + tail_s, started_at, 0.0, errors, out_dir, dict(extra_meta or {}))

    t0 = time.monotonic()
    stop_drain = asyncio.Event()

    async def drain() -> None:
        q = agent.out
        while True:
            try:
                item: AudioOut = await asyncio.wait_for(q.get(), timeout=0.1)
            except TimeoutError:
                if stop_drain.is_set():
                    return
                continue
            t_drain = time.monotonic() - t0
            # The provider's stamp (t=0 at its first push_audio) is taken when the message is
            # parsed, i.e. never later than the drain time; trust it when the two clocks agree,
            # so an event-loop stall cannot shift a recorded onset.
            t_agent = item.t_received
            t = t_agent if 0.0 <= t_drain - t_agent <= TRUST_AGENT_STAMP_S else t_drain
            if item.flush:
                rec.flush(t)
            elif item.pcm16k:
                rec.place(item.pcm16k, t, t_agent=t_agent)

    drain_task = asyncio.create_task(drain())
    drift_ms = 0.0
    max_drift_ms = 0.0
    fi = 0
    dead = False
    try:
        for i in range(n_clip + n_tail):
            expected = i * AUDIO_CHUNK_S
            due = t0 + expected
            now = time.monotonic()
            if due > now:
                await asyncio.sleep(due - now)
            # frames whose timestamp is ≤ this chunk's time go first
            while fi < len(frames) and frames[fi][0] <= expected + 1e-9:
                ft, jpeg = frames[fi]
                fi += 1
                if dead:
                    continue
                try:
                    await agent.push_frame(jpeg, ft)
                    rec.log("send_frame", ft, len(jpeg), t_sent=round(time.monotonic() - t0, 4))
                except Exception as e:  # noqa: BLE001
                    errors.append(f"push_frame@{ft:.2f}: {e!r}")
                    dead = True
            chunk = chunks[i] if i < n_clip else SILENCE_CHUNK
            if not dead:
                try:
                    await agent.push_audio(chunk, expected)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"push_audio@{expected:.2f}: {e!r}")
                    dead = True
            actual = time.monotonic() - t0
            drift_ms = (actual - expected) * 1000.0
            max_drift_ms = max(max_drift_ms, drift_ms)
            if i == n_clip - 1 or i == n_clip + n_tail - 1 or i % 25 == 0:
                rec.log("send_audio" if i < n_clip else "send_silence", expected, len(chunk),
                        t_sent=round(actual, 4), drift_ms=round(drift_ms, 2))
            if dead and i >= n_clip:
                break  # nothing more to send; still wait out the tail for late audio
        if dead:
            remaining = t0 + (n_clip + n_tail) * AUDIO_CHUNK_S - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
    finally:
        try:
            await agent.stop()
        except Exception as e:  # noqa: BLE001
            errors.append(f"stop: {e!r}")
        stop_drain.set()
        await drain_task
    t_end = time.monotonic() - t0
    rec.log("stop", t_end, drift_ms=round(drift_ms, 2), max_drift_ms=round(max_drift_ms, 2))
    meta = {"max_drift_ms": round(max_drift_ms, 2), "n_frames_sent": fi, "n_recv_chunks": rec.n_chunks,
            "clip_s": round(clip_s, 3), "tail_s": tail_s, "fps": fps,
            "agent_audio_end_s": round(rec.play_head_s, 3)}
    errors.extend(getattr(agent, "errors", []))
    return _finish(sample, agent, mode, rec, clip_s + tail_s, started_at, drift_ms, errors, out_dir,
                   {**meta, **(extra_meta or {})})


def _finish(sample: Sample, agent: Agent, mode: Mode, rec: Recorder, duration_s: float, started_at: str,
            drift_ms: float, errors: list[str], out_dir: str | Path | None, meta: dict) -> AgentRun:
    meta = {**meta, **getattr(agent, "meta", {})}
    wav_path, ev_path = "", None
    if out_dir is not None:
        out_dir = Path(out_dir)
        wav, ev = rec.write(out_dir / "agent.wav", duration_s=duration_s)
        wav_path, ev_path = str(wav), str(ev)
    run = AgentRun(clip_id=sample.clip_id, provider=agent.name, mode=mode, agent_audio_path=wav_path,
                   model=getattr(agent, "model", ""), started_at=started_at, drift_ms=round(drift_ms, 2),
                   events_path=ev_path, errors=errors, meta=meta)
    if out_dir is not None:
        (Path(out_dir) / "run.json").write_text(json.dumps(_to_jsonable(run), indent=1))
    return run


# --- providers registry / manifest runner -------------------------------------

def _make_gemini(sample: Sample, samples: list[Sample], model: str) -> Agent:
    from ovfdb.harness.providers.gemini_live import GeminiLive
    return GeminiLive(model=model) if model else GeminiLive()


def _make_openai_realtime(sample: Sample, samples: list[Sample], model: str) -> Agent:
    from ovfdb.harness.providers.openai_realtime import OpenAIRealtime
    return OpenAIRealtime(model=model) if model else OpenAIRealtime()


def _make_human_gt(sample: Sample, samples: list[Sample], model: str) -> Agent:
    from ovfdb.harness.providers.human_gt import HumanGT
    return HumanGT(sample)


def _make_random(sample: Sample, samples: list[Sample], model: str) -> Agent:
    from ovfdb.harness.providers.human_gt import RandomPartner
    seed = int(model) if model.strip().isdigit() else 0
    return RandomPartner(sample, samples, seed=seed)


#: provider name → factory(sample, all_samples, model) -> Agent (one agent per clip).
PROVIDERS: dict[str, Callable[[Sample, list[Sample], str], Agent]] = {
    "gemini_live": _make_gemini,
    "openai_realtime": _make_openai_realtime,
    "human_gt": _make_human_gt,
    "random": _make_random,
}


def run_manifest(manifest: str | Path, provider: str, mode: str = "av", out: str | Path = "",
                 limit: int = 0, concurrency: int = 1, model: str = "", tail_s: float = DEFAULT_TAIL_S,
                 fps: float = DEFAULT_FRAME_FPS) -> list[AgentRun]:
    """Stream every clip of `manifest` through `provider`; write runs/<out>/<clip_id>/{agent.wav,run.json,events.jsonl}.

    Clips whose run.json already exists are skipped (resumable). `model` is passed to the
    provider (Gemini model id; seed for `random`).
    """
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; known: {sorted(PROVIDERS)}")
    if mode not in ("av", "a2a"):
        raise ValueError(f"mode must be av or a2a, got {mode!r}")
    samples = read_manifest(manifest)
    out_dir_root = Path(out or f"runs/{provider}_{mode}")
    out_dir_root.mkdir(parents=True, exist_ok=True)
    (out_dir_root / "manifest.jsonl").write_text(Path(manifest).read_text(encoding="utf-8"), encoding="utf-8")
    todo = samples[:limit] if limit else samples
    out_dir = Path(out or f"runs/{provider}_{mode}")
    out_dir.mkdir(parents=True, exist_ok=True)
    factory = PROVIDERS[provider]
    dir_names = run_dir_names(samples)          # <clip_id>, or <clip_id>__<bucket> when buckets swap the user

    async def main() -> list[AgentRun]:
        sem = asyncio.Semaphore(max(1, concurrency))
        results: list[AgentRun] = []

        async def one(s: Sample) -> None:
            clip_dir = out_dir / dir_names[(s.clip_id, s.bucket.value)]
            if (clip_dir / "run.json").exists():
                log.info("skip %s (run.json exists)", clip_dir.name)
                return
            async with sem:
                agent = factory(s, samples, model)
                log.info("run %s via %s", s.clip_id, agent.name)
                run = await stream_sample(s, agent, mode, fps=fps, tail_s=tail_s, out_dir=clip_dir,
                                          extra_meta={"manifest": str(manifest)})
                if run.errors:
                    log.warning("%s: %d error(s): %s", s.clip_id, len(run.errors), run.errors[:2])
                results.append(run)

        await asyncio.gather(*(one(s) for s in todo))
        return results

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(main())
