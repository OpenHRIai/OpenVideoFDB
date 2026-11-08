# WS10 — Cue judge: a turn-taking predictor as an automatic score for the agent's own signalling

**Depends on:** WS9 (end-of-turn rules + Seamless splits, branch `ws9-endpointing-private`), WS6b (avatar
runs with `agent.mp4`), the R2 track pipeline and audio heads in `smart-turn-multimodal-private`
(`eot/model_av.py`, `scripts/r2_*.py`, Modal volume `smart-turn-v2`), and the bid study's findings
(`docs/r2_floor_bids.md` on branch `r2-floor-bids` of that repo, done 2026-10-27, see §1b). **Est.:** 8–12
working days across four phases, with a kill gate after phase 1. **Status 2026-11-08:** spec + phase 1a done;
phase 0 started (`ovfdb/score/lanes.py` extractor done and run on CANDOR; `cues.py` not started); CANDOR replication
pilot done (§1b), full run pending; phase 1 not started.
**Files (this repo):** `ovfdb/score/lanes.py`, `ovfdb/score/cues.py`, `ovfdb/score/cue_judge.py`,
`ovfdb/cli.py` (`score-cues`), `ovfdb/score/report.py` (one new table), `tests/test_cues.py`,
`results/cues_*.md`, `docs/protocol.md` §11 (new). Training code stays in the private repo; this repo
consumes exported ONNX files.

## 1. What is being measured, and why it is new

VideoFDB scores the agent as a *listener* whose visuals should react (nods, smiles, affect) and as a
*speaker* whose audio should start and stop on time. No rubric or timing class asks whether the agent's
own face and voice telegraph where its turn is going. This WS adds two generation-side measures of that:

| measure | the agent is | human behaviour (literature) | what a cascaded avatar can physically do |
|---|---|---|---|
| **yield cue** | speaker, about to end its turn | gaze returns to the partner, head stills, brow/jaw release, final-lengthening prosody, 200–600 ms before the acoustic offset | face is driven by the TTS waveform; prosodic yield cues are weak in TTS (Ekstedt et al. 2023) |
| **start cue / floor bid** | listener, wants the turn | two time scales. Imminent: inbreath, mouth closes then opens narrowly, gaze and head lift, 300–600 ms before onset (Torreira et al. 2015; Ishii et al. 2016, 2019). Early: a *pre-beginning* — gesture, posture lean, sustained gaze, visible inbreath while the speaker is still talking, taking "the visual floor but not yet the vocal turn" (Mondada 2007; Streeck & Hartge 1992 on turn-transitory gestures), seconds before onset, which invites the speaker to yield and may be abandoned if they do not | nothing can show before the first audio packet; idle→speaking state switch fires on audio. A bid that *influences* the speaker is unmeasurable in this harness: the user is a recording (see §3, bid effect) |

The instrument is a turn-taking predictor trained on human-human video (Seamless Interaction, naturalistic).
If it anticipates the human partner's turn ends and onsets from video alone, but not the avatar's, the
avatar's cues are absent or non-standard. Precedent for "predictor as judge": Ekstedt et al. 2023 (VAP on
TTS), Arora et al. ICLR 2025 (supervised turn-taking judge for spoken dialogue systems), TurnNat 2026; all
audio only. The visual extension and the listener-side readiness measure are not in the literature.

**The known risk, stated up front.** The R2 audio-visual oracle (Meta's own 30 Hz FAU/gaze/head features,
speaker side only, `docs/r2_seamless.md` §4) gained only +0.016 eager AUC and 2–4 points of long-pause
FAR over audio. Literature agrees the audio-visual gain is modest (MM-VAP +4–5 pt hold/shift; Berner et al.
2026 on Seamless +2 pt). The judge does not need video to *beat* audio; it needs the **visual-only** score
to be reliably above chance on human data and to drop when cues are removed. Phase 1 measures exactly that
before anything else is built.

