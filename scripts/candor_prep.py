"""CANDOR: one processed archive -> per-participant 16 kHz audio, VAD regions and 10 Hz face tracks.

    uv run python scripts/candor_prep.py --archive data/candor/hf/data/processed_media_part_034.zip
    uv run python scripts/candor_prep.py --extracted data/candor/raw/processed_media_part_034 --conv <id>

Reads the archive layout documented on the dataset card (one folder per conversation with
``metadata.json``, ``processed/<conversation_id>.mp3`` stereo with one participant per channel,
``processed/<user_id>.mp4`` per participant, ``processed/channel_map.json``). Writes

    data/candor/proc/<conversation_id>/meta.json                 channel map, durations, offsets, probe info
    data/candor/proc/<conversation_id>/<user_id>/audio16.wav     this participant's channel, 16 kHz mono PCM16
    data/candor/proc/<conversation_id>/<user_id>/vad.json        Silero regions [[start, end], ...] (ovfdb.score.vad)
    data/candor/proc/<conversation_id>/<user_id>/face.npy|json   ovfdb.score.lanes tracks at 10 Hz

The video is read once and discarded afterwards when ``--delete-video`` is given (the Modal
path). CANDOR is licensed for commercial use but not redistributable: everything under
``data/candor`` stays local, and every output carries the conversation id in its path so
removals (REMOVALS.md in betterup/candor-tabular) can be honoured.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ovfdb.score import lanes, vad

log = logging.getLogger("candor_prep")
RAW = Path("data/candor/raw")
PROC = Path("data/candor/proc")


def unzip(archive: Path, raw: Path = RAW) -> Path:
    dest = raw / archive.stem
    marker = dest / ".extracted"
    if marker.exists():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(dest)
    marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    return dest


def conversations(extracted: Path) -> list[Path]:
    """Conversation folders: any dir that holds metadata.json (the zip may or may not nest a top-level folder)."""
    return sorted(p.parent for p in extracted.rglob("metadata.json"))


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,start_time,duration,nb_frames,channels,sample_rate:format=duration,start_time",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def channel_map(conv: Path) -> dict[str, str]:
    """{'L': user_id, 'R': user_id}, whatever orientation channel_map.json uses."""
    cm = json.loads((conv / "processed" / "channel_map.json").read_text())
    out: dict[str, str] = {}
    for k, v in cm.items():
        if isinstance(v, dict):                       # {"user_id": {"channel": "L", "side": "left"}} style
            ch = str(v.get("channel") or v.get("audio_channel") or "").upper()[:1]
            if ch in ("L", "R"):
                out[ch] = k
        elif str(k).upper()[:1] in ("L", "R") and len(str(k)) <= 5:   # {"L": user_id}
            out[str(k).upper()[:1]] = str(v)
        elif str(v).upper()[:1] in ("L", "R") and len(str(v)) <= 5:   # {user_id: "L"}
            out[str(v).upper()[:1]] = str(k)
    if set(out) != {"L", "R"}:
        raise ValueError(f"cannot read channel map {cm}")
    return out


def split_audio(mp3: Path, chans: dict[str, str], conv_out: Path, audio_format: str = "wav") -> dict[str, Path]:
    """One 16 kHz mono file per participant. ``wav`` (PCM16, 115 MB/h) locally; ``flac`` (lossless, ≈ 40 %) on the
    volume. soundfile reads both, so the VAD and the audio heads do not care."""
    codec = {"wav": "pcm_s16le", "flac": "flac"}[audio_format]
    wavs = {}
    for ch, uid in chans.items():
        d = conv_out / uid
        d.mkdir(parents=True, exist_ok=True)
        wav = d / f"audio16.{audio_format}"
        if not wav.exists():
            pan = "c0=c0" if ch == "L" else "c0=c1"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-af", f"pan=mono|{pan}", "-ar", "16000",
                            "-ac", "1", "-c:a", codec, str(wav)], check=True)
        wavs[uid] = wav
    return wavs


def process_conversation(conv: Path, out_root: Path = PROC, *, fps: int = lanes.FPS, delete_video: bool = False,
                         skip_face: bool = False, audio_format: str = "wav") -> dict:
    t0 = time.time()
    cid = conv.name
    out = out_root / cid
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((conv / "metadata.json").read_text())
    chans = channel_map(conv)
    mp3 = conv / "processed" / f"{cid}.mp3"
    info: dict = {"conversation_id": cid, "channels": chans, "metadata": meta, "probe": {}}
    info["probe"]["mp3"] = probe(mp3)
    wavs = split_audio(mp3, chans, out, audio_format)
    for uid, wav in wavs.items():
        vj = out / uid / "vad.json"
        if not vj.exists():
            r = vad.detect(wav, backend="silero")
            vj.write_text(json.dumps({"backend": r.backend, "error": r.error, "regions": [[round(a, 3), round(b, 3)] for a, b in r.regions]}))
        mp4 = conv / "processed" / f"{uid}.mp4"
        if mp4.exists():
            info["probe"][uid] = probe(mp4)
            if not skip_face and not (out / uid / "face.json").exists():
                m = lanes.extract(mp4, out / uid, fps=fps)
                info.setdefault("face", {})[uid] = {k: m[k] for k in ("n_rows", "found_rate", "av_sync_offset_ms", "native_fps", "width", "height", "video_start_s", "duration_s", "seconds")}
            if delete_video:
                mp4.unlink()
        else:
            info.setdefault("missing_video", []).append(uid)
    info["seconds"] = round(time.time() - t0, 1)
    (out / "meta.json").write_text(json.dumps(info, indent=1, default=str))
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--archive", type=Path)
    g.add_argument("--extracted", type=Path)
    ap.add_argument("--conv", action="append", default=None, help="restrict to these conversation ids")
    ap.add_argument("--out", type=Path, default=PROC)
    ap.add_argument("--fps", type=int, default=lanes.FPS)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--delete-video", action="store_true")
    ap.add_argument("--skip-face", action="store_true")
    ap.add_argument("--audio-format", choices=["wav", "flac"], default="wav")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = unzip(a.archive) if a.archive else a.extracted
    convs = conversations(root)
    if a.conv:
        convs = [c for c in convs if c.name in set(a.conv)]
    log.info("%d conversations under %s", len(convs), root)
    kw = {"out_root": a.out, "fps": a.fps, "delete_video": a.delete_video, "skip_face": a.skip_face, "audio_format": a.audio_format}
    if a.workers <= 1:
        for c in convs:
            info = process_conversation(c, **kw)
            log.info("%s done in %ss: %s", c.name, info["seconds"], {u: (f["found_rate"], f["av_sync_offset_ms"]) for u, f in info.get("face", {}).items()})
    else:
        with ProcessPoolExecutor(a.workers) as ex:
            futs = {ex.submit(process_conversation, c, **kw): c for c in convs}
            for f in as_completed(futs):
                info = f.result()
                log.info("%s done in %ss", info["conversation_id"], info["seconds"])


if __name__ == "__main__":
    main()
