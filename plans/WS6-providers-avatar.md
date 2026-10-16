# WS6 — More providers + generation bucket (stretch)

**Depends on:** WS3 (contract, streamer), WS5 (judge). **Est.:** 4–6 h.
**Files:** `ovfdb/harness/providers/openai_realtime.py`,
`ovfdb/harness/providers/playwright_avatar.py`, `ovfdb/harness/web/*`,
`ovfdb/score/judge_generation.py`, `ovfdb/score/rubrics/generation_*.txt`,
`ovfdb/score/lanes.py`.

## 6a. OpenAI Realtime (2 h)
- WebSocket `wss://api.openai.com/v1/realtime?model=gpt-realtime` (and
  `gpt-realtime-mini`), `session.update` with `instructions=system_prompt`,
  `turn_detection: server_vad`, input 16 kHz? → OpenAI wants pcm16 @ 24 kHz;
  resample. Append audio with `input_audio_buffer.append`. Output
  `response.audio.delta` pcm16 24 kHz → recorder.
- Video: if the model accepts image items (`conversation.item.create` with
  `input_image`), send 1 fps frames; otherwise run A2A only and record
  `mode="a2a"`. Don't fake AV.

## 6b. Tavus CVI / Anam via headless Chromium (3–4 h) — the only route to generation scores
- Pattern from fugubook `session_runner.py` + `bridge.ts`
  (`docs/reference/fugubook-reuse.md`): Playwright Chromium with
  `--use-fake-device-for-media-stream --use-file-for-fake-video-capture=user.y4m --use-file-for-fake-audio-capture=user.wav`.
  Convert clip with ffmpeg: `-pix_fmt yuv420p user.y4m`, wav 48 kHz.
- A minimal page `harness/web/avatar.html` loads the vendor JS SDK (Tavus CVI
  conversation via Daily; Anam via their SDK/LiveKit), joins with
  `getUserMedia({audio,video})`, and records the remote participant with
  MediaRecorder (VP8+Opus WebM) streamed to Python over a WebSocket, plus
  `performance.now()` timestamps for first remote audio/video frame.
- Clock origin: the moment the page calls `getUserMedia` ≈ clip t=0 (the fake
  device starts playback at track creation). Log and subtract any join delay.
- Persona/system prompt via the vendor API before joining; LLM behind the
  avatar = the vendor's default (document which).
- Output: `agent.webm` → `agent.wav` (16 kHz) + `agent.mp4`.

## 6c. Generation judge (2 h)
- Rubrics verbatim from F.6.2–F.6.4 (`generation_preamble.txt`,
  `affect_match.txt`, `generation_fluency.txt`, per-category decomposed).
- Payload per F.6.1: SBS composite (user left / agent right; audio L/R) →
  frames at 8 fps, ≤ 600, 256 px wide, JPEG; plus text block. Judge must be
  vision-capable (gpt-4o, claude-sonnet-4-6, gemini-2.5-pro).
- Decomposed schema + consistency rules (`docs/protocol.md` §6).
- Optional evidence: run fugubook `extract_lanes.py` on `agent.mp4` and inject
  "agent head-nod / smile / gaze lanes in-window" lines into the text block
  (document as a deviation).

## Acceptance
- OpenAI Realtime A2A run on 10 clips scores end-to-end.
- One Tavus or Anam clip produces `agent.mp4` with the avatar visibly
  responding; generation judge returns valid decomposed JSON.
