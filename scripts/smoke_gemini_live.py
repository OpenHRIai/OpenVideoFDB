"""One real Gemini Live call on a ~10 s synthetic clip (WS3 smoke test).

    uv run python scripts/smoke_gemini_live.py [--mode av|a2a] [--model ID] [--dur 10] [--out runs/smoke_gemini_live]

Needs GOOGLE_API_KEY in .env. The user channel is macOS `say` speech (falls back to
beeps) so the model has something to answer; `agent_speaks_first=True` exercises the
2 s text-kick path. Prints the model that accepted the connection, first-audio latency,
drift, non-silent seconds, transcript and any API errors verbatim; on a model-not-found
error it lists the live/native-audio models visible to the key.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ovfdb.harness.base import AUDIO_SR
from ovfdb.harness.providers.gemini_live import DEFAULT_MODEL, GeminiLive, list_live_models
from ovfdb.harness.streamer import stream_sample
from ovfdb.schema import Bucket, DynamicType, Sample

USER_TEXT = ("Hi there! I'm testing a voice assistant. Can you tell me, in one or two sentences, "
             "a fun fact about octopuses?")


def make_user_wav(path: Path, dur: float) -> str:
    """`say` speech padded to `dur` seconds (16 kHz mono), else beeps at 1 s and 6 s."""
    tmp = path.with_suffix(".aiff")
    if shutil.which("say") and shutil.which("ffmpeg"):
        try:
            subprocess.run(["say", "-o", str(tmp), USER_TEXT], check=True, capture_output=True, timeout=60)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-ac", "1", "-ar", str(AUDIO_SR),
                            "-af", f"adelay=500|500,apad=whole_dur={dur}", "-t", str(dur), str(path)],
                           check=True, capture_output=True, timeout=60)
            tmp.unlink(missing_ok=True)
            return "say"
        except Exception as e:  # noqa: BLE001
            print(f"say/ffmpeg failed ({e!r}); using beeps")
    t = np.arange(int(dur * AUDIO_SR)) / AUDIO_SR
    x = np.zeros_like(t)
    for t0 in (1.0, 6.0):
        m = (t >= t0) & (t < t0 + 0.5)
        x[m] = 0.3 * np.sin(2 * np.pi * 440 * t[m])
    sf.write(str(path), (x * 32767).astype(np.int16), AUDIO_SR, subtype="PCM_16")
    return "beeps"


def make_video(path: Path, dur: float, fps: int = 10, size: int = 256) -> None:
    import av
    from PIL import Image, ImageDraw

    with av.open(str(path), "w") as c:
        s = c.add_stream("mpeg4", rate=fps)
        s.width = s.height = size
        s.pix_fmt = "yuv420p"
        for i in range(int(dur * fps)):
            img = Image.new("RGB", (size, size), (30, 30, 60))
            d = ImageDraw.Draw(img)
            d.ellipse([60, 40, 196, 176], fill=(230, 200, 170))   # a "face"
            d.text((20, 220), f"t={i / fps:.1f}s", fill=(255, 255, 255))
            for pkt in s.encode(av.VideoFrame.from_image(img)):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="av", choices=["av", "a2a"])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dur", type=float, default=10.0)
    ap.add_argument("--tail", type=float, default=5.0)
    ap.add_argument("--out", default="runs/smoke_gemini_live")
    ap.add_argument("--no-speak-first", action="store_true")
    args = ap.parse_args()

    out = Path(args.out) / args.mode
    out.mkdir(parents=True, exist_ok=True)
    wav, mp4 = out / "user.wav", out / "user.mp4"
    src = make_user_wav(wav, args.dur)
    make_video(mp4, args.dur)
    sample = Sample(
        clip_id=f"smoke_{args.mode}", conversation_id="smoke", bucket=Bucket.GENERATION,
        dynamic_type=DynamicType.TURN_TAKING, dynamic_start_s=0.0, dynamic_end_s=args.dur, duration_s=args.dur,
        user_audio_path=str(wav), user_video_path=str(mp4),
        system_prompt=("You are a friendly, concise voice conversation partner on a video call. "
                       "Keep replies to one or two short sentences. "
                       "Start speaking now to begin/continue the conversation."),
        agent_speaks_first=not args.no_speak_first,
    )
    agent = GeminiLive(model=args.model)
    print(f"model={args.model} mode={args.mode} user_audio={src} dur={args.dur}s tail={args.tail}s")
    t_wall = time.monotonic()
    run = await stream_sample(sample, agent, args.mode, fps=1.0, tail_s=args.tail, out_dir=out)
    print(f"wall={time.monotonic() - t_wall:.1f}s")

    x, _ = sf.read(run.agent_audio_path, dtype="int16")
    frames = x[: len(x) // 320 * 320].reshape(-1, 320).astype(np.float32)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    voiced_s = float((rms > 300).sum() * 0.02)
    events = [json.loads(line) for line in Path(run.events_path).read_text().splitlines()]
    recv_t = [e["t"] for e in events if e["type"] == "recv"]
    print(json.dumps({
        "provider": run.provider, "model": run.model, "errors": run.errors, "drift_ms": run.drift_ms,
        "max_drift_ms": run.meta.get("max_drift_ms"), "first_audio_t": run.meta.get("first_audio_t"),
        "speak_first_path": run.meta.get("speak_first_path"), "text_kick_t": run.meta.get("text_kick_t"),
        "output_rate": run.meta.get("output_rate"), "interruptions": run.meta.get("interruptions"),
        "n_audio_sent": run.meta.get("n_audio_sent"), "n_frames_sent": run.meta.get("n_frames_sent"),
        "n_recv_chunks": run.meta.get("n_recv_chunks"), "agent_audio_end_s": run.meta.get("agent_audio_end_s"),
        "voiced_s": round(voiced_s, 2), "wav_len_s": round(len(x) / AUDIO_SR, 2),
        "recv_monotone": recv_t == sorted(recv_t), "n_events": len(events),
        "transcript": " ".join(p["text"] for p in run.meta.get("output_transcript", [])).strip(),
        "agent_wav": run.agent_audio_path,
    }, indent=1))
    if any("not found" in e.lower() or "not supported" in e.lower() or "1008" in e for e in run.errors):
        print("live models visible to this key:")
        for m in list_live_models():
            print("  ", m)
    return 0 if voiced_s > 0.5 and not run.errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