## 1b. The bid study: does the listener bid for the floor? (stands on its own, no judge needed)

The CA literature (Mondada 2007, Streeck & Hartge 1992, Schegloff's pre-beginnings) establishes that
listeners claim the next turn visibly before they speak, from sequential analysis of a handful of cases. No
one has measured it at scale, and the 2021 gaze review finds the turn-initiation evidence inconsistent.
Seamless has both participants' 30 Hz tracks for thousands of naturalistic dyads, so the question can be
answered descriptively, before and independently of any predictor. Four analyses on the R2 train tracks
(Meta features where present, SMPL-H / keypoints for every file, VAD + transcripts for the events):

1. **Event-aligned trajectories.** For every non-backchannel listener onset, stack the listener's features
   from −6 s to +1 s (FAU 24, gaze 2, head 3, arousal/valence; torso pitch and hand height from SMPL-H)
   against matched baselines (same listener, random listening time with ≥ 6 s to the next onset). Mean
   curves with CIs per feature; the lag at which each diverges is the empirical bid horizon. Split by
   what follows: full turn vs backchannel, and by the gap to the speaker's offset (early bids vs
   imminent onsets).
2. **Bid effect, observational.** For each 100 ms frame of a speaker's turn, model P(speaker offset within
   1 s) from the speaker's own audio cues (the R2 audio heads) and, added, the listener's features over the
   previous 3 s. The listener's added likelihood-ratio is the evidence that bids predict yields beyond what
   the speaker's own signal explains. Correlational, not causal: both parties project the same syntactic
   completion; conditioning on the speaker's audio predictability is the partial control, and the
   limitation is stated as such. Sequence check: bid → speaker gaze shift to listener → offset.
3. **Abandoned bids.** Frames whose listener trajectory matches the bid template (from 1) with no onset
   within 4 s: frequency, what the speaker did (kept talking, gaze-checked, ended later), and a spot check
   against the 3P-V annotation text where present. This is the noise estimate the judge labels need.
4. **Site and setting slices.** Per recording site and improvised vs naturalistic, since Berner et al.
   found the two behave differently.

Deliverable: a standalone finding whether or not the judge is built; it also fixes two judge decisions
empirically: which horizons h matter and which features carry the bid.

**Result (done 2026-10-27; report `docs/r2_floor_bids.md`, 33 figures, scripts `scripts/r2_bids_*.py`, all on
branch `r2-floor-bids` of `smart-turn-multimodal-private`, not pushed).** On 3,152 real-turn onsets from 938
listeners (train split; dev as the held-out check; test untouched):
- Listeners bid visibly, but late. Jaw drop (AU26) leaves baseline 1.6 s before the onset (d = 0.55 at
  −0.3 s); lips part / upper-lip raiser / lip funneler at 1.8–1.9 s (d 0.21–0.33); arousal from −1.6 s; head
  and gaze *motion* and the pre-speech blink (AU43) from −0.9 / −0.8 s; hand lift from −0.5 s. At −2 s no
  feature differs from baseline. Gaze and head *position* encodings, brows, valence and torso pitch carry
  nothing. For onsets right after the speaker's stop the mouth preparation starts 1.5–2 s *before the speaker
  stops*; seconds-long pre-beginnings are rare (leads ≥ 2 s on 3 % of onsets; a dev bid score separates the
  last 3 s before an onset from baselines at AUC 0.70, but 1–2 s earlier only at 0.56–0.57).
- Backchannels show the same shape at half the size, with a smile baseline; their jaw-drop peak is a 0.3 s
  spike where a real turn ramps over 1.5 s.
- Bid effect on the speaker: none measurable. The listener's face adds +0.003 [−0.001, +0.007] AUC to the
  audio heads' prediction of the speaker's turn end, and (follow-up analysis 5, hazard style) is at chance
  (0.49–0.52) for speaker pauses of *any* kind at 0.5 / 1 s horizons and 0.2 / 0.5 / 1 s gap thresholds; the
  time-to-next-stop curves after a bid lie on the matched frames (risk ratio 0.97–1.08, CIs spanning 1).
  Pauses are no more bid-driven than ends. Correlational throughout.
