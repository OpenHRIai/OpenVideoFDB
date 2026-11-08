"""10 Hz face tracks from a single-face video (WS10 phase 0, `plans/WS10-cue-judge.md` §5).

One face per file (avatar recordings, a Seamless participant file, a CANDOR participant video).
MediaPipe Face Landmarker gives, per sampled frame, 52 expression blendshapes and a head
transformation matrix; from the landmarks we add an iris offset (gaze proxy), eye openness,
a geometric mouth openness and the face box. The same extractor must run on the human
training videos and on the avatar videos so the judge sees one feature space.

    uv run python -m ovfdb.score.lanes agent.mp4 --out runs_nv/x/<row>/face
    uv run python -m ovfdb.score.lanes a.mp4 b.mp4 --out tracks/      # -> tracks/<stem>/face.npy

Output per video: ``face.npy`` float32 ``(T, len(FEATURES))`` at ``fps`` Hz, NaN on frames
without a face (column ``found`` is 0 there), and ``face.json`` with the column names, the
sampling grid, the found rate, the native video geometry and ``av_sync_offset_ms`` (the lag
that best aligns ``jawOpen`` with the file's own audio envelope; positive = audio leads video).

Time base: row ``k`` is the first decoded frame whose presentation time ``t`` satisfies
``floor(t * fps) == k``, with ``t`` relative to the container start (the audio clock), so the
tracks line up with ``agent.wav`` / the participant's audio without any extra offset.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FPS = 10
DEFAULT_MODEL = Path("data/models/face_landmarker.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
             "float16/latest/face_landmarker.task")
MAX_WIDTH = 640          # frames wider than this are downscaled before detection (face ≥ 1/4 of frame in all our sources)
SYNC_MAX_LAG_S = 2.0     # AV-sync search window

#: MediaPipe's 52 blendshape names in its canonical order (ARKit naming).
BLENDSHAPES = [
    "_neutral", "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff",
    "cheekSquintLeft", "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft",
    "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight",
    "mouthStretchLeft", "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
]
#: Geometry from the transformation matrix and the landmarks.
GEOMETRY = ["head_yaw", "head_pitch", "head_roll", "head_tx", "head_ty", "head_tz",
            "iris_dx", "iris_dy", "eye_open", "mouth_open", "face_cx", "face_cy", "face_w"]
FEATURES = ["found"] + BLENDSHAPES + GEOMETRY
_BS_IX = {n: i for i, n in enumerate(BLENDSHAPES)}
_GEOM0 = 1 + len(BLENDSHAPES)

# Landmark indices (MediaPipe 478-point mesh). "Left"/"right" are the subject's.
L_EYE_INNER, L_EYE_OUTER, L_IRIS, L_LID_UP, L_LID_LO = 133, 33, 468, 159, 145
R_EYE_INNER, R_EYE_OUTER, R_IRIS, R_LID_UP, R_LID_LO = 362, 263, 473, 386, 374
LIP_UP_INNER, LIP_LO_INNER = 13, 14


def _euler(R: np.ndarray) -> tuple[float, float, float]:
    """(yaw, pitch, roll) in degrees: turn about vertical, nod about the ear axis, tilt about the view axis."""
    sy = float(np.hypot(R[0, 0], R[1, 0]))
    yaw = np.arctan2(-R[2, 0], sy)
    if sy > 1e-6:
        pitch, roll = np.arctan2(R[2, 1], R[2, 2]), np.arctan2(R[1, 0], R[0, 0])
    else:
        pitch, roll = np.arctan2(-R[1, 2], R[1, 1]), 0.0
    return float(np.degrees(yaw)), float(np.degrees(pitch)), float(np.degrees(roll))


def _iris_offset(lm, inner: int, outer: int, iris: int, roll_deg: float) -> tuple[float, float]:
    """Iris centre relative to the eye midpoint, in eye widths, de-tilted by the head roll."""
    a, b, c = lm[inner], lm[outer], lm[iris]
    w = float(np.hypot(a.x - b.x, a.y - b.y))
    if w < 1e-6:
        return 0.0, 0.0
    ox, oy = (c.x - (a.x + b.x) / 2) / w, (c.y - (a.y + b.y) / 2) / w
    ph = np.radians(roll_deg)
    return float(ox * np.cos(ph) + oy * np.sin(ph)), float(-ox * np.sin(ph) + oy * np.cos(ph))


def _eye_open(lm, up: int, lo: int, inner: int, outer: int) -> float:
    w = float(np.hypot(lm[inner].x - lm[outer].x, lm[inner].y - lm[outer].y))
    return 0.0 if w < 1e-6 else float(np.hypot(lm[up].x - lm[lo].x, lm[up].y - lm[lo].y) / w)


def frame_features(result) -> np.ndarray:
    """One row of ``FEATURES`` from a FaceLandmarker result; NaN row with found=0 when no face."""
    row = np.full(len(FEATURES), np.nan, np.float32)
    if not result.face_landmarks:
        row[0] = 0.0
        return row
    row[0] = 1.0
    lm = result.face_landmarks[0]
    if result.face_blendshapes:
        for cat in result.face_blendshapes[0]:
            i = _BS_IX.get(cat.category_name)
            if i is not None:
                row[1 + i] = cat.score
    yaw = pitch = roll = np.nan
    if result.facial_transformation_matrixes:
        m = np.asarray(result.facial_transformation_matrixes[0], dtype=np.float64).reshape(4, 4)
        yaw, pitch, roll = _euler(m[:3, :3])
        row[_GEOM0 + 3: _GEOM0 + 6] = m[:3, 3]
    row[_GEOM0: _GEOM0 + 3] = (yaw, pitch, roll)
    r = roll if np.isfinite(roll) else 0.0
    ldx, ldy = _iris_offset(lm, L_EYE_INNER, L_EYE_OUTER, L_IRIS, r)
    rdx, rdy = _iris_offset(lm, R_EYE_INNER, R_EYE_OUTER, R_IRIS, r)
    row[_GEOM0 + 6], row[_GEOM0 + 7] = (ldx + rdx) / 2, (ldy + rdy) / 2
    row[_GEOM0 + 8] = (_eye_open(lm, L_LID_UP, L_LID_LO, L_EYE_INNER, L_EYE_OUTER)
                       + _eye_open(lm, R_LID_UP, R_LID_LO, R_EYE_INNER, R_EYE_OUTER)) / 2
    scale = float(np.hypot(lm[L_EYE_OUTER].x - lm[R_EYE_OUTER].x, lm[L_EYE_OUTER].y - lm[R_EYE_OUTER].y))
    gap = float(np.hypot(lm[LIP_UP_INNER].x - lm[LIP_LO_INNER].x, lm[LIP_UP_INNER].y - lm[LIP_LO_INNER].y))
    row[_GEOM0 + 9] = gap / scale if scale > 1e-6 else np.nan
    xs = np.fromiter((p.x for p in lm), float, len(lm)); ys = np.fromiter((p.y for p in lm), float, len(lm))
    row[_GEOM0 + 10], row[_GEOM0 + 11], row[_GEOM0 + 12] = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, xs.max() - xs.min()
    return row


def _landmarker(model: Path):
    import mediapipe as mp
    opts = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_faces=1,
        output_face_blendshapes=True, output_facial_transformation_matrixes=True,
        min_face_detection_confidence=0.5, min_face_presence_confidence=0.5, min_tracking_confidence=0.5)
    return mp.tasks.vision.FaceLandmarker.create_from_options(opts)


def ensure_model(model: Path = DEFAULT_MODEL) -> Path:
    if not model.exists():
        import httpx
        model.parent.mkdir(parents=True, exist_ok=True)
        log.info("fetching %s", MODEL_URL)
        with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=120) as r, open(model, "wb") as f:
            r.raise_for_status()
            f.writelines(r.iter_bytes())
    return model


def audio_envelope(path: Path, fps: int = FPS) -> np.ndarray | None:
    """RMS of the file's own audio per 1/fps block (mono, any rate); None when the file has no audio stream."""
    import av
    with av.open(str(path)) as c:
        if not c.streams.audio:
            return None
        s = c.streams.audio[0]
        res = av.AudioResampler(format="s16", layout="mono", rate=16000)
        chunks = []
        for fr in c.decode(s):
            for out in res.resample(fr):
                chunks.append(out.to_ndarray().reshape(-1).astype(np.float32) / 32768.0)
        for out in res.resample(None):
            chunks.append(out.to_ndarray().reshape(-1).astype(np.float32) / 32768.0)
    if not chunks:
        return None
    x = np.concatenate(chunks)
    n = 16000 // fps
    m = len(x) // n
    if m == 0:
        return None
    return np.sqrt((x[: m * n].reshape(m, n) ** 2).mean(1))


