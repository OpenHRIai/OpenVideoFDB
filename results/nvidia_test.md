# OpenVideoFDB summary

Runs: runs_nv/gt, runs_nv/random, runs_nv/gemini_live_av, runs_nv/gemini_live_a2a, runs_nv/openai_realtime_av, runs_nv/openai_realtime_a2a, runs_nv/tavus_av2av, runs_nv/anam_a2av, runs_nv/heygen_a2av  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_test.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0). Runs scored only by the generation judge (anam_a2av, heygen_a2av, tavus_av2av) are listed in the Generation tables only.

# Perception (project page Table 1)

All rows of each run scored with the perception rubrics (Fluency, Conversational Flow, Semantic/Visual Grounding; text judge on the agent's audio and transcript), so audio-out agents are included; Timing covers every timed row.

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

# Generation (project page Table 2)

Generation-bucket rows only (project page Table 2): Fluency = Generation Fluency, Dyadic Affect = Affect Match, NV Cue Approp. = cue_appropriateness of the per-category decomposed rubric (vision judge on side-by-side frames, docs/protocol.md §6). Overall = mean of each generation row's available axes. Timing = TOR-Align % / median latency over the timed generation rows (Verbal Interruption, Turn-taking, Verbal Backchanneling); Laughter / Nonverbal Backchanneling / affect rows have no timing class. n = generation rows present in the run (timing and/or judge); the CI table's per-axis n is in the CSV. Runs without generation judge scores (gemini_live_a2a, gemini_live_av, openai_realtime_a2a, openai_realtime_av) are not listed here.

| Model | Setting | n | Fluency ↑ | Dyadic Affect ↑ | NV Cue Approp. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 30 | 4.17 | 3.30 | 3.00 | 3.49 | — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 121 | 2.17 | 1.77 | 0.97 | 1.63 | 31% / 0 ms |
| **Avatars with video in (AV2AV; full-duplex or cascaded, see model name)** | | | | | | | |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | 121 | 3.79 | 2.30 | 1.65 | 2.63 | 31% / 1956 ms |
| **Cascaded speech-to-avatar (A2AV)** | | | | | | | |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | 121 | 3.41 | 1.51 | 1.26 | 2.15 | 44% / 2092 ms |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | 121 | 4.16 | 2.33 | 1.52 | 2.74 | 39% / 1800 ms |

## Generation with 95 % bootstrap CIs

| Model | Setting | n | Fluency | Dyadic Affect | NV Cue Approp. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 30 | 4.17 [3.70, 4.53] | 3.30 [2.67, 3.93] | 3.00 [2.13, 3.87] | 3.49 [3.09, 3.88] | — | — |
| Random baseline (mismatched partner) | AV2AV | 121 | 2.17 [1.40, 2.97] | 1.77 [1.33, 2.33] | 0.97 [0.33, 1.73] | 1.63 [1.19, 2.12] | 31 [19, 44] | 0 [0, 3428] |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | 121 | 3.79 [3.48, 4.06] | 2.30 [1.99, 2.65] | 1.65 [1.22, 2.05] | 2.63 [2.36, 2.89] | 31 [20, 44] | 1956 [1716, 2252] |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | 121 | 3.41 [3.11, 3.69] | 1.51 [1.33, 1.74] | 1.26 [0.88, 1.63] | 2.15 [1.90, 2.41] | 44 [31, 57] | 2092 [1364, 4348] |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | 121 | 4.16 [3.88, 4.38] | 2.33 [2.01, 2.67] | 1.52 [1.15, 1.92] | 2.74 [2.49, 2.98] | 39 [26, 52] | 1800 [1224, 2060] |

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
| **Avatars with video in (AV2AV; full-duplex or cascaded, see model name)** | | | | | | | | |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Emotion Matching | 13 | 3.85 | 2.31 | 1.54 | 2.56 | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Face Emotion Display | 24 | 3.88 | 2.33 | 1.67 | 2.62 | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Laughter | 14 | 3.71 | 1.00 | 0.00 | 1.57 | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Nonverbal Backchanneling | 16 | 4.81 | 3.75 | 0.00 | 2.85 | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Turn-taking | 15 | 3.73 | — | 3.07 | 3.40 | 100% / 1876 ms |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Backchanneling | 16 | 1.88 | 1.06 | 0.31 | 1.08 | 0% / — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Interruption | 23 | 4.35 | 2.91 | 3.87 | 3.71 | 9% / 2180 ms |
| **Cascaded speech-to-avatar (A2AV)** | | | | | | | | |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Emotion Matching | 13 | 4.08 | 1.62 | 0.38 | 2.03 | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Face Emotion Display | 24 | 3.83 | 1.58 | 0.42 | 1.94 | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Laughter | 14 | 2.43 | 1.00 | 0.00 | 1.14 | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Nonverbal Backchanneling | 16 | 3.12 | 1.19 | 0.00 | 1.44 | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Turn-taking | 15 | 4.33 | — | 3.20 | 3.77 | 100% / 5148 ms |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Verbal Backchanneling | 16 | 1.25 | 1.12 | 0.31 | 0.90 | 0% / — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Verbal Interruption | 23 | 4.30 | 2.17 | 3.65 | 3.38 | 39% / 1400 ms |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Emotion Matching | 13 | 4.69 | 1.92 | 1.00 | 2.54 | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Face Emotion Display | 24 | 4.21 | 2.38 | 0.83 | 2.47 | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Laughter | 14 | 3.57 | 1.00 | 0.36 | 1.64 | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Nonverbal Backchanneling | 16 | 5.00 | 4.00 | 0.31 | 3.10 | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Turn-taking | 15 | 4.67 | — | 3.53 | 4.10 | 100% / 1876 ms |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Verbal Backchanneling | 16 | 2.19 | 1.25 | 0.00 | 1.15 | 0% / — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Verbal Interruption | 23 | 4.61 | 2.91 | 3.83 | 3.78 | 26% / 1532 ms |

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
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Emotion Matching | 13 | 3.85 [2.77, 4.77] | 2.31 [1.38, 3.31] | 1.54 [0.38, 2.69] | 2.56 [1.72, 3.46] | — | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Face Emotion Display | 24 | 3.88 [3.21, 4.42] | 2.33 [1.67, 3.04] | 1.67 [0.83, 2.71] | 2.62 [2.21, 3.10] | — | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Laughter | 14 | 3.71 [2.93, 4.50] | 1.00 [1.00, 1.00] | 0.00 [0.00, 0.00] | 1.57 [1.31, 1.83] | — | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Nonverbal Backchanneling | 16 | 4.81 [4.56, 5.00] | 3.75 [2.88, 4.50] | 0.00 [0.00, 0.00] | 2.85 [2.54, 3.15] | — | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Turn-taking | 15 | 3.73 [3.00, 4.40] | — | 3.07 [1.87, 4.20] | 3.40 [2.50, 4.23] | 100 [100, 100] | 1876 [1524, 2228] |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Backchanneling | 16 | 1.88 [0.81, 3.00] | 1.06 [1.00, 1.19] | 0.31 [0.00, 0.94] | 1.08 [0.62, 1.62] | 0 [0, 0] | — |
| Tavus CVI, cascaded (Phoenix-4.5, tavus-gemma-4) | AV2AV | Verbal Interruption | 23 | 4.35 [3.96, 4.70] | 2.91 [2.04, 3.78] | 3.87 [3.13, 4.48] | 3.71 [3.16, 4.28] | 9 [0, 22] | 2180 [1708, 2572] |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Emotion Matching | 13 | 4.08 [3.38, 4.69] | 1.62 [1.31, 1.92] | 0.38 [0.00, 1.15] | 2.03 [1.69, 2.38] | — | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Face Emotion Display | 24 | 3.83 [3.38, 4.21] | 1.58 [1.33, 1.88] | 0.42 [0.00, 1.04] | 1.94 [1.69, 2.24] | — | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Laughter | 14 | 2.43 [1.57, 3.36] | 1.00 [1.00, 1.00] | 0.00 [0.00, 0.00] | 1.14 [0.86, 1.45] | — | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Nonverbal Backchanneling | 16 | 3.12 [2.38, 3.75] | 1.19 [1.00, 1.50] | 0.00 [0.00, 0.00] | 1.44 [1.15, 1.71] | — | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Turn-taking | 15 | 4.33 [3.93, 4.73] | — | 3.20 [2.07, 4.20] | 3.77 [3.03, 4.40] | 100 [100, 100] | 5148 [4148, 6164] |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Verbal Backchanneling | 16 | 1.25 [0.38, 2.13] | 1.12 [1.00, 1.38] | 0.31 [0.00, 0.94] | 0.90 [0.50, 1.31] | 0 [0, 0] | — |
| Anam, cascaded (Cara-4, Gemini 3 Flash) | A2AV | Verbal Interruption | 23 | 4.30 [4.09, 4.52] | 2.17 [1.48, 2.92] | 3.65 [3.09, 4.26] | 3.38 [2.96, 3.88] | 39 [17, 61] | 1400 [1156, 1852] |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Emotion Matching | 13 | 4.69 [4.23, 5.00] | 1.92 [1.31, 2.77] | 1.00 [0.00, 2.15] | 2.54 [2.05, 3.13] | — | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Face Emotion Display | 24 | 4.21 [3.67, 4.62] | 2.38 [1.79, 3.00] | 0.83 [0.21, 1.67] | 2.47 [2.08, 2.88] | — | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Laughter | 14 | 3.57 [2.71, 4.36] | 1.00 [1.00, 1.00] | 0.36 [0.00, 1.07] | 1.64 [1.31, 2.02] | — | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Nonverbal Backchanneling | 16 | 5.00 [5.00, 5.00] | 4.00 [3.25, 4.75] | 0.31 [0.00, 0.94] | 3.10 [2.75, 3.48] | — | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Turn-taking | 15 | 4.67 [4.40, 4.87] | — | 3.53 [2.47, 4.53] | 4.10 [3.50, 4.67] | 100 [100, 100] | 1876 [796, 2780] |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Verbal Backchanneling | 16 | 2.19 [1.19, 3.12] | 1.25 [1.00, 1.75] | 0.00 [0.00, 0.00] | 1.15 [0.81, 1.46] | 0 [0, 0] | — |
| HeyGen LiveAvatar, cascaded (Helen, gpt-5.4-nano) | A2AV | Verbal Interruption | 23 | 4.61 [4.43, 4.83] | 2.91 [2.04, 3.78] | 3.83 [3.13, 4.48] | 3.78 [3.28, 4.28] | 26 [9, 43] | 1532 [1092, 1932] |

## Notes — perception (2026-10-16, NVIDIA test split, four API-model configurations)

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

## Notes — generation (2026-10-17, NVIDIA test split, generation bucket: human reference, random, Tavus CVI, Anam, HeyGen)

- **What this is.** The project page's Table 2 (video-out agents) reproduced with the WS6c vision judge
  (gpt-4o, side-by-side frames USER|AGENT at 8 fps, ≤ 500 frames, 256 px wide, plus the audio-side text block;
  rubrics verbatim from the paper's F.6) on the 121 generation-bucket rows. Overall = mean of Generation Fluency,
  Affect Match ("Dyadic Affect") and the per-category cue_appropriateness ("NV Cue Approp."). Timing reuses the
  audio TOR rules on the three generation dynamics that carry a timing class (VI, TT, VB; 54 rows).
- **Human reference** exists for the 30 rows whose partner video ships (14 Laughter, 16 Nonverbal Backchanneling):
  4.17 / 3.30 / 3.00 / 3.49 vs the paper's 4.42 / 4.14 / 3.18 / 3.92 on all rows. Affect Match is the low axis for
  every configuration here (human −0.8, Anam −1.7 vs the paper), so it is a judge-side offset: a 512 px frame
  ablation gives 4.17 / 3.20 / 2.83 / 3.40 (pane size is not the cause); the paper additionally feeds the judge a
  Qwen visual caption and a Nemotron audio caption of the agent output, which we do not generate (payload says
  "[not available]"; docs/protocol.md §10). Random (mismatched partner video) scores 1.63 overall.
- **All three avatars are cascaded pipelines driven through headless Chrome** with the clip as the user's camera+mic
  (`harness/providers/playwright_avatar.py`, `harness/web/avatar.html`):
  *Tavus CVI* = STT → tavus-gemma-4 → TTS → Phoenix-4.5 lip-synced stock replica "Helen - Casual", Raven-1
  perception on the user's camera (so AV2AV). It is *not* the paper's Tavus Griffin Lite (full-duplex, 3.83).
  *Anam* = Anam's hosted pipeline (STT → Gemini 3 Flash → Anam TTS → Cara-4 stock avatar "Mia"), audio-only
  input (A2AV); the paper's closest row is "Gemini 2.5 + Anam" (Gemini Live audio driving the Anam renderer,
  2.80 overall, 44 % / 2840 ms).
  *HeyGen* = LiveAvatar FULL mode (LiveAvatar-hosted STT → gpt-5.4-nano, the managed default → avatar's default
  voice → stock avatar "Helen (Friendly)"), joined over LiveKit with the clip's audio published as the user's mic;
  no video in (A2AV). The row's system prompt goes in through one stored context (`${system_prompt}` dynamic
  variable); agent-speaks-first rows get an `avatar.speak_response` kick at t = 0 (first audio median 1.6 s).
