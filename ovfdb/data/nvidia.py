"""NVIDIA `nvidia/video-full-duplex-benchmark` adapter (plans/WS7-nvidia-adapter.md).

* `snapshot()` downloads the gated dataset (needs `HF_TOKEN` in `.env`) to `data/nvidia/`.
* `load(split)` joins `0_metadata_<split>` ⋈ `0_annotations_<split>` on `(id, sample_id, bucket)`
  and maps each row 1:1 onto `Sample` (`sample_id` → `clip_id`, `qwen_caption_full` →
  `av_caption`, `user_transcript_chunks` → `user_words`). The user is `speaker1` or `speaker2` per row (`audio_file_path`); when the
  other speaker's files are present (some validation clips: 3 of 8 in release 1.0.0) they become
  the human-GT partner channel. Test ships only the user's channel, so there is no human reference
  on test. Media as shipped: VP9 720p 30 fps mp4 with Opus audio, 32 kHz PCM16 mono wav.
* `ensure_h264(path)` writes an H.264 copy of a VP9-in-MP4 video under `data/nvidia/_h264/`
  for decoders that cannot read VP9 (our PyAV frame sampler can; the helper exists for others).
* `write_manifest_for(split, out)` emits an `ovfdb` manifest so the usual `run` / `score` /
  `report` commands work unchanged (`manifest/nvidia_<split>.jsonl` is git-ignored: the data
  and annotations are non-redistributable).

Only the loader lives in git; never commit anything from `data/nvidia/`.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from ovfdb.schema import Bucket, DynamicType, Sample, Word, write_manifest

log = logging.getLogger(__name__)

REPO_ID = "nvidia/video-full-duplex-benchmark"
ROOT = Path("data/nvidia")
H264_DIR = ROOT / "_h264"
SPLITS = ("validation", "test")


# --- download ------------------------------------------------------------------------

def _token() -> str | None:
    from dotenv import load_dotenv
    load_dotenv(".env", override=True)        # an empty HF_TOKEN exported by the shell must not win
    return (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
            or os.environ.get("HF_HUB_TOKEN") or None)


def snapshot(local_dir: str | Path = ROOT, *, validation_only: bool = False, split: str | None = None) -> Path:
    """Download the dataset (or the parquet tables + one split's media) into `local_dir`.

    `validation_only` fetches the tables and the 8 validation clips (~200 MB) for development.
    `split` restricts media to that split's sample dirs. Re-running only fetches missing files.
    """
    from huggingface_hub import snapshot_download

    tok = _token()
    if not tok:
        raise SystemExit("HF_TOKEN is not set in .env (the dataset is gated; put your Hugging Face token there)")
    local_dir = Path(local_dir)
    patterns: list[str] | None = None
    if validation_only or split:
        want = "validation" if validation_only else split
        # tables first, then only the media dirs that the split references
        snapshot_download(REPO_ID, repo_type="dataset", token=tok, local_dir=str(local_dir),
                          allow_patterns=["*.parquet", "*.md"])
        import pandas as pd
        meta = pd.read_parquet(local_dir / f"0_metadata_{want}.parquet")
        dirs = sorted({str(Path(p).parent) for p in meta["audio_file_path"]})
        patterns = ["*.parquet", "*.md"] + [f"{d}/*" for d in dirs]
    snapshot_download(REPO_ID, repo_type="dataset", token=tok, local_dir=str(local_dir), allow_patterns=patterns)
    return local_dir


# --- transcript ----------------------------------------------------------------------

def parse_transcript_chunks(raw: str | list | None) -> list[Word]:
    """`user_transcript_chunks` JSON → `Word`s. Each chunk is `{text, timestamp}`; `timestamp` is
    `[start, end]` (whisper/Parakeet style) or a single start time, in which case the word ends at
    the next chunk's start (or +0.3 s for the last one). Empty / unparsable → []."""
    if raw is None:
        return []
    chunks = raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            chunks = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(chunks, dict):
        chunks = chunks.get("chunks") or chunks.get("words") or []
    out: list[Word] = []
    starts: list[float | None] = []
    items: list[tuple[str, float | None, float | None]] = []
    for c in chunks or []:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or c.get("word") or "").strip()
        ts = c.get("timestamp")
        if ts is None:
            ts = (c.get("start"), c.get("end"))
        s = e = None
        if isinstance(ts, (list, tuple)):
            if len(ts) >= 1 and ts[0] is not None:
                s = float(ts[0])
            if len(ts) >= 2 and ts[1] is not None:
                e = float(ts[1])
        elif ts is not None:
            try:
                s = float(ts)
            except (TypeError, ValueError):
                s = None
        if not text or s is None:
            continue
        items.append((text, s, e))
        starts.append(s)
    for i, (text, s, e) in enumerate(items):
        if e is None or e < s:
            nxt = next((st for st in starts[i + 1:] if st is not None and st > s), None)
            e = nxt if nxt is not None else s + 0.3
        out.append(Word(text=text, start=round(s, 3), end=round(e, 3)))
    return out