def av_sync_offset_ms(mouth: np.ndarray, env: np.ndarray | None, fps: int = FPS, max_lag_s: float = SYNC_MAX_LAG_S) -> float | None:
    """Lag (ms) of the audio envelope that best matches the mouth track; positive = audio leads video."""
    if env is None:
        return None
    n = min(len(mouth), len(env))
    m, a = np.nan_to_num(mouth[:n].astype(np.float64)), env[:n].astype(np.float64)
    if n < 5 * fps or m.std() < 1e-6 or a.std() < 1e-6:
        return None
    m = (m - m.mean()) / m.std(); a = (a - a.mean()) / a.std()
    L = int(max_lag_s * fps)
    lags = np.arange(-L, L + 1)
    corr = np.array([np.dot(m[max(0, k):n + min(0, k)], a[max(0, -k):n - max(0, k)]) / (n - abs(k)) for k in lags])
    return round(float(lags[int(np.argmax(corr))] * 1000 / fps), 1)


def extract(video: Path, out_dir: Path, *, fps: int = FPS, model: Path = DEFAULT_MODEL, max_width: int = MAX_WIDTH,
            sync: bool = True, start_s: float | None = None, end_s: float | None = None) -> dict:
    """Run the extractor on one video; writes ``face.npy`` + ``face.json`` into ``out_dir`` and returns the json dict.

    ``start_s`` / ``end_s`` restrict decoding to a window of the file (rows stay on the file's own time grid; rows
    before ``start_s`` are NaN with found=0)."""
    import av
    t_wall = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    lmk = _landmarker(ensure_model(model))
    rows: dict[int, np.ndarray] = {}
    meta: dict = {"video": str(video), "fps": fps, "features": FEATURES, "model": str(model)}
    with av.open(str(video)) as c:
        vs = c.streams.video[0]
        vs.thread_type = "AUTO"
        meta.update(width=vs.codec_context.width, height=vs.codec_context.height,
                    native_fps=float(vs.average_rate) if vs.average_rate else None,
                    video_start_s=float((vs.start_time or 0) * vs.time_base),
                    duration_s=float(vs.duration * vs.time_base) if vs.duration else (c.duration / 1e6 if c.duration else None))
        scale = min(1.0, max_width / vs.codec_context.width) if vs.codec_context.width else 1.0
        w = int(round(vs.codec_context.width * scale / 2) * 2); h = int(round(vs.codec_context.height * scale / 2) * 2)
        if start_s:
            c.seek(int(start_s / vs.time_base), stream=vs, backward=True, any_frame=False)
        import mediapipe as mp
        last_k, n_dec = -1, 0
        for fr in c.decode(vs):
            n_dec += 1
            t = float(fr.pts * vs.time_base) if fr.pts is not None else fr.time
            if t is None or (start_s is not None and t < start_s):
                continue
            if end_s is not None and t > end_s:
                break
            k = int(np.floor(t * fps + 1e-6))
            if k <= last_k:
                continue
            last_k = k
            img = fr.reformat(width=w, height=h, format="rgb24").to_ndarray() if scale < 1.0 else fr.to_ndarray(format="rgb24")
            res = lmk.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img)), round(k * 1000 / fps))
            rows[k] = frame_features(res)
    lmk.close()
    T = (last_k + 1) if last_k >= 0 else 0
    arr = np.full((T, len(FEATURES)), np.nan, np.float32)
    arr[:, 0] = 0.0
    for k, r in rows.items():
        arr[k] = r
    sampled = np.zeros(T, bool); sampled[list(rows)] = True
    meta.update(n_rows=T, n_sampled=int(sampled.sum()), n_decoded=n_dec,
                found_rate=float(arr[sampled, 0].mean()) if sampled.any() else 0.0,
                start_s=start_s, end_s=end_s, seconds=round(time.time() - t_wall, 1))
    if sync:
        try:
            env = audio_envelope(video, fps)
            meta["has_audio"] = env is not None
            meta["av_sync_offset_ms"] = av_sync_offset_ms(arr[:, 1 + _BS_IX["jawOpen"]], env, fps)
        except Exception as e:  # noqa: BLE001 — sync is diagnostic, never fatal
            meta["has_audio"], meta["av_sync_offset_ms"], meta["sync_error"] = None, None, str(e)
    np.save(out_dir / "face.npy", arr)
    (out_dir / "face.json").write_text(json.dumps(meta, indent=1))
    return meta


def load(out_dir: Path) -> tuple[np.ndarray, dict]:
    return np.load(out_dir / "face.npy"), json.loads((out_dir / "face.json").read_text())


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("videos", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="output dir (one video) or root for <stem>/ dirs")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--max-width", type=int, default=MAX_WIDTH)
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--no-sync", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for v in a.videos:
        out = a.out if len(a.videos) == 1 else a.out / v.stem
        m = extract(v, out, fps=a.fps, model=a.model, max_width=a.max_width, sync=not a.no_sync, start_s=a.start, end_s=a.end)
        log.info("%s: %d rows, found %.1f%%, sync %s ms, %.0fs", v.name, m["n_rows"], 100 * m["found_rate"],
                 m.get("av_sync_offset_ms"), m["seconds"])


if __name__ == "__main__":
    main()
