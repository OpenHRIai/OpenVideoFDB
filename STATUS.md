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

## HANDOFF 2026-11-08 (session 6, 2026-10-24 → 11-08) — WS10 planned, bid study done
- **WS10 cue judge** (`plans/WS10-cue-judge.md`, new): a turn-taking predictor trained on human-human Seamless video,
  used as an automatic judge of the *agent's own* turn signalling — yield cues as speaker, start cues (floor bids) as
  listener — scored audio-only / visual-only / audio-visual from one backbone with modality dropout. New
  generation-side dimension, not in the paper. Depends on WS9 and the R2 pipeline in `smart-turn-multimodal-private`.
  Kill gate after phase 1 (visual-only AUC ≥ 0.60 on Seamless test). Phases 0–3 not started.
- **Phase 1a, the Seamless floor-bid study, is done** in `~/susurobo/code/smart-turn-multimodal-private`, branch
  `r2-floor-bids` (4 commits, **not pushed**, not merged): `docs/r2_floor_bids.md` (summary at top, §7 = the
  any-pause hazard follow-up), 33 figures, `scripts/r2_bids_*.py`. Headline: listeners prepare visibly in the last
  1.5 s before speaking (mouth from −1.6 s, head/gaze motion and blink from −0.9 s, nothing at −2 s); that
  preparation has no measurable effect on the speaker (turn ends +0.003 AUC; pauses of any kind at chance). Face
  features exist for site V00 only. The spec's §1b carries the numbers and the decisions they fixed (horizons 0.4 /
  1 s; partner-face branch and bid-effect measure dropped).
- **CANDOR (2026-11-08, same session).** Access to the CANDOR corpus (BetterUp; 1,656 unscripted video calls between
  strangers, licence allows commercial use and shareable Models, no redistribution, 30-day removals) was granted to the
  maintainer's HF account `maxipesfix`. Its shipped video features are per-second and useless for the bid study, so the
  replication runs our own extractor on the participant videos. **Done:** `ovfdb/score/lanes.py` (WS10 phase 0: MediaPipe
  Face Landmarker at 10 Hz → `face.npy` (T, 66) + `face.json` with found rate and `av_sync_offset_ms`; ≈ 25× real time on
  the laptop, 100 % faces on the avatar clips), `scripts/candor_prep.py` (archive → per-participant 16 kHz audio, Silero
  VAD, face tracks under `data/candor/proc/<conv>/<uid>/`), `scripts/candor_modal.py` (one container per archive on the
  Modal volume `candor`, video never stored; tested 2026-11-08 on archive 034: 6/6 conversations, tracks match the local
  pilot — commit `db663b4`, details in the script docstring; secret `huggingface` exists in the `susurobo` workspace). Pilot on archive 034 (6 conversations, 5 usable, 256 onsets): the Seamless
  bid-study headline reproduces with the open extractor on strangers at a different site — report
  `docs/candor_floor_bids.md` in `smart-turn-multimodal-private`, branch `candor-bids` (loaders `eot/candor.py`, scripts
  `scripts/candor_bids_*.py`). Local media: `data/candor/raw/processed_media_part_034/<conv>/processed/` (git-ignored).
- **Full CANDOR extraction done 2026-11-08 16:03 JST** (1 h 54 min, 34 containers, 1,656/1,656 conversations, no errors;
  per-archive logs in `data/candor/logs_modal/`). Corpus on the Modal volume `candor` under `proc/`; the analysis set is
  local: `data/candor/packed/<conversation_id>.npz` (9.5 GB, 1,656 files — float16 face tracks, VAD regions, face.json and
  channel map per participant; `candor_modal.py::pack`). 3,308 face tracks (4 conversations ship one video) and 3,312 VAD
  tracks, 1,940 h of video at 320 × 240 / 30 fps; face found median 0.970, mean 0.934, 664 videos < 0.9, 37 < 0.5, 7 < 0.1;
  |AV offset| > 300 ms on 301 of 3,305 (mp4's own audio vs mouth — check self-alignment against the mp3-channel VAD before
  trusting those). Four archives were retried by Modal mid-way, so their `logs` lack the per-video summary for 126
  conversations whose tracks are nonetheless complete (verified from the packed files). Launch record: (`modal run --detach scripts/candor_modal.py --archives all`, app
  `ap-h4oNI1NQSMKC4NziAA4GNz` in the `susurobo` workspace; local log `data/candor/modal_all.log`). Writes per participant
  `audio16.flac`, `vad.json`, `face.npy`/`face.json` and `frames.npz` (frame times, luma/blur, 125-point landmark subset) and
  per conversation `meta.json`, the shipped stereo mp3 and thumbnail — everything a later cue measure might need, since the
  video is not kept. Expect ≈ 360 CPU-hours, ≈ 1.5 h wall-clock, ≈ 100 GB FLAC + 50 GB mp3 + 60 GB tracks on the volume.
  Fetch with `modal volume get candor proc data/candor/proc_modal` (too big for the laptop; pull subsets or analyse on Modal).
