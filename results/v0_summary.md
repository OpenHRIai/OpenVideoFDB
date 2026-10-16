# OpenVideoFDB summary

Runs: runs/gt, runs/random, runs/gemini_live_av, runs/gemini_live_a2a, runs/openai_realtime_av, runs/openai_realtime_a2a  
Judge: gpt-4o. n = manifest rows (clip, bucket) scored. Rows restricted to the first 60 rows of manifest/ovfdb_v0.jsonl. Notation follows the VideoFDB project page (Table 1): Setting = <input>2<output> modality (AV2A = frames + audio in, audio out; A2A = same agents, video withheld; AV2AV = video out). Vis. Ground. = the Semantic/Visual Grounding axis. Overall = mean of each perception row's available judge axes. Timing = TOR-Align % (timed rows whose takeover matches the expected class) / median latency ms over timed rows; an agent already talking when the window opens counts as 0 ms, so read latency together with TOR-Align. The second table repeats the metrics with 95 % bootstrap CIs over rows (1000 resamples, seed 0).

| Model | Setting | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | |
| Human reference | AV2AV | 60 | 4.25 | 4.60 | 3.40 | 4.12 | 100% / 508 ms |
| **Random baseline** | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | 60 | 2.55 | 3.40 | 2.30 | 2.70 | 35% / 40 ms |
| **Full-duplex speech-vision (AV2A)** | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | 60 | 3.25 | 4.40 | 2.90 | 3.45 | 60% / 704 ms |
| OpenAI gpt-realtime | AV2A | 60 | 3.05 | 4.50 | 3.40 | 3.50 | 50% / 904 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | |
| Gemini 3.1 Flash Live | A2A | 60 | 3.55 | 4.40 | 3.20 | 3.67 | 58% / 694 ms |
| OpenAI gpt-realtime | A2A | 60 | 2.50 | 2.90 | 3.30 | 2.80 | 50% / 712 ms |

## With 95 % bootstrap CIs

| Model | Setting | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | 60 | 4.25 [3.80, 4.65] | 4.60 [4.00, 5.00] | 3.40 [2.90, 3.90] | 4.12 [3.67, 4.50] | 100 [100, 100] | 508 [304, 652] |
| Random baseline (mismatched partner) | AV2AV | 60 | 2.55 [1.65, 3.35] | 3.40 [2.00, 4.50] | 2.30 [2.00, 2.70] | 2.70 [1.93, 3.42] | 35 [22, 50] | 40 [0, 2176] |
| Gemini 3.1 Flash Live | AV2A | 60 | 3.25 [2.40, 4.05] | 4.40 [3.40, 5.00] | 2.90 [2.30, 3.60] | 3.45 [2.70, 4.12] | 60 [45, 75] | 704 [264, 1224] |
| OpenAI gpt-realtime | AV2A | 60 | 3.05 [2.10, 4.00] | 4.50 [3.50, 5.00] | 3.40 [2.70, 4.10] | 3.50 [2.75, 4.25] | 50 [35, 65] | 904 [133, 1928] |
| Gemini 3.1 Flash Live | A2A | 60 | 3.55 [2.75, 4.25] | 4.40 [3.40, 5.00] | 3.20 [2.60, 3.70] | 3.67 [3.00, 4.28] | 58 [42, 72] | 694 [246, 1182] |
| OpenAI gpt-realtime | A2A | 60 | 2.50 [1.65, 3.35] | 2.90 [1.80, 4.00] | 3.30 [2.80, 3.70] | 2.80 [2.15, 3.48] | 50 [35, 65] | 712 [600, 872] |

## Per dynamic

