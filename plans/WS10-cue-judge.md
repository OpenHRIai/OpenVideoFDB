# WS10 — Cue judge: a turn-taking predictor as an automatic score for the agent's own signalling

**Depends on:** WS9 (end-of-turn rules + Seamless splits, branch `ws9-endpointing-private`), WS6b (avatar
runs with `agent.mp4`), the R2 track pipeline and audio heads in `smart-turn-multimodal-private`
(`eot/model_av.py`, `scripts/r2_*.py`, Modal volume `smart-turn-v2`), and the bid study's findings
(`docs/r2_floor_bids.md` on branch `r2-floor-bids` of that repo, done 2026-10-27, see §1b). **Est.:** 8–12
working days across four phases, with a kill gate after phase 1. **Status 2026-11-11:** spec, phase 1a, phase 0 (`lanes.py`, `cues.py`)
and the CANDOR replication done; **phase 1 done in its visual-only form** (GRU heads on the open-extractor tracks, §1b
last paragraph: gate 1 met on a fresh hold-out, start cue 0.725, yield cue 0.689), and the same heads trained on
CANDOR for the second human reference (§1b, 'The sequence heads on CANDOR': start cue 0.769, yield cue 0.706); the audio
branch and modality dropout of §2 and the 10 Hz runner of phase 2 are not built. **Version 2, 2026-11-14:** turn ends and pauses are now timed on the
end of audible speech and the human references were recomputed on that clock (§1b, 'Version 2 of the human
references'): start cue 0.724 (Seamless) and 0.769 (CANDOR), yield cue 0.658 and 0.688. Numbers elsewhere in this
spec are version 1 (voice-activity clock) unless marked. **Gaze, 2026-11-14:** the partner-gaze measure mixes head
and eye position and cannot tell a head turn from a look away (§1b, 'What the partner-gaze measure is and is not');
separate head, eye and gaze-on-partner inputs are planned with a labelled pilot first (§5, phase 2, 'Gaze inputs'),
not started.
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
0.56) and not from the mouth — a hold cue *(corrected 2026-11-09: on Seamless only. On CANDOR the head slows equally
before a turn end, d −0.12 vs −0.14 before a pause, so stillness marks a coming stop, not a pause)*. *Own display, not reaction:* with the listener removed (nobody speaks for
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

*Gaze towards the partner (2026-11-09, private repo `scripts/cue_gaze.py`, hypotheses file S9).* With the partner's direction
estimated per person from that person's own listening frames (median of head yaw / pitch and iris offset; 'at the partner' =
within the 70 % listening cone), speakers are at the partner in +15 pp more frames in the last 0.5 s before a turn end than
mid-turn on both corpora (Seamless +15.1 [+10.1, +19.4], CANDOR +15.3 [+14.3, +16.2]), +14 pp vs a pause, nothing before a
pause; rise from ≈ −0.7 s on Seamless. Single-number AUC end vs pause before the offset 0.605 / 0.597 — above the 65
camera-relative features on Seamless (0.571). **Consequence for the judge:** feed gaze relative to the partner, per person
(the pooled camera-relative gaze columns cannot carry this); for an agent the partner direction is the camera. Yield metric 2
(pre-offset horizon) is therefore not ≈ 0 for humans once this feature exists: a human reference of ≈ 0.6 AUC about 0.5 s
ahead. *Resolution (X2):* re-tracking Seamless with the face at CANDOR's 79 px (`lanes --face-px 80`) changes no effect, so
low resolution is not why CANDOR's motion effects are smaller. *In the decoder (`scripts/cue_gaze_decode.py`):* four partner-gaze columns added
to the 65 features raise end-vs-pause AUC at −0.3 / 0 / +0.3 / +1.0 s from 0.560 / 0.586 / 0.681 / 0.716 to 0.605 / 0.644 / 0.726 /
0.770 on Seamless and from 0.621 / 0.652 / 0.696 / 0.727 to 0.641 / 0.673 / 0.720 / 0.751 on CANDOR (paired CIs exclude 0). These
supersede the earlier human reference for metrics 2 and 2b.

