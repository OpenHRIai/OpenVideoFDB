# STATUS — shared progress board

Update this file at the start (claim) and end (report) of every session.
Keep entries terse. Dates are absolute (YYYY-MM-DD).

## Contract changes
_Record any edit to `ovfdb/schema.py` or `ovfdb/harness/base.py` here so other sessions rebase._
- 2026-10-15 — initial schema (WS0).
- 2026-10-16 — `schema.py`: added `run_dir_names(samples)` — run dir = `<clip_id>`, or `<clip_id>__<bucket>` when
  the rows of one clip_id differ in `user_audio_path` (NVIDIA dual-bucket clips swap user/partner between buckets;
  the shared-dir layout silently fed the wrong channel). Used by `harness/streamer.run_manifest` and
  `score/pipeline.iter_rows`; `report` is unaffected (it reads clip_id from timing.json).
- 2026-10-15 — `harness/base.py`: `AudioOut` gained `flush: bool = False` (barge-in: drop queued-unplayed audio at `t_received`; maps Gemini `server_content.interrupted`). Providers stamp `t_received` on their own clock (t=0 at first `push_audio`); streamer re-stamps on drain, keeps provider value as `t_agent` in events. (WS3)

## HANDOFF 2026-10-17 (end of session 3) — read this first
**v0.1.0 is released** (GitHub `OpenHRIai/OpenVideoFDB` + tag/release, HF dataset `OpenHRI/open-videofdb`).
Remotes in this checkout: `origin` = susurobo/OpenVideoFDB, `openhri` = OpenHRIai/OpenVideoFDB — **push both**.
Announcement drafts: `docs/announcement.md`; final example video (not in git): `data/announcement/example_laughter_frisbee.mp4`.

### Done in session 3: the four model configurations on the full NVIDIA test split (226 rows / 172 clips)
`runs_nv/{gemini_live,openai_realtime}_{av,a2a}` streamed (16:04–18:08, four in parallel, concurrency 2; one
network drop at 16:39 cut 6 clip streams → dirs deleted and re-streamed; one process restart at 17:10, resumed),
scored (`ovfdb score … --manifest manifest/nvidia_test.jsonl`, ≈$1.35 judge per run) and reported with
`ovfdb report … --per-dynamic --out results/nvidia_test.md`. README "Results" updated.
Headline (overall / TOR-Align / median latency; paper in brackets): Gemini AV2A 3.00 / 57 % / 1192 ms [2.84 / 66 % /
1720], Gemini A2A 3.13 / 59 % / 1172 [3.03 / 69 % / 1240], gpt-realtime AV2A 3.00 / 56 % / 1412 [2.75 / 72 % / 5400],
gpt-realtime A2A 2.88 / 60 % / 1108 [2.97 / 67 % / 4440]. Visual-stream ignorance reproduces (AV2A ≈ A2A).
Deviations worth a look: Conv. Flow 0.4–1.1 above the paper, Gemini Fluency 0.4–0.5 below, TOR-Align ≈ 10 pt below,
gpt-realtime latency 3–4 s below (onset definition). Verbal Backchanneling 0 % for every run incl. random (no agent
backchannels inside the 1 s window). Notes at the end of `results/nvidia_test.md`.
Re-running: `ovfdb run` is resumable (skips dirs with run.json); a connection drop leaves a run.json with
`errors` — delete that dir and rerun. `ovfdb score` skips existing timing.json/judge.json unless `--force`.

### Gotchas learned today
- Dual-bucket clips swap user/partner between buckets → run dirs `<clip_id>__<bucket>` (`schema.run_dir_names`);
  `report --manifest` filters on the clip_id stored in each row's JSON.
- `score`/`score-timing` without `--manifest` fall back to run.json meta → `<run_dir>/manifest.jsonl` → v0; always pass it.
- NVIDIA rows have no mining evidence → the judge gets `GENERIC_CUES` ("Annotated cue: …"); that line took the human
  reference on Laughter from 3.11 to 3.86 (= paper).
- Stay-silent rule passes an agent talking through a 1 s window; continue-speaking passes vacuously when the agent was
  silent before the window. Paper rules as written; the judge axes catch both. Documented in results notes.
- The NVIDIA licence allows publishing results, forbids redistributing data/derivatives: `runs_nv/`, `data/nvidia/`,
  `manifest/nvidia_*` stay local (all git-ignored). No NVIDIA frames in posts (academic publications only).

### WS6b avatar runs — state (2026-10-16 evening, session 3)
- Harness: `ovfdb/harness/providers/playwright_avatar.py` + `harness/web/avatar.html` (headless Chrome via Playwright
  `channel="chrome"`; the clip is the user's camera+mic; remote avatar recorded to `agent.mp4` aligned to clip t=0;
  AudioWorklet PCM → AudioOut; `run_manifest(bucket=..., partner_video_first=...)`; vendor quota → run aborts).
  Providers `tavus` (CVI full pipeline, Raven perception sees the user → AV2AV, stock Phoenix-4.5 "Helen - Casual",
  LLM tavus-gemma-4, persona cached in `.tavus_persona`) and `anam` (audio-only input → A2AV, stock Cara-4 "Mia",
  Anam-hosted Gemini 3 Flash; `getUserMedia` is overridden in the page so the SDK's mic = the clip — without that
  Anam never hears the user and monologues "it's been quiet").