| Model | Setting | dynamic_type | n | Fluency ↑ | Conv. Flow ↑ | Vis. Ground. ↑ | Overall ↑ | Timing ↑ |
|---|---|---|---|---|---|---|---|---|
| **Human reference** | | | | | | | | |
| Human reference | AV2AV | Laughter | 20 | 4.00 | — | 3.40 | 3.70 | — |
| Human reference | AV2AV | Pause Handling | 10 | 4.50 | 4.60 | — | 4.55 | 100% / 1016 ms |
| Human reference | AV2AV | Turn-taking | 10 | — | — | — | — | 100% / 632 ms |
| Human reference | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 100% / 304 ms |
| Human reference | AV2AV | Verbal Interruption | 10 | — | — | — | — | 100% / 636 ms |
| **Random baseline** | | | | | | | | |
| Random baseline (mismatched partner) | AV2AV | Laughter | 20 | 2.00 | — | 2.30 | 2.15 | — |
| Random baseline (mismatched partner) | AV2AV | Pause Handling | 10 | 3.10 | 3.40 | — | 3.25 | 80% / 196 ms |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 10 | — | — | — | — | 50% / 0 ms |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 0% / — |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 10 | — | — | — | — | 10% / 2904 ms |
| **Full-duplex speech-vision (AV2A)** | | | | | | | | |
| Gemini 3.1 Flash Live | AV2A | Laughter | 20 | 2.40 | — | 2.90 | 2.65 | — |
| Gemini 3.1 Flash Live | AV2A | Pause Handling | 10 | 4.10 | 4.40 | — | 4.25 | 90% / 1236 ms |
| Gemini 3.1 Flash Live | AV2A | Turn-taking | 10 | — | — | — | — | 50% / 1224 ms |
| Gemini 3.1 Flash Live | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 10% / 0 ms |
| Gemini 3.1 Flash Live | AV2A | Verbal Interruption | 10 | — | — | — | — | 90% / 260 ms |
| OpenAI gpt-realtime | AV2A | Laughter | 20 | 1.60 | — | 3.40 | 2.50 | — |
| OpenAI gpt-realtime | AV2A | Pause Handling | 10 | 4.50 | 4.50 | — | 4.50 | 90% / 904 ms |
| OpenAI gpt-realtime | AV2A | Turn-taking | 10 | — | — | — | — | 40% / 1640 ms |
| OpenAI gpt-realtime | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 0% / — |
| OpenAI gpt-realtime | AV2A | Verbal Interruption | 10 | — | — | — | — | 70% / 133 ms |
| **Audio-only baselines (A2A; same agents, video withheld)** | | | | | | | | |
| Gemini 3.1 Flash Live | A2A | Laughter | 20 | 2.80 | — | 3.20 | 3.00 | — |
| Gemini 3.1 Flash Live | A2A | Pause Handling | 10 | 4.30 | 4.40 | — | 4.35 | 100% / 1668 ms |
| Gemini 3.1 Flash Live | A2A | Turn-taking | 10 | — | — | — | — | 40% / 1160 ms |
| Gemini 3.1 Flash Live | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0% / — |
| Gemini 3.1 Flash Live | A2A | Verbal Interruption | 10 | — | — | — | — | 90% / 223 ms |
| OpenAI gpt-realtime | A2A | Laughter | 20 | 3.50 | — | 3.30 | 3.40 | — |
| OpenAI gpt-realtime | A2A | Pause Handling | 10 | 1.50 | 2.90 | — | 2.20 | 80% / 808 ms |
| OpenAI gpt-realtime | A2A | Turn-taking | 10 | — | — | — | — | 70% / 712 ms |
| OpenAI gpt-realtime | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0% / 496 ms |
| OpenAI gpt-realtime | A2A | Verbal Interruption | 10 | — | — | — | — | 50% / 88 ms |

## Per dynamic with 95 % bootstrap CIs

| Model | Setting | dynamic_type | n | Fluency | Conv. Flow | Vis. Ground. | Overall | TOR-Align % | Latency ms |
|---|---|---|---|---|---|---|---|---|---|
| Human reference | AV2AV | Laughter | 20 | 4.00 [3.50, 4.40] | — | 3.40 [2.90, 3.90] | 3.70 [3.30, 4.05] | — | — |
| Human reference | AV2AV | Pause Handling | 10 | 4.50 [3.60, 5.00] | 4.60 [4.00, 5.00] | — | 4.55 [3.80, 5.00] | 100 [100, 100] | 1016 [1000, 1032] |
| Human reference | AV2AV | Turn-taking | 10 | — | — | — | — | 100 [100, 100] | 632 [456, 1032] |
| Human reference | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 100 [100, 100] | 304 [270, 304] |
| Human reference | AV2AV | Verbal Interruption | 10 | — | — | — | — | 100 [100, 100] | 636 [516, 900] |
| Random baseline (mismatched partner) | AV2AV | Laughter | 20 | 2.00 [1.20, 2.80] | — | 2.30 [2.00, 2.70] | 2.15 [1.70, 2.60] | — | — |
| Random baseline (mismatched partner) | AV2AV | Pause Handling | 10 | 3.10 [1.60, 4.50] | 3.40 [2.00, 4.50] | — | 3.25 [1.75, 4.50] | 80 [50, 100] | 196 [0, 2176] |
| Random baseline (mismatched partner) | AV2AV | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 0 [0, 968] |
| Random baseline (mismatched partner) | AV2AV | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| Random baseline (mismatched partner) | AV2AV | Verbal Interruption | 10 | — | — | — | — | 10 [0, 30] | 2904 [0, 4133] |
| Gemini 3.1 Flash Live | AV2A | Laughter | 20 | 2.40 [1.40, 3.20] | — | 2.90 [2.30, 3.60] | 2.65 [1.90, 3.40] | — | — |
| Gemini 3.1 Flash Live | AV2A | Pause Handling | 10 | 4.10 [2.80, 5.00] | 4.40 [3.40, 5.00] | — | 4.25 [3.20, 5.00] | 90 [70, 100] | 1236 [1064, 1408] |
| Gemini 3.1 Flash Live | AV2A | Turn-taking | 10 | — | — | — | — | 50 [20, 80] | 1224 [1091, 1544] |
| Gemini 3.1 Flash Live | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 10 [0, 30] | 0 [0, 0] |
| Gemini 3.1 Flash Live | AV2A | Verbal Interruption | 10 | — | — | — | — | 90 [70, 100] | 260 [109, 325] |
| OpenAI gpt-realtime | AV2A | Laughter | 20 | 1.60 [0.50, 2.70] | — | 3.40 [2.70, 4.10] | 2.50 [1.65, 3.30] | — | — |
| OpenAI gpt-realtime | AV2A | Pause Handling | 10 | 4.50 [3.50, 5.00] | 4.50 [3.50, 5.00] | — | 4.50 [3.50, 5.00] | 90 [70, 100] | 904 [904, 904] |
| OpenAI gpt-realtime | AV2A | Turn-taking | 10 | — | — | — | — | 40 [10, 70] | 1640 [968, 2696] |
| OpenAI gpt-realtime | AV2A | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| OpenAI gpt-realtime | AV2A | Verbal Interruption | 10 | — | — | — | — | 70 [40, 90] | 133 [0, 343] |
| Gemini 3.1 Flash Live | A2A | Laughter | 20 | 2.80 [1.80, 3.60] | — | 3.20 [2.60, 3.70] | 3.00 [2.20, 3.70] | — | — |
| Gemini 3.1 Flash Live | A2A | Pause Handling | 10 | 4.30 [3.10, 5.00] | 4.40 [3.40, 5.00] | — | 4.35 [3.25, 5.00] | 100 [100, 100] | 1668 [1256, 2080] |
| Gemini 3.1 Flash Live | A2A | Turn-taking | 10 | — | — | — | — | 40 [10, 70] | 1160 [1064, 1608] |
| Gemini 3.1 Flash Live | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | — |
| Gemini 3.1 Flash Live | A2A | Verbal Interruption | 10 | — | — | — | — | 90 [70, 100] | 223 [144, 324] |
| OpenAI gpt-realtime | A2A | Laughter | 20 | 3.50 [2.80, 4.10] | — | 3.30 [2.80, 3.70] | 3.40 [2.95, 3.80] | — | — |
| OpenAI gpt-realtime | A2A | Pause Handling | 10 | 1.50 [0.00, 3.00] | 2.90 [1.80, 4.00] | — | 2.20 [1.10, 3.45] | 80 [50, 100] | 808 [648, 1000] |
| OpenAI gpt-realtime | A2A | Turn-taking | 10 | — | — | — | — | 70 [40, 100] | 712 [632, 1128] |
| OpenAI gpt-realtime | A2A | Verbal Backchanneling | 10 | — | — | — | — | 0 [0, 0] | 496 [496, 496] |
| OpenAI gpt-realtime | A2A | Verbal Interruption | 10 | — | — | — | — | 50 [20, 80] | 88 [0, 4167] |

