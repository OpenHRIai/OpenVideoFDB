"""Run HeyGen LiveAvatar on the NVIDIA generation rows, rotating through several LiveAvatar keys.

    uv run python scripts/run_avatar_keys.py                       # HEYGEN_API_KEY, _KEY2, _KEY3 in turn
    uv run python scripts/run_avatar_keys.py --keys HEYGEN_API_KEY --ignore-credits   # e.g. overage enabled

Each key is used until LiveAvatar refuses for credits (`run_manifest` aborts; a row cut mid-session is left
to re-run). Rows whose session failed to start for another reason, or that recorded no avatar video, are
deleted and retried. Stops when every row has a run.json or every key is empty (exit 3). Resumable: rows
with a run.json are skipped.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "runs_nv/heygen_a2av"
N_ROWS = 121
RUN = ("from ovfdb.harness import streamer; streamer.run_manifest('manifest/nvidia_test.jsonl', provider='heygen', "
       "mode='a2a', out='runs_nv/heygen_a2av', concurrency=1, bucket='generation', partner_video_first=True)")
MIN_CREDITS = 2.0          # LiveAvatar refuses a session without credits for one minute (FULL = 2 credits/min)


def credits(key: str) -> float:
    r = httpx.get("https://api.liveavatar.com/v1/users/credits", headers={"X-API-KEY": key}, timeout=30)
    return float(r.json()["data"]["credits_left"]) if r.status_code == 200 else -1.0


def n_done() -> int:
    return sum(1 for _ in OUT.glob("*/run.json"))


def clean_failed_starts() -> int:
    n = 0
    for rj in OUT.glob("*/run.json"):
        errs = json.loads(rj.read_text()).get("errors") or []
        if any(e.startswith("start:") or "avatar not ready" in e or e == "no video recorded" for e in errs):
            print(f"[driver] removing failed start {rj.parent.name}: {errs[:1]}", flush=True)
            shutil.rmtree(rj.parent)
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default="HEYGEN_API_KEY,HEYGEN_API_KEY2,HEYGEN_API_KEY3")
    ap.add_argument("--ignore-credits", action="store_true", help="run even when the balance is low (overage on)")
    a = ap.parse_args()
    env_file = dotenv_values(REPO / ".env")
    names = [k.strip() for k in a.keys.split(",") if env_file.get(k.strip())]
    for name in names:
        key = env_file[name]
        for _ in range(3):
            c = credits(key)
            print(f"[driver] {time.strftime('%H:%M:%S')} {name}: {c} credits, {n_done()}/{N_ROWS} rows done", flush=True)
            if (c < MIN_CREDITS and not a.ignore_credits) or n_done() >= N_ROWS:
                break
            subprocess.run(["uv", "run", "python", "-c", RUN], cwd=REPO, env={**os.environ, "HEYGEN_API_KEY": key},
                           check=False)
            if clean_failed_starts() == 0:
                break
        print(f"[driver] {time.strftime('%H:%M:%S')} {name} done: {credits(key)} credits left", flush=True)
        if n_done() >= N_ROWS:
            break
    print(f"[driver] END {time.strftime('%H:%M:%S')} {n_done()}/{N_ROWS} rows done; credits "
          f"{ {n: credits(env_file[n]) for n in names} }", flush=True)
    sys.exit(0 if n_done() >= N_ROWS else 3)


if __name__ == "__main__":
    main()