- **Results.** HeyGen **4.16 / 2.33 / 1.52 / 2.74**, TOR 39 % / 1800 ms; Tavus CVI **3.79 / 2.30 / 1.65 / 2.63**,
  TOR 31 % / 1956 ms; Anam **3.41 / 1.51 / 1.26 / 2.15**, TOR 44 % / 2092 ms. Against the paper's cascaded rows (2.80 and 2.39 overall; 44 % / 2840 and 31 % / 3520 ms)
  the fluency, cue and timing numbers line up (Anam fluency 3.41 vs 3.48, NV cue 1.26 vs 1.71, TOR 44 % vs 44 %)
  and the overall gap is the Affect Match offset above. **No overall winner between HeyGen and Tavus CVI**: paired
  bootstrap over the same 121 rows (10 000 resamples, seed 0; two-sided p from the bootstrap distribution):

  | Pair | Fluency | Dyadic Affect | NV Cue | Overall |
  |---|---|---|---|---|
  | HeyGen − Tavus CVI | **+0.37 [+0.11, +0.64]** | +0.03 [−0.31, +0.36] | −0.13 [−0.48, +0.21] | +0.12 [−0.12, +0.35] |
  | HeyGen − Anam | **+0.74 [+0.50, +1.00]** | **+0.82 [+0.47, +1.16]** | +0.26 [−0.11, +0.64] | **+0.59 [+0.37, +0.81]** |
  | Tavus CVI − Anam | +0.37 [+0.07, +0.68] | **+0.79 [+0.44, +1.15]** | +0.40 [+0.05, +0.76] | **+0.47 [+0.23, +0.71]** |

  Bold = survives Holm correction over the 12 comparisons (α = 0.05). Defensible reading: HeyGen ≈ Tavus CVI >
  Anam > random overall, HeyGen more fluent than Tavus CVI, human reference above all three. The CIs cover row
  sampling only — one judge (gpt-4o), one run per vendor, and the configurations differ in more than the vendor
  (Tavus sees the user's camera; each uses its own stock avatar and LLM), so this ranks these configurations, not
  the vendors' products.
- **Per dynamic.** Fluency is high wherever the pipeline just has to yield cleanly (Tavus NVB 4.81, both ≥ 4.3 on
  Verbal Interruption and Turn-taking) and collapses on Verbal Backchanneling (1.88 / 1.25): both wait for a full
  turn boundary, never say "mhm" inside the user's story (TOR 0 %), then answer at length. The visual channel is
  flat on both: cue_appropriateness 0.00 on all 14 Laughter and all 16 Nonverbal Backchanneling rows (no laugh,
  nod or smile inside any window — a contact sheet of the same laughter window shows the user and the human
  partner laughing while both avatars hold a neutral face), Affect Match on Laughter 1.00 = the rubric's
  "stone face + warm voice" case. Cue produced 36 % (Tavus) / 31 % (Anam), almost all verbal cues on Verbal
  Interruption and Turn-taking. This is the paper's "cascaded avatars cannot insert nonverbal cues during the
  user's turn" finding, reproduced on two vendor pipelines. HeyGen is the same story: Verbal Backchanneling
  2.19 / TOR 0 %, and on Laughter and Nonverbal Backchanneling exactly one row each scores a cue (a broad smile
  inside the window, rated 5); the other 28 rows are 0 — NV cue 0.36 / 0.31 is one smile, not a behaviour. Its
  advantage is conversational: Turn-taking fluency 4.67 (cue 3.53) and Verbal Interruption 4.61 / 3.83, with
  Turn-taking latency 1.9 s and Verbal Interruption TOR 26 % / 1532 ms. Cue produced: 34 % of rows. Anam's Turn-taking latency (5.1 s median) is its
  STT→LLM→TTS→render chain; Tavus's 1.9 s is Tavus's speculative pipeline.
- **Run facts.** Tavus: 121 rows, concurrency 1, 16:04–21:50 wall across two resumptions, one 1006 network drop
  and two page-connection losses re-streamed, one webm with a mid-call resolution change (converter now
  normalises); three rows with streamer drift 0.3–9.2 s (CPU-heavy scoring ran alongside) had `agent.wav` rebuilt
  from the mp4's audio track; the streamer now trusts the page clock for avatar providers. Tavus billed ≈ clip +
  19 s per row (≈ 145 min). Anam: 121 rows over five free-tier keys (30 min each) in three parallel shards,
  23:40–00:55; Anam billed ≈ clip + 10 s per row (≈ 125 min); the SDK ignores a custom MediaStream unless
  `getUserMedia` is overridden (verified per row by input track id — the first attempt without it produced an
  avatar monologuing "it's been quiet"); "Concurrency limit" right after a session close is transient (retried
  after 25 s). Max playback drift 170 ms. Rows where the avatar never spoke: 5 (Tavus) / 14 (Anam) — the user
  talked through the whole clip. HeyGen: 121 rows, concurrency 1, 09:48–12:35 wall (two stops when the
  machine ran out of memory — a separate ONNX quantization job, not the harness; harness Chrome held ≈ 0.6–1.3 GB
  per row), over three LiveAvatar keys (`scripts/run_avatar_keys.py`; free/trial keys cap sessions at 120 s, which
  the harness absorbs for clips ≤ 105 s) and overage on the first; FULL mode bills 2 credits/min, ≈ 2.1 credits
  per row (≈ 260 credits, ≈ $23). The avatar spoke in every row; max playback drift 302 ms. Judge ≈ $0.24–0.26
  per row, ≈ $30–32 per configuration.
- **Not scored:** rendering quality, lip-sync and realism are out of scope by the rubric's own preamble; the
  Tavus perception rows (paper Table 1 AV2AV) were not run (≈ 145 more Tavus minutes).
