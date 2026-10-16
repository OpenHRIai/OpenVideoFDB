# OpenVideoFDB summary

Runs: runs_nv/gt  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_test_gt.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 60 | 4.57 | 4.06 | 3.64 | 4.22 | 100% / — |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 60 | 4.57 [4.23, 4.80] | 4.06 [4.00, 4.19] | 3.64 [3.21, 4.07] | 4.22 [3.95, 4.43] | 100 [100, 100] | — |

## Per dynamic

| Model | Setting | dynamic_type | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | | |
| Human reference | AV2AV | Laughter | 28 | 4.07 | — | 3.64 | 3.86 | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 32 | 5.00 | 4.06 | — | 4.53 | 100% / — |

## Per dynamic with 95 % bootstrap CIs

| Model | Setting | dynamic_type | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | Laughter | 28 | 4.07 [3.57, 4.50] | — | 3.64 [3.21, 4.07] | 3.86 [3.39, 4.29] | — | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 32 | 5.00 [5.00, 5.00] | 4.06 [4.00, 4.19] | — | 4.53 [4.50, 4.59] | 100 [100, 100] | — |

## Notes (2026-10-16)

- Human reference on the NVIDIA **test** split: the partner channel ships only for the 30 dual-bucket clips
  (Laughter and Nonverbal Backchanneling, perception + generation = 60 rows); for all other dynamics the paper's
  human numbers are the only reference. Judge = gpt-4o, payload v2 with the generic per-dynamic cue
  (NVIDIA rows carry no mining evidence), NVIDIA's own captions, prompts, windows and word-level ASR.
- Per-category comparison with the paper's Table 11 (human reference, perception): Laughter **3.86 vs 3.86**,
  Nonverbal Backchanneling **4.53 vs 4.12**. Timing: Nonverbal Backchanneling 100 % (continue-speaking).
  Before the generic cue line, Laughter was 3.11: the judge read the human partner's continued talking
  through the user's laugh as "monologue, not engaging" and gave fluency 1 on 4 of 14 rows.
- Caveat: these two dynamics are the ones where the paper's human reference is itself lowest on fluency
  context; the overall 4.16 / 4.20 / 4.24 of the paper spans all seven perception dynamics.
