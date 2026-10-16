"""Deterministic timing metrics (paper App. C.2; docs/protocol.md §4).

Pure functions over agent speech segments — no I/O — so they are unit-testable
with synthetic data. Spec: plans/WS4-scoring-timing.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from ovfdb.schema import EXPECTED_TAKEOVER, TIMING_CLASS, Bucket, DynamicType, Segment, TimingClass
from ovfdb.score.segments import (
    activity_fraction,
    first_onset,
    overlaps,
    speaking_at,
)

BACKCHANNEL_MAX_DUR_S = 1.0
BACKCHANNEL_MAX_WORDS = 2          # "< 2 words" in the paper => n_words < 2
#: Measurement slack on the 1.0 s backchannel limit: ASR/VAD segment bounds carry ~0.1 s of
#: jitter (human GT: a 1.04 s "yeah" is still a backchannel). Compared as dur < 1.0 + 0.1.
BACKCHANNEL_DUR_SLACK_S = 0.1
#: smooth-handoff passes when the onset is <= de + tolerance. Mined handoff windows are tight
#: (0.3-1.3 s) and human onsets landed 80-370 ms after de; latency is still onset - ds.
HANDOFF_ONSET_TOLERANCE_S = 0.5
#: backchannel-produced / stay-silent: a segment counts as in-window when it overlaps
#: [ds - tol, de + tol] (human GT "Okay" 80 ms after de). Other classes use the strict window.
WINDOW_EDGE_TOLERANCE_S = 0.25
STAY_SILENT_MAX_INWINDOW_S = 1.0
YIELD_MAX_LATENCY_S = 1.5
CONTINUE_PRE_WINDOW_S = 3.0
CONTINUE_PRE_ACTIVITY_MIN = 0.30
CONTINUE_IN_ACTIVITY_MIN = 0.50
#: A segment ending within this many seconds before ds counts as "immediately preceding" ds.
YIELD_NEAR_DS_S = 1.0
#: Silence this long after a segment marks the yield moment (F.2.3 "sustained silence").
SUSTAINED_SILENCE_S = 1.5
#: Yield moment up to this long after de still counts as a yield "with brief late lag".
YIELD_LATE_LAG_MAX_S = 3.0


def is_backchannel(seg: Segment) -> bool:
    """< 1 s (+ 0.1 s slack) and < 2 normalised words; a wordless VAD region ("mhm") qualifies."""
    return (seg.dur < BACKCHANNEL_MAX_DUR_S + BACKCHANNEL_DUR_SLACK_S
            and seg.n_words < BACKCHANNEL_MAX_WORDS)


def timing_class(dynamic: DynamicType, bucket: Bucket) -> TimingClass | None:
    """App. C.2 timing class for a (dynamic, bucket); None when no timing metric applies."""
    return TIMING_CLASS.get((DynamicType(dynamic), Bucket(bucket)))


@dataclass
class OverlapSummary:
    """Pre-computed in-window overlap line + PRE/IN/POST partition (F.2.3)."""

    total_in_window_s: float
    overlaps: list[tuple[Segment, float]]      # (segment, seconds overlapping the window)
    pre_activity: float                        # fraction of [0, ds) with agent speech
    in_activity: float                         # fraction of [ds, de]
    post_activity: float                       # fraction of (de, clip_end]
    ds: float = 0.0
    de: float = 0.0

    def line(self) -> str:
        """'Agent in-window speech: 2.00s total across 1 segment(s) --- [3.28-9.28] overlaps by 2.00s'."""
        if not self.overlaps:
            return (f"Agent in-window speech: 0.00s "
                    f"(no segments overlap [{self.ds:.2f}, {self.de:.2f}])")
        parts = ", ".join(f"[{s.start:.2f}-{s.end:.2f}] overlaps by {o:.2f}s" for s, o in self.overlaps)
        return (f"Agent in-window speech: {self.total_in_window_s:.2f}s total across "
                f"{len(self.overlaps)} segment(s) --- {parts}")


@dataclass
class YieldAnalysis:
    pre_activity: float
    post_activity: float
    yield_moment_s: float | None
    yielded: bool
    verdict: str
    pre_active_s: float = 0.0
    pre_window_s: float = 0.0
    post_active_s: float = 0.0
    post_window_s: float = 0.0
    lag_s: float | None = None                 # yield_moment_s - de
    trivially_silent: bool = False

    def block(self) -> str:
        """The multi-line 'Yield analysis:' text block injected into the judge payload."""
        ym = f"{self.yield_moment_s:.2f}s" if self.yield_moment_s is not None else "none"
        pre = f"{self.pre_activity * 100:.1f}% ({self.pre_active_s:.2f}s of {self.pre_window_s:.2f}s)"
        post = f"{self.post_activity * 100:.1f}% ({self.post_active_s:.2f}s of {self.post_window_s:.2f}s)"
        return "\n".join([
            "Yield analysis:",
            f"Pre-dynamic agent activity: {pre}",
            f"Post-dynamic agent activity: {post}",
            f"Yield moment (end of speech before sustained silence): {ym}",
            f"Verdict: {self.verdict}",
        ])


@dataclass
class TimingResult:
    timing_class: TimingClass
    passed: bool
    takeover: int                              # observed TO_i
    expected_takeover: int                     # TO*_c
    latency_ms: float | None
    details: dict = field(default_factory=dict)


# --- derived signals ---------------------------------------------------------

def overlap_summary(segs: list[Segment], ds: float, de: float, clip_end: float) -> OverlapSummary:
    ov = overlaps(segs, ds, de)
    return OverlapSummary(
        total_in_window_s=sum(o for _, o in ov),
        overlaps=ov,
        pre_activity=activity_fraction(segs, 0.0, ds),
        in_activity=activity_fraction(segs, ds, de),
        post_activity=activity_fraction(segs, de, clip_end),
        ds=ds,
        de=de,
    )


def _near_ds(segs: list[Segment], ds: float) -> list[Segment]:
    """Segments overlapping ds or ending within YIELD_NEAR_DS_S before it, plus everything after."""
    return sorted((s for s in segs if s.end >= ds - YIELD_NEAR_DS_S), key=lambda s: s.start)


def _speaking_near_ds(segs: list[Segment], ds: float) -> bool:
    return any(s.start <= ds and s.end >= ds - YIELD_NEAR_DS_S for s in segs)


def _yield_moment(segs: list[Segment], ds: float, clip_end: float) -> float | None:
    """End of the first segment (overlapping/preceding ds or later) followed by >= 1.5 s of silence."""
    cands = _near_ds(segs, ds)
    for i, s in enumerate(cands):
        next_start = cands[i + 1].start if i + 1 < len(cands) else clip_end
        if next_start - s.end >= SUSTAINED_SILENCE_S:
            return s.end
    return None


def yield_analysis(segs: list[Segment], ds: float, de: float, clip_end: float,
                   pre_s: float = 5.0, post_s: float = 14.0) -> YieldAnalysis:
    pre0 = max(0.0, ds - pre_s)
    post1 = min(clip_end, de + post_s)
    pre_act = activity_fraction(segs, pre0, ds)
    post_act = activity_fraction(segs, de, post1)
    pre_w, post_w = ds - pre0, max(0.0, post1 - de)
    act = f"Activity {pre_act * 100:.0f}% -> {post_act * 100:.0f}% post-dynamic."
    ya = YieldAnalysis(
        pre_activity=pre_act, post_activity=post_act, yield_moment_s=None, yielded=False, verdict="",
        pre_active_s=pre_act * pre_w, pre_window_s=pre_w,
        post_active_s=post_act * post_w, post_window_s=post_w,
    )
    if not _speaking_near_ds(segs, ds):
        ya.trivially_silent = True
        ya.verdict = f"AGENT WAS NOT SPEAKING (trivially silent). No agent speech near dynamic_start_s. {act}"
        return ya
    ym = _yield_moment(segs, ds, clip_end)
    ya.yield_moment_s = ym
    if ym is None:
        ya.verdict = f"AGENT DID NOT YIELD. No sustained silence after dynamic_start_s. {act}"
        return ya
    lag = ym - de
    ya.lag_s = lag
    moment = f"Yield moment: {ym:.2f}s ({lag:+.2f}s after dynamic_end_s)."
    if lag <= YIELD_MAX_LATENCY_S:
        ya.yielded = True
        ya.verdict = f"AGENT YIELDED. {moment} {act}"
    elif lag <= YIELD_LATE_LAG_MAX_S:
        ya.yielded = True
        ya.verdict = f"AGENT YIELDED with brief late lag. {moment} {act}"
    else:
        ya.verdict = f"AGENT DID NOT YIELD. {moment} {act}"
    return ya


# --- pass rules ---------------------------------------------------------------

def _ms(x: float | None) -> float | None:
    return None if x is None else round(x * 1000.0, 3)


def _onset_latency(seg: Segment, ds: float) -> float:
    """Onset of `seg` relative to ds; 0 if it was already speaking at ds."""
    return max(0.0, seg.start - ds)


def evaluate(segs: list[Segment], ds: float, de: float, cls: TimingClass,
             *, agent_speaks_first: bool = False, clip_end: float | None = None) -> TimingResult:
    """Apply the pass rule for `cls` (docs/protocol.md §4) and compute latency.

    stay-silent:        pass if in-window speech <= 1.0 s OR all overlapping segs are backchannels.
    continue-speaking:  if activity in [ds-3, ds) >= 30 % then require in-window activity >= 50 %; else vacuous pass.
    yield-required:     latency = end of seg overlapping ds (or last seg ending before ds) - ds; pass if <= 1.5 s.
                        No speech near ds -> fail, details["trivially_silent"] = True.
    smooth-handoff:     latency = first onset after ds - ds (0 if speaking at ds);
                        pass if onset <= de + HANDOFF_ONSET_TOLERANCE_S.
    backchannel-produced: pass if >= 1 in-window backchannel AND no in-window non-backchannel seg.
    takeover = 0 if in-window output is silence/backchannels only, else 1.

    "In-window" for the backchannel classes (stay-silent, backchannel-produced) means overlapping
    [ds - WINDOW_EDGE_TOLERANCE_S, de + WINDOW_EDGE_TOLERANCE_S]; `in_window_speech_s` and every
    other class use the strict window [ds, de].
    """
    cls = TimingClass(cls)
    if clip_end is None:
        clip_end = max([de] + [s.end for s in segs])
    segs = sorted(segs, key=lambda s: s.start)
    ov = overlaps(segs, ds, de)
    in_segs = [s for s, _ in ov]
    in_speech_s = sum(o for _, o in ov)
    details: dict = {"in_window_speech_s": round(in_speech_s, 3), "agent_speaks_first": agent_speaks_first}
    if cls in (TimingClass.STAY_SILENT, TimingClass.BACKCHANNEL_PRODUCED):
        tol = WINDOW_EDGE_TOLERANCE_S
        member = [s for s, _ in overlaps(segs, ds - tol, de + tol)]
        details["window_edge_tolerance_s"] = tol
    else:
        member = in_segs
    non_bc = [s for s in member if not is_backchannel(s)]
    bc = [s for s in member if is_backchannel(s)]
    takeover = 0 if not non_bc else 1
    latency: float | None = None

    if cls is TimingClass.STAY_SILENT:
        passed = in_speech_s <= STAY_SILENT_MAX_INWINDOW_S or not non_bc
        if in_segs:
            latency = _onset_latency(in_segs[0], ds)
        details["all_backchannel"] = not non_bc

    elif cls is TimingClass.CONTINUE_SPEAKING:
        pre_act = activity_fraction(segs, max(0.0, ds - CONTINUE_PRE_WINDOW_S), ds)
        in_act = activity_fraction(segs, ds, de)
        details.update(pre_activity=pre_act, in_activity=in_act)
        if pre_act >= CONTINUE_PRE_ACTIVITY_MIN:
            passed = in_act >= CONTINUE_IN_ACTIVITY_MIN
            details["vacuous"] = False
        else:
            passed = True
            details["vacuous"] = True

    elif cls is TimingClass.YIELD_REQUIRED:
        at_ds = speaking_at(segs, ds)
        if at_ds is None:
            preceding = [s for s in segs if s.end <= ds and s.end >= ds - YIELD_NEAR_DS_S]
            at_ds = max(preceding, key=lambda s: s.end) if preceding else None
        if at_ds is None:
            passed = False
            details["trivially_silent"] = True
        else:
            stop = at_ds.end - ds
            details["trivially_silent"] = False
            details["stop_offset_s"] = round(stop, 3)
            latency = max(0.0, stop)
            passed = stop <= YIELD_MAX_LATENCY_S
        ya = yield_analysis(segs, ds, de, clip_end)
        details["yield_moment_s"] = ya.yield_moment_s
        details["yielded"] = ya.yielded
        details["verdict"] = ya.verdict

    elif cls is TimingClass.SMOOTH_HANDOFF:
        at_ds = speaking_at(segs, ds)
        if at_ds is not None:
            latency, passed = 0.0, True
            details["already_speaking_at_ds"] = True
        else:
            details["already_speaking_at_ds"] = False
            onset = first_onset(segs, ds, clip_end)
            if onset is None:
                passed = False
                details["no_onset"] = True
            else:
                latency = onset - ds
                passed = onset <= de + HANDOFF_ONSET_TOLERANCE_S
                details["no_onset"] = False
                details["onset_after_de_s"] = round(onset - de, 3)
                details["onset_tolerance_s"] = HANDOFF_ONSET_TOLERANCE_S

    elif cls is TimingClass.BACKCHANNEL_PRODUCED:
        passed = bool(bc) and not non_bc
        details.update(n_backchannels=len(bc), n_floor_takes=len(non_bc))
        if bc:
            latency = _onset_latency(bc[0], ds)

    else:  # pragma: no cover
        raise ValueError(f"unknown timing class {cls}")

    return TimingResult(
        timing_class=cls, passed=bool(passed), takeover=takeover,
        expected_takeover=EXPECTED_TAKEOVER[cls], latency_ms=_ms(latency), details=details,
    )


# --- aggregation --------------------------------------------------------------

def _summarise(results: list[TimingResult]) -> dict:
    n = len(results)
    lat = [r.latency_ms for r in results if r.latency_ms is not None]
    return {
        "n": n,
        "n_pass": sum(r.passed for r in results),
        "tor_alignment": (sum(r.passed for r in results) / n) if n else None,
        "takeover_rate": (sum(r.takeover for r in results) / n) if n else None,
        "median_latency_ms": median(lat) if lat else None,
    }


def aggregate(results: dict[str, list[TimingResult]]) -> dict:
    """{dynamic: {"tor_alignment": float, "median_latency_ms": float|None, "n": int}, "overall": {...}}.

    TOR-Alignment = fraction of clips whose observed takeover matches EXPECTED_TAKEOVER
    (equivalently, whose pass rule holds). `takeover_rate` is the raw TOR (mean TO_i).
    "overall" pools every clip (not a mean of per-dynamic rates).
    """
    out: dict = {}
    for dyn, rs in results.items():
        out[dyn] = _summarise(rs)
        classes = {r.timing_class.value for r in rs}
        out[dyn]["timing_class"] = classes.pop() if len(classes) == 1 else sorted(classes)
    out["overall"] = _summarise([r for rs in results.values() for r in rs])
    return out
