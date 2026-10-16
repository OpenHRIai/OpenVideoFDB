"""Per-clip agent system prompt (paper F.4) and AV caption (judge input).

* ``system_prompt(sample)``: gpt-4o turns the transcript of **both channels up
  to ``dynamic_start_s`` only** (no future leakage) into a short persona +
  context prompt for the agent under test. When ``agent_speaks_first`` the
  prompt ends with "Start speaking now to begin/continue the conversation."
* ``av_caption(sample)``: gemini-2.5-flash describes the side-by-side clip
  (USER left, PARTNER right) with second-aligned timestamps: speech, facial
  expression, gaze, gestures, laughter. This stands in for the paper's
  ``qwen_caption_full`` (docs/protocol.md §10).

Both are cached in ``data/mining/prompts/<clip_id>.json``.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from ovfdb.data.seamless import fetch, read_transcript
from ovfdb.mine import gemini as G
from ovfdb.mine.verify import sbs_composite
from ovfdb.schema import Sample

PROMPT_DIR = Path("data/mining/prompts")
OPENAI_MODEL = "gpt-4o"
CONTINUE_LINE = "Start speaking now to begin/continue the conversation."
_lock = threading.Lock()
_openai = None


def _openai_client():
    global _openai
    if _openai is None:
        load_dotenv()
        from openai import OpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY missing (.env)")
        _openai = OpenAI()
    return _openai


def _cache_path(clip_id: str) -> Path:
    return PROMPT_DIR / f"{clip_id}.json"


def _load(clip_id: str) -> dict:
    p = _cache_path(clip_id)
    return json.loads(p.read_text()) if p.exists() else {}


def _save(clip_id: str, **kv) -> None:
    with _lock:
        d = _load(clip_id)
        d.update(kv)
        PROMPT_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(clip_id).write_text(json.dumps(d, ensure_ascii=False, indent=1))


# --- transcript view up to the event ------------------------------------------

def _utts_for(file_id: str):
    got = fetch(file_id, ("transcript",))
    return read_transcript(got["transcript"]) if "transcript" in got else []


def pre_event_dialogue(sample: Sample) -> str:
    """Both channels' words from clip start to ``dynamic_start_s``, as
    "[t=12.3s] USER: ..." lines in clip time (pure given the transcripts)."""
    meta = sample.source_meta
    t0, ds_raw = float(meta["t0"]), float(meta["dynamic_start_raw_s"])
    lines: list[tuple[float, str, str]] = []
    for role, fid in (("USER", meta["user_file_id"]), ("AGENT", meta["partner_file_id"])):
        for u in _utts_for(fid):
            if u.end <= t0 or u.start >= ds_raw:
                continue
            words = [w.text for w in u.words if w.start < ds_raw and w.end > t0] or (
                u.transcript.split() if u.end <= ds_raw else [])
            if words:
                lines.append((max(u.start, t0) - t0, role, " ".join(words)))
    lines.sort()
    return "\n".join(f"[t={t:.1f}s] {role}: {text}" for t, role, text in lines)


def system_prompt(sample: Sample, force: bool = False) -> str:
    """F.4 agent-conditioning prompt (cached)."""
    cached = _load(sample.clip_id)
    if cached.get("system_prompt") and not force:
        return cached["system_prompt"]
    dialogue = pre_event_dialogue(sample) or "(no speech before the event)"
    first = sample.agent_speaks_first
    instr = (
        "You write system prompts for a voice-and-video conversational agent that is about to be dropped into the "
        "middle of a real two-person conversation. The agent plays AGENT; the human it talks to is USER. You see the "
        "transcript of both channels up to the moment of the event being tested, nothing after it.\n"
        "Write the prompt as flowing second-person prose addressed to the agent (\"You are ...\"), 120-200 words, "
        "no headings, numbering or bullet points. It should give the agent a short persona consistent with what AGENT "
        "has been saying (name-free, natural, warm); summarise the topic and what each side has said so far so the "
        "agent can continue the same thread, including what AGENT was saying most recently; and tell the agent to "
        "behave like a natural face-to-face conversational partner: listen, react, don't lecture, keep turns short. "
        "Do not mention that this is a test, a benchmark, or a transcript, and do not reveal or predict anything "
        "beyond the given context. "
    )
    instr += (
        f'The agent must already be mid-turn when the clip starts, so the prompt MUST end with exactly this sentence: "{CONTINUE_LINE}"'
        if first else
        "The user speaks first, so tell the agent to wait for the user and reply naturally; do NOT tell it to start speaking."
    )
    user = f"Dynamic being tested (do not mention it): {sample.dynamic_type.value}\n\nTranscript so far:\n{dialogue}"
    r = _openai_client().chat.completions.create(
        model=OPENAI_MODEL, temperature=0.4, max_tokens=400,
        messages=[{"role": "system", "content": instr}, {"role": "user", "content": user}],
    )
    text = (r.choices[0].message.content or "").strip().strip('"')
    if first and not text.rstrip().endswith(CONTINUE_LINE):
        text = text.rstrip() + "\n\n" + CONTINUE_LINE
    if not first and CONTINUE_LINE in text:
        text = text.replace(CONTINUE_LINE, "").rstrip()
    usage = {"model": OPENAI_MODEL, "prompt_tokens": r.usage.prompt_tokens if r.usage else 0,
             "output_tokens": r.usage.completion_tokens if r.usage else 0}
    _save(sample.clip_id, system_prompt=text, system_prompt_usage=usage, pre_event_dialogue=dialogue)
    return text


# --- AV caption ----------------------------------------------------------------

def sbs_path(sample: Sample) -> Path:
    out = Path(sample.user_video_path).parent / "sbs.mp4"
    if sample.partner_video_path is None:
        raise ValueError("av_caption needs the partner video")
    return sbs_composite(sample.user_video_path, sample.partner_video_path, out)


def av_caption(sample: Sample, force: bool = False) -> str:
    """Timestamped AV description of both panes over the full clip (cached)."""
    cached = _load(sample.clip_id)
    if cached.get("av_caption") and not force:
        return cached["av_caption"]
    prompt = (
        "This is a side-by-side video of a face-to-face conversation: LEFT pane = USER, RIGHT pane = PARTNER. "
        f"The clip is {sample.duration_s:.1f} s long. Both voices are mixed in one audio track; use lip movement to attribute speech.\n"
        "Write a detailed, neutral caption (250-400 words) of the whole clip as timestamped prose, in order, for BOTH "
        "people: what each says (paraphrase or short quotes), facial expressions, gaze direction and shifts, head "
        "movements (nods, shakes), hand gestures and self-touch, smiles and laughter, pauses and overlaps. Give times "
        "in seconds from the clip start like [12.3s]. Prefix each observation with USER or PARTNER. Do not interpret "
        "beyond what is visible/audible."
    )
    text, usage = G.generate(prompt, sbs_path(sample), mime="video/mp4", json_out=False, temperature=0.3)
    text = str(text).strip()
    _save(sample.clip_id, av_caption=text, av_caption_usage=usage)
    return text