- Abandoned bids: 3.2 per minute of listening (43 % of bid-score runs above the 10 %-false-bid threshold are
  not followed by any listener vocalisation within 4 s); no after-effect on the speaker.
- Slices: Meta's face features exist for recording site V00 only, so the face study is single-site;
  strangers bid harder than familiar pairs (jaw drop d 0.71 vs 0.51), bid effect null in both.
- Limitations: Meta's extractor, not an open one; gaze/head are neural encodings, not angles; prompted
  conversations; the cross-site body-only replication was not done.

What this fixes below: start-cue horizons h = 0.4 s and 1 s (2 s is a weak tail; 4 s has no visual
correlate and is dropped); bid features are mouth opening and lip posture, blink, head/gaze motion energy,
arousal, hand lift — not gaze direction or posture; the partner-face branch into the speaker's heads and
the "bid effect" validity measure are dropped, since both are ≈ 0 on human data.

**Replication on CANDOR (pilot 2026-11-08; `docs/candor_floor_bids.md` on branch `candor-bids` of the private repo).**
CANDOR (BetterUp, 1,656 unscripted video calls between strangers, 2020 webcams, 320 × 240) answers the study's
limitations in one move: a second site, strangers only, and an open extractor — the study's own `ovfdb/score/lanes.py`
(MediaPipe, 10 Hz) on the participant videos, since CANDOR's shipped video features are per-second. On 5 conversations /
256 onsets the headline holds: inner-lip gap diverges at −1.4 s (d 0.62 at −0.3 s), `jawOpen` at −0.8 s (0.41),
`cheekPuff` and `mouthUpperUp` ≈ 0.4, nothing at −2 s, head/gaze motion and blink late and small, gaze direction (iris
offset, `eyeLook*`), brows and head yaw silent, backchannel = 0.3 s jaw spike with a smile baseline; a
leave-one-conversation-out bid score reaches AUC 0.61 at the onset (0.54 / 0.53 at −1 / −2 s) on five conversations.
Licence consequence: CANDOR permits commercial use and sharing Models trained on it (with notice, no redistribution of
tracks, 30-day removals), so a judge trained on CANDOR could ship without the NC restriction in §2.

**Gate proxy on Seamless test with the open extractor (2026-11-08; private repo `scripts/seamless_mp_gate.py`,
report `docs/seamless_mp_gate.md`).** The phase-1 gate numbers measured with the bid study's plain model (logistic on
3 s rolling mean + slope of the MediaPipe lanes, leave-one-conversation-out) on the 157 local test videos, before any
sequence model exists: start-cue AUC 0.598 [0.56, 0.64] at −0.3 s and 0.642 [0.60, 0.69] at the onset, shuffled-video
control 0.538; yield-cue AUC 0.544 [0.51, 0.57], shuffled 0.487, and the track shifted 1 s into the past gives the same
0.544 — the speaker's face in the last second carries no offset signal with these features. Both miss the letter of
gate 1 with the proxy; the start cue is within reach of a GRU, the yield cue is not. Per-feature d-tables on the same
files reproduce the Meta-feature findings (mouth from −1 s, d 0.54 at −0.3 s on the inner-lip gap, nothing at −2 s,
head/gaze small), so the extractor-agreement question of phase 2 is settled in favour of MediaPipe. Required an
extractor fix: Seamless is filmed full-body and the face was lost on 43 of 157 files until `lanes.py` gained a per-file
probe for rotation and a face crop (mean found rate 0.79 → 0.98).

