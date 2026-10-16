"""Shared data contract for OpenVideoFDB.

Every data source (NVIDIA VideoFDB, Seamless-derived clips) is normalised to
`Sample`; every agent run produces an `AgentRun`; every scorer consumes those
two. Column names mirror NVIDIA's parquet schema where one exists so the two
sources stay interchangeable (see docs/data-sources.md).

All times are seconds relative to clip start (t=0 = first user audio sample).
Changing this file is a contract change: record it in STATUS.md.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Literal


class Bucket(str, Enum):
    PERCEPTION = "perception"
    GENERATION = "generation"


class DynamicType(str, Enum):
    """The 11 VideoFDB conversational dynamics (paper Table 2)."""

    PAUSE_HANDLING = "Pause Handling"
    GAZE_AVOIDANCE_WITH_PAUSE = "Gaze Avoidance with Pause"
    ADAPTOR_HANDLING = "Adaptor Handling"
    NONVERBAL_INTERRUPTION = "Nonverbal Interruption"
    FACE_EMOTION_DISPLAY = "Face Emotion Display"
    NONVERBAL_BACKCHANNELING = "Nonverbal Backchanneling"
    LAUGHTER = "Laughter"
    EMOTION_MATCHING = "Emotion Matching"
    VERBAL_BACKCHANNELING = "Verbal Backchanneling"
    VERBAL_INTERRUPTION = "Verbal Interruption"
    TURN_TAKING = "Turn-taking"


class TimingClass(str, Enum):
    """App. C.2 timing classes."""

    STAY_SILENT = "stay-silent"
    CONTINUE_SPEAKING = "continue-speaking"
    YIELD_REQUIRED = "yield-required"
    SMOOTH_HANDOFF = "smooth-handoff"
    BACKCHANNEL_PRODUCED = "backchannel-produced"


class AgentRole(str, Enum):
    """F.2.3 derived agent role; Fluency is calibrated against it."""

    SILENT = "SILENT"
    SPEAKER = "SPEAKER"
    YIELDING = "YIELDING"
    EXCHANGING = "EXCHANGING"


class Axis(str, Enum):
    FLUENCY = "fluency"
    CONVERSATIONAL_FLOW = "conversational_flow"
    SEMANTIC_GROUNDING = "semantic_grounding"
    GEN_FLUENCY = "generation_fluency"
    AFFECT_MATCH = "affect_match"
    CUE_APPROPRIATENESS = "cue_appropriateness"


# --- Protocol tables (docs/protocol.md §2–4) -------------------------------

#: Which judge axes apply to each (dynamic, bucket). Paper Table 8.
AXES: dict[tuple[DynamicType, Bucket], tuple[Axis, ...]] = {
    (DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION): (Axis.FLUENCY, Axis.CONVERSATIONAL_FLOW),
    (DynamicType.GAZE_AVOIDANCE_WITH_PAUSE, Bucket.PERCEPTION): (Axis.FLUENCY, Axis.CONVERSATIONAL_FLOW),
    (DynamicType.NONVERBAL_INTERRUPTION, Bucket.PERCEPTION): (
        Axis.FLUENCY, Axis.CONVERSATIONAL_FLOW, Axis.SEMANTIC_GROUNDING),
    (DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION): (Axis.FLUENCY, Axis.SEMANTIC_GROUNDING),
    (DynamicType.FACE_EMOTION_DISPLAY, Bucket.PERCEPTION): (Axis.FLUENCY, Axis.SEMANTIC_GROUNDING),
    (DynamicType.LAUGHTER, Bucket.PERCEPTION): (Axis.FLUENCY, Axis.SEMANTIC_GROUNDING),
    (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.PERCEPTION): (Axis.FLUENCY, Axis.CONVERSATIONAL_FLOW),
    (DynamicType.FACE_EMOTION_DISPLAY, Bucket.GENERATION): (
        Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS),
    (DynamicType.LAUGHTER, Bucket.GENERATION): (
        Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS),
    (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.GENERATION): (
        Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS),
    (DynamicType.EMOTION_MATCHING, Bucket.GENERATION): (
        Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS),
    (DynamicType.VERBAL_BACKCHANNELING, Bucket.GENERATION): (
        Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS),
    (DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION): (
        Axis.GEN_FLUENCY, Axis.AFFECT_MATCH, Axis.CUE_APPROPRIATENESS),
    (DynamicType.TURN_TAKING, Bucket.GENERATION): (Axis.GEN_FLUENCY, Axis.CUE_APPROPRIATENESS),
}

#: App. C.2 timing class per (dynamic, bucket); None = no timing metric.
TIMING_CLASS: dict[tuple[DynamicType, Bucket], TimingClass] = {
    (DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION): TimingClass.STAY_SILENT,
    (DynamicType.GAZE_AVOIDANCE_WITH_PAUSE, Bucket.PERCEPTION): TimingClass.STAY_SILENT,
    (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.PERCEPTION): TimingClass.CONTINUE_SPEAKING,
    (DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION): TimingClass.CONTINUE_SPEAKING,
    (DynamicType.NONVERBAL_INTERRUPTION, Bucket.PERCEPTION): TimingClass.YIELD_REQUIRED,
    (DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION): TimingClass.YIELD_REQUIRED,
    (DynamicType.TURN_TAKING, Bucket.GENERATION): TimingClass.SMOOTH_HANDOFF,
    (DynamicType.VERBAL_BACKCHANNELING, Bucket.GENERATION): TimingClass.BACKCHANNEL_PRODUCED,
}

#: Expected takeover TO* per timing class (0 = silence/backchannel expected).
EXPECTED_TAKEOVER: dict[TimingClass, int] = {
    TimingClass.STAY_SILENT: 0,
    TimingClass.YIELD_REQUIRED: 0,
    TimingClass.BACKCHANNEL_PRODUCED: 0,
    TimingClass.CONTINUE_SPEAKING: 1,
    TimingClass.SMOOTH_HANDOFF: 1,
}


def agent_role_for(dynamic: DynamicType, bucket: Bucket) -> AgentRole:
    """F.2.3 role mapping (our reconstruction; see docs/protocol.md §3)."""
    if (dynamic, bucket) in {
        (DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION),
        (DynamicType.GAZE_AVOIDANCE_WITH_PAUSE, Bucket.PERCEPTION),
    }:
        return AgentRole.SILENT
    if (dynamic, bucket) in {
        (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.PERCEPTION),
        (DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION),
    }:
        return AgentRole.SPEAKER
    if (dynamic, bucket) in {
        (DynamicType.NONVERBAL_INTERRUPTION, Bucket.PERCEPTION),
        (DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION),
    }:
        return AgentRole.YIELDING
    return AgentRole.EXCHANGING


# --- Core records -----------------------------------------------------------

@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    """A contiguous stretch of speech by one party."""

    start: float
    end: float
    text: str = ""
    n_words: int = 0

    @property
    def dur(self) -> float:
        return self.end - self.start


@dataclass
class Sample:
    """One benchmark row = (clip, bucket). Mirrors NVIDIA metadata ⋈ annotations."""

    clip_id: str                      # NVIDIA sample_id, or seamless file_id + _cNN
    conversation_id: str              # NVIDIA id, or seamless V_S_I key
    bucket: Bucket
    dynamic_type: DynamicType
    dynamic_start_s: float
    dynamic_end_s: float
    duration_s: float
    user_audio_path: str              # 16 kHz mono wav, clip-relative
    user_video_path: str              # mp4
    system_prompt: str = ""
    agent_speaks_first: bool = False
    agent_channel: str = ""           # NVIDIA: L/R in the combined view; else ""
    av_caption: str = ""              # judge input (NVIDIA: qwen_caption_full)
    user_words: list[Word] = field(default_factory=list)
    partner_audio_path: str | None = None   # human GT "agent" (val/seamless only)
    partner_video_path: str | None = None
    source: Literal["nvidia", "seamless"] = "seamless"
    source_meta: dict = field(default_factory=dict)   # file_ids, raw t0/t1, mining rule, verify log...

    @property
    def axes(self) -> tuple[Axis, ...]:
        return AXES[(self.dynamic_type, self.bucket)]

    @property
    def timing_class(self) -> TimingClass | None:
        return TIMING_CLASS.get((self.dynamic_type, self.bucket))

    @property
    def agent_role(self) -> AgentRole:
        return agent_role_for(self.dynamic_type, self.bucket)


@dataclass
class AgentRun:
    """Output of streaming one Sample through one Agent."""

    clip_id: str
    provider: str                     # e.g. gemini_live, openai_realtime, human_gt, random
    mode: Literal["av", "a2a", "av2av"]
    agent_audio_path: str             # 16 kHz mono wav; sample 0 == clip t=0
    agent_video_path: str | None = None
    model: str = ""
    started_at: str = ""              # ISO wall clock, for bookkeeping only
    drift_ms: float = 0.0             # streamer pacing drift at end of clip
    events_path: str | None = None    # jsonl of send/receive events
    errors: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


# --- (De)serialisation ------------------------------------------------------

def _to_jsonable(obj):
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def sample_to_dict(s: Sample) -> dict:
    return _to_jsonable(s)


def sample_from_dict(d: dict) -> Sample:
    d = dict(d)
    d["bucket"] = Bucket(d["bucket"])
    d["dynamic_type"] = DynamicType(d["dynamic_type"])
    d["user_words"] = [Word(**w) for w in d.get("user_words", [])]
    return Sample(**d)


def write_manifest(samples: Iterable[Sample], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for s in samples:
            f.write(json.dumps(sample_to_dict(s), ensure_ascii=False) + "\n")


def read_manifest(path: str | Path) -> list[Sample]:
    with Path(path).open() as f:
        return [sample_from_dict(json.loads(line)) for line in f if line.strip()]
