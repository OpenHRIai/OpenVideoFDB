# OpenVideoFDB summary

Runs: runs_nv/gt, runs_nv/random, runs_nv/gemini_live_av, runs_nv/gemini_live_a2a, runs_nv/openai_realtime_av, runs_nv/openai_realtime_a2a  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_validation.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 4 | 3.50 | 4.00 | 4.00 | 3.75 | 100% / — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 11 | 3.80 | 4.50 | 4.33 | 4.10 | 83% / 5168 ms |
| **Full-duplex speech-vision (AV2A)** | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | 11 | 2.60 | 2.00 | 3.67 | 2.80 | 67% / 1060 ms |
| OpenAI gpt-realtime | AV2A | 11 | 2.40 | 2.00 | 3.67 | 2.70 | 67% / 910 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | |
| Gemini 3.1 Flash Live | A2A | 11 | 2.20 | 2.00 | 2.67 | 2.30 | 83% / 1348 ms |
| OpenAI gpt-realtime | A2A | 11 | 2.60 | 2.50 | 3.67 | 2.90 | 67% / 844 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 4 | 3.50 [2.00, 5.00] | 4.00 [4.00, 4.00] | 4.00 [4.00, 4.00] | 3.75 [3.00, 4.50] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | 11 | 3.80 [1.80, 5.00] | 4.50 [4.00, 5.00] | 4.33 [4.00, 5.00] | 4.10 [3.20, 4.80] | 83 [50, 100] | 5168 [964, 9372] |
| Gemini 3.1 Flash Live | AV2A | 11 | 2.60 [0.80, 4.40] | 2.00 [0.00, 4.00] | 3.67 [2.00, 5.00] | 2.80 [1.40, 4.00] | 67 [33, 100] | 1060 [0, 2120] |
| OpenAI gpt-realtime | AV2A | 11 | 2.40 [0.40, 4.40] | 2.00 [0.00, 4.00] | 3.67 [2.00, 5.00] | 2.70 [1.30, 4.10] | 67 [33, 100] | 910 [0, 1820] |
| Gemini 3.1 Flash Live | A2A | 11 | 2.20 [0.40, 4.00] | 2.00 [0.00, 4.00] | 2.67 [0.00, 4.00] | 2.30 [0.60, 4.00] | 83 [50, 100] | 1348 [0, 2364] |
| OpenAI gpt-realtime | A2A | 11 | 2.60 [0.60, 4.60] | 2.50 [1.00, 4.00] | 3.67 [2.00, 5.00] | 2.90 [1.70, 4.10] | 67 [33, 100] | 844 [60, 1628] |
