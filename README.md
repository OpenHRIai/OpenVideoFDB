# OpenVideoFDB

An open, runnable implementation of **VideoFDB**, NVIDIA's benchmark for full-duplex
audio-visual conversational agents
([paper](https://arxiv.org/abs/2605.30256) ·
[dataset](https://huggingface.co/datasets/nvidia/video-full-duplex-benchmark) ·
[project page](https://research.nvidia.com/labs/amri/projects/video-fdb/)).

VideoFDB asks a simple question of a video-call agent: while the user is still talking,
pausing, nodding or laughing, does the agent do what a good human listener would do, and
at the right moment? NVIDIA published the dataset (gated) and the protocol, but no
evaluation code or official scorer. This repository provides:

- **The full evaluation pipeline**: a real-time harness that streams a clip's user audio
  (+ 1 fps frames) into an agent and records its speech; the paper's deterministic timing
  metrics (TOR-Alignment, latency, App. C.2); and its LLM-as-judge rubrics (App. F),
  ported verbatim, with a calibrated evidence payload.
- **Agents out of the box**: Gemini Live, OpenAI Realtime (audio-visual and audio-only),
  a human-reference player (the real partner's channel) and a random-partner baseline.
- **An adapter for NVIDIA's dataset** so the same pipeline scores the real benchmark if you
  have access, and **an open clip set** mined from Meta's
  [Seamless Interaction](https://huggingface.co/datasets/facebook/seamless-interaction)
  corpus (CC BY-NC 4.0) for anyone who does not.
- **A human annotator page** (`ovfdb review`) to check mined clips by eye.

Status (2026-10-16): the pipeline reproduces the paper's human-reference numbers on the
NVIDIA test split where that is computable, and lands in the paper's range for the two
API models on the validation split. Model runs on the full NVIDIA test split and the
generation (video-out) judge are not done yet. See *Results* and *Status* below.

## Results

Notation follows the project page: `AV2A` = frames + audio in, audio out; `A2A` = same
agents with video withheld; `AV2AV` = a real person (video out). `Timing` =
TOR-Alignment % / median latency. Judge: gpt-4o. All tables and notes live in `results/`.

**NVIDIA test split, human reference** (`results/nvidia_human_reference.md`): the partner
channel ships for 30 of the 172 test clips (Laughter and Nonverbal Backchanneling, both
buckets), so the human reference is computable on those 60 rows.

| | Fluency | Conv. Flow | Vis. Ground. | Overall | Timing |
|---|---|---|---|---|---|
| OpenVideoFDB, human reference (60 rows) | 4.57 | 4.06 | 3.64 | 4.22 | 100 % |
| Paper, human reference (all 226 rows) | 4.16 | 4.20 | 4.24 | 4.20 | 90 % / 1400 ms |
| Per category: Laughter (P) ours / paper | | | | 3.86 / 3.86 | |
| Per category: Nonverbal Backchanneling (P) ours / paper | | | | 4.53 / 4.12 | |

**NVIDIA validation split, 11 public rows** (`results/nvidia_validation.md`; n ≤ 5 per cell,
a pipeline smoke test, not a result):

| Model | Setting | ours | paper (full test) |
|---|---|---|---|
| Gemini 3.1 Flash Live | AV2A | 2.80 | 2.84 |
| Gemini 3.1 Flash Live | A2A | 2.30 | 3.03 |
| OpenAI gpt-realtime | AV2A | 2.70 | 2.75 |
| OpenAI gpt-realtime | A2A | 2.90 | 2.97 |

**Open Seamless-derived set, 60 day-1 rows** (`results/v0_summary.md`, manifest v0):

| Model | Setting | Fluency | Conv. Flow | Vis. Ground. | Overall | Timing |
|---|---|---|---|---|---|---|
| Human reference | AV2AV | 4.25 | 4.60 | 3.40 | 4.12 | 100 % / 508 ms |
| Random baseline | AV2AV | 2.55 | 3.40 | 2.30 | 2.70 | 35 % / 40 ms |
| Gemini 3.1 Flash Live | AV2A | 3.25 | 4.40 | 2.90 | 3.45 | 60 % / 704 ms |
| OpenAI gpt-realtime | AV2A | 3.05 | 4.50 | 3.40 | 3.50 | 50 % / 904 ms |
| Gemini 3.1 Flash Live | A2A | 3.55 | 4.40 | 3.20 | 3.67 | 58 % / 694 ms |
| OpenAI gpt-realtime | A2A | 2.50 | 2.90 | 3.30 | 2.80 | 50 % / 712 ms |

Caveat on this table: manifest v0's day-1 windows were selected using the partner's
reaction, which makes the human reference pass the timing rules by construction (the
paper's human reference scores 90 % / 78 %). Manifest v1 fixes this with user-cue-only
rules and a human review; on v1 the human reference scores Pause 90 %, Turn-taking 100 %,
Verbal Interruption 71 % against the paper's 90 % / 100 % / 70 %. See `STATUS.md` and
`docs/protocol.md` §10 for every known deviation from the paper.

Two findings so far that hold on both data sources: current API models do not use the
video channel on these dynamics (A2A scores ≥ AV2A almost everywhere), and no model
produces verbal backchannels ("mhm") while the user holds the floor.

## Quick start

Requirements: Python 3.12, [`uv`](https://docs.astral.sh/uv/), `ffmpeg`/`ffprobe` on PATH.

```bash
uv sync
cp .env.example .env        # GOOGLE_API_KEY, OPENAI_API_KEY; HF_TOKEN for the NVIDIA dataset
uv run pytest               # 160 tests, no network needed
```

### Score the real benchmark (needs NVIDIA access)

```bash
uv run ovfdb nvidia snapshot --split test            # gated download, ~5 GB
uv run ovfdb nvidia manifest --split test            # -> manifest/nvidia_test.jsonl (git-ignored)
uv run ovfdb run manifest/nvidia_test.jsonl --provider gemini_live --mode av --out runs_nv/gemini_live_av
uv run ovfdb score runs_nv/gemini_live_av --manifest manifest/nvidia_test.jsonl
uv run ovfdb report runs_nv/gt runs_nv/random runs_nv/gemini_live_av --manifest manifest/nvidia_test.jsonl --per-dynamic
```

### Use the open clip set

The repository ships only manifests (clip windows, labels, system prompts, captions,
review decisions). Media is re-cut locally from Meta's public mirror:

```bash
uv run ovfdb rebuild --manifest manifest/ovfdb_v1_reviewed.jsonl      # fetch + trim, deterministic
uv run ovfdb run manifest/ovfdb_v1_reviewed.jsonl --provider human_gt --mode av --out runs_v1/gt
uv run ovfdb run manifest/ovfdb_v1_reviewed.jsonl --provider openai_realtime --mode av --out runs_v1/openai_realtime_av
uv run ovfdb score runs_v1/openai_realtime_av --manifest manifest/ovfdb_v1_reviewed.jsonl
uv run ovfdb review --manifest manifest/ovfdb_v1_reviewed.jsonl        # annotator page on localhost
```

To mine new clips: `uv run ovfdb mine --dynamics all --limit 10 --tag v2 --manifest manifest/ovfdb_v2.jsonl`
(needs `GOOGLE_API_KEY` for the VLM check and captions, `OPENAI_API_KEY` for system prompts).

### Add an agent

Implement `ovfdb.harness.base.Agent` (`start`, `push_audio`, `push_frame`, `stop`; emit
`AudioOut` chunks with the time they were produced) and register it in
`ovfdb/harness/providers/__init__.py`. See `providers/gemini_live.py` (streaming video) and
`providers/openai_realtime.py` (frames as image items) for the two API styles.

## Layout

```
ovfdb/schema.py        shared contract: Sample, AgentRun, dynamics/axes/timing tables
ovfdb/data/            seamless.py (open clips, rebuild), nvidia.py (gated reference)
ovfdb/mine/            candidate finders, VLM verification, trimming, prompts, captions
ovfdb/harness/         real-time streamer, recorder, providers/
ovfdb/score/           asr, vad, timing (App. C.2), judge (App. F), report
ovfdb/review/          human annotator page
manifest/              published manifests (Seamless-derived); NVIDIA manifests are git-ignored
results/               result tables with notes
docs/protocol.md       the protocol as implemented, with every deviation from the paper
docs/reference/        verbatim paper text (CC BY 4.0) and the project-page tables
```

## How this differs from the paper

- ASR is faster-whisper (paper: Parakeet); the AV captioner for the open set is Gemini Flash
  (paper: Qwen3.5 + Nemotron-Omni). On NVIDIA data the shipped Qwen captions are used.
- Agent speech segments come from VAD with ASR words attached, and the timing rules carry
  small tolerances; the judge payload adds evidence lines (cue, user speech state, annotated
  spans, timestamped transcript) on top of the paper's template. Rubric text is verbatim.
- The open clip set comes from studio face-to-face conversations, not video calls, and is
  mined by rules plus a VLM check plus a human review page, not a three-pass annotation.
- Not implemented yet: the generation (video-out) judge, avatar agents (Tavus, Anam), a
  second judge model for agreement numbers.

## Licences and attribution

Code: MIT. Manifests and everything derived from Seamless Interaction (windows, transcript
excerpts, prompts, captions, review decisions): CC BY-NC 4.0, with attribution to Meta AI's
Seamless Interaction dataset. The NVIDIA VideoFDB dataset is gated and non-redistributable;
this repository contains a loader only and never any of its media or annotations. Paper text
under `docs/reference/` is reproduced under its CC BY 4.0 licence.

If you use this, please cite the VideoFDB paper (arXiv 2605.30256) and, for the open clip
set, Seamless Interaction (Meta AI, 2025).

## Status

`STATUS.md` is the live board: what is done, what is parked, open decisions, and the
exact next steps. `PLAN.md` and `plans/` describe the workstreams.