- **WS10 phase 0 done 2026-11-08:** `ovfdb/score/cues.py` (metrics §3 as pure functions, event mining with the WS9 rules,
  `tests/test_cues.py`), `lanes.py` probe pass (rotation + per-file face crop; Seamless is full-body and lost the face on
  43/157 files before). **Gate proxy on Seamless test** (private repo `scripts/seamless_mp_gate.py`, `docs/seamless_mp_gate.md`,
  MediaPipe lanes on the 157 local test videos under `data/seamless/lanes/test/`): start-cue AUC 0.598 at −0.3 s / 0.642 at the
  onset (shuffled 0.538), yield-cue 0.544 (chance; −1 s shift identical). Start cue within reach of a sequence model, yield cue
  is a negative result; extractor choice settled (MediaPipe). Spec §1b updated.
- **Yield timing answered 2026-11-08** (private repo `scripts/yield_timing.py`, `docs/yield_timing.md`, Seamless test): speakers
  signal the end *after* the acoustic offset, not before — end-vs-pause AUC 0.57 in the last second (head motion the one early
  marker, d 0.27), 0.68 within 300 ms after (jaw closes and lips press, smile, gaze/head settle, blinks drop; a pause keeps the
  jaw half open). Spec §3 gained metric 2b (yield-at-offset) and §1b the summary. To replicate on CANDOR: wire the packed
  tracks into `eot/candor.py` (face16 + VAD from the npz; words from the local AWS zip) and run the same script.
- **Onset + offset analyses on both corpora done 2026-11-08** (private repo `docs/cue_timing.md`, per-dataset paper-style summary `docs/findings_cue_timing.md`; scripts `cue_corpus.py`,
  `cue_onset.py`, `cue_offset.py`; CANDOR events `runs/candor/bids/events_all.jsonl`, 1.07 M rows, 112,950 ends). Start-cue
  gate passes on both (0.62 Seamless / 0.70 CANDOR at −0.3 s, shuffled 0.50); yield signal in the first 300 ms after the
  offset on both; head stillness precedes pauses on both (hold cue); post-offset signals are the speaker's own. CANDOR adds a
  ≈ 1 s pre-end smile on social turns. Spec §1b/§3 updated.
