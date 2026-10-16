# Release announcement drafts (2026-10-16, v0.1.0)

Facts to keep straight: NVIDIA published the VideoFDB dataset and protocol but no
evaluation code or scorer; this repo is an independent reimplementation; the human
reference matches on the test rows where it is computable (60 of 226); model numbers on
the full NVIDIA test split are not run yet; the open clip set is CC BY-NC; nothing from the
NVIDIA dataset is redistributed.

## LinkedIn

Can a video-call AI tell a thinking pause from a hand-over? Does it nod along, or talk over
you? NVIDIA's VideoFDB benchmark asks exactly that, with 11 conversational dynamics scored
on timing and an LLM judge. The dataset and protocol are public; the evaluation code was
not.

Today we're releasing OpenVideoFDB, an open implementation of the full pipeline:

- a real-time harness that streams a clip's audio and video into an agent (Gemini Live,
  OpenAI Realtime, your own) and records what it says and when;
- the paper's timing metrics and judge rubrics, ported verbatim and calibrated;
- an adapter for NVIDIA's gated dataset, and an open clip set mined from Meta's Seamless
  Interaction corpus for everyone else, with a human review page.

Where we can check it, it reproduces the paper: on the NVIDIA test rows that ship a human
partner channel, the human reference scores 4.22 overall vs the paper's 4.20, and the
Laughter category lands at 3.86 vs 3.86.

Two early observations, consistent across both data sources: current API models don't use
the video channel on these dynamics (audio-only scores as well or better), and none of them
produce a verbal "mhm" while you're still talking.

Code (MIT): github.com/OpenHRIai/OpenVideoFDB
Open clip manifests (CC BY-NC): huggingface.co/datasets/OpenHRI/open-videofdb
Paper: arxiv.org/abs/2605.30256

Full NVIDIA test-split model runs and the video-out (generation) judge are next. Issues and
PRs welcome, especially new agents.

## X / Twitter (thread)

1/ NVIDIA's VideoFDB benchmark asks whether a video-call agent reads pauses, nods and
laughs like a human listener. Dataset + protocol are public, the eval code wasn't. We
reimplemented it, open source: github.com/OpenHRIai/OpenVideoFDB

2/ What's in it: a real-time harness (Gemini Live, OpenAI Realtime, bring your own), the
paper's timing metrics + judge rubrics verbatim, a loader for NVIDIA's gated data, and an
open clip set from Meta's Seamless Interaction with a human review UI.

3/ Does it match? On the NVIDIA test rows with a human partner channel, human reference =
4.22 overall (paper: 4.20); Laughter 3.86 vs 3.86. Same models on the public validation
rows land in the paper's range.

4/ Early findings on both data sources: today's API models don't use the video channel on
these dynamics (audio-only ≥ audio-visual), and no model says "mhm" while you're still
talking.

5/ MIT code, CC BY-NC manifests (no media re-hosted; clips re-cut locally from Meta's
mirror). Next: full NVIDIA test-split runs and the video-out judge. Agents welcome.
