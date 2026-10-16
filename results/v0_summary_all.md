# OpenVideoFDB summary

Runs: runs/gt, runs/random, runs/gemini_live_av, runs/gemini_live_a2a, runs/openai_realtime_av, runs/openai_realtime_a2a  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 118 | 4.26 | 4.46 | 4.00 | 4.27 | 95% / 496 ms |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 118 | 2.19 | 2.39 | 3.18 | 2.47 | 47% / 0 ms |
| **Full-duplex speech-vision (AV2A)** | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | 118 | 3.07 | 3.96 | 3.36 | 3.36 | 68% / 820 ms |
| OpenAI gpt-realtime | AV2A | 118 | 3.19 | 3.96 | 3.50 | 3.48 | 64% / 968 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | |
| Gemini 3.1 Flash Live | A2A | 118 | 3.48 | 3.89 | 3.82 | 3.69 | 67% / 860 ms |
| OpenAI gpt-realtime | A2A | 118 | 3.09 | 3.43 | 3.89 | 3.41 | 67% / 762 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 118 | 4.26 [3.96, 4.56] | 4.46 [4.21, 4.71] | 4.00 [3.61, 4.36] | 4.27 [4.06, 4.49] | 95 [91, 100] | 496 [360, 648] |
| Random baseline (mismatched partner) | AV2AV | 118 | 2.19 [1.61, 2.74] | 2.39 [1.61, 3.21] | 3.18 [2.71, 3.68] | 2.47 [1.97, 2.94] | 47 [35, 59] | 0 [0, 680] |
| Gemini 3.1 Flash Live | AV2A | 118 | 3.07 [2.56, 3.59] | 3.96 [3.25, 4.46] | 3.36 [2.82, 3.89] | 3.36 [2.90, 3.79] | 68 [58, 79] | 820 [268, 1128] |
| OpenAI gpt-realtime | AV2A | 118 | 3.19 [2.63, 3.72] | 3.96 [3.32, 4.50] | 3.50 [2.93, 3.97] | 3.48 [3.06, 3.89] | 64 [52, 74] | 968 [172, 1928] |
| Gemini 3.1 Flash Live | A2A | 118 | 3.48 [2.96, 3.94] | 3.89 [3.25, 4.43] | 3.82 [3.39, 4.25] | 3.69 [3.27, 4.05] | 67 [55, 77] | 860 [223, 1100] |
| OpenAI gpt-realtime | A2A | 118 | 3.09 [2.54, 3.65] | 3.43 [2.79, 4.00] | 3.89 [3.46, 4.29] | 3.41 [2.99, 3.80] | 67 [55, 79] | 762 [664, 968] |

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
| **Full-duplex speech-vision (AV2A)** | | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | Adaptor Handling | 8 | 2.38 | — | 4.38 | 3.38 | 62% / — |
| Gemini 3.1 Flash Live | AV2A | Emotion Matching | 8 | — | — | — | — | — |
| Gemini 3.1 Flash Live | AV2A | Face Emotion Display | 16 | 1.75 | — | 2.75 | 2.25 | — |
| Gemini 3.1 Flash Live | AV2A | Gaze Avoidance with Pause | 8 | 3.88 | 4.38 | — | 4.12 | 88% / 820 ms |
| Gemini 3.1 Flash Live | AV2A | Laughter | 20 | 2.40 | — | 2.90 | 2.65 | — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Backchanneling | 16 | 3.75 | 3.00 | — | 3.38 | 88% / — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Interruption | 2 | 3.50 | 4.00 | 4.00 | 3.83 | 100% / 756 ms |
| Gemini 3.1 Flash Live | AV2A | Pause Handling | 10 | 4.10 | 4.40 | — | 4.25 | 90% / 1236 ms |
| Gemini 3.1 Flash Live | AV2A | Turn-taking | 10 | — | — | — | — | 50% / 1224 ms |
| Gemini 3.1 Flash Live | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 10% / 0 ms |
| Gemini 3.1 Flash Live | AV2A | Verbal Interruption | 10 | — | — | — | — | 90% / 260 ms |
| OpenAI gpt-realtime | AV2A | Adaptor Handling | 8 | 2.75 | — | 3.88 | 3.31 | 88% / — |
| OpenAI gpt-realtime | AV2A | Emotion Matching | 8 | — | — | — | — | — |
| OpenAI gpt-realtime | AV2A | Face Emotion Display | 16 | 2.25 | — | 3.50 | 2.88 | — |
| OpenAI gpt-realtime | AV2A | Gaze Avoidance with Pause | 8 | 4.38 | 4.62 | — | 4.50 | 100% / 1420 ms |
| OpenAI gpt-realtime | AV2A | Laughter | 20 | 1.60 | — | 3.40 | 2.50 | — |
| OpenAI gpt-realtime | AV2A | Nonverbal Backchanneling | 16 | 3.75 | 3.00 | — | 3.38 | 88% / — |
| OpenAI gpt-realtime | AV2A | Nonverbal Interruption | 2 | 3.00 | 2.50 | 2.50 | 2.67 | 0% / 3406 ms |
| OpenAI gpt-realtime | AV2A | Pause Handling | 10 | 4.50 | 4.50 | — | 4.50 | 90% / 904 ms |
| OpenAI gpt-realtime | AV2A | Turn-taking | 10 | — | — | — | — | 40% / 1640 ms |
| OpenAI gpt-realtime | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 0% / — |
| OpenAI gpt-realtime | AV2A | Verbal Interruption | 10 | — | — | — | — | 70% / 133 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | | |
| Gemini 3.1 Flash Live | A2A | Adaptor Handling | 8 | 3.50 | — | 5.00 | 4.25 | 62% / — |
| Gemini 3.1 Flash Live | A2A | Emotion Matching | 8 | — | — | — | — | — |
| Gemini 3.1 Flash Live | A2A | Face Emotion Display | 16 | 2.25 | — | 3.62 | 2.94 | — |
| Gemini 3.1 Flash Live | A2A | Gaze Avoidance with Pause | 8 | 3.75 | 4.00 | — | 3.88 | 88% / 860 ms |
| Gemini 3.1 Flash Live | A2A | Laughter | 20 | 2.80 | — | 3.20 | 3.00 | — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Backchanneling | 16 | 4.50 | 3.62 | — | 4.06 | 88% / — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Interruption | 2 | 2.50 | 2.00 | 3.00 | 2.50 | 100% / 439 ms |
| Gemini 3.1 Flash Live | A2A | Pause Handling | 10 | 4.30 | 4.40 | — | 4.35 | 100% / 1668 ms |
| Gemini 3.1 Flash Live | A2A | Turn-taking | 10 | — | — | — | — | 40% / 1160 ms |
| Gemini 3.1 Flash Live | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0% / — |
| Gemini 3.1 Flash Live | A2A | Verbal Interruption | 10 | — | — | — | — | 90% / 223 ms |
| OpenAI gpt-realtime | A2A | Adaptor Handling | 8 | 4.38 | — | 5.00 | 4.69 | 100% / — |
| OpenAI gpt-realtime | A2A | Emotion Matching | 8 | — | — | — | — | — |
| OpenAI gpt-realtime | A2A | Face Emotion Display | 16 | 2.50 | — | 3.88 | 3.19 | — |
| OpenAI gpt-realtime | A2A | Gaze Avoidance with Pause | 8 | 2.75 | 4.62 | — | 3.69 | 100% / 936 ms |
| OpenAI gpt-realtime | A2A | Laughter | 20 | 3.50 | — | 3.30 | 3.40 | — |
| OpenAI gpt-realtime | A2A | Nonverbal Backchanneling | 16 | 4.38 | 3.50 | — | 3.94 | 100% / — |
| OpenAI gpt-realtime | A2A | Nonverbal Interruption | 2 | 2.50 | 1.00 | 2.50 | 2.00 | 0% / 8430 ms |
| OpenAI gpt-realtime | A2A | Pause Handling | 10 | 1.50 | 2.90 | — | 2.20 | 80% / 808 ms |
| OpenAI gpt-realtime | A2A | Turn-taking | 10 | — | — | — | — | 70% / 712 ms |
| OpenAI gpt-realtime | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0% / 496 ms |
| OpenAI gpt-realtime | A2A | Verbal Interruption | 10 | — | — | — | — | 50% / 88 ms |

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
| Gemini 3.1 Flash Live | AV2A | Adaptor Handling | 8 | 2.38 [0.62, 4.12] | — | 4.38 [3.12, 5.00] | 3.38 [2.19, 4.44] | 62 [25, 88] | — |
| Gemini 3.1 Flash Live | AV2A | Emotion Matching | 8 | — | — | — | — | — | — |
| Gemini 3.1 Flash Live | AV2A | Face Emotion Display | 16 | 1.75 [0.75, 2.75] | — | 2.75 [1.75, 3.50] | 2.25 [1.38, 2.94] | — | — |
| Gemini 3.1 Flash Live | AV2A | Gaze Avoidance with Pause | 8 | 3.88 [2.62, 4.88] | 4.38 [3.12, 5.00] | — | 4.12 [2.88, 4.94] | 88 [62, 100] | 820 [0, 1196] |
| Gemini 3.1 Flash Live | AV2A | Laughter | 20 | 2.40 [1.40, 3.20] | — | 2.90 [2.30, 3.60] | 2.65 [1.90, 3.40] | — | — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Backchanneling | 16 | 3.75 [2.50, 5.00] | 3.00 [2.00, 4.00] | — | 3.38 [2.25, 4.50] | 88 [62, 100] | — |
| Gemini 3.1 Flash Live | AV2A | Nonverbal Interruption | 2 | 3.50 [3.00, 4.00] | 4.00 [4.00, 4.00] | 4.00 [4.00, 4.00] | 3.83 [3.67, 4.00] | 100 [100, 100] | 756 [602, 910] |
| Gemini 3.1 Flash Live | AV2A | Pause Handling | 10 | 4.10 [2.80, 5.00] | 4.40 [3.40, 5.00] | — | 4.25 [3.20, 5.00] | 90 [70, 100] | 1236 [1064, 1408] |
| Gemini 3.1 Flash Live | AV2A | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 1224 [1091, 1544] |
| Gemini 3.1 Flash Live | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 10 [0, 30] | 0 [0, 0] |
| Gemini 3.1 Flash Live | AV2A | Verbal Interruption | 10 | — | — | — | — | 90 [70, 100] | 260 [109, 325] |
| OpenAI gpt-realtime | AV2A | Adaptor Handling | 8 | 2.75 [1.25, 4.38] | — | 3.88 [2.25, 5.00] | 3.31 [2.31, 4.38] | 88 [62, 100] | — |
| OpenAI gpt-realtime | AV2A | Emotion Matching | 8 | — | — | — | — | — | — |
| OpenAI gpt-realtime | AV2A | Face Emotion Display | 16 | 2.25 [1.00, 3.25] | — | 3.50 [2.99, 4.00] | 2.88 [2.25, 3.50] | — | — |
| OpenAI gpt-realtime | AV2A | Gaze Avoidance with Pause | 8 | 4.38 [3.12, 5.00] | 4.62 [3.88, 5.00] | — | 4.50 [3.50, 5.00] | 100 [100, 100] | 1420 [1420, 1420] |
| OpenAI gpt-realtime | AV2A | Laughter | 20 | 1.60 [0.50, 2.70] | — | 3.40 [2.70, 4.10] | 2.50 [1.65, 3.30] | — | — |
| OpenAI gpt-realtime | AV2A | Nonverbal Backchanneling | 16 | 3.75 [1.88, 5.00] | 3.00 [1.50, 4.00] | — | 3.38 [1.69, 4.50] | 88 [62, 100] | — |
| OpenAI gpt-realtime | AV2A | Nonverbal Interruption | 2 | 3.00 [1.00, 5.00] | 2.50 [2.00, 3.00] | 2.50 [1.00, 4.00] | 2.67 [1.67, 3.67] | 0 [0, 0] | 3406 [3406, 3406] |
| OpenAI gpt-realtime | AV2A | Pause Handling | 10 | 4.50 [3.50, 5.00] | 4.50 [3.50, 5.00] | — | 4.50 [3.50, 5.00] | 90 [70, 100] | 904 [904, 904] |
| OpenAI gpt-realtime | AV2A | Turn-taking | 10 | — | — | — | — | 40 [10, 70] | 1640 [968, 2696] |
| OpenAI gpt-realtime | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| OpenAI gpt-realtime | AV2A | Verbal Interruption | 10 | — | — | — | — | 70 [40, 90] | 133 [0, 343] |
| Gemini 3.1 Flash Live | A2A | Adaptor Handling | 8 | 3.50 [2.00, 4.75] | — | 5.00 [5.00, 5.00] | 4.25 [3.50, 4.88] | 62 [25, 88] | — |
| Gemini 3.1 Flash Live | A2A | Emotion Matching | 8 | — | — | — | — | — | — |
| Gemini 3.1 Flash Live | A2A | Face Emotion Display | 16 | 2.25 [1.00, 3.25] | — | 3.62 [2.88, 4.25] | 2.94 [2.25, 3.50] | — | — |
| Gemini 3.1 Flash Live | A2A | Gaze Avoidance with Pause | 8 | 3.75 [2.50, 4.75] | 4.00 [2.75, 5.00] | — | 3.88 [2.62, 4.88] | 88 [62, 100] | 860 [0, 1100] |
| Gemini 3.1 Flash Live | A2A | Laughter | 20 | 2.80 [1.80, 3.60] | — | 3.20 [2.60, 3.70] | 3.00 [2.20, 3.70] | — | — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Backchanneling | 16 | 4.50 [3.50, 5.00] | 3.62 [2.88, 4.00] | — | 4.06 [3.19, 4.50] | 88 [62, 100] | — |
| Gemini 3.1 Flash Live | A2A | Nonverbal Interruption | 2 | 2.50 [1.00, 4.00] | 2.00 [0.00, 4.00] | 3.00 [1.00, 5.00] | 2.50 [0.67, 4.33] | 100 [100, 100] | 439 [0, 878] |
| Gemini 3.1 Flash Live | A2A | Pause Handling | 10 | 4.30 [3.10, 5.00] | 4.40 [3.40, 5.00] | — | 4.35 [3.25, 5.00] | 100 [100, 100] | 1668 [1256, 2080] |
| Gemini 3.1 Flash Live | A2A | Turn-taking | 10 | — | — | — | — | 40 [10, 70] | 1160 [1064, 1608] |
| Gemini 3.1 Flash Live | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| Gemini 3.1 Flash Live | A2A | Verbal Interruption | 10 | — | — | — | — | 90 [70, 100] | 223 [144, 324] |
| OpenAI gpt-realtime | A2A | Adaptor Handling | 8 | 4.38 [3.12, 5.00] | — | 5.00 [5.00, 5.00] | 4.69 [4.06, 5.00] | 100 [100, 100] | — |
| OpenAI gpt-realtime | A2A | Emotion Matching | 8 | — | — | — | — | — | — |
| OpenAI gpt-realtime | A2A | Face Emotion Display | 16 | 2.50 [1.25, 3.50] | — | 3.88 [3.25, 4.38] | 3.19 [2.44, 3.81] | — | — |
| OpenAI gpt-realtime | A2A | Gaze Avoidance with Pause | 8 | 2.75 [1.50, 4.00] | 4.62 [3.88, 5.00] | — | 3.69 [2.81, 4.50] | 100 [100, 100] | 936 [716, 1000] |
| OpenAI gpt-realtime | A2A | Laughter | 20 | 3.50 [2.80, 4.10] | — | 3.30 [2.80, 3.70] | 3.40 [2.95, 3.80] | — | — |
| OpenAI gpt-realtime | A2A | Nonverbal Backchanneling | 16 | 4.38 [3.12, 5.00] | 3.50 [2.50, 4.00] | — | 3.94 [2.81, 4.50] | 100 [100, 100] | — |
| OpenAI gpt-realtime | A2A | Nonverbal Interruption | 2 | 2.50 [0.00, 5.00] | 1.00 [0.00, 2.00] | 2.50 [1.00, 4.00] | 2.00 [0.33, 3.67] | 0 [0, 0] | 8430 [8430, 8430] |
| OpenAI gpt-realtime | A2A | Pause Handling | 10 | 1.50 [0.00, 3.00] | 2.90 [1.80, 4.00] | — | 2.20 [1.10, 3.45] | 80 [50, 100] | 808 [648, 1000] |
| OpenAI gpt-realtime | A2A | Turn-taking | 10 | — | — | — | — | 70 [40, 100] | 712 [632, 1128] |
| OpenAI gpt-realtime | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | 496 [496, 496] |
| OpenAI gpt-realtime | A2A | Verbal Interruption | 10 | — | — | — | — | 50 [20, 80] | 88 [0, 4167] |

