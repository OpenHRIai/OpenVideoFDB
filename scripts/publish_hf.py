"""Publish the Seamless-derived manifests + dataset card to a Hugging Face dataset repo (WS8).

    uv run python scripts/publish_hf.py --repo OpenHRIai/open-videofdb [--private] [--dry-run]

Uploads: manifest/ovfdb_v0.jsonl, manifest/ovfdb_v1.jsonl, manifest/ovfdb_v1_reviewed.jsonl,
manifest/reviews/ovfdb_v1.jsonl and hf/README.md (the card). Never anything under data/,
runs*/ or manifest/nvidia_*. Needs HF_TOKEN in .env with write access to the target org.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

FILES = [
    ("manifest/ovfdb_v0.jsonl", "ovfdb_v0.jsonl"),
    ("manifest/ovfdb_v1.jsonl", "ovfdb_v1.jsonl"),
    ("manifest/ovfdb_v1_reviewed.jsonl", "ovfdb_v1_reviewed.jsonl"),
    ("manifest/reviews/ovfdb_v1.jsonl", "reviews/ovfdb_v1.jsonl"),
    ("hf/README.md", "README.md"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="e.g. OpenHRIai/open-videofdb")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv(".env", override=True)
    tok = os.environ.get("HF_TOKEN")
    if not tok:
        raise SystemExit("HF_TOKEN missing in .env")
    for src, _ in FILES:
        if not Path(src).exists():
            raise SystemExit(f"missing {src}")
        if "nvidia" in src:
            raise SystemExit("refusing to publish NVIDIA-derived files")
    if a.dry_run:
        print("would upload:", [f"{s} -> {d}" for s, d in FILES], "to", a.repo)
        return
    from huggingface_hub import HfApi
    api = HfApi(token=tok)
    api.create_repo(a.repo, repo_type="dataset", private=a.private, exist_ok=True)
    for src, dst in FILES:
        api.upload_file(path_or_fileobj=src, path_in_repo=dst, repo_id=a.repo, repo_type="dataset",
                        commit_message=f"OpenVideoFDB manifests: {dst}")
        print("uploaded", dst)
    print(f"https://huggingface.co/datasets/{a.repo}")


if __name__ == "__main__":
    main()
