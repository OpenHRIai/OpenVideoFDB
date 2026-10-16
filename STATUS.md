# STATUS — shared progress board

Update this file at the start (claim) and end (report) of every session.
Keep entries terse. Dates are absolute (YYYY-MM-DD).

## Contract changes
_Record any edit to `ovfdb/schema.py` or `ovfdb/harness/base.py` here so other sessions rebase._
- 2026-10-15 — initial schema (WS0).
- 2026-10-15 — `harness/base.py`: `AudioOut` gained `flush: bool = False` (barge-in: drop queued-unplayed audio at `t_received`; maps Gemini `server_content.interrupted`). Providers stamp `t_received` on their own clock (t=0 at first `push_audio`); streamer re-stamps on drain, keeps provider value as `t_agent` in events. (WS3)

## HANDOFF 2026-10-16 (session 2) — read this first
Committed and pushed through the commits below. Everything on disk under `runs/` is git-ignored.
1. **Done this session.** WS2 nonverbal mining committed (`120a190`; +58 rows / 56 clips, day-1 rows
   unchanged, 150 tests pass). Judge payload v2 committed (`d1bedc4`, `1d4adaf`; docs/protocol.md §5) and
   calibrated: GT 4.12 / random 2.70 overall, GT Pause flow 4.6, GT Laughter fluency 4.0
   (`results/calibration_v2.md`, notes at the bottom). Model runs judged with payload v2 (gpt-4o,
   ≈$0.27/run): gemini_live_av 3.45, openai_realtime_av 3.50, gemini_live_a2a 3.68, openai_realtime_a2a
   (see `results/v0_summary.md`). The a2a runs were judged against the 60 day-1 rows only (they also hold 10
   nonverbal clips that gt/random/av runs lack; a day-1 manifest subset = `head -60 manifest/ovfdb_v0.jsonl`).
2. **Finding — caption speaker swap.** Gemini's AV caption lip-reads a mixed audio track and attributes
   speech to the wrong pane for whole pairs (`V00_S0314_*`: 3 clearly swapped, 6 mixed of 37 decidable
   clips). Payload v2 adds a caveat + timestamped agent transcript, which recovered GT Laughter fluency
   (2.9 → 4.0). Proper fix (WS2, `ovfdb/mine/prompts.py:av_caption`): put both channels' timestamped
   Seamless transcripts in the caption prompt and ask only for visual behaviour; re-caption 110 clips
   (≈$0.5 gemini-2.5-flash) and re-judge (≈$1.6 for 6 runs; Pause rows re-judge too since the caption is
   in the payload).
3. **Known judge limits.** GT Laughter grounding 3.4 (paper ≈ 4.2): "on-topic but flat in tone" — the
   judge cannot hear register. Candidate fix: run `ovfdb/mine/laughter.py` on `agent.wav` and add agent
   laugh spans to the payload. Random scores 2.7 (not 2.1) because wordless spans are no longer read as
   talk-over for anyone; GT–random gap 1.4.
4. **Next steps in order**: (a) nonverbal rows: `ovfdb run` for gt/random/gemini/openai on the 56 new
   clips (incremental; ≈110 → 118 rows, 6 nonverbal dynamics), then `ovfdb score` + `ovfdb report`;
   (b) caption v2 (item 2) and re-judge; (c) WS6b/6c (Tavus/Anam via Playwright, generation judge —
   the 24 generation nonverbal rows have no judge yet); (d) WS8 README + manifest-only publish;
   (e) optional second judge (needs ANTHROPIC_API_KEY) for agreement numbers via `report.agreement`.
5. Keys: GOOGLE_API_KEY and OPENAI_API_KEY in `.env`; no ANTHROPIC key yet. TAVUS/ANAM keys exist in
   fugubook's env if WS6b is attempted. Pre-existing lint nit: `ovfdb/schema.py` UP035 (shared contract,
   left alone).

## Board
| WS | Status | Session / owner | Last update | Notes / blockers |
|----|--------|-----------------|-------------|------------------|
| WS0 scaffold | done | session 1 | 2026-10-15 | schema, stubs, docs, plans |
| WS1 seamless data | done | agent (session 1) | 2026-10-15 | fetch/movement/trim/to_sample/quality gate; 14 tests incl. network. Movement features absent for all annotated nat/test files (see data-sources.md) |
| WS2 mining | done (day-1 + day-2) | session 2 | 2026-10-16 | manifest v0: 118 rows / 110 clips. Day-1: 60 rows, 10 per (dynamic,bucket) for Pause, VBackch, VInterrupt, Turn-taking, Laughter P+G. Day-2 nonverbal: 58 rows (8 per key, NV Interruption only 2). Caption speaker-swap issue → see HANDOFF item 2 |
| WS3 harness (Gemini Live) | done | agent (session 1) | 2026-10-15 | streamer/recorder/human_gt/random/gemini_live; live smoke OK on `gemini-3.1-flash-live-preview` (AV + a2a), drift < 40 ms, no errors. `scripts/smoke_gemini_live.py` |
| WS4 scoring: ASR + timing | done | agent (session 1) | 2026-10-15 | segments/timing/asr/pipeline; 31 tests; faster-whisper small.en int8 ≈ 8× RT. `timing.json` carries all judge blocks except caption/user words |
| WS5 judge + calibration | done (payload v2 calibrated) | session 2 | 2026-10-16 | rubrics verbatim, judge (gpt-4o/claude/gemini backends), report w/ bootstrap CIs. Payload v2: GT 4.12 vs random 2.70; results/calibration_v2.md. ≈$0.013/row-axis |
| WS6 providers: OpenAI RT, Tavus/Anam, gen judge | 6a done; 6b/6c todo (keys needed in .env) | agent (session 1) | 2026-10-15 | openai_realtime provider live-verified (gpt-realtime, -mini; AV via input_image items, 1 fps). Tavus/Anam + generation judge still todo |
| WS7 NVIDIA adapter | blocked (external) | — | 2026-10-15 | access requested 2026-10-15, awaiting approval; **not on the critical path** — all other WS run on Seamless |
| WS8 report + publish | first results table done; README/publish todo | session 2 | 2026-10-16 | results/v0_summary.md (6 runs, day-1 rows) |

