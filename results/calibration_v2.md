# OpenVideoFDB summary

Runs: runs/gt, runs/random  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 118 | 4.26 | 4.46 | 4.00 | 4.27 | 95% / 496 ms |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 118 | 2.19 | 2.39 | 3.18 | 2.47 | 47% / 0 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 118 | 4.26 [3.96, 4.56] | 4.46 [4.21, 4.71] | 4.00 [3.61, 4.36] | 4.27 [4.06, 4.49] | 95 [91, 100] | 496 [360, 648] |
| Random baseline (mismatched partner) | AV2AV | 118 | 2.19 [1.61, 2.74] | 2.39 [1.61, 3.21] | 3.18 [2.71, 3.68] | 2.47 [1.97, 2.94] | 47 [35, 59] | 0 [0, 680] |

## Per dynamic

| Model | Setting | dynamic_type | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | | |
| Human reference | AV2AV | Adaptor Handling | 8 | 4.12 | — | 5.00 | 4.56 | 75% / — |
| Human reference | AV2AV | Emotion Matching | 8 | — | — | — | — | — |
| Human reference | AV2AV | Face Emotion Display | 16 | 3.38 | — | 4.25 | 3.81 | — |
| Human reference | AV2AV | Gaze Avoidance with Pause | 8 | 5.00 | 5.00 | — | 5.00 | 100% / — |
| Human reference | AV2AV | Laughter | 20 | 4.00 | — | 3.40 | 3.70 | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 16 | 5.00 | 4.00 | — | 4.50 | 88% / — |
| Human reference | AV2AV | Nonverbal Interruption | 2 | 2.50 | 3.50 | 2.00 | 2.67 | 100% / 308 ms |
| Human reference | AV2AV | Pause Handling | 10 | 4.50 | 4.60 | — | 4.55 | 100% / 1016 ms |
| Human reference | AV2AV | Turn-taking | 10 | — | — | — | — | 100% / 632 ms |
| Human reference | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 100% / 304 ms |
| Human reference | AV2AV | Verbal Interruption | 10 | — | — | — | — | 100% / 636 ms |
| **Random baseline** | | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | Adaptor Handling | 8 | 1.88 | — | 5.00 | 3.44 | 62% / — |
| Random baseline (mismatched partner) | AV2AV | Emotion Matching | 8 | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Face Emotion Display | 16 | 1.50 | — | 2.25 | 1.88 | — |
| Random baseline (mismatched partner) | AV2AV | Gaze Avoidance with Pause | 8 | 1.88 | 2.12 | — | 2.00 | 50% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Laughter | 20 | 2.00 | — | 2.30 | 2.15 | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Backchanneling | 16 | 1.88 | 1.50 | — | 1.69 | 100% / — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Interruption | 2 | 5.00 | 2.00 | 4.00 | 3.67 | 0% / — |
| Random baseline (mismatched partner) | AV2AV | Pause Handling | 10 | 3.10 | 3.40 | — | 3.25 | 80% / 196 ms |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 10 | — | — | — | — | 50% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 0% / — |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 10 | — | — | — | — | 10% / 2904 ms |

## Per dynamic with 95 % bootstrap CIs

| Model | Setting | dynamic_type | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | Adaptor Handling | 8 | 4.12 [2.88, 4.88] | — | 5.00 [5.00, 5.00] | 4.56 [3.94, 4.94] | 75 [38, 100] | — |
| Human reference | AV2AV | Emotion Matching | 8 | — | — | — | — | — | — |
| Human reference | AV2AV | Face Emotion Display | 16 | 3.38 [2.75, 4.12] | — | 4.25 [4.00, 4.50] | 3.81 [3.44, 4.25] | — | — |
| Human reference | AV2AV | Gaze Avoidance with Pause | 8 | 5.00 [5.00, 5.00] | 5.00 [5.00, 5.00] | — | 5.00 [5.00, 5.00] | 100 [100, 100] | — |
| Human reference | AV2AV | Laughter | 20 | 4.00 [3.50, 4.40] | — | 3.40 [2.90, 3.90] | 3.70 [3.30, 4.05] | — | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 16 | 5.00 [5.00, 5.00] | 4.00 [4.00, 4.00] | — | 4.50 [4.50, 4.50] | 88 [62, 100] | — |
| Human reference | AV2AV | Nonverbal Interruption | 2 | 2.50 [2.00, 3.00] | 3.50 [3.00, 4.00] | 2.00 [1.00, 3.00] | 2.67 [2.00, 3.33] | 100 [100, 100] | 308 [122, 494] |
| Human reference | AV2AV | Pause Handling | 10 | 4.50 [3.60, 5.00] | 4.60 [4.00, 5.00] | — | 4.55 [3.80, 5.00] | 100 [100, 100] | 1016 [1000, 1032] |
| Human reference | AV2AV | Turn-taking | 10 | — | — | — | — | 100 [100, 100] | 632 [456, 1032] |
| Human reference | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 100 [100, 100] | 304 [270, 304] |
| Human reference | AV2AV | Verbal Interruption | 10 | — | — | — | — | 100 [100, 100] | 636 [516, 900] |
| Random baseline (mismatched partner) | AV2AV | Adaptor Handling | 8 | 1.88 [0.50, 3.38] | — | 5.00 [5.00, 5.00] | 3.44 [2.75, 4.19] | 62 [25, 88] | — |
| Random baseline (mismatched partner) | AV2AV | Emotion Matching | 8 | — | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Face Emotion Display | 16 | 1.50 [0.75, 2.50] | — | 2.25 [2.00, 2.75] | 1.88 [1.38, 2.38] | — | — |
| Random baseline (mismatched partner) | AV2AV | Gaze Avoidance with Pause | 8 | 1.88 [0.62, 3.75] | 2.12 [0.62, 3.88] | — | 2.00 [0.62, 3.81] | 50 [12, 88] | 0 [0, 0] |
| Random baseline (mismatched partner) | AV2AV | Laughter | 20 | 2.00 [1.20, 2.80] | — | 2.30 [2.00, 2.70] | 2.15 [1.70, 2.60] | — | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Backchanneling | 16 | 1.88 [0.62, 3.75] | 1.50 [0.50, 3.00] | — | 1.69 [0.56, 3.38] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Interruption | 2 | 5.00 [5.00, 5.00] | 2.00 [2.00, 2.00] | 4.00 [4.00, 4.00] | 3.67 [3.67, 3.67] | 0 [0, 0] | — |
| Random baseline (mismatched partner) | AV2AV | Pause Handling | 10 | 3.10 [1.60, 4.50] | 3.40 [2.00, 4.50] | — | 3.25 [1.75, 4.50] | 80 [50, 100] | 196 [0, 2176] |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 0 [0, 968] |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 10 | — | — | — | — | 10 [0, 30] | 2904 [0, 4133] |

