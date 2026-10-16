# OpenVideoFDB summary

Runs: runs/gt, runs/random  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Overall = mean of each perception row's available judge axes. Brackets are 95 % bootstrap CIs over rows (1000 resamples, seed 0). TOR-Align % = fraction of timed rows whose takeover matches the expected class; latency is the median.

| provider | mode | n | Fluency | Conv. Flow | Grounding | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| human_gt | av | 60 | 4.25 [3.80, 4.65] | 4.60 [4.00, 5.00] | 3.40 [2.90, 3.90] | 4.12 [3.67, 4.50] | 100 [100, 100] | 508 [304, 652] |
| random | av | 60 | 2.55 [1.65, 3.35] | 3.40 [2.00, 4.50] | 2.30 [2.00, 2.70] | 2.70 [1.93, 3.42] | 35 [22, 50] | 40 [0, 2176] |

## Per dynamic

| provider | mode | dynamic_type | n | Fluency | Conv. Flow | Grounding | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| human_gt | av | Laughter | 20 | 4.00 [3.50, 4.40] | — | 3.40 [2.90, 3.90] | 3.70 [3.30, 4.05] | — | — |
| human_gt | av | Pause Handling | 10 | 4.50 [3.60, 5.00] | 4.60 [4.00, 5.00] | — | 4.55 [3.80, 5.00] | 100 [100, 100] | 1016 [1000, 1032] |
| human_gt | av | Turn-taking | 10 | — | — | — | — | 100 [100, 100] | 632 [456, 1032] |
| human_gt | av | Verbal Backchanneling | 10 | — | — | — | — | 100 [100, 100] | 304 [270, 304] |
| human_gt | av | Verbal Interruption | 10 | — | — | — | — | 100 [100, 100] | 636 [516, 900] |
| random | av | Laughter | 20 | 2.00 [1.20, 2.80] | — | 2.30 [2.00, 2.70] | 2.15 [1.70, 2.60] | — | — |
| random | av | Pause Handling | 10 | 3.10 [1.60, 4.50] | 3.40 [2.00, 4.50] | — | 3.25 [1.75, 4.50] | 80 [50, 100] | 196 [0, 2176] |
| random | av | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 0 [0, 968] |
| random | av | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| random | av | Verbal Interruption | 10 | — | — | — | — | 10 [0, 30] | 2904 [0, 4133] |

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
