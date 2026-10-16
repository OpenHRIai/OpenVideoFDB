# WS7 — NVIDIA dataset adapter

**Goal:** load `nvidia/video-full-duplex-benchmark` into `Sample`s so the same
harness/scorer runs on the real benchmark. **Depends on:** WS0 + HF access
approval. **Est.:** 1 h (+ waiting for approval).
**Files:** `ovfdb/data/nvidia.py`, `tests/test_nvidia.py` (skipped without data).

## Step 0 — today
Request access at https://huggingface.co/datasets/nvidia/video-full-duplex-benchmark
(fields: job title, affiliation, country; agree to the evaluation licence).
Note the date in `STATUS.md`.

## Deliverables
1. `snapshot(local_dir="data/nvidia")` via `huggingface_hub.snapshot_download`
   (needs `HF_TOKEN`). Allow `--validation-only` (small) for development.
2. `load(split) -> list[Sample]`: join `0_metadata_{split}` ⋈ `0_annotations_{split}`
   on `(id, sample_id, bucket)`; map columns 1:1 (`qwen_caption_full` →
   `av_caption`, `user_transcript_chunks` JSON → `user_words`). Media paths
   resolved against the snapshot root. Validation also has `speaker2` →
   `partner_audio_path` (human GT); test has none.
3. Transcode helper: VP9-in-MP4 can break some decoders — provide
   `ensure_h264(sample)` that writes an H.264 copy under `data/nvidia/_h264/`
   when needed by the streamer.

## Acceptance
- `uv run ovfdb nvidia load --split validation` prints 11 rows with all
  dynamics and non-empty captions/prompts.
- Human-GT calibration (WS5) on the 11 validation rows runs end-to-end.

## Reminder
Never commit or publish NVIDIA media/annotations. Keep everything under
`data/nvidia/` (git-ignored).
