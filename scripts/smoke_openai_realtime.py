"""One real OpenAI Realtime call on a ~10 s synthetic clip (WS6a smoke test).

    uv run python scripts/smoke_openai_realtime.py [--mode av|a2a] [--model gpt-realtime|gpt-realtime-mini]
                                                   [--dur 10] [--out runs/smoke_openai_realtime]

Needs OPENAI_API_KEY in .env. Reuses the Gemini smoke script's synthetic clip (macOS `say`
speech, falls back to beeps; a drawn "face" video) so the model has something to answer;
`agent_speaks_first=True` exercises the 2 s text-kick path. Prints the model that accepted
the session, first-audio latency, drift, non-silent seconds, transcript and any API error
events verbatim. In `av` mode one JPEG per second is sent as an `input_image` item.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from smoke_gemini_live import make_user_wav, make_video

from ovfdb.harness.base import AUDIO_SR
from ovfdb.harness.providers.openai_realtime import DEFAULT_MODEL, OpenAIRealtime
from ovfdb.harness.streamer import stream_sample
from ovfdb.schema import Bucket, DynamicType, Sample


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="a2a", choices=["av", "a2a"])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dur", type=float, default=10.0)
    ap.add_argument("--tail", type=float, default=5.0)
    ap.add_argument("--out", default="runs/smoke_openai_realtime")
    ap.add_argument("--voice", default=None)
    ap.add_argument("--no-speak-first", action="store_true")
    ap.add_argument("--no-input-transcript", action="store_true")
    args = ap.parse_args()

    out = Path(args.out) / args.model / args.mode
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
    agent = OpenAIRealtime(model=args.model, voice=args.voice, transcribe_input=not args.no_input_transcript)
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
    m = run.meta
    print(json.dumps({
        "provider": run.provider, "model": run.model, "session_model": m.get("session_model"),
        "session_updated": m.get("session_updated"), "errors": run.errors, "drift_ms": run.drift_ms,
        "max_drift_ms": m.get("max_drift_ms"), "first_audio_t": m.get("first_audio_t"),
        "speak_first_path": m.get("speak_first_path"), "text_kick_t": m.get("text_kick_t"),
        "output_rate": m.get("output_rate"), "interruptions": m.get("interruptions"),
        "responses": m.get("responses"), "responses_cancelled": m.get("responses_cancelled"),
        "truncations": m.get("truncations"), "video_path": m.get("video_path"),
        "n_audio_sent": m.get("n_audio_sent"), "n_frames_sent": m.get("n_frames_sent"),
        "n_recv_chunks": m.get("n_recv_chunks"), "agent_audio_end_s": m.get("agent_audio_end_s"),
        "voiced_s": round(voiced_s, 2), "wav_len_s": round(len(x) / AUDIO_SR, 2),
        "recv_monotone": recv_t == sorted(recv_t), "n_events": len(events),
        "event_counts": m.get("event_counts"),
        "transcript": " ".join(p["text"] for p in m.get("output_transcript", [])).strip(),
        "input_transcript": " ".join(p["text"] for p in m.get("input_transcript", [])).strip(),
        "agent_wav": run.agent_audio_path,
    }, indent=1))
    return 0 if voiced_s > 0.5 and not run.errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