- **Gap split done 2026-11-08** (`cue_onset.py --only-gap`, report §1b, findings §2.1b/§3.1b): the listener's start-cue
  ramp is locked to its own onset (0.7–1.0 s ahead in every gap bin, both corpora), so it starts during the speaker's
  speech for gaps < 0.7 s and in the silence otherwise. Silence-vs-silence control (taker vs the speaker's own pauses):
  Seamless chance before the offset, 0.59 at +0.3 s, 0.66 at +1 s; CANDOR 0.61 a second before the offset, flat 0.64 after.
- **Hypotheses register written 2026-11-09** (private repo `docs/hypotheses_cue_signalling.md`): 20 claims about visual cue
  signalling (6 listener, 9 speaker, 5 cross-cutting), each with a prediction, a verdict per corpus and a fixed test for
  data not yet looked at. Timed cues replicate on both corpora; every disagreement involves CANDOR's slow state, for
  which talk type, relationship and medium (video call vs same room) compete. Confirmation data: Seamless dev (80
  conversations, tracks not extracted) and train (1,000; 374 stranger pairs); CANDOR has no untouched conversations,
  only ~98k unsampled turn ends, so a split-half design is proposed. **Correction:** Seamless test is mostly familiar
  pairs (53 of 67 conversations), not strangers as the findings file said; fixed there and in `cue_timing.md`.
- **Five no-new-data checks done 2026-11-09** (private repo `scripts/cue_checks.py`, hypotheses file §6; reports
  `runs/{r2,candor}/cues/checks_*/checks.md`). (A) Matching turn ends and pauses on turn length changes nothing on
  Seamless and removes ~40 % of CANDOR's early listener difference, none of the speaker's pre-end smile. (B) CANDOR's
  readiness posture is not backchannel residue (stronger with the listener silent ≥ 3 s: d 0.31 → 0.40); a third of it
  is a smile. (C) The pre-end smile holds where a word ends at the offset (d 0.23), so not only laughter. (D) Speaker
  and listener faces are near independent within an event (|ρ| ≤ 0.1, no lead): the yield-triggers-start idea has no
  support. (E) The mouth ramp is specific to turn starts: ~0.8–1.6 s before a turn, 0.1–0.5 s before a backchannel —
  relevant to metric 1 (an agent whose mouth opens only at onset reads as backchannelling).
- **Correction 2026-11-09, head stillness:** it is a hold cue on Seamless only. On CANDOR the head slows equally before a
  turn end and a pause (d −0.12 / −0.14 vs mid-turn), so it marks a coming stop, not a pause; the "planning event"
  verdict is withdrawn. Seamless also shows extra head movement ~1 s before a turn end (d +0.41 vs mid-turn). Fixed in
  the hypotheses file (S4–S6), the findings file, the report, and spec §3 metric 4.
- **Filler split at turn ends, 2026-11-09** (`cue_checks.py --only-filler`): on CANDOR the extra early head stillness
  belongs to hesitation fillers (um/uh) only — pauses after one are stiller than other pauses by d −0.28 half a second
  out; trail-off connectives (so/and/but) add nothing; ordinary-word pauses and turn ends slow equally (−0.18 / −0.16).
  Seamless transcripts carry almost no hesitation fillers, so untested there.
- **Gaze-to-partner measure and resolution test, 2026-11-09** (private repo `scripts/cue_gaze.py`; `ovfdb/score/lanes.py`
  gained an optional `face_px` / `--face-px` for resolution-matching experiments, default path unchanged). Speakers look
  back at the partner before a turn end on both corpora: +15 pp of frames in the last 0.5 s vs mid-turn, +14 pp vs a
  pause, single-number AUC end-vs-pause 0.605 (Seamless) / 0.597 (CANDOR) before the offset. The judge needs gaze
  relative to the partner per person (spec note added). Seamless test re-tracked with faces at CANDOR's 79 px
  (`data/seamless/lanes/test_face80/`, 157 files): every effect unchanged (head slowing d −0.32 / −0.32, start-cue AUC
  0.617 / 0.614), so resolution does not explain CANDOR's smaller motion effects.
- **Partner gaze in the yield decoder, 2026-11-09** (`scripts/cue_gaze_decode.py`): end-vs-pause AUC with the four
  partner-gaze columns added — Seamless 0.605 at −0.3 s, 0.726 at +0.3 s (from 0.560 / 0.681); CANDOR 0.641 / 0.720 (from
  0.621 / 0.696). New human reference for metrics 2 and 2b; the judge's inputs should include partner-referenced gaze.
- **Confirmation on unseen data, 2026-11-09** (private repo `scripts/cue_confirm.py`, `scripts/cue_av_gain.py`; hypotheses
  file §9 protocol frozen before scoring, §10 results). Hold-outs: Seamless dev (162 videos fetched and tracked with
  `lanes`, tracks in `data/seamless/lanes/dev`, videos deleted) and 12,000 turn ends / 24,000 pauses of CANDOR never
  sampled before, from the conversation half not used for fitting. Models fitted on the seen data, applied unchanged.
  CANDOR 18 of 18 primary tests confirmed; Seamless 15 of 16 (four smaller than stated). Human reference on unseen
  data, Seamless / CANDOR: start cue at −0.3 s 0.579 [0.54, 0.61] / 0.700; turn end vs pause at −0.3 s 0.578 [0.54, 0.61]
  / 0.643, at +0.3 s 0.674 / 0.722, at +1.0 s 0.764 / 0.754; turn end vs mid-turn at −0.3 s 0.597 / 0.679; gaze at the
  partner, end minus pause +9.1 / +14.0 pp; every model on a face from another conversation 0.50–0.51. **Gate 1 on
  unseen Seamless with the plain model: both pre-event numbers sit just under 0.60 (intervals reach it), the post-stop
  number passes.** Not confirmed: the Seamless listener's floor-taking growing in the first 0.3 s of silence. On top of
  the in-domain audio heads (Seamless dev) the face adds +0.008 / −0.001 / +0.004 AUC at −0.4 / 0 / +0.3 s, none
  distinguishable from zero; with the frozen Smart Turn v3.2 +0.022 / +0.001 / +0.017. Spec §1b and §3 annotated.
- **Corpus differences kept as findings, 2026-11-09** (hypotheses file §11, spec §1b): CANDOR-only cues (listener
  readiness seconds ahead, pre-end smile) and Seamless-only cues (stiller head into a pause) are confirmed on unseen data
  where claimed; literature supports the direction for smiling and head motion, nothing published on the listener's
  pre-speech signals in both media; medium and relationship confounded. The benchmark's agent setting (unknown user,
  video link) matches CANDOR. **Exploratory training-data check** (`scripts/cue_transfer.py`): Seamless-only on both
  tracked splits → start cue 0.638 [0.61, 0.66], end vs mid-turn 0.632, end vs pause before the stop 0.587; CANDOR-only
  model on Seamless dev start cue 0.655; mixing adds nothing. Maintainer decision: Seamless models on Seamless only.
