# OpenVideoFDB

An open, runnable reimplementation of **VideoFDB** — NVIDIA's benchmark for
full-duplex audio-visual conversational agents
([paper](https://arxiv.org/abs/2605.30256), [dataset](https://huggingface.co/datasets/nvidia/video-full-duplex-benchmark),
[project page](https://research.nvidia.com/labs/amri/projects/video-fdb/)).

NVIDIA released the data (gated, non-redistributable) but, as of Oct 2026, no
evaluation code and no reference scores. This repo provides:

- **Open clips** mined from Meta's [Seamless Interaction](https://huggingface.co/datasets/facebook/seamless-interaction)
  dataset (CC-BY-NC 4.0) covering the same 11 conversational dynamics, with
  rule-based + VLM-verified annotation instead of a human annotation pipeline.
- **A real-time harness** that streams a clip's user audio/video into an agent
  (Gemini Live, OpenAI Realtime, avatar vendors via headless Chromium) and
  records the response.
- **The scoring protocol**: the paper's deterministic timing metrics
  (TOR-Alignment, latency) and its LLM-as-judge rubrics, ported verbatim.
- **An adapter for NVIDIA's dataset**, so the same harness runs the real
  benchmark locally if you have access.

Status: scaffold + plan. See `PLAN.md`, `STATUS.md`, `plans/`.

## Quick start (target interface)
```bash
uv sync
cp .env.example .env            # fill keys
uv run ovfdb mine --dynamics all                 # → manifest/ovfdb_v0.jsonl + data/clips/
uv run ovfdb run manifest/ovfdb_v0.jsonl --provider gemini_live --mode av
uv run ovfdb score runs/gemini_live_av
uv run ovfdb report runs/gt runs/random runs/gemini_live_av
```

## Layout
```
ovfdb/schema.py        shared contract: Sample, AgentRun, protocol tables
ovfdb/data/            seamless.py (open clips), nvidia.py (gated reference)
ovfdb/mine/            candidate finders, VLM verify, clip trimming, prompts
ovfdb/harness/         real-time streamer, recorder, providers/
ovfdb/score/           asr, timing (App. C.2), judge (App. F), report
docs/protocol.md       the VideoFDB protocol, condensed
docs/data-sources.md   dataset layouts, URLs, licences
docs/reference/        verbatim paper text (CC BY 4.0) and dataset cards
plans/WS*.md           one spec per workstream
```

## Deviations from the paper
See `docs/protocol.md` §10. Numbers from this harness are not comparable to
NVIDIA's leaderboard; validity is shown by human-GT vs random separation and
cross-judge agreement.

## Licences
Code MIT. Seamless-derived clips and manifest CC-BY-NC 4.0 (attribution: Meta
Seamless Interaction). NVIDIA data is never redistributed here.

## Citation
```bibtex
@misc{mazumdar2026videofdb, title={VideoFDB: Evaluating Full-Duplex Vision-Speech Capabilities in Conversational Agents},
  author={Mazumdar, Amrita and Park, Seonwook and Roy, Rajarshi and Srihari, Nikhil and Wang, Shengze and Zhou, Yuhao and Wang, Julia and Nagano, Koki and De Mello, Shalini},
  year={2026}, eprint={2605.30256}, archivePrefix={arXiv}}
@article{seamless_interaction, title={Seamless Interaction: Dyadic Audiovisual Motion Modeling and Large-Scale Dataset}, author={Agrawal, Vasu and others}, year={2025}}
```
