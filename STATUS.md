# STATUS — shared progress board

Update this file at the start (claim) and end (report) of every session.
Keep entries terse. Dates are absolute (YYYY-MM-DD).

## Contract changes
_Record any edit to `ovfdb/schema.py` or `ovfdb/harness/base.py` here so other sessions rebase._
- 2026-10-15 — initial schema (WS0).
- 2026-10-15 — `harness/base.py`: `AudioOut` gained `flush: bool = False` (barge-in: drop queued-unplayed audio at `t_received`; maps Gemini `server_content.interrupted`). Providers stamp `t_received` on their own clock (t=0 at first `push_audio`); streamer re-stamps on drain, keeps provider value as `t_agent` in events. (WS3)

## Board
| WS | Status | Session / owner | Last update | Notes / blockers |
|----|--------|-----------------|-------------|------------------|
| WS0 scaffold | done | session 1 | 2026-10-15 | schema, stubs, docs, plans |
| WS1 seamless data | done | agent (session 1) | 2026-10-15 | fetch/movement/trim/to_sample/quality gate; 14 tests incl. network. Movement features absent for all annotated nat/test files (see data-sources.md) |
| WS2 mining | in progress (day-1 dialogue dynamics) | agent (session 1) | 2026-10-15 | dialogue finders + VLM verify + prompts; nonverbal dynamics are a day-2 follow-up |
| WS3 harness (Gemini Live) | done | agent (session 1) | 2026-10-15 | streamer/recorder/human_gt/random/gemini_live; live smoke OK on `gemini-3.1-flash-live-preview` (AV + a2a), drift < 40 ms, no errors. `scripts/smoke_gemini_live.py` |
| WS4 scoring: ASR + timing | done | agent (session 1) | 2026-10-15 | segments/timing/asr/pipeline; 31 tests; faster-whisper small.en int8 ≈ 8× RT. `timing.json` carries all judge blocks except caption/user words |
| WS5 judge + calibration | judge done; calibration pending | agent (session 1) | 2026-10-15 | rubrics verbatim, judge (gpt-4o/claude/gemini backends), report w/ bootstrap CIs; gpt-4o good=5 / bad=1 on synthetic Pause Handling. ≈$0.01/clip. Calibration needs WS2 manifest |
| WS6 providers: OpenAI RT, Tavus/Anam, gen judge | todo | — | — | needs WS3, WS5 |
| WS7 NVIDIA adapter | blocked (external) | — | 2026-10-15 | access requested 2026-10-15, awaiting approval; **not on the critical path** — all other WS run on Seamless |
| WS8 report + publish | todo | — | — | last |

## Decisions log
- 2026-10-15 — Perception bucket first; generation is a stretch (needs video-out agents).
- 2026-10-15 — Seamless `naturalistic` split only (improvised uses actors).
- 2026-10-15 — ASR: faster-whisper (paper: Parakeet 0.6B v2). Judge: GPT-4o primary (as paper) + Claude second judge for agreement. AV captioner: Gemini Flash (paper: Qwen3.5-397B + Nemotron-Omni).
- 2026-10-15 — Clip time origin = first user audio chunk sent to agent.

## Open questions
- Agent replies often run past `clip + tail_s` (default 5 s). Consider `tail_s=8–10` for real runs; agent.wav is truncated to the window by design.
- Recorder uses playback-queue placement (Gemini bursts audio faster than real time); `t_received` of the *first* chunk of a burst is the onset. Document in protocol §8 once calibrated.
- Which provider API keys are available? (fugubook `.env` has TAVUS/ANAM/OPENAI/GOOGLE per survey.)
- NVIDIA access: requested 2026-10-15, pending. Non-blocking.