*What the partner-gaze measure is and is not (2026-11-14, found while choosing the blog's example clip).* The four
numbers (head yaw, head pitch, iris left–right, iris up–down) enter one distance as separate dimensions, so they are
not a gaze direction: a head that tilts while the eyes stay on the partner leaves the cone. Seen on Seamless
`V03_S1920_I00000213_P5375` at 81.84 s: the head about 10° from its listening centre, the eyes on the partner throughout
(maintainer's check by eye), labelled 'away' for 2.5 s. The tracker's numbers give no way to correct for this: across
114 Seamless test speakers with ≥ 20 s of listening, head and iris move together rather than against each other while
listening (correlation median +0.12 left–right, +0.06 up–down; negative for only 35 % and 41 % of speakers). The 0/1
label also flickers: on the Seamless test split (216,520 frames) 2.7 % of frames are one-sample blips, 46 % of the 25,028
label changes belong to one, and 15.7 % of frames lie within 15 % of the cut-off distance. None of this reaches the GRU
heads, which read the 65 continuous features, and the averages stand. Version 2, turn end minus pause in the last
0.5 s: head + eyes +13.7 pp [+12.0, +14.9] Seamless / +13.0 [+11.9, +14.0] CANDOR; eyes only +14.0 [+12.5, +15.3] /
+13.0 [+12.0, +13.9]; head only +8.8 [+7.3, +10.1] / +9.0 [+7.8, +10.1]; a 50 % cone shrinks the combined value to
+9.1 / +9.0. Per event (Seamless test split, voice-activity clock, 387 turn ends against 1,507 pauses) the continuous
distance separates turn ends from pauses at AUC 0.618, the 0/1 label at 0.595 (0.593 with blips removed). The level of
the share while speaking (27.6 % / 34.9 % of frames) is set by the 70 % cone and means little on its own. The judge's
gaze inputs are re-planned in §5, phase 2, 'Gaze inputs'.

*Confirmation on unseen data (2026-11-09; private repo `scripts/cue_confirm.py`, hypotheses file §9 protocol and §10
results).* The claims above were tested once under a protocol committed beforehand, with models fitted on the data above
and applied unchanged to Seamless dev (566 turn ends) and to 12,000 CANDOR turn ends never sampled before, from the
conversation half not used for fitting. CANDOR: 18 of 18 primary tests confirmed, values within 0.01 AUC of the earlier
ones. Seamless: 15 of 16 confirmed, values lower than above. **Human reference from unseen data (use these, not the
numbers above), Seamless / CANDOR:** start cue at −0.3 s 0.579 [0.54, 0.61] / 0.700 [0.69, 0.71]; turn end vs pause at
−0.3 s 0.578 [0.54, 0.61] / 0.643 [0.64, 0.65], at +0.3 s 0.674 [0.64, 0.70] / 0.722 [0.71, 0.73], at +1.0 s 0.764 / 0.754;
turn end vs mid-turn at −0.3 s 0.597 [0.57, 0.63] / 0.679 (a coming pause vs mid-turn is 0.560 / 0.568, so this contrast
is partly "about to stop for any reason"); gaze at the partner in the last 0.5 s, turn end minus pause, +9.1 pp
[+2.8, +14.9] / +14.0 pp. The same models on a face from another conversation score 0.50–0.51 on both. **Consequences:**
(1) gate 1 with the plain model on unseen Seamless is not met before the event (0.58 on both sides, intervals reaching
0.60) and is met after the stop; the judge's GRU heads, trained on far more than 65 conversations, have to clear it.
(2) The headline yield measure before the stop should be turn end vs pause (metric 1b below), with turn end vs mid-turn
kept as a secondary number. (3) Withdrawn: "on task talk the user's face in a silence separates floor-taking from waiting
from ≈ 300 ms in" — on Seamless dev the taker-vs-non-taker AUC does not grow in the first 0.3 s of silence (+0.013
[−0.03, +0.05]). (4) CANDOR-only cues (readiness posture, pre-end smile, still head with um / uh) are confirmed on CANDOR
and absent or untestable on Seamless: inputs, never rules. *Audio plus visual (`scripts/cue_av_gain.py`):* added to the
in-domain audio heads on Seamless dev, the face changes turn-end-vs-pause AUC by +0.008 / −0.001 / +0.004 at −0.4 / 0 /
+0.3 s, none distinguishable from zero (frozen Smart Turn v3.2 as the audio model: +0.022 / +0.001 / +0.017). The judge's
case does not rest on this: it measures whether an agent's face behaves like a human's, not whether a face helps a
detector; metric 5 (visual gain) should be expected near zero for humans with a strong audio model.

*Two human references, and which one fits the benchmark (2026-11-09; hypotheses file §11).* Seamless is same-room talk
between mostly acquainted people; CANDOR is video calls between strangers. The cues that differ (CANDOR only: the
listener's readiness seconds ahead, the speaker's smile before ending; Seamless only: a stiller head into a pause than
into a turn end; blink after a turn end with opposite signs) are confirmed on unseen data on the corpus where they were
claimed, so they are properties of the setting, not noise. The literature supports the direction for smiling (more on
video among strangers) and for head motion (smaller on video) and has no study of the listener's pre-speech signals in
both media; medium and relationship are confounded here. **An agent in this benchmark meets an unknown user over a video
link, which is the CANDOR setting.** Report both references; do not treat CANDOR-side cues as artefacts. *Training data
(exploratory, `scripts/cue_transfer.py`):* Seamless-only models trained on both tracked splits (about 130 conversations per
fold) reach 0.638 [0.61, 0.66] on the start cue and 0.632 on turn end vs mid-turn, so gate 1's start-cue criterion is
within reach on Seamless with more data; turn end vs pause before the stop stays at 0.59 in every variant. A CANDOR-only
model scores 0.655 on the Seamless start cue (the cue transfers across settings); mixing corpora adds nothing over
Seamless-only training. Decision: the Seamless reference models are trained on Seamless only.

*Seamless only, five times the data (2026-11-09, exploratory; private repo `scripts/seamless_train_subset.py`,
`scripts/cue_seamless_scale.py`, hypotheses file §10 and §11).* 300 conversations of the Seamless train split (156 stranger
/ 144 acquainted pairs, drawn with a fixed seed before any video was opened; 600 videos tracked into
`data/seamless/lanes/train`, face found 97.7 %, no failures) give 1,846 more turn ends. **Seamless-only models trained on
test + this subset (353 conversations) and scored unchanged on dev:** start cue 0.653 [0.61, 0.69] (was 0.579; the same
model on a face from another conversation 0.525), turn end vs mid-turn 0.631 [0.60, 0.66] (was 0.597), turn end vs pause
at +0.3 s 0.701 (was 0.674), turn end vs pause at −0.3 s 0.583 [0.54, 0.62] (was 0.578). Start cue and turn end vs
mid-turn are still rising with data. **Cross-validated over all 424 tracked Seamless conversations:** 0.660 / 0.644 /
0.735 / 0.627 in the same order, against 0.700 / 0.679 / 0.722 / 0.643 on CANDOR; dev is the low set for turn end vs pause
before the stop (0.578 for dev events in that run, 0.64 for the others). **Consequences:** (1) gate 1's start-cue
criterion is met on unseen Seamless by a plain Seamless-only model, and so is metric 1; metric 1b sits at 0.58–0.63 on
Seamless and is not secured on dev. (2) Most of the earlier Seamless-vs-CANDOR gap in the model scores was training-set
size, not setting. Use the cross-validated values as the Seamless human reference. (3) The frozen test-trained models and
protocol statistics on the subset as a second unseen set: 14 of 16 primary tests confirmed; the growth of floor-taking in
the silence fails again (−0.019), and "stiller head into a pause than into a turn end" does not replicate (+0.02
[−0.04, +0.08]) and is no longer a Seamless-side cue. Those frozen models are the small ones and understate model scores;
with the larger models (every event scored by a model fitted on the other nine tenths of the 424 conversations) the
growth of floor-taking in the first 0.3 s of silence is still absent (+0.007 [−0.01, +0.03]; +0.097 by 1.0 s), while the
taker-vs-non-taker AUC 0.3 s before the stop is 0.544 [0.53, 0.56], small but above chance (CANDOR 0.591): the listener's
early sign is present on Seamless at about half the CANDOR size, not absent. Gaze back to the partner, turn end minus pause, is +15.2 pp pooled,
the same size as on CANDOR. Blink and downward gaze rise before a listener speaks on Seamless (+0.19, +0.24; near zero on
CANDOR). (4) **Strangers vs acquainted pairs in the same room (180 vs 238 conversations): no statistic differs.** Seamless
strangers show no readiness posture (+0.05 [−0.07, +0.18]; CANDOR +0.36), no pre-end smile (−0.04; CANDOR +0.19) and
fewer blinks after a turn end (−0.23; CANDOR +0.24). So being strangers does not produce the CANDOR-side cues; the medium
and the other corpus differences remain.
**Hold-out rule for the other 700 train conversations (fixed 2026-11-10 07:40, while their tracking ran and before any
was scored):** the first 200 conversations of the seeded order in which they are tracked (seed 1,
`seamless_train_subset.py --rest-out`) are a fresh hold-out, scored once by models trained on test + subset + the other
500; the full protocol table is decided on it by the protocol's rules (`cue_seamless_scale.py` part 6). It settles whether
turn end vs pause before the stop is 0.58 (dev) or 0.64 (test, subset) on unseen Seamless, and gives the Seamless human
reference for metric 1b. **Result (2026-11-10 20:15; all 1,000 train conversations tracked, the last 378 on Modal with
`modal_seamless_lanes.py`; `runs/r2/cues/confirm/scale2.md`; hypotheses file §10 'All of Seamless and a fresh
hold-out'):** models fitted on 833 Seamless conversations, scored once on the 187 hold-out conversations with a turn end
(1,079 ends, 6,610 pauses): start cue 0.644 [0.62, 0.67], turn end vs pause at −0.3 s 0.628 [0.60, 0.65], at +0.3 s
0.723 [0.70, 0.75], turn end vs mid-turn 0.641 [0.62, 0.66]; controls 0.48–0.51; 14 of 16 primary tests confirmed, the
same 14 as on the subset; dev had confirmed 15 of 16, with the stiller head passing at +0.15 (corrected 2026-11-11).
Floor-taking growth (+0.014, failing on all three unseen sets) and stiller head into a pause (+0.042) are dropped for
Seamless (pooled over all events they are +0.017 [0.007, 0.028] and +0.060 [+0.03, +0.09], real and
small). Cross-validated over all 1,091 tracked Seamless conversations: 0.657 / 0.651 / 0.739 / 0.639 (start, mid-turn,
+0.3 s, −0.3 s); dev alone stays at 0.59 for turn end vs pause before the stop while every other set is 0.63–0.65, so
dev is the odd set and the Seamless reference for metric 1b is 0.63–0.64, equal to CANDOR's 0.643. Learning curves
have flattened (353 → 833 conversations: +0.013 on the start cue, ≤ +0.006 elsewhere), so the remaining start-cue gap
to CANDOR (0.657 vs 0.700) is not training-set size; the judge's sequence heads are the next thing that could close
it. The listener's early taker sign is 0.558 [0.55, 0.57] on Seamless (present, half of CANDOR's 0.591); the readiness
posture is +0.09 [+0.04, +0.14] (small, a quarter of CANDOR's, identical for strangers and acquainted pairs).
Relationship (382 vs 695 conversations) separates nothing.

**The judge's sequence heads (phase 1, 2026-11-11; private repo `scripts/cue_gru.py`, report `docs/cue_gru_heads.md`,
hypotheses file §10 'The judge's sequence heads').** A GRU head (gated recurrent unit: a recurrent network that reads the
window's 10 Hz face frames one at a time and turns its final state into one logit; 65 face features for the listener, 69
with the gaze-to-partner columns for the speaker, plus a face-found flag) per statistic, on exactly the stand-ins' events,
rows, per-file z-scores, frames and shuffled-face control (their features recomputed from the stored windows match to
1e-4). One forced change: frames after the other party speaks again are blank in the stacks and their count differs a
little between turn ends and pauses 0.3 s into the silence (AUC 0.53 alone), so each GRU window ends at the last frame
before anyone speaks again. Trained on the 833 training conversations; hidden size, dropout and context (1 s = the
stand-in's window, or 2 s; 3 s for the listener) chosen on dev only, three seeds averaged; the 187-conversation hold-out
scored once.

| statistic (metric) | logistic stand-in, hold-out | GRU heads, hold-out | paired difference | GRU control | CANDOR, logistic |
|---|---|---|---|---|---|
| start cue, 0.3 s before the first word (3) | 0.644 [0.62, 0.67] | **0.725 [0.70, 0.75]** | +0.080 [+0.06, +0.10] | 0.524 | 0.700 |
| turn end vs pause, 0.3 s before the stop (1b) | 0.628 [0.60, 0.65] | **0.686 [0.66, 0.71]** | +0.058 [+0.04, +0.08] | 0.503 | 0.643 |
| turn end vs pause, 0.3 s into the silence (2b) | 0.723 [0.70, 0.75] | **0.787 [0.77, 0.81]** | +0.064 [+0.05, +0.08] | 0.491 | 0.722 |
| turn end vs mid-turn speech, 0.3 s before the stop (1) | 0.641 [0.62, 0.66] | **0.689 [0.67, 0.71]** | +0.048 [+0.03, +0.06] | 0.484 | 0.679 |

The sequence heads beat the window summaries on every statistic, by +0.05 to +0.08 AUC with paired intervals excluding
zero and controls at chance. *(Corrected the same day, next paragraph: an earlier version of this paragraph called the
start-cue gap to CANDOR a model gap because the Seamless GRU, 0.725, is above CANDOR's logistic, 0.700. A CANDOR GRU
reaches 0.769, so the gap stays between like models.)* Before the stop, most of the yield gain needs the
second-to-last second (1 s window +0.031, 2 s window +0.058). **Gate 1 is met on a fresh hold-out with visual-only heads**
(start 0.725, yield 0.689, both ≥ 0.60, controls ≤ 0.53). These are the Seamless human references for metrics 1, 1b, 2b
and 3 from now on; the logistic values stay as the floor a window-summary judge would reach. Dev was the selection set
(its values 0.00–0.04 above the hold-out's); visual only, windows anchored on known events, 2 s the longest context the
stacks allow before the stop.

**The sequence heads on CANDOR (2026-11-11; `scripts/cue_gru.py --corpus candor`, same report, second part; hypotheses
file §10 'The sequence heads on CANDOR, and across corpora').** The same heads, grid, window rules and control, trained
on CANDOR only, so that the two human references compare between like models. The split is the confirmatory protocol's:
the GRUs are fitted on the exploration half (already-sampled events of one half of the conversations) minus a
validation part (one conversation in five of that half, 144 conversations, used only for early stopping and for
choosing the configuration), 608 conversations and 4,507–4,585 positives per statistic, about the size of the Seamless
training sets; the hold-out (12,000 never-sampled turn ends and 24,000 pauses from the 839 conversations of the other
half) was scored once. The logistic stand-in is the protocol's and reproduces its reported values.

*Units: every cell is an AUC (0.5 = chance) except the two columns marked 'difference', which are differences between
two AUCs; brackets are 95 % intervals from resampling whole conversations; 'control' is the same GRU on the face track
of a file from another conversation.*

| statistic (metric) | CANDOR logistic stand-in, hold-out | **CANDOR GRU heads, hold-out** | GRU − logistic on the same rows (difference) | CANDOR GRU control | Seamless GRU heads, hold-out | CANDOR − Seamless between GRUs (difference) |
|---|---|---|---|---|---|---|
| start cue, 0.3 s before the first word (3) | 0.700 [0.69, 0.71] | **0.769 [0.76, 0.78]** | +0.069 [+0.065, +0.073] | 0.495 | 0.725 [0.70, 0.75] | **+0.045 [+0.02, +0.07]** |
| turn end vs pause, 0.3 s before the stop (1b) | 0.643 [0.64, 0.65] | **0.669 [0.66, 0.68]** | +0.026 [+0.021, +0.031] | 0.497 | 0.686 [0.66, 0.71] | −0.017 [−0.04, +0.01] |
| turn end vs pause, 0.3 s into the silence (2b) | 0.722 [0.72, 0.73] | **0.761 [0.75, 0.77]** | +0.039 [+0.035, +0.042] | 0.498 | 0.787 [0.77, 0.81] | −0.026 [−0.05, −0.01] |
| turn end vs mid-turn speech, 0.3 s before the stop (1) | 0.679 [0.67, 0.69] | **0.706 [0.70, 0.71]** | +0.027 [+0.023, +0.031] | 0.500 | 0.689 [0.67, 0.71] | +0.017 [−0.01, +0.04] |

The sequence heads beat the window summaries on CANDOR as well, on all four statistics. **The start-cue gap between the
corpora survives between sequence models**: +0.045 [+0.016, +0.074] (0.769 against 0.725), against +0.056 between the
logistic models on the same two hold-outs; the sequence model lifts both corpora by the same amount within error
(+0.069 and +0.080). A listener on a CANDOR call is easier to read just before speaking with either model class; the gap
is a property of the corpus, not of the model (medium, kind of talk, population and recording remain confounded). The
speaker statistics gain less on CANDOR than on Seamless and end within 0.03 of each other between the corpora; only
'turn end vs pause into the silence' differs with an interval excluding zero, slightly higher on Seamless. **These are
the CANDOR human references for metrics 1, 1b, 2b and 3** (0.706, 0.669, 0.761, 0.769); gate 1's criteria hold on
CANDOR too. *Exploratory, outside the protocol:* each corpus's heads scored unchanged on the other corpus's hold-out
lose 0.03–0.05 AUC against the heads trained there and stay far above chance (start cue: Seamless-trained 0.734 on
CANDOR, CANDOR-trained 0.693 on Seamless; controls 0.49–0.52), so a judge trained on one corpus is usable on the other
setting, at that cost, and each setting is best scored against the reference of a head trained on it. Limits: CANDOR
has about twenty times more events than were used, so 0.769 is not a ceiling; the between-corpus intervals are as wide
as the 187 Seamless hold-out conversations allow.

**Version 2 of the human references (2026-11-14): events timed on audible speech.** Version 1 timed a turn end or a
pause at the end of the speaker's VAD (voice-activity detection) segment. That moment is a median 0.12 s (Seamless)
and 0.11 s (CANDOR) after the speech one can clearly hear, so version 2 times every turn end and pause at the end of
audible speech (the last 10 ms frame within 25 dB of the loudest frame in the 1.5 s before the VAD end, on the
speaker's own channel; private repo `modal_audible_ends.py`, switch `CUE_CLOCK=audible` in `scripts/cue_corpus.py`).
The sequence heads were retrained on that clock (`scripts/cue_gru_retimed.py`, `modal_gru_retimed.py`, run tag `aud`)
and every analysis and planned test aligned on the stop was run again (plot report `docs/cue_timing.md`, section
'Version 2'). **Use these as the human references from now on.** All values are hold-out AUC (area under the curve,
0.5 = chance) with 95 % intervals over conversations: 187 Seamless conversations, 839 CANDOR conversations.

| statistic (metric) | Seamless GRU, v1 (AUC) | Seamless GRU, v2 (AUC) | Seamless logistic, v2 (AUC) | CANDOR GRU, v1 (AUC) | CANDOR GRU, v2 (AUC) | CANDOR logistic, v2 (AUC) |
|---|---|---|---|---|---|---|
| start cue, 0.3 s before the first word (3; not re-timed) | 0.725 | **0.724 [0.70, 0.75]** | 0.644 | 0.769 | **0.769 [0.76, 0.78]** | 0.700 |
| turn end vs pause, 0.3 s before the stop (1b) | 0.686 | **0.675 [0.65, 0.70]** | 0.622 | 0.669 | **0.663 [0.66, 0.67]** | 0.636 |
| turn end vs pause, 0.3 s into the silence (2b) | 0.787 | **0.769 [0.75, 0.79]** | 0.703 | 0.761 | **0.746 [0.74, 0.75]** | 0.705 |
| turn end vs mid-turn speech, 0.3 s before the stop (1) | 0.689 | **0.658 [0.64, 0.68]** | 0.616 | 0.706 | **0.688 [0.68, 0.69]** | 0.666 |

Gate 1 still holds on both corpora (start and yield cue ≥ 0.60; controls on another conversation's face 0.49 to 0.52
on Seamless and 0.495 to 0.500 on CANDOR, all ≤ 0.53). The start-cue gap between the corpora is unchanged (+0.045
[+0.016, +0.074]). A head moved to the other corpus loses 0.03 to 0.04 AUC (was 0.03 to 0.05). The frozen protocol
rerun on the audible clock: 18 of 18 primary tests confirmed on the CANDOR hold-out (as before), 16 of 16 on the
Seamless fresh hold-out (was 14 of 16; S5 and L6 sit at their thresholds), 14 of 16 on the Seamless dev set (was 15
of 16; S4b, head stillness before a turn end, drops out) and 14 of 16 on the train subset (as before). These sets
had been scored once already, so this is a re-timing of confirmed results, not a second confirmation.
**Consequence for the judge and the metrics of §3:** a horizon 'before the stop' or 'into the silence' is counted
from the last audible sample of the speech, in line with §3 item 6, which already measures the agent's horizon
against the first audible sample; a judge trained on VAD-timed events would place the stop about 0.1 s late. The per-event lags and the loudness track of every recording
are saved for training (STATUS, WS10 entry of 2026-11-14).

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
1b. **Yield-vs-hold AUC before the stop** *(added 2026-11-09; headline pre-stop yield measure)* — `p_eager` at offset −
   0.3 s on completes vs incompletes (turn end coming vs pause coming). Metric 1 also rewards any sign that speech is
   about to stop (a coming pause scores 0.56 against mid-turn speech); 1b does not. Human reference on unseen data:
   0.63–0.64 Seamless (0.628 [0.60, 0.65] on a fresh 187-conversation hold-out with 833-conversation models, 0.639
   [0.63, 0.65] cross-validated over all 1,091 tracked conversations; the dev split alone is 0.59), 0.643 CANDOR, with
   gaze relative to the partner among the inputs. *With the judge's own GRU heads (§1b, 2026-11-11): 0.686 [0.66, 0.71] on the same
   hold-out; use that as the Seamless reference, the logistic value as the window-summary floor. CANDOR-trained GRU heads
   on the CANDOR hold-out: 0.669 [0.66, 0.68] (AUC, 95 % interval); use that as the CANDOR reference. The two do not
   differ reliably (−0.017 [−0.04, +0.01]).*
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
   "hold-cue agreement" — `p_end` falling when the speaker's head freezes into a silence — is worth reporting here.
   Corrected 2026-11-09: that holds on Seamless only; on CANDOR stillness precedes turn ends equally, so the
   secondary metric applies to the task-talk reference only and must not be built into the judge as a rule.)*
   For avatars this measures whether their pauses look like turn ends (TTS phrase breaks usually do).
5. **Visual gain** — AV minus A for metrics 1 and 3; the number that survives the "TTS audio is cue-poor"
   objection.
6. **Controls, always reported next to the numbers:** shuffled-video (face track from a different clip of
   the same run; must land at chance), frozen-video (one frame held; must land at chance), AV-sync
   correction (`av_sync_offset_ms` from the lane extractor applied to the face track before scoring; the
   horizon is measured against the first *audible* sample), face-found rate per run.

Judge validity on human data (phase 1 and 3 report, Seamless test split, 133 speaker files):

- visual-only yield-cue AUC and start-cue AUC with CIs; **gate: both ≥ 0.60 and shuffled-video ≤ 0.53**; *Met 2026-11-11 on the
  187-conversation hold-out with visual-only GRU heads: start 0.725, yield 0.689, controls 0.48–0.52 (§1b). The same
  heads trained on CANDOR meet it on the CANDOR hold-out: start 0.769, yield 0.706, controls 0.50.*
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
*Done 2026-11-11 in a different form (§1b, last paragraph): visual-only GRU heads on the open-extractor tracks of 833
Seamless conversations, laptop CPU, four window-anchored heads instead of the 10 Hz `HeadsAV` runner, chosen on dev and
scored once on the fresh hold-out. Gate 1 met: start cue 0.725, yield cue 0.689, controls ≤ 0.53. Not built: the audio
branch and modality dropout, the `p_start(h)` horizons as streaming heads, the sensitivity curves of §3. The oracle
features were dropped once phase 2's extractor question was settled for MediaPipe. The same heads were then trained on
CANDOR (608 conversations of the protocol's exploration half) for the second human reference: start cue 0.769, yield
cue 0.706 on the CANDOR hold-out (§1b, 'The sequence heads on CANDOR').*
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
- **Gaze inputs (added 2026-11-14; not started).** Why: §1b, 'What the partner-gaze measure is and is not'. The judge
  gets three gaze signals per frame in place of the four partner-gaze columns, from the same extractor on human and
  avatar video:
  1. *head direction*: yaw and pitch in degrees (MediaPipe head transform, already tracked);
  2. *eye direction in the head*: in degrees, i.e. gaze direction minus head direction; today only iris position (no
     unit) and the eight `eyeLook*` blendshapes exist;
  3. *gaze on the partner*: angle in degrees between the gaze direction and the partner's direction. A 0/1 version only
     where a share of frames is reported, with hysteresis (two cut-offs, so the label changes only after the angle has
     clearly crossed the boundary, not on every frame that grazes it).

  Partner direction: for an avatar, the camera (the user is behind it), no calibration; on CANDOR, the screen (near
  the camera, usually below it), estimated per person from listening frames in gaze angles; on Seamless, off camera,
  estimated the same way. The boundary for 'on the partner' becomes an angle (about the width of a face at the
  seating distance) instead of the 70 % share. Inputs are relative to the partner so that they mean the same thing in
  the training data and on avatars.
  - *Pilot and gate G (before any re-tracking; est. 1–2 days plus labelling).* A person labels 'eyes on the partner:
    yes / no' on about 300 frames per source (Seamless, CANDOR, the avatar runs), oversampling hard cases (head moves
    while the eyes stay; blinks; sideways glances with a still head). Compared against the labels: (a) the current
    head + iris label, (b) a geometric eye-in-head angle from MediaPipe's iris and eye-corner landmarks, (c) a
    dedicated appearance-based gaze-estimation model run on face crops (candidates to be chosen; licence and accuracy
    on these videos unchecked). Agreement as Cohen's kappa (agreement beyond chance: 0 = chance, 1 = perfect), 95 %
    intervals over recordings, per source. **Gate G:** re-track only where (b) or (c) clearly beats (a). CANDOR's
    320 × 240 frames leave the eyes a few pixels wide and may support head direction only; decide per corpus.
  - *If gate G passes:* re-track all recordings (2,296 Seamless, 3,183 CANDOR) and the avatar runs on Modal; rerun the
    gaze statistics (hypotheses S9 family) as version 3 and the GRU heads with the three inputs; report the gain over
    the current inputs (the four partner-gaze columns add +0.02 to +0.05 AUC to the decoder, §1b).
  - *What it buys on avatars:* the judge can then tell whether an avatar's eyes leave the camera while it talks and come
    back before a turn end, which the current inputs cannot separate from head motion.

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