- Runs on the 121 generation rows (human-reference rows first): `runs_nv/tavus_av2av` **done and scored** (see results/nvidia_generation.md notes for run facts);
  `runs_nv/anam_a2av` stopped at 1 valid row — **Anam usage limit reached** (free 30 min; ~25 of them burnt by the
  first, invalid run). Resume after upgrading with the same command (resumable; errored dirs already deleted):
  `uv run python -c "from ovfdb.harness import streamer; streamer.run_manifest('manifest/nvidia_test.jsonl', provider='anam', mode='a2a', out='runs_nv/anam_a2av', concurrency=1, bucket='generation', partner_video_first=True)"`
- Generation-judge width ablation (2026-10-16, gt 30 rows, gpt-4o): 512 px frames give 4.17 / 3.20 / 2.83 / 3.40 vs
  256 px 4.17 / 3.30 / 3.00 / 3.49 (paper 4.42 / 4.14 / 3.18 / 3.92) — pane size is not what holds Affect Match down;
  keep the paper's 256 px. Remaining suspects: no agent-side visual/audio captions in our payload, judge version.
- Cost model (measured): Tavus bills ≈ clip + 19 s per row, Anam ≈ clip + 5 s; 121 generation rows = 105 clip min →
  Tavus ≈ 145 min, Anam ≈ 125 min; perception rows would add about the same again. Plans: Tavus Starter $59/100 min
  + $0.37/min, Growth $397/1250 min; Anam Starter $12/50 min (5 min/session cap) + $0.16/min, Explorer $49/250 min.
  Generation judge (gpt-4o, 3 axes, ≤500 low-detail frames) ≈ $0.26/row → ≈ $32 per 121-row configuration.

### Next (priority order)
1. Anam A2AV run once the plan has minutes (resume command above), then `score-timing` + `score-generation` + `report` with `runs_nv/anam_a2av` added; optionally the 105 perception rows for Tavus (Table 1 AV2AV row, ≈ 145 more Tavus minutes).
2. Second judge (claude) for agreement numbers (`report.agreement`; needs ANTHROPIC_API_KEY).
3. Seamless track items (see below): Verbal Backchanneling decision, laughter bleed fix, top-ups, v1 model runs.
4. Tavus/Anam on the Seamless v1 manifest (same harness; CC-BY-NC clips can be shown in posts).

### Seamless track — state when parked
- **Manifest v0** (`manifest/ovfdb_v0.jsonl`, 118 rows / 110 clips, day-1 + nonverbal): fully run and judged for
  gt / random / gemini_live {av,a2a} / openai_realtime {av,a2a}; tables in `results/v0_summary*.md`. Known
  flaw: day-1 windows were selected using the partner's reaction → human-reference timing 100 % by
  construction (see docs/protocol.md §10).
- **Manifest v1** (`manifest/ovfdb_v1.jsonl`, 60 rows, day-1 only, user-cue-only rules, `ovfdb mine --tag v1`):
  human-reviewed with the annotator page (`ovfdb review`; decisions in `manifest/reviews/ovfdb_v1.jsonl`,
  applied in `manifest/ovfdb_v1_reviewed.jsonl`: 48 accept / 7 reject / 1 unsure / 4 unreviewed). Human
  reference + random run and timed in `runs_v1/` (timing only, no judge):
  Pause 90 % (paper 90 %), Turn-taking 100 % / 360 ms (paper 100 % / 640), Verbal Interruption 71 % / 1052 ms
  (paper 70 % / 960), Verbal Backchanneling 14 % (paper 69 %) — see below. No model runs on v1 yet.
- **Open decisions (user):** (1) Verbal Backchanneling — keep user-only breath slots (human 14 %; at a
  mid-story breath real listeners say "mhm" only 7–9 % of the time over 150 slots) or anchor this one dynamic
  on the partner's actual backchannel as the paper's annotators effectively did (disclose); recommended: anchor.
  (2) keep or drop the 4 unreviewed rows (`review-apply --drop-unreviewed`).
- **To do if resumed:** laughter detector bleed fix (partner's laugh on the user's mic was attributed to the
  user in 2 reviewed clips: keep a laugh only if the user's channel is louder than the partner's over the span);
  top up Laughter-G (6/10), Laughter-P (8/9), Verbal Backchanneling (7/10) with the fixed rules and re-review;
  then model runs on v1 (≈1 h streaming + ≈$1 judge per 4 configs); caption v2 (per-channel transcripts in
  the caption prompt; current captions sometimes swap USER/PARTNER speech); nonverbal day-2 rules also
  condition on the partner (other_speaking_after, b_reply_lag, partner_event, b_stop) — same fix needed.