- **Seamless only, five times the data, 2026-11-09 (exploratory)** (private repo `scripts/seamless_train_subset.py`,
  `scripts/cue_seamless_scale.py`, `runs/r2/cues/confirm/scale.md`; hypotheses file §10/§11, spec §1b and metric 1b):
  600 videos of a 300-conversation Seamless train subset (156 stranger / 144 acquainted, fixed seed) tracked into
  `data/seamless/lanes/train` (97.7 % face found, 0 failures, 1.2 GB; videos deleted). Seamless-only models on test +
  subset (353 conversations), scored unchanged on dev: start cue 0.653 [0.61, 0.69] (was 0.579, control 0.525), end vs
  mid-turn 0.631 (was 0.597), end vs pause at +0.3 s 0.701, end vs pause at −0.3 s 0.583 (unchanged). Cross-validated
  over all 424 tracked conversations: 0.660 / 0.644 / 0.735 / 0.627; dev is the low set for end vs pause before the
  stop. Gate 1's start-cue criterion is met on unseen Seamless; most of the earlier gap to CANDOR was training-set size.
  Frozen protocol on the subset: 14 of 16 primary tests confirmed; floor-taking growth in the silence fails again;
  "stiller head into a pause" does not replicate. With the larger models in place of the frozen small one: floor-taking
  growth still absent (+0.007), listener's early taker sign 0.544 [0.53, 0.56] (present, half of CANDOR's 0.591). Strangers vs acquainted in the same room: no statistic differs, and
  Seamless strangers show neither the readiness posture nor the pre-end smile nor the post-end blink of CANDOR, so
  relationship does not produce the CANDOR-side cues. **Tracking the other 700 train conversations (started 2026-11-09 21:03, restarted 2026-11-10 07:34, done 2026-11-10 by 15:45):** the first run froze at 22:29 when the lid
  was closed on battery: the six open downloads kept dead sockets forever because the loader streamed with no
  timeout (`ovfdb/data/seamless.py`, fixed to 60 s per chunk; the fetch script now retries a download three
  times). 123 of 1,400 videos were done at the restart; the rest take about 9 h more with the Mac plugged in and
  the lid open (`caffeinate -is` cannot stop lid-closed sleep on battery). Tracking the other 700 train
  conversations (1,400 videos, about 9 h, six workers) into the same `data/seamless/lanes/train`, log
  `data/seamless/lanes/train_rest_extract.log`; file order from `seamless_train_subset.py --rest-out` (seed 1, so an
  interrupted run leaves a random sample; rerunning skips tracked files). Hold-out rule fixed 2026-11-10 07:40, before any of them was scored: the
  first 200 conversations of that order are a fresh hold-out (`seamless_train_subset.py holdout()`), the other 500 are
  training. `cue_seamless_scale.py` now loads five sets (test, train subset, train extra, hold-out, dev), fits the
  'all training' models on the first three, scores them on dev and the hold-out, and decides the full protocol table on
  the hold-out by the protocol's rules (part 6; dry run passes). Then rerun it when the tracking is done.
  **Moved to Modal 2026-11-10 15:40** after a power scare: `modal_seamless_lanes.py` (private repo root) downloads each
  video in a container, runs the same extractor with the laptop's library versions pinned, and writes the tracks to the
  Modal volume `seamless-lanes` under `/train/<file_id>/`; `--download DIR` copies them into `data/seamless/lanes/train`,
  skipping files already there. On a file tracked both ways the tracks differ by about 1 % of each feature's spread
  (correlation ≥ 0.9998, same face-found flags): x86 vs Apple Silicon inference noise, negligible for the models. The
  laptop run had reached 1,021 of 1,400 when the remaining 378 were submitted to Modal (60 containers).
  **Done 2026-11-10 20:15.** All 2,000 train videos tracked (1,032 + 1 retry on the laptop, 378 on Modal in 5 min; 0
  failures; 3.9 GB), verified complete and loadable. Rerun of `cue_seamless_scale.py` (`runs/r2/cues/confirm/scale2.md`;
  hypotheses file §10 'All of Seamless and a fresh hold-out', §11 update; findings §10 addendum; spec §1 and metric 1b):
  the fresh 187-conversation hold-out scored once by 833-conversation models confirms 14 of 16 primary tests, the same
  14 as the subset (dev had 15 of 16: stiller-head-into-a-pause passed there at +0.15; corrected 2026-11-11). Floor-taking
  growth and stiller-head-into-a-pause are dropped for Seamless (the first fails on all three unseen sets; pooled +0.017 and
  +0.060, real and small); turn end vs pause before the stop is 0.628 [0.60, 0.65] on the hold-out and 0.639 [0.63,
  0.65] cross-validated over 1,091 conversations, equal to CANDOR's 0.643, with dev the odd set at 0.59 for an unknown
  reason; start cue 0.644 hold-out / 0.657 CV (CANDOR 0.700); turn end vs mid-turn 0.641 / 0.651 (0.679); end vs pause
  at +0.3 s 0.723 / 0.739 (0.722); controls 0.48–0.51. Learning curves flat from 353 to 833 conversations (≤ +0.013), so
  the remaining start-cue gap to CANDOR is not data size. Listener's early taker sign 0.558 (present, half of CANDOR);
  readiness posture +0.09 (small, a quarter of CANDOR, same for strangers and acquainted); hesitation stillness (S6) now
  measurable on Seamless and matches CANDOR (−0.195 vs −0.222); blink and downward gaze before speaking confirmed as a
  same-room cue. Relationship (382 vs 695 conversations) separates nothing. Seamless human reference for metric 1b:
  0.63–0.64. **Not done:** audio-plus-visual on CANDOR. The judge's GRU heads (phase 1) are done, next entry.
