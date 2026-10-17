# OpenVideoFDB summary

Runs: runs_nv/gt, runs_nv/random, runs_nv/tavus_av2av  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_test.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 60 | 4.57 | 4.06 | 3.64 | 4.22 | 100% / — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 226 | 1.57 | 2.06 | 2.73 | 2.03 | 53% / 0 ms |
| **Full-duplex AV2AV avatars** | | | | | | | |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | 145 | — | — | — | — | 31% / 1956 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 60 | 4.57 [4.23, 4.80] | 4.06 [4.00, 4.19] | 3.64 [3.21, 4.07] | 4.22 [3.95, 4.43] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | 226 | 1.57 [1.24, 1.95] | 2.06 [1.48, 2.67] | 2.73 [2.37, 3.08] | 2.03 [1.72, 2.37] | 53 [44, 62] | 0 [0, 124] |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | 145 | — | — | — | — | 31 [20, 44] | 1956 [1716, 2252] |

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
| **Full-duplex AV2AV avatars** | | | | | | | | |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Emotion Matching | 13 | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Face Emotion Display | 48 | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Laughter | 14 | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Nonverbal Backchanneling | 16 | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Turn-taking | 15 | — | — | — | — | 100% / 1876 ms |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Backchanneling | 16 | — | — | — | — | 0% / — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Interruption | 23 | — | — | — | — | 9% / 2180 ms |

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
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Emotion Matching | 13 | — | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Face Emotion Display | 48 | — | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Laughter | 14 | — | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Nonverbal Backchanneling | 16 | — | — | — | — | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Turn-taking | 15 | — | — | — | — | 100 [100, 100] | 1876 [1524, 2228] |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Interruption | 23 | — | — | — | — | 9 [0, 22] | 2180 [1708, 2572] |

# Generation

Generation-bucket rows only (project page Table 2): Fluency = Generation Fluency, Dyadic Affect = Affect Match, NV Cue Approp. = cue_appropriateness of the per-category decomposed rubric (vision judge on side-by-side frames, docs/protocol.md §6). Overall = mean of each generation row's available axes. Timing = TOR-Align % / median latency over the timed generation rows (Verbal Interruption, Turn-taking, Verbal Backchanneling); Laughter / Nonverbal Backchanneling / affect rows have no timing class. n = generation rows present in the run (timing and/or judge); the CI table's per-axis n is in the CSV.

| Model | Setting | n | Fluency ↑ | Dyadic Affect ↑ | NV Cue Approp. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 30 | 4.17 | 3.30 | 3.00 | 3.49 | — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 121 | 2.17 | 1.77 | 0.97 | 1.63 | 31% / 0 ms |
| **Full-duplex AV2AV avatars** | | | | | | | |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | 121 | 3.79 | 2.30 | 1.65 | 2.63 | 31% / 1956 ms |

## Generation with 95 % bootstrap CIs

| Model | Setting | n | Fluency | Dyadic Affect | NV Cue Approp. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 30 | 4.17 [3.70, 4.53] | 3.30 [2.67, 3.93] | 3.00 [2.13, 3.87] | 3.49 [3.09, 3.88] | — | — |
| Random baseline (mismatched partner) | AV2AV | 121 | 2.17 [1.40, 2.97] | 1.77 [1.33, 2.33] | 0.97 [0.33, 1.73] | 1.63 [1.19, 2.12] | 31 [19, 44] | 0 [0, 3428] |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | 121 | 3.79 [3.48, 4.06] | 2.30 [1.99, 2.65] | 1.65 [1.22, 2.05] | 2.63 [2.36, 2.89] | 31 [20, 44] | 1956 [1716, 2252] |

## Generation per dynamic