**Yield timing (2026-11-08; private repo `scripts/yield_timing.py`, `docs/yield_timing.md`).** Do speakers signal the
end visually before the acoustic offset or after it? Speaker's lanes from −3 to +2 s around 417 complete offsets vs
1,883 incomplete pauses (frames after anyone speaks again masked) and 1,251 mid-turn frames, Seamless test. Before the
offset a turn end and a pause look alike (end-vs-pause AUC 0.57 in the last second, the same with or without the mouth);
the one early marker is head motion, raised before a turn end relative to a pause from −0.9 s (d 0.27 at −0.3 s; pauses
are preceded by a still head). Within 300 ms after the offset they separate: AUC 0.68 at +0.3 s, 0.71 at +1 s (0.63 /
0.65 without the mouth) — at a turn end the jaw closes fully and the lips press, a smile appears, gaze and head settle,
blinks drop; in a pause the jaw stays half open in speaking posture with the gaze still moving. Consequences in §3:
metric 2's pre-offset horizon is ≈ 0 for humans and is kept only as a secondary head-motion measure; the yield measure
is the face at τ = 0.3–0.5 s into the silence telling an end from a pause (metric 4's hold-vs-yield question), human
reference 0.68 (0.63 without the mouth).

**Both sides on both corpora (2026-11-08, evening; private repo `scripts/cue_onset.py` / `cue_offset.py`, report
`docs/cue_timing.md`).** Same extractor, same rules, Seamless test (417 ends, 1,883 pauses) and all of CANDOR (109,950
ends, 12,000 used; 1,579 conversations). *Onset:* start-cue AUC at −0.3 s 0.617 [0.58, 0.66] on Seamless and 0.697
[0.69, 0.70] on CANDOR, shuffled 0.50 / 0.51 — **gate 1's start-cue criterion passes on both** with the plain model
(one logistic per scoring offset; the earlier 0.598 / 0.538 came from one model for all offsets and a shuffle that could
draw the partner's file). *Offset:* the end-vs-pause signal arrives in the first 300 ms after the sound stops on both
(0.57 → 0.68 Seamless, 0.62 → 0.70 CANDOR from the window ending at −0.3 s to the one ending at +0.3 s); CANDOR adds a
≈ 1 s smile build-up before social turn ends that Seamless lacks. *Pause precursor:* the head goes still half a second
before a within-turn pause on both corpora (d −0.32 / −0.14 at −0.3 s), decodable from head + gaze + eyes alone (0.58 /
0.56) and not from the mouth — a hold cue. *Own display, not reaction:* with the listener removed (nobody speaks for
≥ 1 s) ends still separate from pauses at 0.61–0.68, and aligned on the listener's onset the smile, gaze settling and
blink suppression are already in place before the listener's first word. Metrics 2, 2b and 4 annotated accordingly.
*Start cue is onset-locked, not offset-locked (report §1b):* split by the gap between the speaker's offset and the
listener's onset, the listener's preparation ramp begins 0.7–1.0 s before its own onset in every gap bin on both
corpora, so it falls inside the partner's speech for short gaps and inside the silence for long ones. Against the same
listener during the speaker's own pauses (silence vs silence), a Seamless listener is at chance while the speaker still
talks (0.50–0.53) and becomes distinguishable from 300 ms into the silence (0.59, 0.66 at +1 s); a CANDOR listener is
already distinguishable a second before the offset (0.61) and the silence adds nothing (0.64 flat) — the social-talk
listener state. Consequence for the h = 1 s head: it cannot fire before the user's own ramp; on task talk the user's
face in a silence separates floor-taking from waiting from ≈ 300 ms in, the same moment the speaker's yield display
appears.

## 2. Model

One backbone, three modes, trained with modality dropout so audio-only, visual-only and audio-visual scores
come from identical weights and are directly comparable.

```
speaker audio ──► frozen Smart Turn v3.2 / NC encoder, pooled 384-d every 320 ms  ─┐
speaker audio ──► mel GRU over the last 1 s                                        ├─► fusion MLP ─► heads @ 10 Hz
speaker face  ──► 10 Hz feature track, GRU over the last 3 s (64-d)                │     p_end(τ)  P(turn has ended | …, silence τ)
                                                                                     │     p_eager   P(turn ends within 400 ms | still speaking)
VAD state     ──► τ, speech-so-far, turn length                                    ┘     p_start(h) P(own onset within h | listening), h ∈ {0.4, 1} s  [new]
```

- `p_end` and `p_eager` are the R2 heads (`eot/model_av.py`, `HeadsAV`). `p_start(h)` are two new heads
  on the *listener's own* channel (the agent as listener: its face while the user speaks), h ∈ {0.4, 1} s:
  label 1 at frames where this participant's own first non-backchannel onset is ≤ h ahead, negatives from
  listening stretches with ≥ h + 2 s to the next own onset. Horizons fixed by the bid study (§1b): the
  visible preparation lives in the last 1.5 s, so 0.4 s catches the imminent-onset cue and 1 s the
  preparation ramp; 2 s and 4 s were dropped (no visual correlate at −2 s). Backchannel onsets (< 1 s,
  < 2 words, WS4 definition) are excluded from both classes. Abandoned bids (3.2 per listening minute,
  §1b) are negatives under these labels; known, quantified label noise.
- No partner-face branch into the speaker's heads: the bid study measured the listener's face adding
  +0.003 AUC to the speaker's turn-end prediction and chance-level for pauses, so it would only add
  parameters. Each participant's heads see that participant's own face and audio plus the VAD state of both.
- Modality dropout: each training window drops the audio branch with p = 0.3, the face branches with p = 0.3,
  never both; a presence flag per branch enters the fusion (the `has_mov` mechanism already exists).
- Face features: phase 1 uses Meta's shipped movement features (the oracle's 31-d) because the tracks are
  already on the Modal volume; the judge that ships (phase 2) uses an open extractor that runs on avatar
  video — MediaPipe Face Landmarker (52 blendshapes + head transform; the design doc §3.2 input set) or
  OpenFace/py-feat AUs. The same extractor must produce the Seamless training tracks and the avatar tracks.
- Why not VAP proper: the explicit heads map one-to-one onto the metrics below, reuse the R2 pipeline, and
  keep the audio side comparable with the released smart-turn-streaming numbers. Skantze's VAP/MM-VAP
  (public code, CANDOR-trained) is the external baseline in phase 3, not the backbone.
- Licence: trained on Seamless → CC BY-NC 4.0 model, published as `OpenHRI/ovfdb-cue-judge` (ONNX) for
  benchmark use only; nothing from it enters a commercial release.

## 3. Metrics (`ovfdb/score/cues.py`, pure functions over probability tracks + segment lists)

Events come from the run's own channels with the WS9 outcome rules applied to (agent = A, user = B):

| event | definition | n per 121-row avatar run (est.) |
|---|---|---|
| agent **complete** turn end | agent VAD stop; user takes a real turn within 3 s and keeps it 1 s | 150–250 |
| agent **incomplete** pause | agent VAD stop; agent resumes within 5 s first | 100–300 (TTS has few) |
| agent **onset** | first non-backchannel agent onset after ≥ 1 s of user speech or silence | 200–350 |
| mid-turn negatives | random frames with ≥ 1 s of agent speech ahead | matched 1:1 |

Per run, per mode (A, V, AV), with conversation-level bootstrap CIs (clips as the resampling unit):

1. **Yield-cue AUC** — `p_eager` at offset − 0.3 s on completes vs mid-turn negatives. Chance 0.5.
2. **Yield horizon** *(2026-11-08: ≈ 0 for humans — see §1b yield timing; report it, but the headline yield measure is 2b)* — on completes, the earliest time before the acoustic offset at which `p_eager` stays
   above θ_eager until the offset; θ_eager fitted on Seamless human data for ≤ 10 % withdrawn signals.
   Report detection rate and median horizon (ms). Missed = 0.
2b. **Yield-at-offset AUC** *(added 2026-11-08)* — the face in the first 0.3–0.5 s of the silence telling a complete
   turn end from an incomplete pause (`p_end(τ)` at τ = 0.3 and 0.5 s, V mode, completes vs incompletes). Human reference
   on Seamless test with the plain model: 0.68 at +0.3 s, 0.63 without the mouth features. For avatars this is the
   hold-vs-yield question: a face that drops to a closed neutral mouth at every TTS phrase break signals "end" at pauses
   it does not mean; one that keeps the speaking posture across a pause and closes only at the real end scores human.
3. **Start-cue AUC(h)** — `p_start(0.4)` scored at onset − 0.3 s and `p_start(1)` at onset − 0.5 s, on
   agent onsets vs listening negatives. **Bid lead** — the earliest time before the onset at which
   `p_start(1 s)` stays above θ_bid (fitted on human data at 10 % false bids) until the onset; median and
   detection rate. Human reference from the bid study (§1b): 40 % of onsets above threshold at the onset,
   median lead 0.5 s, p90 1.8 s, leads ≥ 2 s on 3 %. An avatar whose face only moves on audio shows 0.
3b. *(dropped 2026-11-08)* A "bid effect" validity measure (the listener's face predicting the speaker's
   offset) was planned here; the bid study measured it at +0.003 AUC for ends and chance for pauses, so
   there is nothing for the judge to validate against. The causal question (does an avatar's bid shorten a
   live user's turn) stays out of reach in this harness, where the user is a recording; see §7.
4. **Hold-cue FAR** — share of incomplete pauses on which `p_end(τ)` crosses the human-fitted θ(τ) table.
   *(2026-11-08: humans precede a within-turn pause with a still head from −0.5 s on both corpora; a secondary
   "hold-cue agreement" — `p_end` falling when the speaker's head freezes into a silence — is worth reporting here.)*
   For avatars this measures whether their pauses look like turn ends (TTS phrase breaks usually do).
5. **Visual gain** — AV minus A for metrics 1 and 3; the number that survives the "TTS audio is cue-poor"
   objection.
6. **Controls, always reported next to the numbers:** shuffled-video (face track from a different clip of
   the same run; must land at chance), frozen-video (one frame held; must land at chance), AV-sync
   correction (`av_sync_offset_ms` from the lane extractor applied to the face track before scoring; the
   horizon is measured against the first *audible* sample), face-found rate per run.

Judge validity on human data (phase 1 and 3 report, Seamless test split, 133 speaker files):

- visual-only yield-cue AUC and start-cue AUC with CIs; **gate: both ≥ 0.60 and shuffled-video ≤ 0.53**;
- sensitivity: time-shift the human face track by +1 s and by −1 s, replace it with a static frame — the
  visual-only AUCs must fall towards chance monotonically with the degradation;
- improvised vs naturalistic and per-site slices (Berner et al. found domain sensitivity).

## 4. Data

| use | source | status |
|---|---|---|
| training, phase 1 | R2 train tracks on Modal: 1,000 naturalistic pairs, 37,868 labelled silences, Meta movement features on 46 % of windows, dev/test speakers excluded | exists (`docs/r2_seamless.md` §1) |
| training, phase 2 | open-extractor 10 fps face tracks for the same pairs; needs the 4K video per file (~70 MB/min) → extract on Modal CPU, keep tracks (few KB/min), discard video | to build; ~1 CPU-day on Modal with 16 containers |
| extractor agreement | the 157 naturalistic/test videos already local (12 GB, `data/seamless/raw/naturalistic/test/video`) + the dev files with Meta features | local |
| human reference for the judge | Seamless test split, both participants | exists (WS9 frozen set + full-file tracks) |
| avatar evaluation | `runs_nv/{tavus_av2av,anam_a2av,heygen_a2av}` (121 generation rows each, `agent.mp4` 1280×720 30 fps + `agent.wav` + events with `first_video_s`/`first_audio_s`); `runs_v1/post/*` (7 Seamless clips, 3 avatars + human partner) | exists |
| paired human-vs-avatar on the same stimuli | re-run the three avatars on `manifest/ovfdb_v1_reviewed.jsonl` (48 accepted rows; ≈ 20 vendor-minutes each) — the NVIDIA human partner video exists on 4 validation rows only, so pairing must come from Seamless | phase 3, optional but recommended |
| cross-site replication / commercial training set | CANDOR processed flavour (34 archives, 346 GB, 3,312 participant videos): `scripts/candor_prep.py` per archive, `scripts/candor_modal.py` for all 34 on Modal volume `candor` (video discarded; ≈ 100 GB FLAC + 20 GB tracks kept); events by the WS9 rules on Silero VAD + 2024 AWS words (`eot/candor.py`, private repo) | pilot archive done locally (`data/candor/`); full run pending |

Licence boundaries as in WS9/R2: Seamless-derived tracks and the model under NC; NVIDIA avatar runs stay
local (results publishable, frames not).

## 5. Phases, gates, estimates

**Phase 0 — metrics and extraction scaffolding (1–2 days, this repo, no training).**
- **Done 2026-11-07/08 (probe/crop for full-body video, `frames.npz` extras added 11-08):** `ovfdb/score/lanes.py`: MediaPipe Face Landmarker at 10 fps on any mp4 (one face box per file as in the
  WS9 builder; reuse `fugubook/avatar-bench/extract_lanes.py` for blendshapes, head pose, gaze proxy,
  mouth openness, `av_sync_offset_ms`). Output `face.npy` (T, 64) + `face.json` (fps, box, found-rate).
  Dependency behind the existing `lanes` extra; `face_landmarker.task` fetched to `data/models/`.
- **Done 2026-11-08:** `ovfdb/score/cues.py`: event mining on `AgentRun` + user segments (WS9 rules with A/B = agent/user),
  metrics 1–6 from probability tracks, bootstrap CIs. Unit tests on synthetic tracks (a track that rises
  300 ms before every complete must give horizon 300 and AUC 1.0; a flat track gives 0 and 0.5; shuffled
  control at chance).
- Run the extractor on all avatar runs and the 7 post clips; record face-found rate and AV offset per
  vendor. **Gate 0:** faces found on ≥ 95 % of avatar frames (Anam/HeyGen/Tavus are head-and-shoulders;
  expected to pass).

**Phase 1a — the bid study. Done 2026-10-27** (private repo, local CPU; report and numbers in §1b). It
fixed the horizons, the feature set and the label-noise estimate used from phase 1 on, and removed the
partner-face branch and measure 3b.

**Phase 1 — visual-signal gate with the oracle features (2–3 days, private repo, Modal).**
- Extend `HeadsAV`: `p_start(h)` heads (h = 0.4, 1 s) on the participant's own face, modality dropout,
  presence flags. Train on the R2 train tracks (two seeds, the R2 recipe and epoch selection on dev). The
  bid study's `scripts/r2_bids_common.py` already loads both participants' tracks and defines onsets,
  backchannels and baselines; reuse it for the labels.
- Evaluate on Seamless test in A / V / AV modes with the controls of §3. **Gate 1:** visual-only yield-cue
  AUC ≥ 0.60 and start-cue AUC ≥ 0.60, both with the shuffled control ≤ 0.53. If only one passes, continue
  with that measure. If neither passes, stop: the honest finding is that face features of this kind do
  not carry a detectable anticipatory signal, and the WS closes with that note in `results/`.
- Cost: ≈ 2 GPU-hours per seed on Modal (the R2 runs were 199 k parameters).
- Expectation from §1b: the start-cue gate should pass at h = 0.4 s (a plain logistic on the last 3 s of
  face features already reaches 0.70 on dev); the yield-cue gate is the uncertain one (the R2 oracle's
  speaker-face gain was +0.016 eager AUC).

**Phase 2 — the judge that runs on avatar video (3–5 days).**
- *(settled 2026-11-08 by the gate proxy above: MediaPipe reproduces the Meta-feature findings on the same files)* Extractor agreement on the 157 local test videos: correlation of MediaPipe blendshapes / head pose with
  Meta's FAUValue / head_encodings / gaze_encodings per frame; pick MediaPipe or OpenFace by agreement and
  CPU cost. Open question from the design doc (§8) settled here.
- Decision point: (a) if a linear map from open features to the oracle's 31-d reproduces the phase-1
  visual-only AUC within 0.02 on the test files that have both, ship the phase-1 model behind that map and
  skip the train re-extraction; (b) otherwise extract open tracks for the 1,000 train pairs on Modal and
  retrain with the phase-1 recipe. Budget assumes (b).
- Export stateless ONNX (one window → three probabilities, A/V/AV by presence flags) + a 10 Hz sliding
  runner in `ovfdb/score/cue_judge.py`; the audio features come from the public `smart-turn-streaming`
  package (`eot.features`), so this repo adds no torch dependency.
- Publish `OpenHRI/ovfdb-cue-judge` (CC BY-NC, model card with the phase-1/2 validity numbers).

**Phase 3 — scoring runs and the results note (2 days, this repo).**
- `ovfdb score-cues <run> --manifest …` → `<row>/cues.json`; `report` gains a "Cue signalling" table:
  yield-cue AUC / horizon, start-cue AUC / horizon, hold FAR, visual gain, controls, per run.
- Score: human reference (Seamless test files as a run through the human_gt provider, both roles), the three
  avatars on the 121 NVIDIA rows, the 7 post clips; MM-VAP (Candor-trained, public) as an external
  visual-only baseline on the same events.
- Optional paired set: the three avatars on the 48 reviewed v1 rows (vendor cost ≈ 1 h total).
- `results/cues_nvidia_generation.md` + README paragraph; `docs/protocol.md` §11 documents the measure as an
  OpenVideoFDB extension, clearly marked as not part of the paper's protocol.

**Phase 4 — human validation (later, 1 day + raters).** 100 muted 2 s pre-offset and pre-onset snippets
(human and avatar), raters press a key when they think the turn is about to end / begin; correlate rater
lead with the judge's horizon. This is what turns "the predictor says" into "people see it too".

## 6. Acceptance
- `uv run pytest tests/test_cues.py` passes on synthetic tracks (metrics 1–6, controls, bootstrap).
- Phase-1 report with the gate numbers and the sensitivity curves, in `results/cues_validity.md`.
- If gate 1 passes: `ovfdb score-cues` runs on `runs_nv/heygen_a2av` end to end and the report table shows
  the human reference, three avatars, and all controls, with CIs.

## 7. Open questions
- Negatives for the start-cue AUC: listening stretches include backchannels; exclude ± 0.5 s around any
  user-side backchannel of the agent, or keep them as hard negatives? Start with exclusion, report both.
- Abandoned bids (measured, §1b): 3.2 per listening minute, 43 % of bid-score runs. They are negatives
  under onset labels, so the human-reference start-cue AUC is understated and the human-vs-avatar gap is
  conservative. The 30-example spot-check list is in the report's §5 and has not been eyeballed yet.
- Bid effect on avatars needs a live run: a human user talking to the avatar through the Playwright
  harness with the camera on, so the user can respond to the avatar's bids. Out of scope for WS10; the
  harness already supports it technically (fake-device flags replaced by a real camera).
- AV-sync for human Seamless files is 0 by construction; for avatars `first_video_s − first_audio_s` and the
  lane cross-correlation can disagree — report both and use the cross-correlation.
- Whether to report horizons against the vendor's own "speaking state" transition as a secondary anchor
  (Anam/HeyGen expose it in session events); useful diagnostically, never the headline.
- Improvised Seamless data: excluded from training (WS decision 2026-10-15); a test-time slice only.
