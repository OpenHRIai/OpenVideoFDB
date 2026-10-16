# OpenVideoFDB summary

Runs: runs_nv/gt, runs_nv/random, runs_nv/gemini_live_av, runs_nv/gemini_live_a2a, runs_nv/openai_realtime_av, runs_nv/openai_realtime_a2a  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to manifest/nvidia_validation.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 4 | 3.50 | 4.00 | 3.00 | 3.50 | 100% / — |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 11 | 3.60 | 4.50 | 4.33 | 4.00 | 83% / 5168 ms |
| **Full-duplex speech-vision (AV2A)** | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | 11 | 2.60 | 2.00 | 3.67 | 2.80 | 67% / 1060 ms |
| OpenAI gpt-realtime | AV2A | 11 | 2.80 | 2.00 | 4.33 | 3.10 | 67% / 910 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | |
| Gemini 3.1 Flash Live | A2A | 11 | 2.60 | 2.00 | 3.00 | 2.60 | 83% / 1348 ms |
| OpenAI gpt-realtime | A2A | 11 | 2.60 | 2.50 | 4.00 | 3.00 | 67% / 844 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 4 | 3.50 [2.00, 5.00] | 4.00 [4.00, 4.00] | 3.00 [3.00, 3.00] | 3.50 [2.50, 4.50] | 100 [100, 100] | — |
| Random baseline (mismatched partner) | AV2AV | 11 | 3.60 [2.20, 4.60] | 4.50 [4.00, 5.00] | 4.33 [4.00, 5.00] | 4.00 [3.50, 4.40] | 83 [50, 100] | 5168 [964, 9372] |
| Gemini 3.1 Flash Live | AV2A | 11 | 2.60 [0.80, 4.40] | 2.00 [0.00, 4.00] | 3.67 [2.00, 5.00] | 2.80 [1.40, 4.00] | 67 [33, 100] | 1060 [0, 2120] |
| OpenAI gpt-realtime | AV2A | 11 | 2.80 [1.00, 4.80] | 2.00 [0.00, 4.00] | 4.33 [4.00, 5.00] | 3.10 [1.40, 4.40] | 67 [33, 100] | 910 [0, 1820] |
| Gemini 3.1 Flash Live | A2A | 11 | 2.60 [0.80, 4.40] | 2.00 [0.00, 4.00] | 3.00 [2.00, 5.00] | 2.60 [1.20, 3.80] | 83 [50, 100] | 1348 [0, 2364] |
| OpenAI gpt-realtime | A2A | 11 | 2.60 [0.80, 4.40] | 2.50 [1.00, 4.00] | 4.00 [2.00, 5.00] | 3.00 [1.70, 4.20] | 67 [33, 100] | 844 [60, 1628] |

## Notes (2026-10-16, NVIDIA validation split — pipeline smoke test)

- The public validation split: 11 rows, 8 clips, one row per (bucket, dynamic) cell. Judge axes exist for the
  5 perception rows; the human reference is computable only on the 4 rows whose clips ship the partner channel
  (Laughter P+G, Nonverbal Backchanneling P+G), i.e. 2 judged rows. Treat every number here as n ≤ 5.
- Same models as the paper's Table 1 rows "Gemini 3.1 Flash Live" and "OpenAI gpt-realtime" (AV2A / A2A);
  our judge payload v2 on NVIDIA's own captions, prompts, windows and word-level ASR. Model overall
  2.6–3.1 vs the paper's 2.7–3.0 on the full test set: the pipeline lands in the right range on real data.
- Random beats every model here (4.0): on NVIDIA's long windows (Gaze 5–6 s window inside a 61 s clip,
  Turn-taking 1–35 s) a mismatched human partner often happens to be doing the right thing; n = 5.
- Rule leniencies seen: stay-silent "in-window speech ≤ 1 s" passes an agent that talks through a 1 s window
  (Gaze row: pass with 0 ms latency while the judge gives 0); continue-speaking passes vacuously when the agent
  was silent before the window. Both are the paper's rules as written; the judge axes catch them.
- Both models greet ("Hey there, it's so nice to chat...") instead of continuing mid-conversation when
  `agent_speaks_first` is set, which the fluency rubric penalises as wrong-turn talking.
- Dual-bucket clips swap user and partner between buckets; runs are keyed `<clip>__<bucket>` for them
  (`schema.run_dir_names`). Before that fix the human reference was fed its own user's speech.
