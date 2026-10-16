# WS1 — Seamless data layer

**Goal:** fetch, pair, and trim Seamless Interaction files into `Sample`s.
**Depends on:** WS0. **Unblocks:** WS2. **Est.:** 2 h.
**Files:** `ovfdb/data/seamless.py`, `tests/test_seamless.py`.

## Deliverables
1. `load_filelist()` — download + cache `assets/filelist.csv` (GitHub raw) to
   `data/seamless/filelist.csv`; return a DataFrame. Add `interaction_key`
   (= `V_S_I` prefix) and `participant` columns.
2. `pairs(label="naturalistic", split="test", require_3p=False)` → list of
   `(file_id_a, file_id_b)` with both participants present.
3. `fetch(file_id, kinds=("audio","vad","transcript","3P-V"))` — HTTPS GET from
   `dl.fbaipublicfiles.com` into `data/seamless/raw/{label}/{split}/{kind}/`,
   idempotent, with progress for video (180 MB). Video is a separate kind;
   never fetch it unless a candidate clip needs it.
4. `fetch_movement(file_id, features=("emotion_valence","emotion_arousal","gaze_encodings","head_encodings","FAUValue"))`
   — pin the exact `ALL_FEATURES` names from
   `src/seamless_interaction/fs.py` (fetch once, store the dict in the module).
5. Parsers: `read_vad(file_id) -> list[Segment]`, `read_transcript(file_id) -> list[Utterance]`
   (words with start/end), `read_3pv(file_id) -> list[Annotation]` (file is
   JSON-lines despite `.json`).
6. `trim(file_id_user, file_id_partner, t0, t1, out_dir) -> (user_wav_16k, user_mp4, partner_wav_16k, partner_mp4)`
   via ffmpeg (`-ss t0 -to t1`, audio → 16 kHz mono pcm_s16le, video → H.264
   720p 30 fps). Keep both sides: the partner's audio is the human-GT "agent".
7. `to_sample(...)` building a `Sample` (see `ovfdb/schema.py`) with
   `source="seamless"`, times re-based so clip start = 0.

## Acceptance
- `uv run pytest tests/test_seamless.py` passes with network (mark `@network`).
- `uv run ovfdb seamless fetch V03_S0503_I00000074_P2454 --kinds vad,transcript,3P-V`
  writes three files; parsers return non-empty lists with monotone times.
- `uv run ovfdb seamless trim V03_S0503_I00000074_P2454 V03_S0503_I00000074_P2455 60 100`
  writes 4 media files; ffprobe durations ≈ 40 s.

## Notes
- Prefer `naturalistic/test` (39 files with 3P-V) and `naturalistic/train` for
  volume. Skip `improvised`.
- Cache aggressively; a full interaction pair is ~430 MB with video.
- The card warns ~10 % of interactions have misaligned timestamps; drop a pair
  if VAD and transcript disagree grossly (e.g. words outside any VAD region
  > 20 % of the time).
