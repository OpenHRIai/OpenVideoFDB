"""Perception judge (text-only LLM; paper App. F.5, docs/protocol.md §5).

One call per (clip, axis): system = shared preamble + (universal fluency rubric |
category rubric) + output-schema reminder; user = the F.5.1 evidence packet built
from the `Sample` (caption, user words) and the per-clip `timing.json` written by
WS4 (`overlap_line`, `partition_block`, `yield_block`, `transcript`).

Judges: `gpt-4o` (OpenAI, paper default), `claude-sonnet-4-6` (Anthropic),
`gemini-2.5-pro` (google-genai). Results are cached per clip at
`<cache_dir>/<axis>_<judge>.json`, keyed by sha256(system, user, judge).
Spec: plans/WS5-judge.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import cache, lru_cache
from pathlib import Path

from dotenv import load_dotenv

from ovfdb.schema import AXES, AgentRole, Axis, Bucket, DynamicType, Sample
from ovfdb.score.segments import words_to_segments

load_dotenv()
log = logging.getLogger(__name__)

RUBRIC_DIR = Path(__file__).parent / "rubrics"
DEFAULT_JUDGE = "gpt-4o"
NO_CAPTION = "[no caption available]"
NO_SPEECH = "[no speech]"
NO_USER_SPEECH = "[no user speech]"
#: Gap (s) between user words that starts a new utterance chunk (same rule as agent segments).
USER_CHUNK_GAP_S = 0.5
MAX_OUTPUT_TOKENS = 1024

#: Axes handled by this (text-only) judge. Generation axes go through judge_generation.py.
PERCEPTION_AXES: frozenset[Axis] = frozenset({Axis.FLUENCY, Axis.CONVERSATIONAL_FLOW, Axis.SEMANTIC_GROUNDING})

#: F.5.4 dispatch: which rubric file serves each category axis (docs/protocol.md §2).
#: Fluency is universal (`fluency.txt`) and not listed here. Emotion Matching aliases
#: to Face Emotion Display; Nonverbal Interruption has one rubric per axis.
CATEGORY_AXES: dict[DynamicType, dict[Axis, str]] = {
    DynamicType.PAUSE_HANDLING: {Axis.CONVERSATIONAL_FLOW: "pause_handling"},
    DynamicType.GAZE_AVOIDANCE_WITH_PAUSE: {Axis.CONVERSATIONAL_FLOW: "gaze_avoidance_with_pause"},
    DynamicType.NONVERBAL_BACKCHANNELING: {Axis.CONVERSATIONAL_FLOW: "nonverbal_backchanneling"},
    DynamicType.NONVERBAL_INTERRUPTION: {
        Axis.CONVERSATIONAL_FLOW: "nonverbal_interruption_flow",
        Axis.SEMANTIC_GROUNDING: "nonverbal_interruption_grounding",
    },
    DynamicType.FACE_EMOTION_DISPLAY: {Axis.SEMANTIC_GROUNDING: "face_emotion_display"},
    DynamicType.EMOTION_MATCHING: {Axis.SEMANTIC_GROUNDING: "face_emotion_display"},
    DynamicType.LAUGHTER: {Axis.SEMANTIC_GROUNDING: "laughter"},
    DynamicType.ADAPTOR_HANDLING: {Axis.SEMANTIC_GROUNDING: "adaptor_handling"},
}

#: One-paragraph expected-behaviour text per F.2.3 role. The paper gives the enum
#: (and one example line for Laughter); the wording here is ours.
ROLE_DESCRIPTIONS: dict[AgentRole, str] = {
    AgentRole.SILENT: (
        "The user keeps the floor through a pause or a look-away; this is a think-cue, NOT a turn offer. "
        "The agent is expected to stay silent through the dynamic window, let the user finish the thought, and "
        "respond only once the user has clearly completed the turn. Silence inside the window is correct, not a "
        "failure; a brief sub-second backchannel is tolerable, but any substantive speech inside the window is a "
        "turn grab."
    ),
    AgentRole.SPEAKER: (
        "The agent holds the floor and is expected to keep speaking fluently through the dynamic window. The "
        "user's cue (a nod, smile, raised eyebrows, or a self-directed gesture) is not a turn offer and carries no "
        "request, so stopping, trailing off, or visibly reacting to it is a failure. Continuous, unaffected agent "
        "speech across the window is the correct behaviour."
    ),
    AgentRole.YIELDING: (
        "The agent is speaking (or should already be speaking) when the user signals an interruption at "
        "dynamic_start_s. The agent is expected to stop within about 1-1.5s of the cue, hand the floor to the "
        "user, and stay silent while the user takes the turn; a short reaction lag is natural. After the user has "
        "spoken, the agent's next contribution should respond to what the user actually said. Use the "
        "pre-computed Yield analysis block as ground truth for whether and when the agent stopped."
    ),
    AgentRole.EXCHANGING: (
        "An ordinary exchange around an affective or nonverbal cue: the user displays an expression, laughs, or "
        "offers affect, and the agent is expected to respond in turn, taking the floor when it is natural to do "
        "so and giving it back when the user resumes. The agent's continued speech in a warm, fitting register is "
        "the natural response, NOT a failure; the agent does not need to narrate the cue, and the cue may land "
        "during or at the end of the agent's own turn."
    ),
}

OUTPUT_SCHEMA = (
    'Respond with a JSON object only: {"analysis": "cite timings and quoted phrases", '
    '"rating": integer 0-5, "reasoning": "one sentence summary"}'
)

#: USD per 1M tokens (input, output) for cost estimates in summaries; indicative only.
PRICES_PER_M: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "gemini-2.5-pro": (1.25, 10.00),
}


class JudgeError(RuntimeError):
    """Base class for judge failures."""


class JudgeUnavailable(JudgeError):
    """The requested judge cannot run (unknown name or missing API key)."""


class JudgeParseError(JudgeError):
    """The judge's reply was not a valid {analysis, rating, reasoning} object."""


