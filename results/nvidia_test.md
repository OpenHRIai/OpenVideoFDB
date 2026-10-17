# OpenVideoFDB summary

Runs: runs_nv/gt, runs_nv/random, runs_nv/gemini_live_av, runs_nv/gemini_live_a2a, runs_nv/openai_realtime_av, runs_nv/openai_realtime_a2a  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_test.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 60 | 4.57 | 4.06 | 3.64 | 4.22 | 100% / — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 226 | 1.57 | 2.06 | 2.73 | 2.03 | 53% / 0 ms |
| **Full-duplex speech-vision (AV2A)** | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | 226 | 2.72 | 3.28 | 3.22 | 3.00 | 57% / 1192 ms |
| OpenAI gpt-realtime | AV2A | 226 | 2.73 | 2.94 | 3.37 | 3.00 | 56% / 1412 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | |
| Gemini 3.1 Flash Live | A2A | 226 | 2.93 | 3.41 | 3.22 | 3.13 | 59% / 1172 ms |
| OpenAI gpt-realtime | A2A | 226 | 2.66 | 2.94 | 3.15 | 2.88 | 60% / 1108 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 60 | 4.57 [4.23, 4.80] | 4.06 [4.00, 4.19] | 3.64 [3.21, 4.07] | 4.22 [3.95, 4.43] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | 226 | 1.57 [1.24, 1.95] | 2.06 [1.48, 2.67] | 2.73 [2.37, 3.08] | 2.03 [1.72, 2.37] | 53 [44, 62] | 0 [0, 124] |
| Gemini 3.1 Flash Live | AV2A | 226 | 2.72 [2.31, 3.13] | 3.28 [2.72, 3.80] | 3.22 [2.85, 3.59] | 3.00 [2.66, 3.32] | 57 [49, 65] | 1192 [796, 1520] |
| OpenAI gpt-realtime | AV2A | 226 | 2.73 [2.32, 3.17] | 2.94 [2.46, 3.44] | 3.37 [2.93, 3.75] | 3.00 [2.66, 3.34] | 56 [48, 65] | 1412 [796, 2744] |
| Gemini 3.1 Flash Live | A2A | 226 | 2.93 [2.51, 3.34] | 3.41 [2.89, 3.91] | 3.22 [2.81, 3.58] | 3.13 [2.78, 3.48] | 59 [50, 67] | 1172 [716, 1460] |
| OpenAI gpt-realtime | A2A | 226 | 2.66 [2.24, 3.06] | 2.94 [2.44, 3.44] | 3.15 [2.68, 3.56] | 2.88 [2.52, 3.20] | 60 [52, 69] | 1108 [524, 1500] |

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
| **Full-duplex speech-vision (AV2A)** | | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | Adaptor Handling | 13 | 0.31 | — | 3.31 | 1.81 | 85% / — |
| Gemini 3.1 Flash Live | AV2A | Emotion Matching | 13 | — | — | — | — | — |
| Gemini 3.1 Flash Live | AV2A | Face Emotion Display | 48 | 2.71 | — | 3.12 | 2.92 | — |
| Gemini 3.1 Flash Live | AV2A | Gaze Avoidance with Pause | 17 | 2.94 | 3.18 | — | 3.06 | 82% / 0 ms |
| Gemini 3.1 Flash Live | AV2A | Laughter | 28 | 3.43 | — | 3.36 | 3.39 | — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Backchanneling | 32 | 2.31 | 2.81 | — | 2.56 | 50% / — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Interruption | 8 | 3.25 | 2.50 | 3.12 | 2.96 | 12% / 2996 ms |
| Gemini 3.1 Flash Live | AV2A | Pause Handling | 13 | 4.31 | 4.46 | — | 4.38 | 100% / 894 ms |
| Gemini 3.1 Flash Live | AV2A | Turn-taking | 15 | — | — | — | — | 100% / 1268 ms |
| Gemini 3.1 Flash Live | AV2A | Verbal Backchanneling | 16 | — | — | — | — | 0% / — |
| Gemini 3.1 Flash Live | AV2A | Verbal Interruption | 23 | — | — | — | — | 30% / 1180 ms |
| OpenAI gpt-realtime | AV2A | Adaptor Handling | 13 | 1.08 | — | 3.08 | 2.08 | 92% / — |
| OpenAI gpt-realtime | AV2A | Emotion Matching | 13 | — | — | — | — | — |
| OpenAI gpt-realtime | AV2A | Face Emotion Display | 48 | 3.21 | — | 3.75 | 3.48 | — |
| OpenAI gpt-realtime | AV2A | Gaze Avoidance with Pause | 17 | 2.65 | 3.29 | — | 2.97 | 82% / 0 ms |
| OpenAI gpt-realtime | AV2A | Laughter | 28 | 3.43 | — | 3.64 | 3.54 | — |
| OpenAI gpt-realtime | AV2A | Nonverbal Backchanneling | 32 | 2.75 | 2.94 | — | 2.84 | 62% / — |
| OpenAI gpt-realtime | AV2A | Nonverbal Interruption | 8 | 2.25 | 1.25 | 2.25 | 1.92 | 0% / 4564 ms |
| OpenAI gpt-realtime | AV2A | Pause Handling | 13 | 3.15 | 3.54 | — | 3.35 | 100% / 0 ms |
| OpenAI gpt-realtime | AV2A | Turn-taking | 15 | — | — | — | — | 100% / 1340 ms |
| OpenAI gpt-realtime | AV2A | Verbal Backchanneling | 16 | — | — | — | — | 0% / — |
| OpenAI gpt-realtime | AV2A | Verbal Interruption | 23 | — | — | — | — | 17% / 3468 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | | |
| Gemini 3.1 Flash Live | A2A | Adaptor Handling | 13 | 0.38 | — | 2.31 | 1.35 | 77% / — |
| Gemini 3.1 Flash Live | A2A | Emotion Matching | 13 | — | — | — | — | — |
| Gemini 3.1 Flash Live | A2A | Face Emotion Display | 48 | 3.04 | — | 3.62 | 3.33 | — |
| Gemini 3.1 Flash Live | A2A | Gaze Avoidance with Pause | 17 | 2.94 | 3.12 | — | 3.03 | 82% / 0 ms |
| Gemini 3.1 Flash Live | A2A | Laughter | 28 | 3.57 | — | 3.36 | 3.46 | — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Backchanneling | 32 | 2.81 | 3.38 | — | 3.09 | 50% / — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Interruption | 8 | 3.25 | 2.38 | 3.25 | 2.96 | 12% / 3092 ms |
| Gemini 3.1 Flash Live | A2A | Pause Handling | 13 | 4.54 | 4.46 | — | 4.50 | 100% / 990 ms |
| Gemini 3.1 Flash Live | A2A | Turn-taking | 15 | — | — | — | — | 100% / 1172 ms |
| Gemini 3.1 Flash Live | A2A | Verbal Backchanneling | 16 | — | — | — | — | 0% / — |
| Gemini 3.1 Flash Live | A2A | Verbal Interruption | 23 | — | — | — | — | 43% / 1204 ms |
| OpenAI gpt-realtime | A2A | Adaptor Handling | 13 | 0.85 | — | 2.69 | 1.77 | 85% / — |
| OpenAI gpt-realtime | A2A | Emotion Matching | 13 | — | — | — | — | — |
| OpenAI gpt-realtime | A2A | Face Emotion Display | 48 | 2.71 | — | 3.12 | 2.92 | — |
| OpenAI gpt-realtime | A2A | Gaze Avoidance with Pause | 17 | 2.47 | 3.06 | — | 2.76 | 82% / 0 ms |
| OpenAI gpt-realtime | A2A | Laughter | 28 | 4.14 | — | 3.79 | 3.96 | — |
| OpenAI gpt-realtime | A2A | Nonverbal Backchanneling | 32 | 3.31 | 3.44 | — | 3.38 | 69% / — |
| OpenAI gpt-realtime | A2A | Nonverbal Interruption | 8 | 2.75 | 1.75 | 2.88 | 2.46 | 25% / 1780 ms |
| OpenAI gpt-realtime | A2A | Pause Handling | 13 | 2.15 | 2.92 | — | 2.54 | 92% / 1328 ms |
| OpenAI gpt-realtime | A2A | Turn-taking | 15 | — | — | — | — | 100% / 884 ms |
| OpenAI gpt-realtime | A2A | Verbal Backchanneling | 16 | — | — | — | — | 0% / — |
| OpenAI gpt-realtime | A2A | Verbal Interruption | 23 | — | — | — | — | 35% / 2776 ms |

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
| Gemini 3.1 Flash Live | AV2A | Adaptor Handling | 13 | 0.31 [0.00, 0.77] | — | 3.31 [2.15, 4.46] | 1.81 [1.15, 2.54] | 85 [62, 100] | — |
| Gemini 3.1 Flash Live | AV2A | Emotion Matching | 13 | — | — | — | — | — | — |
| Gemini 3.1 Flash Live | AV2A | Face Emotion Display | 48 | 2.71 [2.08, 3.38] | — | 3.12 [2.71, 3.58] | 2.92 [2.46, 3.40] | — | — |
| Gemini 3.1 Flash Live | AV2A | Gaze Avoidance with Pause | 17 | 2.94 [1.76, 4.12] | 3.18 [2.18, 4.18] | — | 3.06 [1.97, 4.15] | 82 [65, 100] | 0 [0, 0] |
| Gemini 3.1 Flash Live | AV2A | Laughter | 28 | 3.43 [2.50, 4.36] | — | 3.36 [2.86, 3.86] | 3.39 [2.68, 4.11] | — | — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Backchanneling | 32 | 2.31 [1.06, 3.44] | 2.81 [1.81, 3.62] | — | 2.56 [1.62, 3.47] | 50 [25, 75] | — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Interruption | 8 | 3.25 [2.12, 4.25] | 2.50 [1.62, 3.25] | 3.12 [2.25, 3.75] | 2.96 [2.08, 3.58] | 12 [0, 38] | 2996 [820, 10708] |
| Gemini 3.1 Flash Live | AV2A | Pause Handling | 13 | 4.31 [3.31, 5.00] | 4.46 [3.54, 5.00] | — | 4.38 [3.46, 5.00] | 100 [100, 100] | 894 [0, 1788] |
| Gemini 3.1 Flash Live | AV2A | Turn-taking | 15 | — | — | — | — | 100 [100, 100] | 1268 [921, 2532] |
| Gemini 3.1 Flash Live | AV2A | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | — |
| Gemini 3.1 Flash Live | AV2A | Verbal Interruption | 23 | — | — | — | — | 30 [13, 48] | 1180 [716, 1580] |
| OpenAI gpt-realtime | AV2A | Adaptor Handling | 13 | 1.08 [0.00, 2.23] | — | 3.08 [1.92, 4.23] | 2.08 [1.15, 3.12] | 92 [77, 100] | — |
| OpenAI gpt-realtime | AV2A | Emotion Matching | 13 | — | — | — | — | — | — |
| OpenAI gpt-realtime | AV2A | Face Emotion Display | 48 | 3.21 [2.58, 3.75] | — | 3.75 [3.33, 4.12] | 3.48 [3.10, 3.81] | — | — |
| OpenAI gpt-realtime | AV2A | Gaze Avoidance with Pause | 17 | 2.65 [1.47, 3.82] | 3.29 [2.29, 4.29] | — | 2.97 [1.91, 4.03] | 82 [65, 100] | 0 [0, 1212] |
| OpenAI gpt-realtime | AV2A | Laughter | 28 | 3.43 [2.57, 4.14] | — | 3.64 [3.29, 4.00] | 3.54 [2.93, 4.04] | — | — |
| OpenAI gpt-realtime | AV2A | Nonverbal Backchanneling | 32 | 2.75 [1.62, 3.94] | 2.94 [2.12, 3.75] | — | 2.84 [1.91, 3.75] | 62 [38, 88] | — |
| OpenAI gpt-realtime | AV2A | Nonverbal Interruption | 8 | 2.25 [0.62, 3.75] | 1.25 [0.25, 2.25] | 2.25 [1.38, 3.25] | 1.92 [0.75, 3.00] | 0 [0, 0] | 4564 [1940, 8340] |
| OpenAI gpt-realtime | AV2A | Pause Handling | 13 | 3.15 [1.69, 4.31] | 3.54 [2.23, 4.54] | — | 3.35 [1.96, 4.39] | 100 [100, 100] | 0 [0, 3716] |
| OpenAI gpt-realtime | AV2A | Turn-taking | 15 | — | — | — | — | 100 [100, 100] | 1340 [396, 2212] |
| OpenAI gpt-realtime | AV2A | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | — |
| OpenAI gpt-realtime | AV2A | Verbal Interruption | 23 | — | — | — | — | 17 [4, 35] | 3468 [1428, 5676] |
| Gemini 3.1 Flash Live | A2A | Adaptor Handling | 13 | 0.38 [0.08, 0.77] | — | 2.31 [0.77, 3.46] | 1.35 [0.46, 2.15] | 77 [54, 100] | — |
| Gemini 3.1 Flash Live | A2A | Emotion Matching | 13 | — | — | — | — | — | — |
| Gemini 3.1 Flash Live | A2A | Face Emotion Display | 48 | 3.04 [2.46, 3.62] | — | 3.62 [3.25, 4.00] | 3.33 [2.90, 3.75] | — | — |
| Gemini 3.1 Flash Live | A2A | Gaze Avoidance with Pause | 17 | 2.94 [1.76, 4.12] | 3.12 [2.06, 4.18] | — | 3.03 [1.91, 4.15] | 82 [65, 100] | 0 [0, 0] |
| Gemini 3.1 Flash Live | A2A | Laughter | 28 | 3.57 [2.57, 4.43] | — | 3.36 [2.86, 3.79] | 3.46 [2.75, 4.07] | — | — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Backchanneling | 32 | 2.81 [1.69, 3.88] | 3.38 [2.50, 4.12] | — | 3.09 [2.22, 3.88] | 50 [25, 75] | — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Interruption | 8 | 3.25 [2.00, 4.38] | 2.38 [1.62, 3.00] | 3.25 [2.50, 3.88] | 2.96 [2.12, 3.54] | 12 [0, 38] | 3092 [660, 11156] |
| Gemini 3.1 Flash Live | A2A | Pause Handling | 13 | 4.54 [3.69, 5.00] | 4.46 [3.54, 5.00] | — | 4.50 [3.62, 5.00] | 100 [100, 100] | 990 [0, 1980] |
| Gemini 3.1 Flash Live | A2A | Turn-taking | 15 | — | — | — | — | 100 [100, 100] | 1172 [636, 1692] |
| Gemini 3.1 Flash Live | A2A | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | — |
| Gemini 3.1 Flash Live | A2A | Verbal Interruption | 23 | — | — | — | — | 43 [26, 65] | 1204 [912, 1472] |
| OpenAI gpt-realtime | A2A | Adaptor Handling | 13 | 0.85 [0.00, 1.92] | — | 2.69 [1.15, 3.85] | 1.77 [0.77, 2.77] | 85 [62, 100] | — |
| OpenAI gpt-realtime | A2A | Emotion Matching | 13 | — | — | — | — | — | — |
| OpenAI gpt-realtime | A2A | Face Emotion Display | 48 | 2.71 [2.08, 3.29] | — | 3.12 [2.50, 3.67] | 2.92 [2.38, 3.44] | — | — |
| OpenAI gpt-realtime | A2A | Gaze Avoidance with Pause | 17 | 2.47 [1.41, 3.53] | 3.06 [2.12, 4.00] | — | 2.76 [1.76, 3.79] | 82 [65, 100] | 0 [0, 1500] |
| OpenAI gpt-realtime | A2A | Laughter | 28 | 4.14 [3.57, 4.64] | — | 3.79 [3.50, 4.00] | 3.96 [3.61, 4.25] | — | — |
| OpenAI gpt-realtime | A2A | Nonverbal Backchanneling | 32 | 3.31 [2.12, 4.38] | 3.44 [2.62, 4.06] | — | 3.38 [2.44, 4.16] | 69 [44, 88] | — |
| OpenAI gpt-realtime | A2A | Nonverbal Interruption | 8 | 2.75 [1.38, 4.00] | 1.75 [0.75, 2.75] | 2.88 [1.75, 3.62] | 2.46 [1.25, 3.38] | 25 [0, 50] | 1780 [0, 8020] |
| OpenAI gpt-realtime | A2A | Pause Handling | 13 | 2.15 [0.92, 3.31] | 2.92 [1.77, 3.85] | — | 2.54 [1.38, 3.58] | 92 [77, 100] | 1328 [0, 1684] |
| OpenAI gpt-realtime | A2A | Turn-taking | 15 | — | — | — | — | 100 [100, 100] | 884 [0, 1524] |
| OpenAI gpt-realtime | A2A | Verbal Backchanneling | 16 | — | — | — | — | 0 [0, 0] | — |
| OpenAI gpt-realtime | A2A | Verbal Interruption | 23 | — | — | — | — | 35 [17, 57] | 2776 [524, 7412] |