## Calibration notes (v2, 2026-10-16)

Payload v2 (`ovfdb/score/judge.py`, docs/protocol.md §5) adds evidence lines only; rubric and
preamble text are unchanged. Judge gpt-4o, n = 20 perception rows (10 Pause Handling, 10 Laughter)
per run; timing rows unchanged from v1.

| metric | v0 (ASR segs) | v1 (VAD segs) | v2 (VAD + payload v2) | paper GT |
|---|---|---|---|---|
| GT overall | 3.95 | 3.70 | **4.12** | ≈ 4.4 |
| random overall | 2.15 | 2.12 | 2.70 | — |
| GT Pause Handling flow | 4.60 | 4.20 | 4.60 | ≈ 4.5 |
| GT Laughter fluency | 2.60 | 2.90 | 4.00 | ≈ 4.5 |
| GT Laughter grounding | 3.50 | 3.80 | 3.40 | ≈ 4.2 |
| GT TOR-Align | 70 % | 100 % | 100 % | 90 % |

What moved and why:
- **Laughter fluency 2.9 → 4.0.** v1's judge called the human partner "repetitive / mirroring the
  user" on several Laughter clips. Root cause: the Gemini AV caption attributes speech by lip
  reading a mixed audio track and had swapped USER/PARTNER for whole pairs (`V00_S0314_*`), so the
  partner's own words looked like echoes of the user. v2 adds a caption caveat, a timestamped agent
  transcript and per-span annotations (words / backchannel / non-lexical), which let the judge
  re-attribute speech from the transcripts. A transcript-overlap check over all 110 clips finds 3
  clearly swapped and 6 mixed captions among the 37 decidable ones (`scratchpad/caption_swap.json`
  in the session; re-captioning with per-channel transcripts in the prompt is the proper fix).
- **GT Pause Handling flow 4.2 → 4.6.** Wordless VAD spans (breaths, "mhm") are now labelled as
  non-lexical, so they are no longer read as turn grabs. Two rows still get 3 (a vocalisation inside
  the pause; a 0.1 s overlap with the user's resumption).
- **Laughter grounding 3.8 → 3.4.** Four GT rows are rated 3 "on-topic but flat in tone"; the judge
  cannot hear register and whisper carries no laugh tokens. Candidate fix: run the laughter
  detector on `agent.wav` and add agent laugh spans to the payload.
- **Random 2.1 → 2.7.** The same non-lexical labelling helps the random partner (its breaths were
  also "talk-over"), and the cue line states that the laugh was a reaction to the agent. GT–random
  gap stays 1.4 points; the judge still separates. An earlier v2 draft quoted the human partner's
  words in the cue line ("right after the agent said ...") which inflated random's grounding; the
  committed version never quotes the partner.
- **Human-reference TOR-Align is 100 % by construction on the day-1 dynamics** (paper: 90 % perception /
  78 % generation). The paper's windows annotate the *user's* cue and let the partner's reaction fall where it
  may; our day-1 mining rules condition on the partner (Pause Handling rejects candidates where the partner
  spoke, Verbal Interruption requires `b_stop ≤ 1.5 s`, Turn-taking's window ends at the partner's onset, Verbal
  Backchanneling is built around the partner's token). GT latency (~500 ms) is tight for the same reason. Models
  and random are still judged fairly against the windows; only the GT line is inflated. Fix = re-mine with
  user-cue-only windows (fixed post-cue window), which changes the manifest. Day-2 nonverbal rules key on
  video events and are less circular (GT 75–88 %).