## Notes (2026-10-16, all 118 manifest rows)

- Rows: 60 day-1 dialogue rows + 58 day-2 nonverbal rows (110 clips). 54 perception rows carry judge
  axes; 64 generation rows carry only timing (generation judge = WS6c, not built yet). Judge gpt-4o,
  payload v2 (`results/calibration_v2.md`); `results/v0_summary.md` is the day-1-only table.
- **Calibration holds on the nonverbal set**: GT 4.27 vs random 2.47 overall; GT TOR-Align 95 %
  (Adaptor 75 %, NV Backchanneling 88 %, Gaze 100 %, NV Interruption 100 %). GT Face Emotion Display
  fluency 3.38 is the weakest GT cell (the judge wants an audible reaction to a face the agent cannot
  hear about).
- **Judge blind spots**: Adaptor Handling grounding is 5.0 for GT, random and two model runs — the
  rubric rewards *not* reacting to the gesture, which any run satisfies trivially; its fluency axis does
  the discriminating (GT 4.1 / random 1.9). Random's NV Interruption fluency 5.0 is n = 2 noise.
- **Nonverbal Interruption has only 2 rows** (mining found few clean hand/head "stop" gestures); treat
  that line as anecdotal until more are mined.
- **Video does not help the current models**: on every nonverbal dynamic a2a ≥ av for both providers
  (Gemini overall 3.69 a2a vs 3.36 av; OpenAI Face Emotion Display 3.19 a2a vs 2.88 av; Gemini NV
  Backchanneling 4.06 a2a vs 3.38 av). With frames present both models tend to talk about / react to
  what they see (Face Emotion fluency 1.75–2.25) instead of carrying on. Gaze Avoidance with Pause is the
  one place AV is ≥ a2a (OpenAI 4.50 vs 3.69): both stay silent through a look-away pause (TOR 88–100 %).
- Run meta for the new clips: max_drift under 70 ms; OpenAI logs a benign
  `conversation_already_has_active_response` on the text kick for ~8 clips (the response still arrives).
- **Human-reference TOR-Align is 100 % by construction on the day-1 dynamics** (paper: 90 % perception /
  78 % generation). The paper's windows annotate the *user's* cue and let the partner's reaction fall where it
  may; our day-1 mining rules condition on the partner (Pause Handling rejects candidates where the partner
  spoke, Verbal Interruption requires `b_stop ≤ 1.5 s`, Turn-taking's window ends at the partner's onset, Verbal
  Backchanneling is built around the partner's token). GT latency (~500 ms) is tight for the same reason. Models
  and random are still judged fairly against the windows; only the GT line is inflated. Fix = re-mine with
  user-cue-only windows (fixed post-cue window), which changes the manifest. Day-2 nonverbal rules key on
  video events and are less circular (GT 75–88 %).
