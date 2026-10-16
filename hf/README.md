---
license: cc-by-nc-4.0
task_categories:
  - audio-classification
  - video-classification
language:
  - en
tags:
  - conversational-ai
  - full-duplex
  - turn-taking
  - benchmark
  - videofdb
  - seamless-interaction
pretty_name: OpenVideoFDB (manifests)
size_categories:
  - n<1K
---

# OpenVideoFDB manifests

Clip manifests for **OpenVideoFDB**, an open implementation of NVIDIA's VideoFDB benchmark
for full-duplex audio-visual conversational agents
([code](https://github.com/OpenHRIai/OpenVideoFDB) · [paper](https://arxiv.org/abs/2605.30256)).

This dataset contains **no media**. Each row names a window inside a public recording of
Meta's [Seamless Interaction](https://huggingface.co/datasets/facebook/seamless-interaction)
corpus; the clips are re-cut locally and deterministically with
`uv run ovfdb rebuild --manifest <file>`.

## Files

| file | rows | what |
|---|---|---|
| `ovfdb_v0.jsonl` | 118 | first mined set: 5 dialogue dynamics (60 rows) + 6 nonverbal dynamics (58 rows). Day-1 windows were selected using the partner's reaction, so the human reference passes the timing rules by construction; kept for reproducibility of `results/v0_summary*.md`. |
| `ovfdb_v1.jsonl` | 60 | the 5 dialogue dynamics re-mined with user-cue-only rules and fixed post-cue windows. |
| `ovfdb_v1_reviewed.jsonl` | 53 | v1 after a human review (7 rejects dropped). Use this one. |
| `reviews/ovfdb_v1.jsonl` | 56 | the raw human decisions (accept / reject / unsure, notes, window fixes). |

## Row schema (one row = one clip × bucket)

`clip_id` (Seamless `file_id` + `_cNN`), `conversation_id`, `bucket` (perception |
generation), `dynamic_type` (one of the 11 VideoFDB dynamics), `dynamic_start_s`,
`dynamic_end_s`, `duration_s` (clip-relative seconds), `user_audio_path`,
`user_video_path`, `partner_audio_path`, `partner_video_path` (local paths after rebuild),
`system_prompt` (agent-side prompt, GPT-4o), `agent_speaks_first`, `av_caption`
(Gemini Flash caption of the side-by-side clip), `user_words` (Seamless word timings,
clip-relative), `source_meta` (`user_file_id`, `partner_file_id`, raw `t0`/`t1`,
`mining_rule`, rule evidence, VLM verdict, review decision).

## Dynamics

Perception: Pause Handling, Gaze Avoidance with Pause, Adaptor Handling, Nonverbal
Interruption, Face Emotion Display, Nonverbal Backchanneling, Laughter.
Generation: Face Emotion Display, Nonverbal Backchanneling, Laughter, Verbal Interruption,
Verbal Backchanneling, Turn-taking, Emotion Matching.

## Known limitations

- Source recordings are studio face-to-face conversations (two cameras), not video calls.
- Captions are machine-generated and occasionally attribute speech to the wrong speaker; the
  evaluation payload tells the judge to trust the per-channel transcripts for who said what.
- Verbal Backchanneling windows in v1 are breath points inside long user turns; real
  listeners say "mhm" there only ~10 % of the time (the paper's annotated windows give 69 %).
- Audio bleed between the two microphones can make a partner's laugh look like the user's.

## Licence and attribution

CC BY-NC 4.0, the licence of the source corpus. Please attribute Meta AI's Seamless
Interaction dataset (Agrawal et al., 2025) and cite the VideoFDB paper
(arXiv 2605.30256). The NVIDIA VideoFDB dataset itself is gated and non-redistributable and
is not part of this release.