| Model | Setting | dynamic_type | n | Fluency ↑ | Dyadic Affect ↑ | NV Cue Approp. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | | |
| Human reference | AV2AV | Laughter | 14 | 4.07 | 2.79 | 3.50 | 3.45 | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 16 | 4.25 | 3.75 | 2.56 | 3.52 | — |
| **Random baseline** | | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | Emotion Matching | 13 | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Face Emotion Display | 24 | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Laughter | 14 | 2.21 | 1.29 | 0.64 | 1.38 | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Backchanneling | 16 | 2.12 | 2.19 | 1.25 | 1.85 | — |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 15 | — | — | — | — | 93% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 16 | — | — | — | — | 0% / 22732 ms |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 23 | — | — | — | — | 13% / 4676 ms |
| **Full-duplex AV2AV avatars** | | | | | | | | |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Emotion Matching | 13 | 3.85 | 2.31 | 1.54 | 2.56 | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Face Emotion Display | 24 | 3.88 | 2.33 | 1.67 | 2.62 | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Laughter | 14 | 3.71 | 1.00 | 0.00 | 1.57 | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Nonverbal Backchanneling | 16 | 4.81 | 3.75 | 0.00 | 2.85 | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Turn-taking | 15 | 3.73 | — | 3.07 | 3.40 | 100% / 1876 ms |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Backchanneling | 16 | 1.88 | 1.06 | 0.31 | 1.08 | 0% / — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Interruption | 23 | 4.35 | 2.91 | 3.87 | 3.71 | 9% / 2180 ms |

## Generation per dynamic with 95 % bootstrap CIs

