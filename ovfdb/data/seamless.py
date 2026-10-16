"""Seamless Interaction data layer (plans/WS1-data-seamless.md).

Per-file HTTPS access to Meta's public mirror; no auth, no 50 GB tars.
URL scheme verified 2026-10-15 against facebookresearch/seamless_interaction
`src/seamless_interaction/fs.py`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

import httpx
import pandas as pd

from ovfdb.schema import Bucket, DynamicType, Sample, Segment, Word

MIRROR = "https://dl.fbaipublicfiles.com/seamless_interaction"
FILELIST_URL = (
    "https://raw.githubusercontent.com/facebookresearch/seamless_interaction/main/assets/filelist.csv"
)
DATA_DIR = Path("data/seamless")

#: The mirror answers S3 ``AccessDenied`` (403) for keys that do not exist
#: (e.g. 3P-V on a file without annotations, movement on a file with
#: ``has_imitator_movement=0``); fs.py upstream treats 403 the same way.
_MISSING_STATUS = {403, 404}

# kind -> (subpath template, extension)
KINDS: dict[str, tuple[str, str]] = {
    "audio": ("audio", "wav"),
    "video": ("video", "mp4"),
    "vad": ("metadata/vad", "jsonl"),
    "transcript": ("metadata/transcript", "jsonl"),
    "3P-V": ("annotations/3P-V", "json"),
    "3P-IS": ("annotations/3P-IS", "json"),
    "3P-R": ("annotations/3P-R", "json"),
    "1P-IS": ("annotations/1P-IS", "json"),
    "1P-R": ("annotations/1P-R", "json"),
}

#: ``ALL_FEATURES`` for the per-frame feature groups, pinned verbatim from
#: ``src/seamless_interaction/constants.py`` (imported by fs.py) on 2026-10-15.
#: URL = {MIRROR}/{label}/{split}/{group}/{feature}/{file_id}.npy, 30 Hz rows.
#: Only files with ``has_imitator_movement=1`` in filelist.csv have the
#: ``movement`` / ``movement_v4`` groups on the mirror (403 otherwise); smplh and
#: boxes_and_keypoints exist for every file we probed.
#: Verified shapes/dtypes on V00_S0062_I00000137_P0092 (naturalistic/test,
#: 116 s -> 3480 frames), identical for ``movement`` and ``movement_v4``:
#:   emotion_valence (3480, 1) float64   emotion_arousal (3480, 1) float64
#:   gaze_encodings  (3480, 2) float64   head_encodings  (3480, 3) float64
#:   FAUValue        (3480, 24) float64  emotion_scores  (3480, 8) float64
#:   expression      (3480, 128) float64 is_valid        (3480, 1) float64
ALL_FEATURES: dict[str, tuple[str, ...]] = {
    "smplh": (
        "body_pose", "global_orient", "is_valid", "left_hand_pose", "right_hand_pose", "translation",
    ),
    "boxes_and_keypoints": ("box", "is_valid_box", "keypoints"),
    "movement": (
        "EmotionArousalToken", "emotion_valence", "EmotionValenceToken", "expression", "FAUToken",
        "frame_latent", "FAUValue", "gaze_encodings", "alignment_head_rotation", "head_encodings",
        "alignment_translation", "hypernet_features", "emotion_arousal", "is_valid", "emotion_scores",
    ),
    "movement_v4": (
        "head_encodings", "gaze_encodings", "expression", "frame_latent", "alignment_head_rotation",
        "alignment_translation", "emotion_scores", "emotion_valence", "emotion_arousal", "FAUValue",
        "FAUToken", "EmotionValenceToken", "EmotionArousalToken", "hypernet_features", "is_valid",
        "is_occluded", "pred_vertices",
    ),
}
MOVEMENT_FEATURES: tuple[str, ...] = ALL_FEATURES["movement"]
DEFAULT_MOVEMENT_FEATURES: tuple[str, ...] = (
    "emotion_valence", "emotion_arousal", "gaze_encodings", "head_encodings", "FAUValue",
)
MOVEMENT_HZ = 30.0

#: Quality gate: drop a file when more than this fraction of transcript words
#: lie outside every VAD region (the card warns ~10 % of interactions are
#: misaligned).
MAX_WORDS_OUTSIDE_VAD = 0.2


@dataclass
class Utterance:
    start: float
    end: float
    transcript: str
    words: list[Word]


@dataclass
class Annotation:
    annotation: str
    start_ts: float
    end_ts: float


def interaction_key(file_id: str) -> str:
    """'V03_S0503_I00000074_P2454' -> 'V03_S0503_I00000074'."""
    return file_id.rsplit("_P", 1)[0]


@lru_cache(maxsize=4)
def load_filelist(cache: Path = DATA_DIR / "filelist.csv") -> pd.DataFrame:
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", FILELIST_URL, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with cache.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    df = pd.read_csv(cache)
    df["interaction_key"] = df["file_id"].map(interaction_key)
    df["participant"] = df["file_id"].str.rsplit("_P", n=1).str[-1]
    return df


def pairs(label: str = "naturalistic", split: str = "test", require_3p: bool = False) -> list[tuple[str, str]]:
    """Interaction pairs (file_id_a, file_id_b) with both participants present."""
    df = load_filelist()
    df = df[(df["label"] == label) & (df["split"] == split)]
    if require_3p:
        df = df[df["has_annotation_3p"] == 1]
    out = []
    for _, g in df.groupby("interaction_key"):
        ids = sorted(g["file_id"].tolist())
        if len(ids) == 2:
            out.append((ids[0], ids[1]))
    return out


def url_for(file_id: str, kind: str, label: str, split: str) -> str:
    sub, ext = KINDS[kind]
    return f"{MIRROR}/{label}/{split}/{sub}/{file_id}.{ext}"


def local_path(file_id: str, kind: str, label: str, split: str) -> Path:
    sub, ext = KINDS[kind]
    return DATA_DIR / "raw" / label / split / sub / f"{file_id}.{ext}"


def _label_split(file_id: str) -> tuple[str, str]:
    df = load_filelist()
    row = df[df["file_id"] == file_id]
    if row.empty:
        raise KeyError(f"{file_id} not in filelist")
    return row.iloc[0]["label"], row.iloc[0]["split"]


def _download(url: str, dst: Path) -> bool:
    """Stream ``url`` to ``dst`` atomically. False when the mirror has no such key."""
    if dst.exists():
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
        if r.status_code in _MISSING_STATUS:
            return False
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(dst)
    return True


def fetch(file_id: str, kinds: tuple[str, ...] = ("audio", "vad", "transcript", "3P-V")) -> dict[str, Path]:
    """Download the requested kinds for one participant file (idempotent).

    Kinds the mirror does not have for this file (e.g. 3P-V on an
    un-annotated file) are left out of the returned dict.
    """
    label, split = _label_split(file_id)
    out: dict[str, Path] = {}
    for kind in kinds:
        dst = local_path(file_id, kind, label, split)
        if _download(url_for(file_id, kind, label, split), dst):
            out[kind] = dst
    return out


# --- movement features (30 Hz .npy) ------------------------------------------

def movement_url(file_id: str, feature: str, label: str, split: str, group: str = "movement") -> str:
    return f"{MIRROR}/{label}/{split}/{group}/{feature}/{file_id}.npy"


def movement_path(file_id: str, feature: str, label: str, split: str, group: str = "movement") -> Path:
    return DATA_DIR / "raw" / label / split / group / feature / f"{file_id}.npy"


def has_movement(file_id: str) -> bool:
    """True when filelist.csv flags the file as having movement features on the mirror."""
    df = load_filelist()
    row = df[df["file_id"] == file_id]
    if row.empty:
        raise KeyError(f"{file_id} not in filelist")
    return int(row.iloc[0]["has_imitator_movement"]) == 1


def fetch_movement(
    file_id: str,
    features: tuple[str, ...] = DEFAULT_MOVEMENT_FEATURES,
    group: str = "movement",
) -> dict[str, Path]:
    """Download per-frame ``.npy`` features for one file (idempotent).

    ``group`` is ``"movement"`` or ``"movement_v4"``; feature names must be in
    ``ALL_FEATURES[group]``. Features absent on the mirror (every one of them
    when ``has_imitator_movement=0``) are left out of the result rather than
    raising, so callers can ``len(result) == 0`` to detect "no movement data".
    """
    if group not in ALL_FEATURES:
        raise KeyError(f"unknown feature group {group!r}; expected one of {sorted(ALL_FEATURES)}")
    bad = [f for f in features if f not in ALL_FEATURES[group]]
    if bad:
        raise KeyError(f"unknown {group} feature(s) {bad}; expected a subset of {ALL_FEATURES[group]}")
    label, split = _label_split(file_id)
    out: dict[str, Path] = {}
    for feature in features:
        dst = movement_path(file_id, feature, label, split, group)
        if _download(movement_url(file_id, feature, label, split, group), dst):
            out[feature] = dst
    return out


def load_movement(file_id: str, features: tuple[str, ...] = DEFAULT_MOVEMENT_FEATURES, group: str = "movement"):
    """``fetch_movement`` + ``np.load`` -> {feature: ndarray[(n_frames, dim), float64]} at 30 Hz."""
    import numpy as np

    return {k: np.load(p, allow_pickle=False) for k, p in fetch_movement(file_id, features, group).items()}


# --- parsers ----------------------------------------------------------------

def read_vad(path: Path) -> list[Segment]:
    segs = []
    for line in path.read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            segs.append(Segment(start=float(d["start"]), end=float(d["end"])))
    return sorted(segs, key=lambda s: s.start)


def read_transcript(path: Path) -> list[Utterance]:
    """Words whose forced alignment failed (``"start": null``, typically
    numerals like ``"10,"``) are dropped; utterance-level times are always set."""
    utts = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        words = [
            Word(text=w["word"], start=float(w["start"]), end=float(w["end"]))
            for w in d.get("words", [])
            if w.get("start") is not None and w.get("end") is not None
        ]
        utts.append(Utterance(start=float(d["start"]), end=float(d["end"]), transcript=d.get("transcript", ""), words=words))
    return sorted(utts, key=lambda u: u.start)


def read_annotations(path: Path) -> list[Annotation]:
    """3P-V / 3P-IS / ... files are JSON-lines despite the .json extension."""
    anns = []
    for line in path.read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            anns.append(Annotation(annotation=d["annotation"], start_ts=float(d["start_ts"]), end_ts=float(d["end_ts"])))
    return sorted(anns, key=lambda a: a.start_ts)


def transcript_words(utts: list[Utterance]) -> list[Word]:
    """Flatten utterances into one time-ordered word list."""
    return sorted((w for u in utts for w in u.words), key=lambda w: (w.start, w.end))


# --- quality gate -------------------------------------------------------------

def words_outside_vad_frac(words: list[Word], vad: list[Segment]) -> float:
    """Fraction of words that overlap no VAD region at all (pure; 0.0 when no words)."""
    if not words:
        return 0.0
    segs = sorted(vad, key=lambda s: s.start)
    outside = 0
    j = 0
    for w in sorted(words, key=lambda w: w.start):
        while j < len(segs) and segs[j].end < w.start:
            j += 1
        if j >= len(segs) or segs[j].start > w.end:
            outside += 1
    return outside / len(words)


def pair_is_consistent(user_id: str, partner_id: str | None = None,
                       max_outside: float = MAX_WORDS_OUTSIDE_VAD) -> bool:
    """Reject files whose transcript and VAD disagree grossly (misaligned timestamps).

    A file passes when it has both a VAD and a transcript and at most
    ``max_outside`` of its words fall outside every VAD region. With
    ``partner_id`` both sides must pass.
    """
    for fid in (user_id, partner_id) if partner_id else (user_id,):
        got = fetch(fid, ("vad", "transcript"))
        if "vad" not in got or "transcript" not in got:
            return False
        words = transcript_words(read_transcript(got["transcript"]))
        if not words or words_outside_vad_frac(words, read_vad(got["vad"])) > max_outside:
            return False
    return True


# --- ffmpeg trimming ----------------------------------------------------------

AUDIO_SR = 16000
VIDEO_SHORT_SIDE = 720   # mirror videos are 2160x3840 portrait; 720p = 720x1280 here
VIDEO_FPS = 30


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH")
    return exe


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({p.returncode}): {p.stderr[-2000:]}")


def media_duration(path: Path | str) -> float:
    """Container duration in seconds via ffprobe."""
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe not found on PATH")
    p = subprocess.run(
        [exe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(p.stdout.strip())


def trim_audio(src: Path, dst: Path, t0: float, t1: float) -> Path:
    """[t0, t1] of ``src`` -> 16 kHz mono pcm_s16le wav."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run([
        _ffmpeg(), "-y", "-v", "error", "-nostdin",
        "-ss", f"{t0:.3f}", "-i", str(src), "-t", f"{t1 - t0:.3f}",
        "-vn", "-ac", "1", "-ar", str(AUDIO_SR), "-c:a", "pcm_s16le", str(dst),
    ])
    return dst


