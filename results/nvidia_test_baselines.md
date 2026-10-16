# OpenVideoFDB summary

Runs: runs_nv/gt, runs_nv/random  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_test.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 60 | 4.57 | 4.06 | 3.64 | 4.22 | 100% / — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 226 | 1.57 | 2.06 | 2.73 | 2.03 | 53% / 0 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 60 | 4.57 [4.23, 4.80] | 4.06 [4.00, 4.19] | 3.64 [3.21, 4.07] | 4.22 [3.95, 4.43] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | 226 | 1.57 [1.24, 1.95] | 2.06 [1.48, 2.67] | 2.73 [2.37, 3.08] | 2.03 [1.72, 2.37] | 53 [44, 62] | 0 [0, 124] |

## Per dynamic

| Model | Setting | dynamic_type | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | | |
| Human reference | AV2AV | Laughter | 28 | 4.07 | — | 3.64 | 3.86 | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 32 | 5.00 | 4.06 | — | 4.53 | 100% / — |
| **Random baseline** | | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | Adaptor Handling | 13 | 1.46 | — | 4.23 | 2.85 | 92% / — |
| Random baseline (mismatched partner) | AV2AV | Emotion Matching | 13 | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Face Emotion Display | 48 | 1.08 | — | 2.42 | 1.75 | — |
| Random baseline (mismatched partner) | AV2AV | Gaze Avoidance with Pause | 17 | 1.59 | 2.18 | — | 1.88 | 53% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Laughter | 28 | 1.71 | — | 2.36 | 2.04 | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Backchanneling | 32 | 2.00 | 2.25 | — | 2.12 | 94% / — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Interruption | 8 | 1.38 | 1.12 | 1.88 | 1.46 | 12% / 5620 ms |
| Random baseline (mismatched partner) | AV2AV | Pause Handling | 13 | 2.00 | 2.23 | — | 2.12 | 77% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 15 | — | — | — | — | 93% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 16 | — | — | — | — | 0% / 22732 ms |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 23 | — | — | — | — | 13% / 4676 ms |

## Per dynamic with 95 % bootstrap CIs

| Model | Setting | dynamic_type | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | Laughter | 28 | 4.07 [3.57, 4.50] | — | 3.64 [3.21, 4.07] | 3.86 [3.39, 4.29] | — | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 32 | 5.00 [5.00, 5.00] | 4.06 [4.00, 4.19] | — | 4.53 [4.50, 4.59] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | Adaptor Handling | 13 | 1.46 [0.54, 2.46] | — | 4.23 [3.08, 5.00] | 2.85 [2.04, 3.58] | 92 [77, 100] | — |
| Random baseline (mismatched partner) | AV2AV | Emotion Matching | 13 | — | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Face Emotion Display | 48 | 1.08 [0.71, 1.46] | — | 2.42 [2.17, 2.75] | 1.75 [1.50, 2.00] | — | — |
| Random baseline (mismatched partner) | AV2AV | Gaze Avoidance with Pause | 17 | 1.59 [0.59, 2.65] | 2.18 [1.06, 3.29] | — | 1.88 [0.88, 2.85] | 53 [29, 76] | 0 [0, 50] |
| Random baseline (mismatched partner) | AV2AV | Laughter | 28 | 1.71 [0.86, 2.64] | — | 2.36 [2.07, 2.71] | 2.04 [1.50, 2.64] | — | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Backchanneling | 32 | 2.00 [1.12, 3.06] | 2.25 [1.44, 3.06] | — | 2.12 [1.28, 3.03] | 94 [81, 100] | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Interruption | 8 | 1.38 [0.24, 2.75] | 1.12 [0.24, 2.25] | 1.88 [1.12, 2.88] | 1.46 [0.58, 2.58] | 12 [0, 38] | 5620 [874, 18462] |
| Random baseline (mismatched partner) | AV2AV | Pause Handling | 13 | 2.00 [0.85, 3.46] | 2.23 [1.08, 3.62] | — | 2.12 [0.96, 3.54] | 77 [54, 100] | 0 [0, 30] |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 15 | — | — | — | — | 93 [80, 100] | 0 [0, 0] |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | 22732 [22732, 22732] |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 23 | — | — | — | — | 13 [0, 26] | 4676 [1188, 18772] |

## Notes (2026-10-16, NVIDIA test split baselines)

- **Human reference** is computable only on the 60 rows (30 clips) whose partner channel ships: Laughter and
  Nonverbal Backchanneling, perception + generation. 4.22 overall vs the paper's 4.20 (all dynamics).
- **Random baseline** (a mismatched partner channel played as the agent, drawn from another conversation that
  ships one) covers all 226 rows: 2.03 overall (Fluency 1.57 / Flow 2.06 / Grounding 2.73), TOR-Align 53 %
  with 0 ms median latency (the mismatched partner is usually already talking at the cue). Adaptor Handling
  grounding is 4.23 for random, as on the Seamless set: that rubric rewards not reacting, which a stranger's
  audio satisfies trivially; its fluency axis (1.46) does the discriminating.
- Judge gpt-4o, payload v2 with the generic per-dynamic cue; NVIDIA's captions, prompts, windows and ASR.
  Judge cost: human reference $0.38, random $1.33.
- Model rows for the test split are not run yet (≈1.5 h streaming, ≈$25 API, ≈$3 judge per the four configs).
