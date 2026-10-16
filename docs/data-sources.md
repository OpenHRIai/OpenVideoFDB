# Data sources

## A. NVIDIA `nvidia/video-full-duplex-benchmark` (the reference)
- HF dataset, **gated** (form + per-user manual approval), NVIDIA Evaluation
  License: non-commercial evaluation only, **no redistribution**. Request access
  at https://huggingface.co/datasets/nvidia/video-full-duplex-benchmark .
- ~5 GB, 432 files. Layout:
  ```
  0_metadata_{validation,test}.parquet      # 11 / 226 rows
  0_annotations_{validation,test}.parquet   # same rows, judge inputs
  README.md  LICENSE.md  "Video-Full-Duplex-Benchmark Data Card.docx"
  <id>/<sample_id>/speaker{1,2}.{wav,mp4}   # 16 kHz mono wav; VP9-in-mp4 (use pyav/imageio-ffmpeg, not decord)
  ```
  Validation ships both speakers; test ships only the user side (`speaker1`).
- `0_metadata_*`: `id`, `sample_id`, `bucket` (perception|generation),
  `duration_s`, `audio_file_path`, `video_file_path`, `system_prompt`.
- `0_annotations_*` (join on id, sample_id, bucket): `dynamic_type`,
  `dynamic_start_s`, `dynamic_end_s`, `agent_speaks_first` (bool),
  `agent_channel` (L|R|""), `qwen_caption_full` (AV caption for the judge),
  `user_transcript_chunks` (JSON list of `{text, timestamp}` word-level ASR).
- Multiple rows can share a `sample_id` (same clip in both buckets): 237 rows,
  180 distinct clips.
- Official scoring: not released. Email amritam@nvidia.com with per-sample
  outputs; an HF Space and a judge model are "coming".
- Full card: `docs/reference/nvidia_dataset_card.md`. Leaderboard incl. the
  newer Tavus Griffin Lite rows: `docs/reference/nvidia_project_page_leaderboard.txt`.

## B. Meta `facebook/seamless-interaction` (our open source of clips)
- CC-BY-NC 4.0. Not gated. 4,000+ h, two labels: `naturalistic` (use this) and
  `improvised` (actors; avoid). Splits dev/test/train.
- Every file is individually fetchable (no auth) from the public mirror:
  ```
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/video/{file_id}.mp4          # H.264 1080p 30 fps, ~180 MB for ~2.5 min
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/audio/{file_id}.wav          # 48 kHz 16-bit, denoised, ~33 MB
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/metadata/vad/{file_id}.jsonl
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/metadata/transcript/{file_id}.jsonl
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/annotations/{3P-V|3P-IS|3P-R|1P-IS|1P-R}/{file_id}.json
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/{smplh|boxes_and_keypoints|movement|movement_v4}/{feature}/{file_id}.npy
  ```
  (URL scheme from `src/seamless_interaction/fs.py` in the GitHub repo; also
  WebDataset tars on HF at `{label}/{split}/{batch:04d}/{archive:04d}.tar`, ~1 GB each.)
- `file_id` = `V<vendor>_S<session>_I<interaction>_P<participant>`. The two
  participants of one interaction share `V_S_I` and differ in `P`. Pair them
  via `assets/filelist.csv` from the GitHub repo
  (`https://raw.githubusercontent.com/facebookresearch/seamless_interaction/main/assets/filelist.csv`,
  129k rows: file_id,label,split,batch_idx,archive_idx,has_imitator_movement,has_annotation_1p,has_annotation_3p).
- Counts with 3rd-party annotations (`has_annotation_3p=1`): naturalistic
  test 39, naturalistic train 504, improvised dev 20 / test 30 / train 1070.
  Naturalistic dev has none, so for annotation-driven mining use naturalistic
  **test** (39 files) and train (504).
- Formats (verified 2026-10-15 on `V03_S0503_I00000074_P2454`, naturalistic/test):
  - `vad.jsonl`: one `{"start": s, "end": s}` per line (seconds; speech regions).
  - `transcript.jsonl`: one utterance per line
    `{"words":[{"word","start","end","score"}], "start", "end", "transcript"}`.
  - `3P-V.json`: *JSON lines* (despite the extension), e.g.
    `{"annotation": "The participant rubs their head with their right hand.", "start_ts": 61, "end_ts": 66}`.
    `3P-IS` = internal state ("feels self-reflective and uncertain"), same shape.
- Movement features (npz keys when loaded via the HF tar; as separate `.npy`
  on the mirror): `movement:emotion_arousal`, `movement:emotion_valence`,
  `movement:emotion_scores`, `movement:expression`, `movement:FAUToken/FAUValue`,
  `movement:gaze_encodings`, `movement:head_encodings`, `movement:frame_latent`,
  `movement:alignment_head_rotation`, `movement:alignment_translation`,
  `boxes_and_keypoints:*`, `smplh:*`. 30 Hz. Exact feature names for the
  per-file mirror come from `ALL_FEATURES` in `fs.py` — fetch and pin it in WS1.
- Known noise (from the card): ~10 % of interactions have misaligned
  start/end; occasional participant-id errors; variable site quality.
- Recording setup: in-person, face-to-face, one camera per participant, both
  looking at each other. Not a video call — see `docs/protocol.md` §10.

## C. Licensing summary for what we publish
- Code: MIT (ours).
- Manifest (file_id + timestamps + labels + prompts) and trimmed Seamless clips:
  CC-BY-NC 4.0 with attribution to Meta's Seamless Interaction dataset.
- NVIDIA data: loader only; never copy media or annotations into the repo or HF.