# --- load ---------------------------------------------------------------------------

def _tables(split: str, root: Path):
    import pandas as pd
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    meta = pd.read_parquet(root / f"0_metadata_{split}.parquet")
    ann = pd.read_parquet(root / f"0_annotations_{split}.parquet")
    df = meta.merge(ann, on=["id", "sample_id", "bucket"], how="inner", validate="one_to_one")
    if len(df) != len(meta):
        log.warning("%s: %d metadata rows but %d joined rows", split, len(meta), len(df))
    return df


def _partner_paths(user_audio: Path, user_video: Path) -> tuple[str | None, str | None]:
    """speaker2 next to speaker1 (validation only); None when the other channel is not shipped."""
    def other(p: Path) -> Path | None:
        n = p.name
        if n.startswith("speaker1"):
            q = p.with_name("speaker2" + n[len("speaker1"):])
        elif n.startswith("speaker2"):
            q = p.with_name("speaker1" + n[len("speaker2"):])
        else:
            return None
        return q if q.exists() else None
    a, v = other(user_audio), other(user_video)
    return (str(a) if a else None), (str(v) if v else None)


def load(split: str = "validation", root: str | Path = ROOT) -> list[Sample]:
    """All rows of `split` as `Sample`s (one per (sample_id, bucket)); media paths resolved under `root`."""
    root = Path(root)
    if not (root / f"0_metadata_{split}.parquet").exists():
        raise FileNotFoundError(f"{root}/0_metadata_{split}.parquet not found; run `ovfdb nvidia snapshot` first")
    df = _tables(split, root)
    out: list[Sample] = []
    for r in df.itertuples(index=False):
        audio = root / str(r.audio_file_path)
        video = root / str(r.video_file_path)
        p_audio, p_video = _partner_paths(audio, video)
        out.append(Sample(
            clip_id=str(r.sample_id),
            conversation_id=str(r.id),
            bucket=Bucket(str(r.bucket)),
            dynamic_type=DynamicType(str(r.dynamic_type)),
            dynamic_start_s=float(r.dynamic_start_s),
            dynamic_end_s=float(r.dynamic_end_s),
            duration_s=float(r.duration_s),
            user_audio_path=str(audio),
            user_video_path=str(video),
            system_prompt=str(r.system_prompt or ""),
            agent_speaks_first=bool(r.agent_speaks_first),
            agent_channel=str(r.agent_channel or ""),
            av_caption=str(r.qwen_caption_full or ""),
            user_words=parse_transcript_chunks(r.user_transcript_chunks),
            partner_audio_path=p_audio,
            partner_video_path=p_video,
            source="nvidia",
            source_meta={"split": split, "id": str(r.id), "sample_id": str(r.sample_id)},
        ))
    return out


def write_manifest_for(split: str, out: str | Path | None = None, root: str | Path = ROOT) -> Path:
    """Write `manifest/nvidia_<split>.jsonl` (git-ignored) so `ovfdb run/score/report` can use it."""
    samples = load(split, root)
    dst = Path(out) if out else Path("manifest") / f"nvidia_{split}.jsonl"
    write_manifest(samples, dst)
    return dst


# --- media ---------------------------------------------------------------------------

def video_codec(path: str | Path) -> str:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=False)
    return p.stdout.strip()


def ensure_h264(path: str | Path, out_dir: str | Path = H264_DIR) -> Path:
    """Return an H.264 version of `path` (the file itself if already H.264), transcoding once into `out_dir`."""
    src = Path(path)
    if video_codec(src) in ("h264", "avc1"):
        return src
    dst = Path(out_dir) / src.parent.parent.name / src.parent.name / src.name
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(dst)]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg h264 transcode failed for {src}: {p.stderr[-800:]}")
    return dst
