"""Deterministic timing metrics (paper App. C.2; docs/protocol.md §4).

Pure functions over agent speech segments — no I/O — so they are unit-testable
with synthetic data. Spec: plans/WS4-scoring-timing.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ovfdb.schema import EXPECTED_TAKEOVER, Segment, TimingClass

BACKCHANNEL_MAX_DUR_S = 1.0
BACKCHANNEL_MAX_WORDS = 2          # "< 2 words" in the paper => n_words < 2
STAY_SILENT_MAX_INWINDOW_S = 1.0
YIELD_MAX_LATENCY_S = 1.5
CONTINUE_PRE_WINDOW_S = 3.0
CONTINUE_PRE_ACTIVITY_MIN = 0.30
CONTINUE_IN_ACTIVITY_MIN = 0.50


def is_backchannel(seg: Segment) -> bool:
    return seg.dur < BACKCHANNEL_MAX_DUR_S and seg.n_words < BACKCHANNEL_MAX_WORDS


@dataclass
class OverlapSummary:
    """Pre-computed in-window overlap line + PRE/IN/POST partition (F.2.3)."""

    total_in_window_s: float
    overlaps: list[tuple[Segment, float]]      # (segment, seconds overlapping the window)
    pre_activity: float                        # fraction of [0, ds) with agent speech
    in_activity: float                         # fraction of [ds, de]
    post_activity: float                       # fraction of (de, clip_end]

    def line(self) -> str:
        """'Agent in-window speech: 2.00s total across 1 segment(s) --- [3.28-9.28] overlaps by 2.00s'."""
        raise NotImplementedError


@dataclass
class YieldAnalysis:
    pre_activity: float
    post_activity: float
    yield_moment_s: float | None
    yielded: bool
    verdict: str

    def block(self) -> str:
        """The multi-line 'Yield analysis:' text block injected into the judge payload."""
        raise NotImplementedError


@dataclass
class TimingResult:
    timing_class: TimingClass
    passed: bool
    takeover: int                              # observed TO_i
    expected_takeover: int                     # TO*_c
    latency_ms: float | None
    details: dict = field(default_factory=dict)


def overlap_summary(segs: list[Segment], ds: float, de: float, clip_end: float) -> OverlapSummary:
    raise NotImplementedError


def yield_analysis(segs: list[Segment], ds: float, de: float, clip_end: float,
                   pre_s: float = 5.0, post_s: float = 14.0) -> YieldAnalysis:
    raise NotImplementedError


def evaluate(segs: list[Segment], ds: float, de: float, cls: TimingClass,
             *, agent_speaks_first: bool = False, clip_end: float | None = None) -> TimingResult:
    """Apply the pass rule for `cls` (docs/protocol.md §4) and compute latency.

    stay-silent:        pass if in-window speech <= 1.0 s OR all overlapping segs are backchannels.
    continue-speaking:  if activity in [ds-3, ds) >= 30 % then require in-window activity >= 50 %; else vacuous pass.
    yield-required:     latency = end of seg overlapping ds (or last seg ending before ds) - ds; pass if <= 1.5 s.
                        No speech near ds -> fail, details["trivially_silent"] = True.
    smooth-handoff:     latency = first onset after ds - ds (0 if speaking at ds); pass if onset <= de.
    backchannel-produced: pass if >= 1 in-window backchannel AND no in-window non-backchannel seg.
    takeover = 0 if in-window output is silence/backchannels only, else 1.
    """
    raise NotImplementedError


def aggregate(results: dict[str, list[TimingResult]]) -> dict:
    """{dynamic: {"tor_alignment": float, "median_latency_ms": float|None, "n": int}, "overall": {...}}.

    TOR-Alignment = fraction of clips whose observed takeover matches EXPECTED_TAKEOVER
    (equivalently, whose pass rule holds).
    """
    _ = EXPECTED_TAKEOVER
    raise NotImplementedError