def trim_video(src: Path, dst: Path, t0: float, t1: float) -> Path:
    """[t0, t1] of ``src`` -> H.264 yuv420p, short side 720, 30 fps, faststart; AAC audio kept."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    short = VIDEO_SHORT_SIDE
    scale = f"scale=w='if(gt(iw,ih),-2,{short})':h='if(gt(iw,ih),{short},-2)'"
    _run([
        _ffmpeg(), "-y", "-v", "error", "-nostdin",
        "-ss", f"{t0:.3f}", "-i", str(src), "-t", f"{t1 - t0:.3f}",
        "-vf", f"{scale},fps={VIDEO_FPS}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ac", "1",
        "-movflags", "+faststart", str(dst),
    ])
    return dst


def trim(user_id: str, partner_id: str, t0: float, t1: float, out_dir: Path | str,
         video: bool = True, tolerance: float = 0.25) -> dict[str, Path]:
    """Cut [t0, t1] (raw file seconds) of both participants into ``out_dir``.

    Fetches audio (+ video) for both ids if missing. Returns
    ``{"user_wav", "partner_wav"[, "user_mp4", "partner_mp4"]}``; every output
    is verified with ffprobe to be within ``tolerance`` s of ``t1 - t0``.
    """
    if not 0 <= t0 < t1:
        raise ValueError(f"need 0 <= t0 < t1, got {t0=} {t1=}")
    out_dir = Path(out_dir)
    kinds = ("audio", "video") if video else ("audio",)
    src_u, src_p = fetch(user_id, kinds), fetch(partner_id, kinds)
    for fid, got in ((user_id, src_u), (partner_id, src_p)):
        missing = [k for k in kinds if k not in got]
        if missing:
            raise FileNotFoundError(f"{fid}: mirror has no {missing}")
    out = {
        "user_wav": trim_audio(src_u["audio"], out_dir / "user.wav", t0, t1),
        "partner_wav": trim_audio(src_p["audio"], out_dir / "partner.wav", t0, t1),
    }
    if video:
        out["user_mp4"] = trim_video(src_u["video"], out_dir / "user.mp4", t0, t1)
        out["partner_mp4"] = trim_video(src_p["video"], out_dir / "partner.mp4", t0, t1)
    want = t1 - t0
    for key, path in out.items():
        got = media_duration(path)
        if abs(got - want) > tolerance:
            raise RuntimeError(f"{key} {path}: duration {got:.3f}s, expected {want:.3f}s (clip past end of file?)")
    return out


# --- Sample construction -----------------------------------------------------

def rebase_words(words: list[Word], t0: float, t1: float) -> list[Word]:
    """Words overlapping [t0, t1] with times made clip-relative and clamped (pure)."""
    out = []
    for w in words:
        if w.end <= t0 or w.start >= t1:
            continue
        out.append(Word(text=w.text, start=max(0.0, w.start - t0), end=min(t1 - t0, w.end - t0)))
    return sorted(out, key=lambda w: (w.start, w.end))


def to_sample(user_id: str, partner_id: str, t0: float, t1: float, bucket: Bucket | str,
              dynamic_type: DynamicType | str, dynamic_start_s: float, dynamic_end_s: float,
              clip_index: int, out_root: Path | str = "data/clips", **extra) -> Sample:
    """Trim a clip and build its ``Sample``.

    ``t0``/``t1``/``dynamic_start_s``/``dynamic_end_s`` are all in raw file
    seconds (the transcript/VAD/annotation timeline); the Sample stores the
    dynamic window re-based to clip time (clip start = 0). ``extra`` keys that
    are ``Sample`` fields (``system_prompt``, ``av_caption``, ...) are passed
    through; anything else (e.g. ``mining_rule``) lands in ``source_meta``.
    """
    bucket, dynamic_type = Bucket(bucket), DynamicType(dynamic_type)
    if not t0 <= dynamic_start_s <= dynamic_end_s <= t1:
        raise ValueError(f"dynamic window [{dynamic_start_s}, {dynamic_end_s}] must lie inside [{t0}, {t1}]")
    clip_id = f"{user_id}_c{clip_index:02d}"
    out_dir = Path(out_root) / clip_id
    paths = trim(user_id, partner_id, t0, t1, out_dir)
    tr = fetch(user_id, ("transcript",))
    words = transcript_words(read_transcript(tr["transcript"])) if "transcript" in tr else []
    label, split = _label_split(user_id)

    sample_fields = {f.name for f in fields(Sample)}
    passthrough = {k: v for k, v in extra.items() if k in sample_fields}
    meta = {
        "user_file_id": user_id, "partner_file_id": partner_id, "label": label, "split": split,
        "t0": float(t0), "t1": float(t1),
        "dynamic_start_raw_s": float(dynamic_start_s), "dynamic_end_raw_s": float(dynamic_end_s),
        **{k: v for k, v in extra.items() if k not in sample_fields},
    }
    return Sample(
        clip_id=clip_id,
        conversation_id=interaction_key(user_id),
        bucket=bucket,
        dynamic_type=dynamic_type,
        dynamic_start_s=float(dynamic_start_s - t0),
        dynamic_end_s=float(dynamic_end_s - t0),
        duration_s=float(t1 - t0),
        user_audio_path=str(paths["user_wav"]),
        user_video_path=str(paths["user_mp4"]),
        user_words=rebase_words(words, t0, t1),
        partner_audio_path=str(paths["partner_wav"]),
        partner_video_path=str(paths["partner_mp4"]),
        source="seamless",
        source_meta=meta,
        **passthrough,
    )