## Notes (2026-10-16, NVIDIA test split, four API-model configurations)

- **Setup.** All 226 test rows (172 clips) streamed through Gemini 3.1 Flash Live (`gemini-3.1-flash-live-preview`)
  and OpenAI gpt-realtime, each in AV2A (frames at 1 fps + audio) and A2A (video withheld). Four runs in parallel,
  concurrency 2 each: 16:04–18:08 wall (one restart at 17:10, resumable). A single network drop at 16:39 cut six
  clip streams (all four providers at the same second); those run dirs were deleted and re-streamed. Max
  playback drift 6–34 ms per run. The only errors left in `run.json` are OpenAI's benign
  `conversation_already_has_active_response` on the text kick (4–6 clips per OpenAI run).
- **Scoring.** faster-whisper small.en + VAD segments, timing rules on the 121 timed rows, gpt-4o judge (payload v2,
  generic per-dynamic cue) on the 105 perception rows: 228 axis calls ≈ 450 k input / 23 k output tokens ≈ $1.35
  per run. Two clips ship without a caption (`[no caption available]` in the payload), as for the baselines.
- **Versus the project page (Table 1).** Overall: Gemini AV2A 3.00 (paper 2.84), Gemini A2A 3.13 (3.03), gpt-realtime
  AV2A 3.00 (2.75), gpt-realtime A2A 2.88 (2.97) — all within 0.25 and inside our bootstrap CIs. Axes: our Conv. Flow
  runs 0.4–1.1 higher than the paper's (Gemini AV2A 3.28 vs 2.20), our Fluency 0.4–0.5 lower for Gemini (2.72 vs 3.15
  AV2A, 2.93 vs 3.40 A2A) and equal for gpt-realtime; Vis. Grounding within ±0.4. Ranking by overall is the same as
  the paper's for the three pairs it determines (Gemini A2A > Gemini AV2A; Gemini AV2A ≥ gpt-realtime AV2A), except
  that gpt-realtime A2A < gpt-realtime AV2A here (2.88 vs 3.00) where the paper has 2.97 vs 2.75.