@dataclass
class JudgeResult:
    axis: str
    judge: str
    rating: int
    analysis: str
    reasoning: str
    raw: str
    rubric: str = ""
    usage: dict = field(default_factory=dict)      # prompt_tokens / completion_tokens / n_calls
    cached: bool = False
    key: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --- rubrics ----------------------------------------------------------------

@cache
def load_rubric(name: str) -> str:
    path = RUBRIC_DIR / f"{name}.txt"
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise FileNotFoundError(f"empty rubric {path}")
    return text


def rubric_name(axis: Axis | str, dynamic: DynamicType | str) -> str:
    """Rubric file stem for (axis, dynamic); ValueError for a generation axis or an unmapped pair."""
    axis, dynamic = Axis(axis), DynamicType(dynamic)
    if axis is Axis.FLUENCY:
        return "fluency"
    try:
        return CATEGORY_AXES[dynamic][axis]
    except KeyError:
        raise ValueError(f"no perception rubric for axis {axis.value!r} on {dynamic.value!r}") from None


def role_description(role: AgentRole | str) -> str:
    return ROLE_DESCRIPTIONS[AgentRole(role)]


def build_system_prompt(axis: Axis | str, sample: Sample) -> str:
    """Preamble (F.5.2) + fluency (F.5.3) or category rubric (F.5.4) + output-schema reminder."""
    name = rubric_name(axis, sample.dynamic_type)
    return "\n\n".join([load_rubric("perception_preamble"), load_rubric(name), OUTPUT_SCHEMA])


# --- user payload (F.5.1) ----------------------------------------------------

def format_user_speech(sample: Sample, gap: float = USER_CHUNK_GAP_S) -> str:
    """`[t0-t1s] text` per utterance; words closer than `gap` seconds merge into one chunk."""
    segs = words_to_segments(sample.user_words, gap=gap)
    if not segs:
        return NO_USER_SPEECH
    return "\n".join(f"[{s.start:.2f}-{s.end:.2f}s] {s.text}" for s in segs)


def _quoted(block: str) -> str:
    return f'"""\n{block.strip()}\n"""'


def build_user_message(sample: Sample, timing_json: dict) -> str:
    """The F.5.1 evidence packet. `timing_json` is the per-clip dict written by `pipeline.score_timing`."""
    role = AgentRole(timing_json.get("agent_role") or sample.agent_role.value)
    ds, de = sample.dynamic_start_s, sample.dynamic_end_s
    lines = [
        f"Category: {sample.dynamic_type.value}",
        f"Bucket: {sample.bucket.value}",
        f"Agent role: {role.value}. {role_description(role)}",
        f"Dynamic event: t={ds:.2f}s to t={de:.2f}s",
        f"Clip duration: {sample.duration_s:.2f}s",
        timing_json["overlap_line"],
    ]
    if role is AgentRole.YIELDING and timing_json.get("yield_block"):
        lines.append(timing_json["yield_block"])
    caption = (sample.av_caption or "").strip() or NO_CAPTION
    transcript = (timing_json.get("transcript") or "").strip() or NO_SPEECH
    lines += [
        "AV caption (covers full clip including the dynamic event):",
        _quoted(caption),
        "User speech (with timestamps):",
        _quoted(format_user_speech(sample)),
        "Agent speech segments (times when agent was audible) --- partitioned by dynamic window:",
        _quoted(timing_json["partition_block"]),
        "Agent speech transcript:",
        _quoted(transcript),
        "Rate on the 0-5 scale per the rubric above.",
    ]
    return "\n".join(lines)