## Notes (2026-10-16, first model results)

- Rows: the 60 day-1 manifest rows (54 clips; Pause Handling, Verbal Backchanneling, Verbal Interruption,
  Turn-taking, Laughter P+G). The a2a run dirs also hold 10 later nonverbal clips, excluded here via
  `--manifest manifest/ovfdb_v0.jsonl --rows 60`. Judge payload v2 (`results/calibration_v2.md`).
  Laughter "n = 20" counts both buckets; its judge axes come from the 10 perception rows.
- Models: `gemini-3.1-flash-live-preview` (Gemini Live) and `gpt-realtime` (OpenAI Realtime, server VAD;
  AV = 1 fps `input_image` items). a2a = same clips, frames withheld.
- **Pause Handling**: all four runs stay silent by the timing rule (80–100 %), but the judge is stricter
  than the rule on sub-second in-window tokens — e.g. OpenAI a2a fluency 1.5 comes from seven rows rated
  0 for a 0.25–0.6 s "yeah" / sentence fragment inside the pause (rule: ≤ 1 s or backchannel ⇒ pass; role
  text: "a brief sub-second backchannel is tolerable"). The fluency axis is absorbing category-correctness
  here; open question whether to tighten the stay-silent rule (any lexical onset inside the window
  fails) or to add a payload hint. Rubric text untouched so far.
- **Verbal Backchanneling**: 0–10 % for every model (GT 100 %): no model produces a short in-window
  backchannel; they either stay silent or take the turn (takeover rate 0.6 for OpenAI AV).
- **Verbal Interruption**: Gemini yields in 90 % of rows (median 220–260 ms), OpenAI 50–70 %.
- **Turn-taking**: 40–70 % (GT 100 %); model onsets land 1.1–1.6 s after `ds`, past our tight mined
  handoff windows (+0.5 s tolerance); OpenAI a2a is the fastest (712 ms, 70 %).
- **Laughter**: OpenAI AV fluency 1.6 — the model goes silent through the laugh in 5/10 rows and the
  judge scores "no response when one was expected"; Gemini keeps talking (2.4–2.8). All models are
  below GT (4.0) on this axis; grounding 2.9–3.4 vs GT 3.4 (GT itself is capped by "flat in tone", see
  calibration notes).
- AV vs a2a is not consistently different on these audio-first dynamics (Gemini a2a ≥ av; OpenAI av ≫ a2a
  on Pause, a2a ≫ av on Laughter). The nonverbal dynamics (56 new clips) are where video should matter;
  runs on them are the next step.