- **Visual-stream ignorance reproduces.** AV2A and A2A differ by 0.12–0.13 overall per model, with overlapping CIs
  (Gemini 3.00 vs 3.13, gpt-realtime 3.00 vs 2.88); Vis. Grounding is identical for Gemini (3.22 / 3.22) and 0.2 apart
  for gpt-realtime. Video in does not change what either agent says.
- **Timing.** TOR-Align 56–60 % here vs 66–72 % on the project page; random scores 53 %. Median latency 1.1–1.4 s for
  both models, vs 1.2–1.7 s (Gemini) and 4.4–5.4 s (gpt-realtime) in the paper. Our latency is the first audio chunk
  received after the window opens (provider-stamped, playback-queue placement, protocol §8); the paper's 4–5 s for
  gpt-realtime suggests a different onset definition or client. Per dynamic: Turn-taking 100 % for all four
  (random 93 %: the rule is easy when the user stops), Pause Handling 92–100 %, Verbal Interruption 17–43 %
  (the agents rarely yield within the window), Nonverbal Interruption 0–25 % on n = 8, Verbal Backchanneling 0 % for
  every run including random: no agent produces a ≤ 2-word backchannel inside the 1 s window; they stay silent through
  the user's story and answer afterwards. Adaptor Handling TOR 77–92 % with fluency 0.3–1.1: the judge
  penalises any reaction to the fidget, which the timing rule does not.
- **Per dynamic highlights.** Pause Handling is Gemini's best cell (4.38 AV2A / 4.50 A2A) and gpt-realtime's weakest
  judged cell (3.35 / 2.54); Laughter is gpt-realtime's best (3.54 / 3.96, human 3.86). Face Emotion Display (48
  rows) sits at 2.9–3.5 for all four.
- **Known caveats carried over** (`STATUS.md`, `docs/protocol.md` §10): stay-silent rules pass an agent that talks
  through the window; continue-speaking passes vacuously when the agent was silent before it; the judge sees
  the generic cue line, not clip-specific evidence; the human reference exists only for the 60 rows with a
  shipped partner channel. Generation (video-out) judge not run — the Generation table of the project page has
  no counterpart here.
