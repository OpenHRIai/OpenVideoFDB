"""CANDOR on Modal: every processed archive -> VAD, 16 kHz FLAC and 10 Hz face tracks on the ``candor`` volume.

    uv run --with modal modal run scripts/candor_modal.py --archives 034            # one archive (the 6-conversation test)
    uv run --with modal modal run --detach scripts/candor_modal.py --archives all   # all 34 (≈ 1.5 h wall-clock)
    uv run --with modal modal volume get candor proc data/candor/proc_modal         # fetch the tracks (≈ 20 GB + audio)
    uv run --with modal modal volume get candor logs data/candor/logs_modal

Test on archive 034 (6 conversations, 2026-11-08): 6/6 done in 1172 s on 4 CPUs, i.e. ≈ 390 CPU-s per participant
video on Modal's x86 cores (≈ 4× the Apple-silicon figure). Against the local pilot tracks: identical row counts,
found rates and AV offsets; blendshapes differ by a median 5e-4 (p99 0.06, tracking is stateful so a few frames
diverge); face found/not-found disagrees on 0.4 % of frames; Silero VAD disagrees on ≈ 0.1 % of frames (one
participant 1.7 %). Same faster-whisper / mediapipe / numpy versions on both sides, so that is x86 vs arm64 numerics.
A full archive holds ≈ 50 conversations, so one container at 8 CPUs needs ≈ 1.5 h; the whole corpus is
≈ 360 CPU-hours.

One container per archive: download the zip from the gated Hugging Face dataset (token from the Modal secret
``huggingface``, created once with ``modal secret create huggingface HF_TOKEN=<token>``), unzip to the container's own disk, run
``scripts/candor_prep.process_conversation`` on each conversation with the video deleted after extraction, write
``/vol/proc/<conversation_id>/...`` and ``/vol/logs/<archive>.json``, commit the volume, discard the container.
The 346 GB of video is never stored anywhere. Everything CANDOR lives on its own volume (``candor``), apart from
the CC BY-NC Seamless material on ``smart-turn-v2``.
"""

from __future__ import annotations

import modal

APP = "ovfdb-candor"
VOL = "/vol"
REPO = "betterup/candor-processed"
N_ARCHIVES = 34
CPUS = 8

app = modal.App(APP)
volume = modal.Volume.from_name("candor", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg", "libgl1", "libegl1", "libgles2", "libglib2.0-0")
    .pip_install("numpy==2.5.4", "soundfile>=0.12", "scipy>=1.13", "av>=12", "pydantic>=2.7", "httpx>=0.27",
                 "huggingface-hub>=0.24", "faster-whisper==1.2.1", "mediapipe==1.1.1", "tqdm>=4.66")
    .add_local_file("data/models/face_landmarker.task", "/root/data/models/face_landmarker.task")
    .add_local_python_source("ovfdb")
    .add_local_dir("scripts", remote_path="/root/scripts")
)


HF_SECRET = modal.Secret.from_name("huggingface")   # once: modal secret create huggingface HF_TOKEN=$(cat ~/.cache/huggingface/token)


@app.function(image=image, volumes={VOL: volume}, cpu=CPUS, memory=16384, timeout=6 * 3600,
              max_containers=N_ARCHIVES, secrets=[HF_SECRET])
def process_archive(part: str, audio_format: str = "flac") -> dict:
    import json
    import os
    import shutil
    import sys
    import time
    from concurrent.futures import ProcessPoolExecutor
    from pathlib import Path

    sys.path.insert(0, "/root/scripts"); sys.path.insert(0, "/root")
    os.chdir("/root")                                   # lanes.DEFAULT_MODEL is relative: data/models/face_landmarker.task
    import candor_prep as P
    from huggingface_hub import hf_hub_download

    t0 = time.time()
    name = f"processed_media_part_{part}.zip"
    work = Path("/scratch"); work.mkdir(exist_ok=True)
    log_path = Path(VOL) / "logs" / f"{part}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    zp = Path(hf_hub_download(REPO, f"data/{name}", repo_type="dataset", local_dir=str(work), token=os.environ["HF_TOKEN"]))
    t_dl = time.time() - t0
    raw = P.unzip(zp, raw=work / "raw")
    zp.unlink()
    convs = P.conversations(raw)
    out_root = Path(VOL) / "proc"
    results, errors = [], {}
    with ProcessPoolExecutor(CPUS) as ex:
        futs = {ex.submit(P.process_conversation, c, out_root, fps=10, delete_video=True, audio_format=audio_format): c.name for c in convs}
        for f, cid in futs.items():
            try:
                r = f.result()
                results.append({k: r[k] for k in ("conversation_id", "seconds", "missing_video") if k in r} | {"face": r.get("face", {})})
            except Exception as e:  # noqa: BLE001 — one bad conversation must not sink the archive
                errors[cid] = repr(e)
    shutil.rmtree(raw, ignore_errors=True)
    summary = {"part": part, "archive": name, "n_conversations": len(convs), "done": len(results), "errors": errors,
                   "download_s": round(t_dl, 1), "total_s": round(time.time() - t0, 1), "results": results}
    log_path.write_text(json.dumps(summary, indent=1, default=str))
    volume.commit()
    return {k: v for k, v in summary.items() if k != "results"}


@app.local_entrypoint()
def main(archives: str = "034", audio_format: str = "flac"):
    parts = [f"{i:03d}" for i in range(1, N_ARCHIVES + 1)] if archives == "all" else archives.split(",")
    print(f"{len(parts)} archive(s): {parts[:5]}{'...' if len(parts) > 5 else ''}")
    for r in process_archive.map(parts, kwargs={"audio_format": audio_format}):
        print(f"part {r['part']}: {r['done']}/{r['n_conversations']} conversations, download {r['download_s']}s, total {r['total_s']}s, errors {r['errors']}")