# --- backends -----------------------------------------------------------------

def backend_for(judge: str) -> str:
    if judge.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if judge.startswith("claude-"):
        return "anthropic"
    if judge.startswith("gemini-"):
        return "google"
    raise JudgeUnavailable(f"unknown judge {judge!r}; expected a gpt-*, claude-* or gemini-* model id")


def _require_key(name: str, judge: str) -> str:
    key = (os.environ.get(name) or "").strip()
    if not key:
        raise JudgeUnavailable(f"{name} is not set (needed for judge {judge!r}); add it to .env")
    return key


@lru_cache(maxsize=4)
def _client(backend: str, judge: str):
    if backend == "openai":
        from openai import OpenAI
        return OpenAI(api_key=_require_key("OPENAI_API_KEY", judge))
    if backend == "anthropic":
        from anthropic import Anthropic
        return Anthropic(api_key=_require_key("ANTHROPIC_API_KEY", judge))
    if backend == "google":
        from google import genai
        key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
        if not key:
            raise JudgeUnavailable(f"GOOGLE_API_KEY is not set (needed for judge {judge!r}); add it to .env")
        return genai.Client(api_key=key)
    raise JudgeUnavailable(backend)  # pragma: no cover


def _call(judge: str, system: str, user: str) -> tuple[str, dict]:
    """One judge call. Returns (raw text, usage dict). Temperature 0, JSON output where the API supports it."""
    backend = backend_for(judge)
    client = _client(backend, judge)
    if backend == "openai":
        r = client.chat.completions.create(
            model=judge, temperature=0, response_format={"type": "json_object"},
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = r.choices[0].message.content or ""
        u = r.usage
        usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0), "completion_tokens": getattr(u, "completion_tokens", 0)}
        return text, usage
    if backend == "anthropic":
        r = client.messages.create(
            model=judge, max_tokens=MAX_OUTPUT_TOKENS, temperature=0, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in r.content)
        usage = {"prompt_tokens": r.usage.input_tokens, "completion_tokens": r.usage.output_tokens}
        return text, usage
    if backend == "google":
        from google.genai import types
        r = client.models.generate_content(
            model=judge, contents=user,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0,
                                               response_mime_type="application/json",
                                               max_output_tokens=MAX_OUTPUT_TOKENS),
        )
        text = r.text or ""
        um = getattr(r, "usage_metadata", None)
        usage = {"prompt_tokens": getattr(um, "prompt_token_count", 0) or 0,
                 "completion_tokens": getattr(um, "candidates_token_count", 0) or 0}
        return text, usage
    raise JudgeUnavailable(backend)  # pragma: no cover


# --- parsing / validation ------------------------------------------------------

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_response(raw: str) -> dict:
    """Parse `{analysis, rating, reasoning}`; tolerate code fences / surrounding prose; JudgeParseError otherwise."""
    text = raw.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            try:
                obj = json.loads(text[a:b + 1])
            except json.JSONDecodeError:
                obj = None
    if not isinstance(obj, dict):
        raise JudgeParseError(f"not a JSON object: {raw[:200]!r}")
    if "rating" not in obj:
        raise JudgeParseError(f"missing 'rating': {raw[:200]!r}")
    rating = obj["rating"]
    try:
        if isinstance(rating, str):
            rating = float(rating.strip())
        if isinstance(rating, bool) or float(rating) != int(float(rating)):
            raise ValueError
        rating = int(float(rating))
    except (TypeError, ValueError):
        raise JudgeParseError(f"rating not an integer: {obj['rating']!r}") from None
    if not 0 <= rating <= 5:
        raise JudgeParseError(f"rating out of range 0-5: {rating}")
    return {
        "analysis": str(obj.get("analysis", "")),
        "rating": rating,
        "reasoning": str(obj.get("reasoning", "")),
    }


# --- scoring ------------------------------------------------------------------

def cache_key(system: str, user: str, judge: str) -> str:
    h = hashlib.sha256()
    for part in (system, user, judge):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def cache_file(cache_dir: Path, axis: Axis | str, judge: str) -> Path:
    return Path(cache_dir) / f"{Axis(axis).value}_{judge}.json"