- **WS10 phase 1, the judge's sequence heads — done 2026-11-11 (session 7, side session).** Small GRU heads (a GRU is a gated recurrent unit, a recurrent network that reads a sequence one step at a time) read the 10 Hz face tracks frame by frame for the four statistics the logistic stand-ins measure, on the stand-ins' own events, rows, per-file z-scores, frames and shuffled-face control (private repo `scripts/cue_gru.py`, report `docs/cue_gru_heads.md`, hypotheses file §10 'The judge's sequence heads', spec §1b last paragraph + phase 1 note). Trained on test + train subset + train extra (833 conversations), configuration chosen on dev only, the 187-conversation hold-out scored once: start cue **0.725** [0.70, 0.75] (logistic 0.644), turn end vs pause at −0.3 s **0.686** (0.628), at +0.3 s **0.787** (0.723), turn end vs mid-turn **0.689** (0.641); paired gains +0.05 to +0.08 with intervals excluding zero; controls 0.48–0.52. **Gate 1 met** with visual-only heads. The start-cue gap to CANDOR's logistic (0.700) was a model gap, not the setting. Before the stop most of the yield gain needs a 2 s window (+0.031 with 1 s, +0.058 with 2 s). Laptop CPU, about a minute per configuration and seed; the overnight runs stalled while the lid was closed on battery (wall clock only). Not built: audio branch / modality dropout, 10 Hz runner (phase 2). *(The CANDOR GRU for the other reference is done, next entry; it withdraws 'the start-cue gap was a model gap'.)*
- **WS10 sequence heads on CANDOR — done 2026-11-11 (side session of session 7).** The same GRU heads trained on CANDOR only, so the two human references compare between like models (private repo: `scripts/cue_gru.py` now takes `--corpus candor` and has a `cross` step; report `docs/cue_gru_heads.md` second part; plot report §4d and summary table; hypotheses file §10 'The sequence heads on CANDOR, and across corpora' and §11; spec §1b 'The sequence heads on CANDOR', metric 1b, gate line, phase 1 note). Split = the confirmatory protocol's: GRUs fitted on the exploration half (already-sampled events of one half of the conversations) minus a validation part (one conversation in five of that half, 144 conversations, used only for early stopping and choosing the configuration), i.e. 608 conversations and about 4,500 positives per statistic, the size of the Seamless training sets; the hold-out (12,000 never-sampled turn ends, 839 conversations of the other half) scored once. All values are AUC with 95 % intervals over conversations: start cue **0.769** [0.76, 0.78] (CANDOR logistic 0.700), turn end vs pause at −0.3 s **0.669** (0.643), at +0.3 s **0.761** (0.722), turn end vs mid-turn **0.706** (0.679); paired gains +0.069 / +0.026 / +0.039 / +0.027, intervals excluding zero; shuffled-face controls 0.495–0.500. **The start-cue gap between the corpora survives between sequence models:** CANDOR 0.769 against Seamless 0.725, +0.045 [+0.016, +0.074] (logistic on the same hold-outs +0.056); the sequence model lifts both by the same amount, so the earlier line 'the gap was a model gap, not the setting' is withdrawn in every document. The three speaker statistics end within 0.03 of each other between the corpora (only +0.3 s excludes zero, Seamless slightly higher). Exploratory cross-corpus check (outside the protocol, nothing chosen): heads scored unchanged on the other corpus's hold-out lose 0.03–0.05 against the heads trained there and stay far above chance (start cue: Seamless-trained 0.734 on CANDOR, CANDOR-trained 0.693 on Seamless). Run outputs `runs/candor/cues/gru/v1/` in the private repo (git-ignored; CANDOR is not redistributable). Laptop CPU, under 10 minutes of training in all. Not done: larger CANDOR heads (about twenty times more events exist than were used; the never-sampled events of the fitting half could be used without touching the hold-out), audio branch / modality dropout, 10 Hz runner (phase 2).
- **Plot report brought up to the full Seamless data, 2026-11-11** (private repo `docs/cue_timing.md`, the document that
  embeds the figures). The four cue scripts take `--split all` (a combined corpus class reads test, dev and train) and
  were rerun on all 1,091 conversations (`runs/r2/cues/{onset,offset,gaze,checks}_all/`, figures `seamless_all_*.png`);
  `scripts/cue_summary_figs.py` draws two summary figures from stored results (the two corpora side by side per
  statistic; the Seamless learning curves). The report opens with a summary of agreements and disagreements, has
  full-data rows in every table, and new sections on partner gaze, matched checks, and unseen-data results including the
  GRU hold-out scores. Withdrawn there: head stillness as a hold cue (difference +0.06 on full Seamless, CANDOR +0.04),
  and 'the Seamless listener foretells nothing' (0.56 against CANDOR's 0.59). New from the matched checks: the start cue
  is specific to turn starts on both corpora (backchannels ramp for 0.5 s at a fifth of the size); the pre-end smile
  exists on both where a turn trails off without words, and only on CANDOR where it ends on a word. Model scores are
  comparable across corpora only between like models: no GRU has been trained on CANDOR. The first checks run crashed
  overnight (the combined corpus returned no backchannels; fixed, rerun in 2 min).
- **Next:** (1) the remaining bid-study analyses on CANDOR (abandoned bids, slices by quality flags / know-your-partner,
  backchannels) and the words-in-last-second split of CANDOR's pre-end smile of the bid study on the whole corpus
  and the Seamless/MediaPipe cell (157 local test videos) to separate site from extractor; (2) WS10 phase 0 remainder
  here (`ovfdb/score/cues.py` metrics with synthetic-track tests, face-found rate + AV offset table on the avatar runs);
  (3) decide whether the WS10 judge trains on CANDOR (commercial) instead of Seamless (NC) — spec §2 licence line.
  WS9 (end-of-turn set) is still only on branch `ws9-endpointing-private`. Independent of WS10, the earlier "Next" list
  (Tavus perception rows, second judge, Seamless v1 model runs) still stands.

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
- Runs on the 121 generation rows (human-reference rows first): `runs_nv/tavus_av2av` **done and scored** (see the generation notes in results/nvidia_test.md for run facts);
  `runs_nv/anam_a2av` **done** (121 rows over five free-tier keys ANAM_API_KEY..KEY5, three parallel shards via
  `shard=(i,3)` with `ANAM_API_KEY` exported per process; "Concurrency limit" right after a close is transient and
  retried; "Usage limit" aborts the shard cleanly, no run.json). Same command to resume/re-run:
  `uv run python -c "from ovfdb.harness import streamer; streamer.run_manifest('manifest/nvidia_test.jsonl', provider='anam', mode='a2a', out='runs_nv/anam_a2av', concurrency=1, bucket='generation', partner_video_first=True)"`
- Generation-judge width ablation (2026-10-16, gt 30 rows, gpt-4o): 512 px frames give 4.17 / 3.20 / 2.83 / 3.40 vs
  256 px 4.17 / 3.30 / 3.00 / 3.49 (paper 4.42 / 4.14 / 3.18 / 3.92) — pane size is not what holds Affect Match down;
  keep the paper's 256 px. Remaining suspects: no agent-side visual/audio captions in our payload, judge version.
- Cost model (measured): Tavus bills ≈ clip + 19 s per row, Anam ≈ clip + 5 s; 121 generation rows = 105 clip min →
  Tavus ≈ 145 min, Anam ≈ 125 min; perception rows would add about the same again. Plans: Tavus Starter $59/100 min
  + $0.37/min, Growth $397/1250 min; Anam Starter $12/50 min (5 min/session cap) + $0.16/min, Explorer $49/250 min.
  Generation judge (gpt-4o, 3 axes, ≤500 low-detail frames) ≈ $0.26/row → ≈ $32 per 121-row configuration.

### WS6b HeyGen LiveAvatar (2026-10-17, session 4) — done
- **Result** (`results/nvidia_test.md` Generation section, 121 generation rows): HeyGen **4.16 / 2.33 / 1.52 / 2.74**, TOR 39 % /
  1800 ms. Paired bootstrap vs Tavus CVI: overall +0.12 [−0.12, +0.35] → **no winner**; fluency +0.37 [+0.11, +0.64]
  (survives Holm over 12 comparisons); both HeyGen and Tavus > Anam overall. Table in the results notes. NV cue on
  Laughter/NVB = one smiling row each, rest 0 (same "no nonverbal cue during the user's turn" finding). README updated.
- Vendor `heygen` in `playwright_avatar.py` + `web/avatar.html`: LiveAvatar FULL mode (REST token/start in Python,
  LiveKit join in the page, clip audio published as the mic → A2AV; stock "Helen (Friendly)", gpt-5.4-nano; one stored
  context `${system_prompt}` per key, cached by key fingerprint in `.heygen_context`; agent-speaks-first =
  `avatar.speak_response` kick at t=0). Plan session caps ("maximum allowed (120s)") are absorbed when clip + 15 s
  fits. `session.stopped NO_CREDITS` mid-row → run.json removed + run stops (`agent.quota_hit`).
- Tests: `tests/test_avatar_heygen.py` (23, mocked HTTP + fake page WS + fake agent; mutation-checked).
- Tooling: `scripts/run_avatar_keys.py` rotates HEYGEN_API_KEY/_KEY2/_KEY3 (`--keys K --ignore-credits` for
  overage), re-runs failed starts / no-video rows; `scripts/memguard.py` logs physical footprints and kills runaway
  harness browsers / run processes before the machine runs out of memory.
- Keys: HEYGEN_API_KEY* must be **LiveAvatar** keys (app.liveavatar.com), not HeyGen platform keys (api.heygen.com
  streaming endpoints are gone). FULL = 2 credits/min, ≈ 2.1 credits/row; this run ≈ 260 credits.
- Gotchas: macOS RSS hides compressed memory — use `memguard.footprint_mb`. Both "out of application memory"
  crashes today were a detached `~/.cache/smart-turn-multimodal-quant` `requant2.py --method percentile` job
  (> 20 GB in a minute), not the harness (harness Chrome 0.6–1.3 GB). `pgrep -f "<pattern>"` inside a shell loop
  matches its own command line — use `[p]attern`.
- Scoring: `ovfdb score-timing` + `ovfdb score-generation runs_nv/heygen_a2av --manifest manifest/nvidia_test.jsonl`
  (≈ $30, ≈ 1.6 h serial). **One NVIDIA report** (`results/nvidia_generation.*` merged in, 2026-10-17):
  `ovfdb report runs_nv/gt runs_nv/random runs_nv/gemini_live_av runs_nv/gemini_live_a2a runs_nv/openai_realtime_av
  runs_nv/openai_realtime_a2a runs_nv/tavus_av2av runs_nv/anam_a2av runs_nv/heygen_a2av --manifest
  manifest/nvidia_test.jsonl --per-dynamic --out results/nvidia_test.md`, then re-append the two Notes sections
  (perception, generation) — the report overwrites the file. Sections: Perception (Table 1) and Generation (Table 2).
- `report.write` now leaves generation-only runs (avatars: generation judge axes, no perception axes) out of the
  perception table and names them in its note — they used to show n = 145 with "—" cells (24 dual-bucket clips
  got a timing-only perception row). Test: `test_write_lists_generation_only_runs_in_generation_tables_only`.

### Post video: three avatars on Seamless clips (2026-10-17, session 4)
- NVIDIA clips cannot appear in posts (no redistribution/derivatives), so the three avatars were re-run on 7
  Seamless v1 clips (4 Turn-taking + 3 Verbal Interruption; `runs_v1/post/manifest.jsonl`, runs in
  `runs_v1/post/{gt,heygen_a2av,tavus_av2av,anam_a2av}`, timing scored; ≈ 2.3 clip-minutes per vendor).
- `scripts/avatar_sbs.py`: user (left) | human partner + 3 avatars (2x2) | one event timeline: the user's speech
  (VAD on user.wav — the v1 word alignment can smear a word over silence, e.g. P0222_c00 "Yeah," 7.1–16.9 s),
  then "User stops speaking" and each responder's first onset popping in with its latency; each responder pane
  carries its own speech strip (own spans, user-stop marker, playhead) along its bottom edge. PIL-rendered labels (this ffmpeg lacks drawtext); audio = every voice loudnorm'd to -18 LUFS
  (avatars -3 dB), limited — the lapel mics peak at -30 dB vs TTS at 0 dB; CC BY-NC attribution burned in. Outputs (not in git) in `data/announcement/`:
  `avatars_turn_taking_c02.mp4` (P0223_c02: human +0.5 s, Tavus +2.2, HeyGen +2.3, Anam +3.7) and
  `avatars_turn_taking_c00.mp4` (P0222_c00: human +0.4 s, HeyGen +1.8, Tavus +2.8, Anam +4.3; the user is silent
  after 7.4 s in both clips — nobody talks over anyone).
  Title "Turn-taking latency" (script default `<dynamic> latency`). A frame of c02 is in the README
  (`docs/media/avatars_turn_taking_c02.png`); GitHub does not play repo-hosted mp4s inline, so the video itself is
  linked/attached separately (web-editor upload or a release asset).

### Next (priority order)
1. Tavus CVI on the 105 perception rows (paper Table 1 AV2AV row; ≈ 145 Tavus minutes) — `run_manifest(..., provider='tavus', bucket='perception')`, then `ovfdb score` (perception judge) and add to `results/nvidia_test.md`. Affect-Match offset: try adding an agent-side visual/audio caption (Gemini Flash) to the generation payload and re-judge gt.
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
| WS6 providers: OpenAI RT, Tavus/Anam/HeyGen, gen judge | **done** (6a, 6b Tavus + Anam + HeyGen on the 121 generation rows, 6c) | session 3 (+ agent for 6c) | 2026-10-17 | `results/nvidia_test.md` (Generation section): gt 4.17/3.30/3.00/3.49 (paper 3.92), random 1.63, **Tavus CVI 3.79/2.30/1.65/2.63** (31 %/1956 ms), **Anam 3.41/1.51/1.26/2.15** (44 %/2092 ms; paper Gemini 2.5+Anam 2.80, 44 %/2840), **HeyGen 4.16/2.33/1.52/2.74** (39 %/1800 ms). Judge `score-generation` (gpt-4o vision, F.6 rubrics, ≈$0.26/row). Harness `playwright_avatar.py` + `web/avatar.html` (`run_manifest(bucket, partner_video_first, shard)`). Not run: Tavus perception rows (Table 1 AV2AV) |
| WS7 NVIDIA adapter + test-split runs | done | session 3 | 2026-10-16 | loader, gt/random, and the 4 API-model configs on all 226 test rows scored + reported: `results/nvidia_test.md`. Generation judge (WS6c) still todo |
| WS10 cue judge | phases 0, 1a done; **phase 1 (visual-only GRU heads) done 2026-11-11, gate 1 met on a fresh hold-out; same heads trained on CANDOR for the second human reference (start cue AUC 0.769 against Seamless 0.725)**; phase 2 (runner, audio branch) next | sessions 6–7 | 2026-11-11 | `plans/WS10-cue-judge.md`: visual turn-taking predictor as a judge of the agent's own yield/start cues. Phase 1 gate first: visual-only AUC ≥ 0.60 on Seamless test (the R2 oracle gained only +0.016 eager AUC, so this may close with a negative result). Training in `smart-turn-multimodal-private` (R2 tracks on Modal); this repo gets `score/lanes.py`, `score/cues.py`, `score/cue_judge.py`, `score-cues`. **Phase 1a (bid study, §1b) done 2026-10-27** in `smart-turn-multimodal-private`, branch `r2-floor-bids` (4 commits, not pushed), report `docs/r2_floor_bids.md`: listeners bid visibly but late (mouth from −1.6 s, head/gaze motion and blink from −0.9 s; nothing at −2 s); bid effect on the speaker's offset ≈ 0 (+0.003 AUC) and on pauses of any kind ≈ 0 (bid score at chance 0.49–0.52, risk ratio ≈ 1; report §7); face features exist for site V00 only. For WS10: keep h = 0.4 / 1 s, drop h = 4 s; expect measure 3b ≈ 0 |
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
