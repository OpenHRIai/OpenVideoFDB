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
| WS2 mining | day-1 done; day-2 nonverbal in progress | agent (session 1) | 2026-10-15 | manifest v0: 60 rows / 54 clips, 10 per (dynamic,bucket) for Pause, VBackch, VInterrupt, Turn-taking, Laughter P+G. VLM accept 65 %. Nonverbal 6 dynamics + review page next |
| WS3 harness (Gemini Live) | done | agent (session 1) | 2026-10-15 | streamer/recorder/human_gt/random/gemini_live; live smoke OK on `gemini-3.1-flash-live-preview` (AV + a2a), drift < 40 ms, no errors. `scripts/smoke_gemini_live.py` |
| WS4 scoring: ASR + timing | done | agent (session 1) | 2026-10-15 | segments/timing/asr/pipeline; 31 tests; faster-whisper small.en int8 ≈ 8× RT. `timing.json` carries all judge blocks except caption/user words |
| WS5 judge + calibration | judge done; calibration pending | agent (session 1) | 2026-10-15 | rubrics verbatim, judge (gpt-4o/claude/gemini backends), report w/ bootstrap CIs; gpt-4o good=5 / bad=1 on synthetic Pause Handling. ≈$0.01/clip. Calibration needs WS2 manifest |
| WS6 providers: OpenAI RT, Tavus/Anam, gen judge | 6a done; 6b/6c todo | agent (session 1) | 2026-10-15 | openai_realtime provider live-verified (gpt-realtime, -mini; AV via input_image items, 1 fps). Tavus/Anam + generation judge still todo |
| WS7 NVIDIA adapter | blocked (external) | — | 2026-10-15 | access requested 2026-10-15, awaiting approval; **not on the critical path** — all other WS run on Seamless |
| WS8 report + publish | todo | — | — | last |

## Decisions log
- 2026-10-15 — Perception bucket first; generation is a stretch (needs video-out agents).
- 2026-10-15 — Seamless `naturalistic` split only (improvised uses actors).
- 2026-10-15 — ASR: faster-whisper (paper: Parakeet 0.6B v2). Judge: GPT-4o primary (as paper) + Claude second judge for agreement. AV captioner: Gemini Flash (paper: Qwen3.5-397B + Nemotron-Omni).
- 2026-10-15 — Publish manifest only (file_ids + timestamps + labels + prompts/captions) and a re-fetch/trim command; never re-host Seamless media. CC-BY-NC 4.0 allows it, but privacy exposure isn't worth it.
- 2026-10-15 — Clip time origin = first user audio chunk sent to agent.

## Calibration findings (2026-10-15, preliminary, 14/20 perception rows judged)
- GT overall 4.18 (Flu 4.07 / Flow 4.60 / Ground 3.5 n=4) vs random 2.32 — judge separates. TOR-Align GT 70 % vs random 27.5 %.
- GT Turn-taking 50 %: human onset lands 80–370 ms after our tight window end (whisper onset lag + windows 0.3–1.3 s). Fix: handoff onset tolerance (~0.5 s) in timing.py; min window 1.0 s in mining.
- GT Verbal Backchanneling 40 %: whisper drops non-lexical "mhm"; "Mm-hmm"/"Yeah. Yeah." count as 2 words; 1.04 s > 1.0 s. Fix: agent segments = VAD on agent.wav ∪ ASR words; backchannel tokenisation (hyphenated/repeated token = 1 word); ±0.25 s window tolerance.
- Pause Handling 100 %, Verbal Interruption 90 % on GT — fine.
- Scoring was per clip dir, losing the perception row of clips shared across buckets (6 Laughter clips). Fix in progress: outputs per (clip, bucket).

## Open questions
- OpenAI Realtime: video is item-based (one image per frame, seen at next response), not a continuous stream like Gemini Live; gpt-realtime speaks spontaneously on the first TTS pause while -mini needs the text kick. Report per model.
- Agent replies often run past `clip + tail_s` (default 5 s). Consider `tail_s=8–10` for real runs; agent.wav is truncated to the window by design.
- Recorder uses playback-queue placement (Gemini bursts audio faster than real time); `t_received` of the *first* chunk of a burst is the onset. Document in protocol §8 once calibrated.
- Which provider API keys are available? (fugubook `.env` has TAVUS/ANAM/OPENAI/GOOGLE per survey.)
- NVIDIA access: requested 2026-10-15, pending. Non-blocking.
