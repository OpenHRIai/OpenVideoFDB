"""Small shared wrapper around the google-genai SDK for the mining stages
(VLM verification, AV caption, audio laughter detection).

Media <= ``INLINE_LIMIT`` bytes go inline; larger files go through the Files
API (uploaded, polled until ACTIVE, deleted afterwards).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

MODEL = "gemini-2.5-flash"
INLINE_LIMIT = 20 * 1024 * 1024
_client = None


def client():
    global _client
    if _client is None:
        load_dotenv()
        from google import genai

        if not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY missing (.env)")
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def _media_part(path: Path, mime: str):
    from google.genai import types

    data = path.read_bytes()
    if len(data) <= INLINE_LIMIT:
        return types.Part.from_bytes(data=data, mime_type=mime), None
    c = client()
    f = c.files.upload(file=str(path), config={"mime_type": mime})
    while f.state and f.state.name == "PROCESSING":
        time.sleep(2)
        f = c.files.get(name=f.name)
    if f.state and f.state.name == "FAILED":
        raise RuntimeError(f"Files API processing failed for {path}")
    return f, f.name


def parse_json(text: str):
    """Tolerant JSON extraction (handles ```json fences and leading prose)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise
        return json.loads(text[start:])


def generate(prompt: str, media: Path | None = None, mime: str = "video/mp4", json_out: bool = True,
             model: str = MODEL, retries: int = 3, temperature: float = 0.2) -> tuple[object, dict]:
    """One generate_content call. Returns (parsed JSON or text, usage dict)."""
    from google.genai import types

    c = client()
    part, uploaded = (None, None)
    contents = []
    if media is not None:
        part, uploaded = _media_part(Path(media), mime)
        contents.append(part)
    contents.append(prompt)
    cfg = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json" if json_out else "text/plain",
    )
    try:
        last = None
        for attempt in range(retries):
            try:
                r = c.models.generate_content(model=model, contents=contents, config=cfg)
                text = r.text or ""
                u = r.usage_metadata
                usage = {"prompt_tokens": getattr(u, "prompt_token_count", 0) or 0,
                         "output_tokens": getattr(u, "candidates_token_count", 0) or 0,
                         "model": model}
                return (parse_json(text) if json_out else text), usage
            except Exception as e:  # noqa: BLE001 - retry on transient API/JSON errors
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"gemini failed after {retries} attempts: {last}")
    finally:
        if uploaded:
            try:
                c.files.delete(name=uploaded)
            except Exception as e:  # noqa: BLE001
                print(f"warning: could not delete uploaded file {uploaded}: {e}")


def cost_usd(usage: dict) -> float:
    """gemini-2.5-flash list price (2026): $0.30 / 1M input (text/video/audio), $2.50 / 1M output."""
    return usage.get("prompt_tokens", 0) * 0.30e-6 + usage.get("output_tokens", 0) * 2.50e-6
