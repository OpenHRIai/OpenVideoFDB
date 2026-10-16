# OpenVideoFDB — plan

Goal: an open, runnable version of VideoFDB (NVIDIA, arXiv 2605.30256) in ~2
person-days, with no manual annotation pass beyond ~1 hour of spot checks.

## What VideoFDB is (one paragraph)
237 clips from two-person video calls, each centred on one of 11 nonverbal
conversational dynamics (pause handling, gaze aversion, laughter, nods, adaptors,
interruptions, backchannels, turn-taking, emotion display/matching). One
participant becomes the "user": their audio+video is streamed in real time to the
agent under test, with a clip-specific system prompt; the agent's output stream
is recorded. Scoring = (a) deterministic timing metrics around the annotated
event window (TOR-Alignment + latency, 5 timing classes) and (b) an LLM judge
scoring 0–5 on rubric axes (perception: Fluency, Conversational Flow, Semantic
Grounding; generation: Fluency, Dyadic Affect Match, Nonverbal Cue
Appropriateness). Full details: `docs/protocol.md`.

## Facts that shape the design
- NVIDIA's HF dataset (`nvidia/video-full-duplex-benchmark`) ships *all*
  annotations for both splits, including the 226-row test set. Only the
  official reference scores are withheld. It is gated, approved per user, and
  non-redistributable. → We write a loader for it (WS7) and can run the real
  benchmark locally once access is approved, but the open release must use
  other data.
- No evaluation code has been released by NVIDIA (paper, dataset card and
  project page all say "coming"). Submission today = email per-sample outputs.
- Meta's Seamless Interaction dataset (`facebook/seamless-interaction`,
  CC-BY-NC 4.0) is the open source of clips: per-participant 1080p video,
  denoised 48 kHz audio, 100 Hz VAD, word-level transcripts, 30 Hz movement
  features (emotion valence/arousal, FAUs, gaze/head encodings), and for ~90
  dev/test files timestamped third-party visual annotations. Every file is
  individually downloadable over HTTPS — no 50 GB tars. Prefer `naturalistic`
  (the `improvised` split uses actors).
- `fugubook` has no Gemini Live / OpenAI Realtime / LiveKit client and no
  user-video injection. Reusable pieces: Chromium fake-capture-from-file flags
  (`apps/renderer-bridge/renderer_bridge/session_runner.py`), MediaRecorder
  capture + backchannel (`apps/arena-renderer/web/bridge.ts`),
  `turn_gap_latency` (`renderer_bridge/metrics_aggregation.py`), `DeepgramSTT`
  (`renderer_bridge/stt.py`), face/gaze lane extraction (`avatar-bench/`).
  See `docs/reference/fugubook-reuse.md`.
- Perception bucket (agent takes audio+video, emits audio) covers 7/11 dynamics
  and every model family in the paper. Generation bucket needs video-out agents
  (Tavus/Anam) and a vision judge → stretch.

## Workstreams
| WS | Name | Spec | Depends on | Est. |
|----|------|------|-----------|------|
| WS0 | Schema + scaffold (done in session 1) | — | — | 1 h |
| WS1 | Seamless data layer: filelist, per-file fetch, pairing, trim | `plans/WS1-data-seamless.md` | WS0 | 2 h |
| WS2 | Mining: candidate finders for the 11 dynamics + VLM verify + review page | `plans/WS2-mining.md` | WS1 | 5 h |
| WS3 | Harness: real-time clip streamer + Gemini Live provider + recording | `plans/WS3-harness.md` | WS0 | 4 h |
| WS4 | Scoring: ASR with word timestamps + timing metrics (App. C.2) | `plans/WS4-scoring-timing.md` | WS0 | 3 h |
| WS5 | LLM judge: perception prompts (App. F) + AV captioner + GT/random calibration | `plans/WS5-judge.md` | WS4 | 4 h |
| WS6 | More providers: OpenAI Realtime; Tavus/Anam via Playwright; generation judge | `plans/WS6-providers-avatar.md` | WS3, WS5 | 4–6 h |
| WS7 | NVIDIA dataset adapter (gated) | `plans/WS7-nvidia-adapter.md` | WS0 | 1 h |
| WS8 | Report table, README, HF manifest publish | `plans/WS8-report-publish.md` | all | 2 h |

Parallelisable from the start: WS1, WS3, WS4, WS7 (independent). WS2 needs WS1;
WS5 needs WS4's segment format; WS6 needs WS3+WS5; WS8 last.

## Day plan (single person; sessions can overlap)
**Day 1**
- AM: WS1, then WS2 dialogue-channel dynamics (Pause Handling, Verbal
  Backchanneling, Verbal Interruption, Turn-taking, Laughter) — these fall
  out of VAD + transcript of both participants. In parallel: WS3 (Gemini
  Live), WS4 (timing + ASR), WS7 (request NVIDIA access *now*).
- PM: WS5 judge. **Calibrate before evaluating any model**: run the real
  partner's channel as the "agent" (human ground truth) and a mismatched
  partner channel (random baseline) through ASR→timing→judge. Paper GT means:
  ~4.5 Fluency / ~4.5 Flow / ~4.2 Grounding; random must land far below.
  Then first real run: Gemini Live AV vs A2A on the ~50 day-1 clips.

**Day 2**
- AM: WS2 nonverbal dynamics (Nonverbal Backchanneling, Face Emotion Display,
  Emotion Matching, Gaze Avoidance with Pause, Adaptor Handling, Nonverbal
  Interruption) from movement features + 3P-V text + VLM verify. Target
  100–120 clips, ≥8 per dynamic. Generate `agent_speaks_first` prompts (F.4).
- PM: WS6 OpenAI Realtime; Tavus/Anam if time (only path to generation
  scores). WS8 report + publish manifest/scripts to GitHub and HF.

## Non-goals (for now)
- Matching NVIDIA's absolute numbers (different captioner, no reference scores).
  Validity evidence = GT/random separation + cross-judge agreement.
- Open-weight models (MiniCPM-o etc.) — need a GPU box; add later behind the
  same `Agent` interface.
- Multi-turn evaluation, training splits.

## Definition of done (v0)
- `uv run ovfdb mine` produces `manifest/ovfdb_v0.jsonl` (≥80 clips, all 11
  dynamics) + trimmed media under `data/clips/`.
- `uv run ovfdb run --provider gemini_live --mode av` records `runs/<run>/<clip>/agent.wav`.
- `uv run ovfdb score <run>` writes per-clip timing + judge JSON and a
  Table-1-style summary with bootstrap CIs.
- GT and random baselines reported alongside.
- README documents protocol, deviations from the paper, licences.
