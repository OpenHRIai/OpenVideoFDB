# VideoFDB protocol — working notes

Condensed from arXiv 2605.30256v2 (CC BY 4.0). Verbatim text, including every
rubric and prompt, is in `docs/reference/videofdb_paper_arxiv_2605.30256v2.txt`
— grep for the section heading (e.g. `F.5.4 Category rubrics`). Section
headings appear twice in that file (TOC + body); take the second hit.

## 1. Taxonomy (Table 2) — 11 dynamics, 4 channels
Channels: **D** dialogue, **G** eye gaze, **F** face, **B** body.

| Dynamic | Channels | Bucket(s) | What the user does | Expected agent behaviour |
|---|---|---|---|---|
| Pause Handling | D·G | P | pauses mid-thought, keeps the floor | stay silent, let user continue |
| Gaze Avoidance with Pause | D·G | P | looks away while pausing (think-cue) | read as thinking, stay silent |
| Adaptor Handling | B | P | self-directed gesture (scratch, hair, fidget) | ignore it; no reaction |
| Nonverbal Interruption | D·B | P | raised hand / head shake / "stop" while agent speaks | yield within ~1–1.5 s |
| Face Emotion Display | G·F | P, G | visible facial expression | affectively congruent reply (P) / mirror in face+voice (G) |
| Nonverbal Backchanneling | D·F | P, G | nods / smiles while agent speaks | keep talking (P) / produce nod-smile-"mhm" while user speaks (G) |
| Laughter | D·F | P, G | laughs at agent's words | warm continuation (P) / laugh back in-window (G) |
| Emotion Matching | F | G | user shows affect | agent's combined AV response matches |
| Verbal Backchanneling | D·F | G | user is speaking | agent emits ≥1 short ack (<1 s, <2 words), no floor-take |
| Verbal Interruption | D | G | user interrupts agent verbally | agent halts, stays yielded |
| Turn-taking | D | G | user offers the floor | agent starts within handoff window; no talk-over on re-entry |

NVIDIA counts (test/val): Perception — Adaptor 13/1, Face Emotion 24/1, Gaze
Avoidance 17/1, Laughter 14/1, NV Backchannel 16/1, NV Interruption 8/0, Pause
13/0. Generation — Emotion Matching 13/0, Face Emotion 24/1, Laughter 14/1, NV
Backchannel 16/1, Turn-taking 15/1, Verbal Backchannel 16/1, Verbal
Interruption 23/1. Clip median 46 s (IQR 34–61); dynamic window median 2.5 s.
Clip = 1–3 lead-in turns + up to 1 follow-up turn around the event.

## 2. Axes per dynamic (Table 8)
Perception axes: **Fluency** (universal), **Conversational Flow**, **Semantic
Grounding**. Generation axes: **Fluency**, **Dyadic Affect Match**, **Cue
Appropriateness** (decomposed: cue_produced / cue_timing / cue_appropriateness).

| Dynamic | P: Flu | P: Flow | P: Ground | G: Flu | G: Affect | G: Cue |
|---|---|---|---|---|---|---|
| Pause Handling | ✓ | ✓ | | | | |
| Gaze Avoidance with Pause | ✓ | ✓ | | | | |
| Nonverbal Interruption | ✓ | ✓ | ✓ | | | |
| Adaptor Handling | ✓ | | ✓ | | | |
| Face Emotion Display | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Laughter | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Nonverbal Backchanneling | ✓ | ✓ | | ✓ | ✓ | ✓ |
| Emotion Matching | | | | ✓ | ✓ | ✓ |
| Verbal Backchanneling | | | | ✓ | ✓ | ✓ |
| Verbal Interruption | | | | ✓ | ✓ | ✓ |
| Turn-taking | | | | ✓ | | ✓ |

Emotion Matching aliases to the Face Emotion Display rubric.

## 3. Agent roles (derived signal, F.2.3)
`agent_role_for(dynamic_type, bucket)` → one of SILENT, SPEAKER, YIELDING,
EXCHANGING. Fluency is calibrated against this. Mapping (our reconstruction;
paper gives the enum and examples, not the full table):

| Dynamic (bucket) | Role |
|---|---|
| Pause Handling (P), Gaze Avoidance (P) | SILENT |
| Nonverbal Backchanneling (P), Adaptor Handling (P) | SPEAKER |
| Nonverbal Interruption (P), Verbal Interruption (G) | YIELDING |
| Face Emotion Display (P/G), Laughter (P/G), Emotion Matching (G), Verbal Backchanneling (G), NV Backchanneling (G), Turn-taking (G) | EXCHANGING |

## 4. Timing metrics (App. C.2) — deterministic, implement in `ovfdb/score/timing.py`
Inputs: agent speech segments `[(start, end, text)]` from word-timestamped ASR,
window `[ds, de]`, `agent_speaks_first`. A **backchannel** segment = `< 1 s` and
`< 2 words`.

