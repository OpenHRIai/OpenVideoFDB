"""Segment helpers: words -> segments, activity/overlap math, PRE/IN/POST partition.

Pure functions (no I/O) over `ovfdb.schema.Word` / `Segment` so they can be
unit-tested with synthetic data. Spec: plans/WS4-scoring-timing.md; payload
format: docs/protocol.md §5 and paper App. F.5.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ovfdb.schema import Segment, Word

#: Two words closer than this (silence between them) belong to one segment.
SEGMENT_GAP_S = 0.5


def words_to_segments(words: list[Word], gap: float = SEGMENT_GAP_S) -> list[Segment]:
    """Merge consecutive words into segments when the silence between them is < `gap`.

    Words are sorted by start first; text is space-joined; `n_words` counts the words
    merged into each segment. Empty-text words are dropped.
    """
    ws = sorted((w for w in words if w.text.strip()), key=lambda w: (w.start, w.end))
    segs: list[Segment] = []
    cur_words: list[Word] = []
    for w in ws:
        if cur_words and (w.start - cur_words[-1].end) < gap:
            cur_words.append(w)
        else:
            if cur_words:
                segs.append(_make_segment(cur_words))
            cur_words = [w]
    if cur_words:
        segs.append(_make_segment(cur_words))
    return segs


def _make_segment(ws: list[Word]) -> Segment:
    return Segment(
        start=ws[0].start,
        end=max(w.end for w in ws),
        text=" ".join(w.text.strip() for w in ws),
        n_words=len(ws),
    )


def overlap_seconds(seg: Segment, t0: float, t1: float) -> float:
    """Seconds of `seg` that fall inside [t0, t1] (0 if none)."""
    return max(0.0, min(seg.end, t1) - max(seg.start, t0))


def overlaps(segs: list[Segment], t0: float, t1: float) -> list[tuple[Segment, float]]:
    """Segments overlapping [t0, t1] by a positive amount, with the overlap in seconds."""
    out = []
    for s in segs:
        o = overlap_seconds(s, t0, t1)
        if o > 0:
            out.append((s, o))
    return out


def active_seconds(segs: list[Segment], t0: float, t1: float) -> float:
    return sum(o for _, o in overlaps(segs, t0, t1))


def activity_fraction(segs: list[Segment], t0: float, t1: float) -> float:
    """Fraction of [t0, t1] covered by agent speech; 0.0 for an empty interval."""
    if t1 <= t0:
        return 0.0
    return min(1.0, active_seconds(segs, t0, t1) / (t1 - t0))


def first_onset(segs: list[Segment], t0: float, t1: float) -> float | None:
    """Start of the first segment that begins inside [t0, t1], or None."""
    starts = [s.start for s in segs if t0 <= s.start <= t1]
    return min(starts) if starts else None


def speaking_at(segs: list[Segment], t: float) -> Segment | None:
    """The segment containing time `t` (start <= t < end), or None."""
    for s in segs:
        if s.start <= t < s.end:
            return s
    return None


# --- PRE / IN / POST partition (judge payload) ------------------------------

@dataclass
class Part:
    """One region of the partition. `spans` are segments clipped to [t0, t1]."""

    name: str
    t0: float
    t1: float
    spans: list[tuple[float, float]] = field(default_factory=list)

    @property
    def active_s(self) -> float:
        return sum(e - s for s, e in self.spans)

    @property
    def dur(self) -> float:
        return max(0.0, self.t1 - self.t0)

    @property
    def activity(self) -> float:
        return min(1.0, self.active_s / self.dur) if self.dur > 0 else 0.0


@dataclass
class Partition:
    pre: Part
    inside: Part
    post: Part


def partition(segs: list[Segment], ds: float, de: float, clip_end: float) -> Partition:
    """Split agent speech into PRE [0, ds), IN [ds, de], POST (de, clip_end].

    A segment straddling a boundary is clipped and appears in both regions, so
    each region's listed spans sum to its reported active seconds.
    """
    parts = Partition(
        pre=Part("PRE-DYNAMIC", 0.0, ds),
        inside=Part("DYNAMIC WINDOW", ds, de),
        post=Part("POST-DYNAMIC", de, clip_end),
    )
    for part in (parts.pre, parts.inside, parts.post):
        for s in sorted(segs, key=lambda x: x.start):
            a, b = max(s.start, part.t0), min(s.end, part.t1)
            if b > a:
                part.spans.append((a, b))
    return parts


def _span_line(s: float, e: float) -> str:
    return f"[{s:6.2f}, {e:.2f}] {e - s:.2f}s"


def format_partition(parts: Partition) -> str:
    """Render the partition as the judge payload block (paper F.5.1 example):

        -- PRE-DYNAMIC (0.00 -> 37.00s) -- active 10.00s of 37.00s (27%)
        [ 20.24, 24.32] 4.08s
        -- DYNAMIC WINDOW (37.00 -> 46.00s) -- active 0.00s of 9.00s (0%)
        (no agent speech overlaps the dynamic window)
        -- POST-DYNAMIC (46.00 -> 61.00s) -- active 0.00s of 15.00s (0%)
    """
    lines: list[str] = []
    for part in (parts.pre, parts.inside, parts.post):
        lines.append(
            f"-- {part.name} ({part.t0:.2f} -> {part.t1:.2f}s) -- "
            f"active {part.active_s:.2f}s of {part.dur:.2f}s ({part.activity * 100:.0f}%)"
        )
        if part is parts.inside and not part.spans:
            lines.append("(no agent speech overlaps the dynamic window)")
        lines.extend(_span_line(s, e) for s, e in part.spans)
    return "\n".join(lines)