| Model | Setting | dynamic_type | n | Fluency | Dyadic Affect | NV Cue Approp. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | Laughter | 14 | 4.07 [3.43, 4.64] | 2.79 [1.93, 3.71] | 3.50 [2.36, 4.57] | 3.45 [2.79, 4.07] | — | — |
| Human reference | AV2AV | Nonverbal Backchanneling | 16 | 4.25 [3.62, 4.75] | 3.75 [2.94, 4.56] | 2.56 [1.44, 3.69] | 3.52 [3.06, 3.98] | — | — |
| Random baseline (mismatched partner) | AV2AV | Emotion Matching | 13 | — | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Face Emotion Display | 24 | — | — | — | — | — | — |
| Random baseline (mismatched partner) | AV2AV | Laughter | 14 | 2.21 [1.14, 3.36] | 1.29 [1.00, 1.57] | 0.64 [0.00, 1.57] | 1.38 [0.90, 1.86] | — | — |
| Random baseline (mismatched partner) | AV2AV | Nonverbal Backchanneling | 16 | 2.12 [1.06, 3.19] | 2.19 [1.44, 3.00] | 1.25 [0.31, 2.19] | 1.85 [1.12, 2.60] | — | — |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 15 | — | — | — | — | 93 [80, 100] | 0 [0, 0] |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | 22732 [22732, 22732] |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 23 | — | — | — | — | 13 [0, 26] | 4676 [1188, 18772] |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Emotion Matching | 13 | 3.85 [2.77, 4.77] | 2.31 [1.38, 3.31] | 1.54 [0.38, 2.69] | 2.56 [1.72, 3.46] | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Face Emotion Display | 24 | 3.88 [3.21, 4.42] | 2.33 [1.67, 3.04] | 1.67 [0.83, 2.71] | 2.62 [2.21, 3.10] | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Laughter | 14 | 3.71 [2.93, 4.50] | 1.00 [1.00, 1.00] | 0.00 [0.00, 0.00] | 1.57 [1.31, 1.83] | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Nonverbal Backchanneling | 16 | 4.81 [4.56, 5.00] | 3.75 [2.88, 4.50] | 0.00 [0.00, 0.00] | 2.85 [2.54, 3.15] | — | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Turn-taking | 15 | 3.73 [3.00, 4.40] | — | 3.07 [1.87, 4.20] | 3.40 [2.50, 4.23] | 100 [100, 100] | 1876 [1524, 2228] |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Backchanneling | 16 | 1.88 [0.81, 3.00] | 1.06 [1.00, 1.19] | 0.31 [0.00, 0.94] | 1.08 [0.62, 1.62] | 0 [0, 0] | — |
| Tavus CVI (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Interruption | 23 | 4.35 [3.96, 4.70] | 2.91 [2.04, 3.78] | 3.87 [3.13, 4.48] | 3.71 [3.16, 4.28] | 9 [0, 22] | 2180 [1708, 2572] |

## Notes (2026-10-16/17, NVIDIA test split, generation bucket: human reference, random, Tavus CVI)

- **What this is.** The project page's Table 2 (video-out agents) reproduced with the WS6c vision judge
  (gpt-4o, side-by-side frames USER|AGENT at 8 fps, ≤ 500 frames, 256 px wide, plus the audio-side text block;
  rubrics verbatim from the paper's F.6) on the 121 generation-bucket rows. Overall = mean of Generation Fluency,
  Affect Match ("Dyadic Affect") and the per-category cue_appropriateness ("NV Cue Approp."). Timing reuses the
  audio TOR rules on the three generation dynamics that carry a timing class.
- **Human reference** exists for the 30 rows whose partner video ships (14 Laughter, 16 Nonverbal Backchanneling):
  4.17 / 3.30 / 3.00 / 3.49 vs the paper's 4.42 / 4.14 / 3.18 / 3.92 on all rows. Affect Match is the low axis. A
  512 px frame ablation gives 4.17 / 3.20 / 2.83 / 3.40, so pane size is not the cause; the paper additionally feeds
  the judge a Qwen visual caption and a Nemotron audio caption of the agent output, which we do not have (payload
  says "[not available]"; see docs/protocol.md §10). Random (mismatched partner video) scores 1.63 overall.
- **Tavus CVI** = Tavus's hosted conversational pipeline (STT → tavus-gemma-4 → TTS → Phoenix-4.5 lip-synced stock
  replica "Helen - Casual", Raven-1 perception on the user's camera), driven through headless Chrome with the clip
  as the user's camera+mic (`harness/providers/playwright_avatar.py`). It is *not* the paper's Tavus Griffin Lite
  (full-duplex AV2AV model, 3.83 overall); the comparable project-page rows are the cascaded avatars
  (Gemini 2.5 + Anam 2.80, Gemini 2.5 + Keyframe 2.39). Ours: **3.79 / 2.30 / 1.65 / 2.63**, TOR-Align 31 % /
  1956 ms (paper cascaded: 44 % / 2840 ms and 31 % / 3520 ms; Griffin Lite 62.8 % / 1892 ms; human 78 % / 900 ms).
- **Reading the per-dynamic rows.** Fluency is high wherever the pipeline just has to yield cleanly (Nonverbal
  Backchanneling 4.81, Verbal Interruption 4.35) and collapses on Verbal Backchanneling (1.88): the replica waits for
  a full turn boundary and never produces an "mhm" inside the user's story (TOR 0 %), then answers at length. The
  visual channel is flat: cue_appropriateness is 0.00 on all 14 Laughter and all 16 Nonverbal Backchanneling rows
  (no laugh, nod or smile inside any window; cue produced 36 % overall, mostly verbal cues on Verbal Interruption
  and Turn-taking), and Affect Match on Laughter is 1.00 — the rubric's "stone face + warm voice" case. This is the
  paper's "cascaded avatars cannot insert nonverbal cues during the user's turn" finding, reproduced on a different
  vendor pipeline. Turn-taking TOR 100 % / 1876 ms; Verbal Interruption 9 % (the replica rarely yields within the
  window; median 2.2 s to stop).
- **Run facts.** 121 rows, concurrency 1, 16:04–21:50 wall across two resumptions (session restarts), one 1006
  network drop re-streamed, two page-connection losses re-streamed, one webm with a mid-call resolution change
  (now normalised in the converter). Max playback drift 25 ms except three rows (0.3–9.2 s) where CPU-heavy
  scoring ran concurrently; their `agent.wav` was rebuilt from the mp4's audio track (page clock), and the streamer
  now trusts the page clock for avatar providers. Tavus billed ≈ clip + 19 s per row (≈ 145 min); the judge cost
  ≈ $0.26/row ($32 for the run). Rows where the replica never spoke: 5 (user talked through the whole clip).
- **Anam** (A2AV, stock Cara-4 "Mia" + Anam-hosted Gemini 3 Flash): harness works (the page overrides
  `getUserMedia` so the SDK's microphone is the clip; without that Anam hears silence), but the free plan's 30 min
  were exhausted after 1 valid row; resumable once the plan is upgraded (`runs_nv/anam_a2av`).
- **Not scored:** the paper's "Dyadic Affect" and "NV Cue" rely on captions we do not generate; rendering quality,
  lip-sync and realism are out of scope by the rubric's own preamble.