| Timing class | Dynamics | Pass rule | Latency |
|---|---|---|---|
| stay-silent | Pause Handling, Gaze Avoidance | in-window agent speech ≤ 1 s, OR every overlapping segment is a backchannel | first in-window onset − ds (if any) |
| continue-speaking | NV Backchanneling (P), Adaptor Handling | if agent activity in the 3 s before ds ≥ 30 %, then in-window activity must be ≥ 50 %; else vacuously pass | n/a |
| yield-required | NV Interruption (P), Verbal Interruption (G) | agent stops within 1.5 s of ds | end of agent segment overlapping (or immediately preceding) ds, minus ds |
| smooth-handoff | Turn-taking | agent starts within the annotated handoff window | `first_onset_after(ds) − ds`; 0 if already speaking at ds |
| backchannel-produced | Verbal Backchanneling | ≥ 1 in-window backchannel AND no in-window segment above backchannel limits | first in-window backchannel onset − ds |

TOR per clip: 0 if silence/backchannel, 1 otherwise. Expected TO\* = 0 for
stay-silent, yield-required, backchannel-produced; 1 for continue-speaking,
smooth-handoff. **TOR-Alignment** = fraction of clips whose observed takeover
matches TO\* (i.e. the pass rule). Report per dynamic and aggregate, plus median
latency (ms). Human GT: 90 % / 1400 ms (perception), 78 % / 900 ms (generation).

**Implementation decisions (WS4, `ovfdb/score/timing.py`)** — where the paper is
underspecified: `tor_alignment` = pass-rule rate; the literal TO_i is kept as
`takeover` and reported as raw `takeover_rate`. "Immediately preceding" segment for
yield-required = ends within 1.0 s before ds; nothing near ds ⇒ `trivially_silent`,
fail, latency None. Negative yield latency clamps to 0 (signed value in
`details.stop_offset_s`). Yield moment = end of the first segment (from ds on)
followed by ≥ 1.5 s silence; verdict bands by lag vs de: ≤ 1.5 s YIELDED, 1.5–3 s
"with brief late lag", else DID NOT YIELD. Yield-analysis windows: pre [ds−5, ds],
post [de, de+14], clipped at clip edges. Partition block prints activity on all
three headers; a segment straddling ds/de is clipped into both regions.
**Agent segments are VAD-derived, not ASR-derived** (`ovfdb/score/vad.py`,
`segments.merge_vad_and_words`): speech regions come from Silero VAD (the ONNX model
bundled with faster-whisper; RMS-energy VAD with a noise-floor-relative threshold,
20 ms frames, min speech 150 ms, min silence 300 ms as fallback), regions < 0.5 s
apart merge, ASR words attach to the region containing their midpoint (else the
nearest region within 0.5 s), and a region with no words is a non-lexical
vocalisation (`text=""`, `n_words=0`, counts as a backchannel when < 1 s).
`timing.json` records the path used in `segments_source` (`vad+asr` or the
`asr`-only fallback). **Word counting** for the backchannel limit normalises
tokens (lower-case, punctuation stripped, hyphens split), merges consecutive
vocalisation tokens ("mm -hmm", "uh huh" → 1) and collapses immediate repetitions
("yeah yeah" → 1). **Tolerances**: backchannel duration is compared as
`< 1.0 + 0.1 s` slack (segment-bound jitter); smooth-handoff passes when the first
onset is `≤ de + 0.5 s` (latency still `onset − ds`); for backchannel-produced and
stay-silent, "in-window" membership means overlapping `[ds − 0.25, de + 0.25]`
(`in_window_speech_s` and the other classes keep the strict window). Calibration
evidence (human GT, STATUS.md): whisper dropped non-lexical "mhm" entirely, wrote
"Mm -hmm." / "Yeah. Yeah." as 2 words, timed a "yeah" at 1.04 s, placed an "Okay"
80 ms after de, and lagged acoustic onsets by 80–370 ms in every Turn-taking
failure of our tight (0.3–1.3 s) mined handoff windows.

