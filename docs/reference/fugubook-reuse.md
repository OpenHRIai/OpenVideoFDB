# What to reuse from `../fugubook` (surveyed 2026-10-15)

Short version: fugubook has **no** Gemini Live / OpenAI Realtime / LiveKit
client and **no user-video injection** (every transceiver is video `recvonly`;
telephony `TransportParams` has no `video_in`). Its Tavus/HeyGen/Anam code
drives those vendors' *lip-sync renderers* from our own STT→LLM→TTS pipecat
pipeline, not their conversational products. Reusable pieces:

## Feeding a pre-recorded clip into a WebRTC-only vendor (Tavus CVI, Anam)
- `apps/renderer-bridge/renderer_bridge/session_runner.py` (`_run_with_playwright`)
  and `smoke_test.py` launch headless Chromium with
  `--use-fake-device-for-media-stream`. Add
  `--use-file-for-fake-video-capture=clip.y4m --use-file-for-fake-audio-capture=clip.wav`
  and `getUserMedia` replays the clip. Cheapest path to AV input for browser SDKs.
- `apps/arena-renderer/web/bridge.ts`: `connectSide()` (sendrecv audio
  transceiver, `createSilentTrack()`, `sender.replaceTrack()`),
  `maybeStartRecorder()` / `startAvaturnRecorder()` (MediaRecorder VP8+Opus WebM
  streamed over a backchannel WebSocket), `startAudioCapture` + `PcmCaptureProcessor`
  (AudioWorklet raw 48 kHz PCM).
- `SessionRunner._write_outputs()` writes `track_{a,b}.webm` + `transcript.json`.
- Python alternative: `apps/arena/arena/webrtc_client.py` (`WebRTCAgentSession`,
  aiortc) — swap its placeholder `AudioStreamTrack` for aiortc `MediaPlayer(file)`.
  `apps/arena/arena/avatar_recorder.py` (`AvatarRecorder`, PyAV muxer, 1280x720 MP4).

## Scoring helpers
- `apps/renderer-bridge/renderer_bridge/metrics_aggregation.py`:
  `turn_gap_latency(energy_entries, ...)` — energy VAD on two channels (20 ms
  grid), onset(Y) − offset(X) at speaker changes. Vendor-agnostic; fits
  "user clip channel vs agent channel". Also `_binarize` / `_segments`,
  `lipsync_f1`, `gaze_on_user_pct`, `lane_metrics`.
- `apps/renderer-bridge/renderer_bridge/audio_pipeline.py`
  (`AudioPipeline.compute_turn_latency`), `mixer.py` (`AudioMixer`),
  `backfill_session_metrics.py` (offline latency from two track files).
- `avatar-bench/extract_lanes.py` (+ identical `tools/extract_lanes.py`, module
  form `renderer_bridge/lane_extraction.py`): MediaPipe FaceLandmarker at 8 fps →
  `head_frontal`, `eye_contact`, `blink`, `mouth_openness`, `audio_envelope`,
  `gaze_angle_deg`, head pose, `av_sync_offset_ms`, `ttff_ms`. Needs
  `face_landmarker.task` beside the script. Useful as *evidence* for the
  generation judge (did the avatar nod/smile in-window?).
- `avatar-bench/aggregate_stats.py`: `lipsync_score`, `gaze_on_user_pct`.
- `renderer_bridge/composite.py`: `composite_side_by_side`, `transcode_to_mp4`
  (ffmpeg) — reuse for the SBS judge video.
- ASR: `renderer_bridge/stt.py` `DeepgramSTT` (raw WebSocket, linear16 48 kHz).
  We default to faster-whisper instead; keep as an option.
- LLM judge pattern: `renderer_bridge/evaluator.py` (Gemini Flash on transcripts).

## Env / keys known to exist there
`DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `TAVUS_API_KEY`,
`HEYGEN_API_KEY`, `ANAM_API_KEY`, `AVATURN_LIVE_API_KEY`, `CARTESIA_API_KEY`.

## Not reusable
- Telephony pipecat pipeline (own STT/LLM/TTS; not the systems under test).
- Challenge arena (text-transcript challenges), matchmaker, Prisma leaderboard.
- Known bugs there: ~25 % video packet loss on the aiortc path, agents dropping
  after 30–45 s — prefer the Playwright path for avatar vendors.
