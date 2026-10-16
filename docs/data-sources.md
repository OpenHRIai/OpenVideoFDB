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
  **As shipped (release 1.0.0, verified 2026-10-16):** the user side is `speaker1` *or* `speaker2` per
  row (`audio_file_path`); the other speaker's files exist for only 3 of the 8 validation clips (4 of 11
  rows: Laughter P+G, Nonverbal Backchanneling P+G) and for no test clip, so the human reference is
  computable on those 4 rows only. wav is **32 kHz** PCM16 mono (card says 16 kHz; the harness
  resamples); mp4 is VP9 1280x720 30 fps with **Opus** audio (PyAV decodes it; `ensure_h264` exists
  for decoders that cannot). `user_transcript_chunks` = `[{"text", "timestamp": [start, end]}]`.
  `agent_channel` is empty on validation. Windows are long (e.g. Turn-taking 1–35 s, Verbal
  Backchanneling 21–35 s, Face Emotion 11–20 s), unlike our 1–2 s mined windows. Captions are
  600–1000 chars (ours ≈ 2500). Test: 226 rows, 202 distinct user files, durations 14–142 s (median 46).
  Loader: `ovfdb nvidia snapshot|load|manifest` (`ovfdb/data/nvidia.py`); manifests
  `manifest/nvidia_*.jsonl` are git-ignored.
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
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/video/{file_id}.mp4          # H.264 **2160x3840 portrait** 29.97 fps (card says 1080p; mirror is 4K), ~180 MB for ~2.5 min
  https://dl.fbaipublicfiles.com/seamless_interaction/{label}/{split}/audio/{file_id}.wav          # 48 kHz pcm_f32le mono, denoised, ~33 MB
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
- **Missing keys return HTTP 403 (S3 AccessDenied), not 404.** `fetch()` treats both as absent.
- **Movement features (`movement`, `movement_v4`) exist only for files with
  `has_imitator_movement=1`.** None of the 39 naturalistic/test 3P-annotated files
  have them; 122/504 in naturalistic/train do. `smplh` and `boxes_and_keypoints`
  exist regardless. Gate with `seamless.has_movement(file_id)`. Verified shapes
  (30 Hz rows, float64): emotion_valence (T,1), emotion_arousal (T,1),
  gaze_encodings (T,2), head_encodings (T,3), FAUValue (T,24), emotion_scores (T,8),
  expression (T,128), is_valid (T,1). Exact names pinned in `ALL_FEATURES` in
  `ovfdb/data/seamless.py`.
- Transcript words whose forced alignment failed have `start: null` (numerals);
  `read_transcript` drops them.
- Trim cost ≈ 0.25 s wall per clip-second (4K decode); `-hwaccel videotoolbox` if
  mining hundreds of clips.
- Known noise (from the card): ~10 % of interactions have misaligned
  start/end; occasional participant-id errors; variable site quality.
- Recording setup: in-person, face-to-face, one camera per participant, both
  looking at each other. Not a video call — see `docs/protocol.md` §10.

## C. Licensing summary for what we publish
- Code: MIT (ours).
- Manifest (file_id + timestamps + labels + prompts) and trimmed Seamless clips:
  CC-BY-NC 4.0 with attribution to Meta's Seamless Interaction dataset.
- NVIDIA data: loader only; never copy media or annotations into the repo or HF.