## 5. Perception judge (text-only; F.5)
Model: gpt-4o in the paper (also validated llama-3.1-70b, claude-sonnet-4-6;
pairwise agreement 77–89 % within 1 point). Output schema (universal):
```json
{"analysis": "cite timings and quoted phrases", "rating": 0-5, "reasoning": "one sentence"}
```
User message template (`judge.build_user_message`, **payload v2**; lines marked `+`
are OpenVideoFDB additions to the paper's F.5.1 template, see below):
```
Category: {dynamic_type}
Bucket: {bucket}
Agent role: {role description}
Dynamic event: t={ds}s to t={de}s
Clip duration: {dur}s
+ Mined cue: {the USER behaviour the clip was selected for, from source_meta.evidence}
+ User speech state: {user speaking X% of the window; speaking at window start | was speaking until T; next user speech at T}
Agent in-window speech: {X.XXs total across N segment(s) --- [a-b] overlaps by Ys}
{yield_analysis block, YIELDING roles only}
AV caption (covers full clip including the dynamic event):
"""{av_caption}"""
+ NOTE on the caption: its USER/PARTNER attribution of speech ... is sometimes swapped. Take who-said-what from the transcripts ...
User speech (with timestamps):
"""[t0-t1s] text per chunk"""
Agent speech segments (times when agent was audible) --- partitioned by dynamic window; each span says what was said, or that it was a backchannel / wordless vocalisation:
"""PRE / IN / POST with activity percentages; + every span line carries "words", backchannel "Yeah" or non-lexical vocalisation, no words (...)"""
+ Agent speech (with timestamps):
+ """[t0-t1s] text per agent segment; wordless VAD regions say (non-lexical vocalisation, no words)"""
Agent speech transcript:
"""{agent_transcript or [no speech]}"""
```
**Why v2** (calibration v1, `results/calibration_v1.md`): with VAD-derived agent
segments the judge read wordless spans (breaths, "mhm", laughs) as talk-over, and on
Laughter clips it called the human partner "repetitive" / "mirroring the user" because
Gemini's caption had attributed the partner's words to the USER (speech attribution in
the side-by-side caption is lip-read from a mixed track and is wrong for whole pairs,
e.g. `V00_S0314_*`). v2 only adds *evidence* lines; rubric and preamble text are
unchanged. The cue line describes the USER's cue only (never what the human partner did
next), so GT and model runs receive identical cue text. `judge.PAYLOAD_VERSION` is
stored in `judge.json` / `judge_summary.json`; the judge cache key covers the payload,
so a payload change re-judges automatically.
Yield-analysis block example:
```
Yield analysis:
Pre-dynamic agent activity: 52.0% (2.60s of 5.00s)
Post-dynamic agent activity: 34.6% (4.84s of 14.00s)
Yield moment (end of speech before sustained silence): 9.28s
Verdict: AGENT YIELDED with brief late lag. Yield moment: 9.28s (+2.28s after dynamic_end_s). Activity 52% -> 35% post-dynamic.
```
System prompt = shared preamble (F.5.2) + universal Fluency axis (F.5.3) +
category rubric (F.5.4). Fluency overrides: system-prompt leak → 0; wrong-turn
talking; language mismatch → 0–1; content mismatch (rare). Category rubrics
are 0–5 anchored; copy them verbatim from the reference text.

## 6. Generation judge (vision-capable; F.6)
Payload: sampled JPEG frames of the agent video (or side-by-side composite,
USER left / AGENT right, user audio L / agent audio R) at **8 fps, ≤600 frames,
256 px wide**, plus a text block with user-side GT, overlap signal, agent
visual caption, agent audio caption, segments, transcript. Universal axes:
Affect Match (late >1.5 s after stimulus caps at 3) and Generation Fluency.
Per-category decomposed schema:
```json
{"analysis": "...", "cue_produced": 0|1, "cue_timing": "during"|"late"|"absent",
 "cue_appropriateness": 0-5, "reasoning": "..."}
```
Consistency rules: cue_produced=0 ⇒ timing=absent, appropriateness=0;
"during" = onset within [ds, de] or within 500 ms of ds.

## 7. Agent-side system prompt (F.4)
For clips where the agent must already be speaking (`agent_speaks_first`), build
a prompt from the transcript of both channels **up to the event window only**
(no future leakage), preserving the topic, and end with
"Start speaking now to begin/continue the conversation". NVIDIA generated
these with GPT-4o from Parakeet transcripts. Prompts are per-clip and shipped
in the metadata (`system_prompt`).

## 8. Harness (App. D)
Unified real-time harness: stream user audio (+ sampled frames for AV runs; 1 fps
typical, MiniCPM-o configurable) over WebSocket; log the agent's spoken
response. A2A = same clip, frames withheld. Open models were run on one H100
each. Cascaded avatars: Gemini Live 2.5 → Anam / Keyframe, run in LiveKit Cloud.

## 9. Calibration (C.3)
Reference set = human GT (the real partner's channel as "agent") + RANDOM
(mismatched partner channel), n=110 each. GT means ≈ 4.5 / 4.5 / 4.2 (Flu / Flow /
Ground). Reproduce this before trusting any model score.

## 10. Known deviations in OpenVideoFDB
- Clips from Seamless Interaction (face-to-face in a studio, two cameras), not
  video calls. Gaze semantics: participants look at each other, not into the
  lens — detect gaze *aversion relative to baseline*, not "at camera".
- AV caption from Gemini Flash instead of Qwen3.5-397B + Nemotron-Omni.
- ASR faster-whisper instead of Parakeet.
- Agent speech segments come from VAD (Silero via faster-whisper's bundled ONNX
  model, energy fallback) with ASR words attached, not from ASR words alone, and
  the timing rules carry small tolerances (backchannel `< 1.0 + 0.1 s`,
  handoff onset `≤ de + 0.5 s`, `±0.25 s` window membership for the backchannel
  classes; see §4). Justification: with ASR-only segments the human partner scored
  40 % on Verbal Backchanneling (whisper drops "mhm", counts "Mm -hmm" as 2 words,
  pads a "yeah" to 1.04 s) and 50 % on Turn-taking (word onsets 80–370 ms after
  the end of our 0.3–1.3 s handoff windows), far below the paper's ≈78 % GT.
- Mining is rule-based + VLM-verified with spot checks, not a 3-pass human pipeline.