- Tooling that carries over to NVIDIA: scoring pipeline (payload v2, calibrated), report in project-page
  notation (`--manifest/--rows` filters), `ovfdb review` annotator page (works on any manifest with
  `user_video_path`; needs `partner_file_id/t0/t1` in source_meta only for the partner-words panel).

### Release v0.1.0 (2026-10-16, WS8)
- README rewritten with results; LICENSE (MIT code / CC BY-NC manifests); `ovfdb rebuild` re-cuts clips from a
  manifest; `hf/README.md` dataset card + `scripts/publish_hf.py`; announcement drafts in `docs/announcement.md`.
- **Published 2026-10-16:** GitHub https://github.com/OpenHRIai/OpenVideoFDB (fresh copy of susurobo/OpenVideoFDB,
  tag + release `v0.1.0`; `origin` remote still points at susurobo, `openhri` at the org — push both), HF dataset
  https://huggingface.co/datasets/OpenHRI/open-videofdb (manifests + card only). LinkedIn / X posts: user, from
  `docs/announcement.md`.
- NVIDIA progress: adapter done; validation smoke test + human reference on the 60 test rows with a partner
  channel match the paper (`results/nvidia_*.md`); random baseline on all 226 test rows done (2.03 overall, 53 %;
  `results/nvidia_test_baselines.md`); **model runs on the 226 test rows not started** (≈1.5 h, ≈$25 API + $3 judge) — first thing after the release.

### NVIDIA track — next steps
1. WS7 (`plans/WS7-nvidia-adapter.md`, `docs/data-sources.md`): load the gated HF dataset → `Sample`s
   (ids pass through; `av_caption` = provided caption; `user_words` from provided ASR or whisper on the user
   audio; `agent_speaks_first` + `system_prompt` as shipped). Human GT = the partner channel as shipped.
2. Run gt / random / gemini_live / openai_realtime on the NVIDIA clips (`ovfdb run <manifest> --out runs_nv/..`),
   score with payload v2, report with `--manifest` — compare with the project page tables directly (same clips,
   same windows, same human reference).
3. Keys: GOOGLE_API_KEY / OPENAI_API_KEY in `.env`; HF token needed for the gated download (HF_TOKEN in `.env`).

## Board
| WS | Status | Session / owner | Last update | Notes / blockers |
|----|--------|-----------------|-------------|------------------|
| WS0 scaffold | done | session 1 | 2026-10-15 | schema, stubs, docs, plans |
| WS1 seamless data | done | agent (session 1) | 2026-10-15 | fetch/movement/trim/to_sample/quality gate; 14 tests incl. network. Movement features absent for all annotated nat/test files (see data-sources.md) |
| WS2 mining | done (day-1 + day-2) | session 2 | 2026-10-16 | manifest v0: 118 rows / 110 clips. Day-1: 60 rows, 10 per (dynamic,bucket) for Pause, VBackch, VInterrupt, Turn-taking, Laughter P+G. Day-2 nonverbal: 58 rows (8 per key, NV Interruption only 2). Caption speaker-swap issue → see HANDOFF item 2 |
| WS3 harness (Gemini Live) | done | agent (session 1) | 2026-10-15 | streamer/recorder/human_gt/random/gemini_live; live smoke OK on `gemini-3.1-flash-live-preview` (AV + a2a), drift < 40 ms, no errors. `scripts/smoke_gemini_live.py` |
| WS4 scoring: ASR + timing | done | agent (session 1) | 2026-10-15 | segments/timing/asr/pipeline; 31 tests; faster-whisper small.en int8 ≈ 8× RT. `timing.json` carries all judge blocks except caption/user words |
| WS5 judge + calibration | done (payload v2 calibrated) | session 2 | 2026-10-16 | rubrics verbatim, judge (gpt-4o/claude/gemini backends), report w/ bootstrap CIs. Payload v2: GT 4.12 vs random 2.70; results/calibration_v2.md. ≈$0.013/row-axis |
| WS6 providers: OpenAI RT, Tavus/Anam, gen judge | 6a, 6c done; 6b done for Tavus (121 gen rows), Anam blocked on plan minutes | session 3 (+ agent for 6c) | 2026-10-17 | `results/nvidia_generation.md`: gt 4.17/3.30/3.00/3.49 (paper 3.92), random 1.63, **Tavus CVI 3.79/2.30/1.65/2.63**, TOR 31 %/1956 ms. Judge: `score-generation` (gpt-4o vision, F.6 rubrics verbatim, ≈$0.26/row). Harness: `playwright_avatar.py` + `web/avatar.html`. Anam: 1 valid row, free minutes exhausted — resume command in the WS6b section |
| WS7 NVIDIA adapter + test-split runs | done | session 3 | 2026-10-16 | loader, gt/random, and the 4 API-model configs on all 226 test rows scored + reported: `results/nvidia_test.md`. Generation judge (WS6c) still todo |
| WS8 report + publish | results tables done; README/publish todo | session 2 | 2026-10-16 | results/v0_summary.md (day-1 rows), results/v0_summary_all.md (all 118 rows) |

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