def _load_cached(path: Path, key: str) -> JudgeResult | None:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if d.get("key") != key:
        return None
    known = JudgeResult.__dataclass_fields__
    r = JudgeResult(**{k: v for k, v in d.items() if k in known})
    r.cached = True
    return r


def score_axis(sample: Sample, timing_json: dict, axis: Axis | str, judge: str = DEFAULT_JUDGE, *,
               cache_dir: str | Path | None = None, force: bool = False) -> JudgeResult:
    """Judge one axis of one clip. One retry on an unparseable reply; raises JudgeParseError after that."""
    axis = Axis(axis)
    if axis not in PERCEPTION_AXES:
        raise ValueError(f"{axis.value} is a generation axis; use judge_generation")
    system = build_system_prompt(axis, sample)
    user = build_user_message(sample, timing_json)
    key = cache_key(system, user, judge)
    path = cache_file(Path(cache_dir), axis, judge) if cache_dir is not None else None
    if path is not None and not force:
        hit = _load_cached(path, key)
        if hit is not None:
            return hit

    usage = {"prompt_tokens": 0, "completion_tokens": 0, "n_calls": 0}
    last_err: JudgeParseError | None = None
    raw, parsed = "", None
    for attempt in range(2):
        prompt = user if attempt == 0 else user + "\n\nReturn ONLY the JSON object described in the system prompt."
        raw, u = _call(judge, system, prompt)
        usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
        usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)
        usage["n_calls"] += 1
        try:
            parsed = parse_response(raw)
            break
        except JudgeParseError as e:
            last_err = e
            log.warning("judge %s/%s: unparseable reply on attempt %d: %s", judge, axis.value, attempt + 1, e)
    if parsed is None:
        raise JudgeParseError(f"{judge}/{axis.value} on {sample.clip_id}: {last_err}")

    result = JudgeResult(
        axis=axis.value, judge=judge, rating=parsed["rating"], analysis=parsed["analysis"],
        reasoning=parsed["reasoning"], raw=raw, rubric=rubric_name(axis, sample.dynamic_type), usage=usage,
        cached=False, key=key, created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        d = result.to_dict()
        d.update(clip_id=sample.clip_id, dynamic_type=sample.dynamic_type.value, bucket=sample.bucket.value,
                 system_sha256=hashlib.sha256(system.encode()).hexdigest(), user_message=user)
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def score_sample(sample: Sample, timing_json: dict, judge: str = DEFAULT_JUDGE, *,
                 axes: Iterable[Axis | str] | None = None, cache_dir: str | Path | None = None,
                 force: bool = False) -> dict[str, JudgeResult]:
    """Judge every perception axis of `sample` (or the subset `axes`). Generation axes are skipped with a note.

    Returns {axis_value: JudgeResult}. Warns when the sample has no AV caption (judge then sees
    `[no caption available]` and must rely on transcripts, as the paper's qwen_caption fallback).
    """
    wanted = sample.axes if axes is None else tuple(Axis(a) for a in axes)
    if sample.bucket is not Bucket.PERCEPTION:
        log.warning("%s: bucket %s is not judged by the perception judge; skipping", sample.clip_id, sample.bucket.value)
        return {}
    if not (sample.av_caption or "").strip():
        log.warning("%s: av_caption is empty; judge payload uses %s", sample.clip_id, NO_CAPTION)
    out: dict[str, JudgeResult] = {}
    for axis in wanted:
        if axis not in PERCEPTION_AXES:
            log.info("%s: axis %s is a generation axis; skipped (see judge_generation)", sample.clip_id, axis.value)
            continue
        if axis not in sample.axes:
            log.info("%s: axis %s does not apply to %s; skipped", sample.clip_id, axis.value, sample.dynamic_type.value)
            continue
        out[axis.value] = score_axis(sample, timing_json, axis, judge, cache_dir=cache_dir, force=force)
    return out


def estimate_cost_usd(usage: dict, judge: str) -> float | None:
    """Indicative USD cost from PRICES_PER_M; None for an unknown judge."""
    p = PRICES_PER_M.get(judge)
    if p is None:
        return None
    return (usage.get("prompt_tokens", 0) * p[0] + usage.get("completion_tokens", 0) * p[1]) / 1e6


def perception_pairs() -> list[tuple[DynamicType, Bucket]]:
    """All (dynamic, bucket) pairs in schema.AXES that this judge must cover."""
    return [k for k in AXES if k[1] is Bucket.PERCEPTION]
