# WS3 — Real-time harness + Gemini Live provider

**Goal:** stream a clip's user audio (+ frames) to an agent in real time, record
the agent's audio with clip-relative timestamps. **Depends on:** WS0.
**Unblocks:** WS6. **Est.:** 4 h.
**Files:** `ovfdb/harness/base.py` (contract — edit with care, log in STATUS),
`ovfdb/harness/streamer.py`, `ovfdb/harness/providers/gemini_live.py`,
`ovfdb/harness/providers/human_gt.py`, `ovfdb/harness/recorder.py`,
`tests/test_streamer.py`.

## Contract (`base.py`)
```python
class Agent(Protocol):
    name: str
    async def start(self, system_prompt: str, mode: Literal["av","a2a"]) -> None
    async def push_audio(self, pcm16k: bytes, t: float) -> None   # 20–100 ms chunks
    async def push_frame(self, jpeg: bytes, t: float) -> None     # AV mode only, ~1 fps
    async def stop(self) -> None
    # output: agent audio arrives via an asyncio.Queue[(pcm16k_bytes, t_received)]
```
`AgentRun` (schema.py) is the result: `agent_audio_path` (16 kHz mono wav whose
sample 0 = clip t=0, silence-padded), `provider`, `mode`, `started_at`,
`events` (send/receive log), `errors`.

## Streamer (`streamer.py`)
- Decode `user.wav` → 16 kHz PCM16; decode `user.mp4` → JPEG frames at `fps`
  (default 1; 256–512 px wide) with pyav/imageio-ffmpeg.
- Pace by wall clock: chunk i is pushed no earlier than `t0 + i*chunk_s`.
  Assert total drift < 100 ms at the end; record actual send times.
- Mixer/recorder: received audio chunks are placed at `t_received` in a
  silence buffer and written to `agent.wav`. Keep the raw chunk log too.
- Continue streaming `clip_duration + tail_s` (default 5 s) of silence so late
  responses are captured.

## Gemini Live (`providers/gemini_live.py`)
- `google-genai` SDK, `client.aio.live.connect(model, config)`; model default
  `gemini-2.5-flash-native-audio-preview` (make it a flag; paper used 2.5 and
  3.1 Flash Native/Live). `response_modalities=["AUDIO"]`, system instruction =
  clip `system_prompt`. Send audio via `send_realtime_input(audio=...)` at
  16 kHz PCM; frames via `send_realtime_input(video=...)` JPEG. Output audio
  is 24 kHz PCM → resample to 16 kHz in the recorder.
- Disable automatic VAD? No — keep server VAD (that *is* the full-duplex
  behaviour under test). Do not send `activity_start/end`.
- For `agent_speaks_first`, after `start()` send one text turn "Start speaking
  now..." only if the system prompt alone does not trigger speech within 2 s
  (log which path was taken).

## Human GT / random (`providers/human_gt.py`)
Not a network agent: `HumanGT` returns `partner.wav` as the agent audio;
`RandomPartner` returns another clip's `partner.wav` (seeded). Needed by WS5
calibration. Trivial but must go through the same `AgentRun` path.

## CLI
`uv run ovfdb run --manifest manifest/ovfdb_v0.jsonl --provider gemini_live --mode av --out runs/<name> [--limit N] [--concurrency 2]`
Writes `runs/<name>/<clip_id>/agent.wav`, `run.json` (AgentRun), `events.jsonl`.

## Acceptance
- `tests/test_streamer.py`: a fake agent that echoes chunks after 300 ms →
  recorded onset within ±50 ms of 0.3 s; total duration = clip + tail.
- One real Gemini Live call on a 20 s clip produces audible, on-topic audio
  and `events.jsonl` with monotone timestamps.
