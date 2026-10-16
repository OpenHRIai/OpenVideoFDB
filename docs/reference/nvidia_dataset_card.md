---
license: other
license_name: nvidia-evaluation-license
license_link: LICENSE.md
language:
- en
size_categories:
- n<1K
pretty_name: Video-Full-Duplex-Benchmark
tags:
- audio
- video
- conversational
- benchmark
- multimodal
- source:human
- source:synthetic
task_categories:
- audio-to-audio
configs:
- config_name: default
  data_files:
  - split: validation
    path: 0_metadata_validation.parquet
  - split: test
    path: 0_metadata_test.parquet
gated: true
extra_gated_heading: Request Access — NVIDIA VideoFDB
extra_gated_description: >-
  A benchmark dataset for evaluating multimodal AI agents in video
  conversations. This dataset contains proprietary audio/video data licensed
  from NVIDIA and its licensors — please read the terms and complete all fields
  to request access.
extra_gated_prompt: >-
  This dataset ("Dataset") is made available by NVIDIA Corporation ("NVIDIA").
  By requesting access, you agree to the terms set forth in the [LICENSE
  file](https://huggingface.co/datasets/nvidia/video-full-duplex-benchmark/blob/main/LICENSE.md) in
  this repository (the "License") for use of the Dataset.
extra_gated_fields:
  Job Title/Position: text
  Affiliation: text
  Country: country
extra_gated_button_content: I agree to the License terms.
---

# VideoFDB: Video-Full-Duplex-Benchmark

[Project Page](https://research.nvidia.com/labs/amri/projects/video-fdb) · [HuggingFace](https://huggingface.co/datasets/nvidia/video-full-duplex-benchmark) · [Paper (arXiv)](https://arxiv.org/abs/2605.30256)

## Dataset Description

A benchmark dataset of annotated, two-person video conference recordings designed to support the evaluation of multimodal AI agents in conversational settings. The dataset covers 11 distinct conversational dynamics — spanning verbal, nonverbal, and mixed-modality behavior — annotated through a three-pass human-in-the-loop pipeline.

The benchmark consists of trimmed clips, each isolating a single annotated conversational dynamic drawn from naturalistic, locally recorded two-person video calls. Each clip includes 1–3 turns of contextual lead-in speech preceding the dynamic onset and up to one turn following it, providing sufficient conversational context for evaluation.

All conversations are in English. Recordings were made in participants' own environments using video conferencing software, reflecting naturalistic ecological conditions rather than controlled studio settings.

Each sample is scored under one of two rubrics: `bucket="perception"` evaluates how the agent perceives a dynamic produced by the user, and `bucket="generation"` evaluates how the agent generates one of its own. A few dynamic categories (Laughter, Nonverbal Backchanneling, Face Emotion Display) appear under both buckets.

This dataset is only for evaluation and benchmarking of AI solutions for non-commercial and research purposes only (not for commercial use).

## Dataset Owner(s)

NVIDIA Corporation

## Dataset Creation Date

April 2026

## Dataset Version

Current version: 1.0.0

## License/Terms of Use

This dataset is made available under a custom NVIDIA Data Evaluation License Agreement — a custom, non-commercial research license. Access is gated; users must agree to terms before being provided access. NVIDIA will review and approve access on a per-user basis.

See [`LICENSE.md`](./LICENSE.md) for the full text.

## Intended Usage

This dataset is designed for research into the evaluation of multimodal conversational AI agents. Specifically, it supports:

- Benchmarking AI agent behavior across conversational dynamics spanning verbal, nonverbal, and mixed-modality signals
- Development of evaluation frameworks for naturalistic human-agent interaction in video conferencing settings

## Dataset Characterization

**Data Collection Method**

- Human

**Labeling Method**

- Hybrid: Human, Synthetic

### Source Data

Samples are drawn from David AI's human-generated video dataset corpus — a collection of naturalistic two-person audio-video conversations locally recorded in participants' own environments. All source recordings meet the technical quality thresholds specified below (720p minimum, 30 fps, 24 kHz audio).

Conversations selected for this benchmark are ring-fenced exclusively for model evaluation and are not made available for model training.

### Clip Preparation

Recordings are trimmed to isolate a single conversational dynamic alongside sufficient contextual lead-in (typically 1–3 speaker turns) so the dynamic can be understood in its conversational context. Trimming is performed programmatically based on annotator-supplied timestamps.

### Annotation Methodology

- Human

Dataset construction follows a three-pass human-in-the-loop (HITL) pipeline, moving from broad candidate discovery through expert validation to final quality review.

#### Pass 1: Clip Discovery

Annotators screen full-length recordings to identify candidate occurrences of conversational dynamics. For each candidate, annotators log the dynamic type, a provisional subtype, and trimming timestamps. Clips are then programmatically trimmed around each target dynamic.

#### Pass 2: Validation and Labeling

Annotators review each trimmed clip, assigning `dynamic_time_start` / `dynamic_time_end` timestamps and final subtype label(s) from the taxonomy.

#### Pass 3: Quality Review

Final reviewer validates label accuracy, timestamp precision, and taxonomy consistency across all annotated clips. Clips that do not meet quality standards are flagged for re-annotation or rejected.

#### Pass 4: Prompt Annotation

Each clip is enriched with model-derived annotations that feed two distinct downstream contexts: the agent system prompt consumed by the model under test, and the judge context consumed by the LLM rubric scorer at evaluation time. We use Qwen3.5-VL 397B-A17B VLM and Nemotron-v3-Nano-Omni to produce an audio-visual caption, and GPT-4o to generate an agent system prompt.

## Dataset Format

Audio (.wav), Video (.mp4 with 2-channel stereo audio), Text (.json)

## Dataset Quantification

Each sample includes two speakers. For the public eval set, we release both speakers' audio and video streams, as well as a combined stream. For the hidden scoring set, we only release `speaker1.{wav,mp4}` and the annotations, omitting speaker2's media and combined files.

### File Structure

```
video-full-duplex-benchmark-1.0.0.zip
├── 0_metadata_validation.parquet      # 11  rows × 7  cols
├── 0_metadata_test.parquet            # 226 rows × 7  cols
├── 0_annotations_validation.parquet   # 11  rows × 10 cols
├── 0_annotations_test.parquet         # 226 rows × 10 cols
├── README.md
├── LICENSE.md
└── [id]/
    └── [sample_id]/
        ├── speakerN.wav   # user-side audio (16 kHz PCM mono WAV)
        └── speakerN.mp4   # user-side video (VP9 in MP4)
```

### Parquet Schemas

`0_metadata_{validation,test}.parquet` — one row per `(sample_id, bucket)`:

| column | type | description |
|---|---|---|
| `id` | string | conversation UUID |
| `sample_id` | string | clip UUID within the conversation |
| `bucket` | string | `"perception"` or `"generation"` |
| `duration_s` | float | clip length in seconds (re-measured via ffprobe) |
| `audio_file_path` | string | relative path to the user-side `.wav` |
| `video_file_path` | string | relative path to the user-side `.mp4` |
| `system_prompt` | string | LLM-generated prompt fed to the agent under test |

`0_annotations_{validation,test}.parquet` — per-sample judge inputs; joins the metadata table on `(id, sample_id, bucket)`:

| column | type | description |
|---|---|---|
| `id`, `sample_id`, `bucket` | string | join keys |
| `dynamic_type` | string | human-annotated category (e.g. `"Verbal Interruption"`) |
| `dynamic_start_s` | float | start time of the dynamic event, seconds |
| `dynamic_end_s` | float | end time of the dynamic event, seconds |
| `agent_speaks_first` | bool | whether the agent should initiate vs. continue |
| `agent_channel` | string | `"L"`, `"R"`, or empty — agent stereo channel in the original combined view |
| `qwen_caption_full` | string | full-clip AV caption (Qwen-Omni) fed to the perception judge |
| `user_transcript_chunks` | string | JSON-encoded list of `{text, timestamp}` dicts — word-level ASR |

### Splits

This is an evaluation-only benchmark — there is no `train` split.

- **`validation`** — 11 rows across 8 unique sample_ids, a stratified pick of one row per (bucket, dynamic_type) cell. Released for development / sanity-checking evaluator code; ground-truth annotations are public.
- **`test`** — 226 rows. The held-out evaluation set; the data ships with this release but the leaderboard / reference scores are not distributed here.

## Dataset Statistics

| Bin | Dynamic | Public Eval Set | Hidden Scoring Set | Total |
|---|---|---|---|---|
| Perception | Adaptor Handling | 1 | 13 | 14 |
| Perception | Face Emotion Display \* | 1 | 24 | 25 |
| Perception | Gaze Avoidance with Pause | 1 | 17 | 18 |
| Perception | Laughter \* | 1 | 14 | 15 |
| Perception | Nonverbal Backchanneling \* | 1 | 16 | 17 |
| Perception | Nonverbal Interruption | 0 | 8 | 8 |
| Perception | Pause Handling | 0 | 13 | 13 |
| Generation | Emotion Matching | 0 | 13 | 13 |
| Generation | Face Emotion Display \* | 1 | 24 | 25 |
| Generation | Laughter \* | 1 | 14 | 15 |
| Generation | Nonverbal Backchanneling \* | 1 | 16 | 17 |
| Generation | Turn-taking | 1 | 15 | 16 |
| Generation | Verbal Backchanneling | 1 | 16 | 17 |
| Generation | Verbal Interruption | 1 | 23 | 24 |
| | **Total (row sum)** | **11** | **226** | **237** |
| | **Distinct sample_ids** | **8** | **172** | **180** |

Total release size: ~4.8 GB.

## Evaluation Methodology

We will provide a Hugging Face evaluation Space where users can submit predictions on the hidden test set and receive scores. The Space is not yet live — in the interim, please contact [amritam@nvidia.com](mailto:amritam@nvidia.com) to score your samples. We will also release a judge model in the near future to make evaluation more accessible.

## Quickstart

```python
from datasets import load_dataset
from huggingface_hub import snapshot_download
import os, soundfile as sf

repo_dir = snapshot_download("nvidia/video-full-duplex-benchmark", repo_type="dataset")
ds = load_dataset("nvidia/video-full-duplex-benchmark")        # ds["validation"], ds["test"]

row = ds["test"][0]
audio_path = os.path.join(repo_dir, row["audio_file_path"])
video_path = os.path.join(repo_dir, row["video_file_path"])
audio, sr = sf.read(audio_path)
print(row["system_prompt"][:120], "...")
print(f"{row['bucket']:10s} {row['duration_s']:.2f}s  audio={audio.shape}")
```

The audio/video columns are **plain string paths**, not HF `Audio` / `Video` features — consumers resolve them against the repo root and load with their decoder of choice. (`pyav` / `imageio-ffmpeg` are recommended for the VP9-in-MP4 video; some `decord` builds reject that codec combination.)

## Ethical Considerations

NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. When downloaded or used in accordance with our terms of service, developers should work with their internal developer teams to ensure this dataset meets requirements for the relevant industry and use case and addresses unforeseen product misuse.

Please report quality, risk, security vulnerabilities or NVIDIA AI Concerns [here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/).

## Citation

```bibtex
@misc{mazumdar2026videofdb,
      title         = {VideoFDB: Evaluating Full-Duplex Vision-Speech Capabilities in Conversational Agents},
      author        = {Mazumdar, Amrita and Park, Seonwook and Roy, Rajarshi and Srihari, Nikhil and Wang, Shengze and Zhou, Yuhao and Wang, Julia and Nagano, Koki and De Mello, Shalini},
      year          = {2026},
      eprint        = {2605.30256},
      archivePrefix = {arXiv},
      primaryClass  = {cs.CV},
      url           = {https://arxiv.org/abs/2605.30256}
}
```