## Decisions log
- 2026-10-15 — Perception bucket first; generation is a stretch (needs video-out agents).
- 2026-10-15 — Seamless `naturalistic` split only (improvised uses actors).
- 2026-10-15 — ASR: faster-whisper (paper: Parakeet 0.6B v2). Judge: GPT-4o primary (as paper) + Claude second judge for agreement. AV captioner: Gemini Flash (paper: Qwen3.5-397B + Nemotron-Omni).
- 2026-10-15 — Publish manifest only (file_ids + timestamps + labels + prompts/captions) and a re-fetch/trim command; never re-host Seamless media. CC-BY-NC 4.0 allows it, but privacy exposure isn't worth it.
- 2026-10-15 — Clip time origin = first user audio chunk sent to agent.

## Calibration findings
**v2 (2026-10-16, judge payload v2; results/calibration_v2.md):** GT 4.12 vs random 2.70 overall (Flu 4.25/2.55, Flow 4.60/3.40, Ground 3.40/2.30). GT Laughter fluency 2.9 → 4.0 once the caption's swapped speaker labels were neutralised by a caveat + timestamped agent transcript; GT Pause flow 4.2 → 4.6 once wordless VAD spans were labelled non-lexical. Laughter grounding 3.4 ("flat in tone": judge can't hear register). TOR-Align unchanged (GT 100 % / random 35 %).

**v1 (2026-10-16, after VAD-derived segments + tolerances; results/calibration_v1.md):** TOR-Align GT 100 % vs random 35 % (Turn-taking 100/50, VBackch 100/0, Pause 100/80, VInterrupt 100/10). Judge GT 3.70 vs random 2.12 — GT dropped from 3.95 because wordless VAD spans (breaths, "mhm") now appear as agent activity and the judge reads them as talk-over. Laughter GT fluency 2.9: 8/10 captions never mention the laugh; judge penalises listening through a mid-turn laugh and co-construction overlap. Next: payload v2 — explicit cue line from mining, mark backchannel/non-lexical spans in the partition block, user speech state inside the window, punctuated transcript. Rubric text untouched.

**v0 (2026-10-15, ASR-only segments; results/calibration_v0.md):**
- GT overall 4.18 (Flu 4.07 / Flow 4.60 / Ground 3.5 n=4) vs random 2.32 — judge separates. TOR-Align GT 70 % vs random 27.5 %.
- GT Turn-taking 50 %: human onset lands 80–370 ms after our tight window end (whisper onset lag + windows 0.3–1.3 s). Fix: handoff onset tolerance (~0.5 s) in timing.py; min window 1.0 s in mining.
- GT Verbal Backchanneling 40 %: whisper drops non-lexical "mhm"; "Mm-hmm"/"Yeah. Yeah." count as 2 words; 1.04 s > 1.0 s. Fix: agent segments = VAD on agent.wav ∪ ASR words; backchannel tokenisation (hyphenated/repeated token = 1 word); ±0.25 s window tolerance.
- Pause Handling 100 %, Verbal Interruption 90 % on GT — fine.
- Scoring is now per manifest row: `runs/<name>/<clip>/<bucket>/{timing.json,judge.json,judge/}`; summaries use `n_rows`/`rows`. Full calibration (n=20 P rows): GT 3.95 vs random 2.15 overall; see results/calibration_v0.md.
- GT Laughter fluency only 2.60 (paper GT fluency ≈ 4.5) — inspect judge analyses before trusting fluency on Laughter clips.

## Open questions
- OpenAI Realtime: video is item-based (one image per frame, seen at next response), not a continuous stream like Gemini Live; gpt-realtime speaks spontaneously on the first TTS pause while -mini needs the text kick. Report per model.
- Agent replies often run past `clip + tail_s` (default 5 s). Consider `tail_s=8–10` for real runs; agent.wav is truncated to the window by design.
- Recorder uses playback-queue placement (Gemini bursts audio faster than real time); `t_received` of the *first* chunk of a burst is the onset. Document in protocol §8 once calibrated.
- Which provider API keys are available? (fugubook `.env` has TAVUS/ANAM/OPENAI/GOOGLE per survey.)
- NVIDIA access: requested 2026-10-15, pending. Non-blocking.
