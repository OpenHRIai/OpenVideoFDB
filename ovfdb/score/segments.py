"""Segment helpers: words -> segments, activity/overlap math, PRE/IN/POST partition.

Pure functions (no I/O) over `ovfdb.schema.Word` / `Segment` so they can be
unit-tested with synthetic data. Spec: plans/WS4-scoring-timing.md; payload
format: docs/protocol.md §5 and paper App. F.5.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ovfdb.schema import Segment, Word

#: Two words closer than this (silence between them) belong to one segment.
SEGMENT_GAP_S = 0.5

#: Non-lexical vocalisation tokens ("mm", "hmm", "mhm", "uh", "huh", "um", "ah", "oh"). Whisper
#: writes "mm-hmm" / "mm -hmm" / "uh huh" as two tokens; consecutive vocalisations count as one.
_VOCALISATION = re.compile(r"^(?:m+|h+m+|m+h+m*|u+h+|hu+h+|u+m+|a+h+|o+h+)$")
_NON_TOKEN = re.compile(r"[^a-z0-9'\s]")


def normalise_tokens(text: str) -> list[str]:
    """Lower-cased, punctuation-free tokens for word counting (docs/protocol.md §4).

    Hyphens split tokens; consecutive vocalisation tokens merge ("mm -hmm" -> "mmhmm",
    "uh huh" -> "uhhuh"); an immediate repetition collapses ("yeah yeah" -> "yeah").
    """
    cleaned = _NON_TOKEN.sub(" ", text.lower().replace("-", " "))
    out: list[str] = []
    for tok in (t.strip("'") for t in cleaned.split()):
        if not tok:
            continue
        if out and _VOCALISATION.match(tok) and _VOCALISATION.match(out[-1]):
            out[-1] += tok
        elif not out or tok != out[-1]:
            out.append(tok)
    return out


def count_words(text: str) -> int:
    """Number of normalised tokens in `text` (the `n_words` a backchannel is judged on)."""
    return len(normalise_tokens(text))


def words_to_segments(words: list[Word], gap: float = SEGMENT_GAP_S) -> list[Segment]:
    """Merge consecutive words into segments when the silence between them is < `gap`.

    Words are sorted by start first; text is space-joined; `n_words` is `count_words` of the
    joined text. Empty-text words are dropped. For callers with no audio; with audio prefer
    `merge_vad_and_words`.
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
    text = " ".join(w.text.strip() for w in ws)
    return Segment(start=ws[0].start, end=max(w.end for w in ws), text=text, n_words=count_words(text))


def merge_regions(regions: list[tuple[float, float]], gap: float) -> list[tuple[float, float]]:
    """Sort `(start, end)` regions and merge any two separated by less than `gap` seconds."""
    out: list[tuple[float, float]] = []
    for s, e in sorted(regions):
        if out and s - out[-1][1] < gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _nearest_region(regions: list[tuple[float, float]], w: Word) -> tuple[int | None, float]:
    """(index, distance) of the region closest to word `w`; distance 0 when they overlap."""
    best, best_d = None, float("inf")
    for i, (s, e) in enumerate(regions):
        d = max(0.0, s - w.end, w.start - e)
        if d < best_d:
            best, best_d = i, d
    return best, best_d


def merge_vad_and_words(regions: list[tuple[float, float]], words: list[Word],
                        gap: float = SEGMENT_GAP_S) -> list[Segment]:
    """Segments from VAD `regions`, with ASR `words` attached for text / `n_words`.

    Regions closer than `gap` are merged first (same rule as `words_to_segments`). A word
    belongs to the region containing its midpoint, else to the nearest region within `gap`
    (whisper onsets lag the acoustic onset by up to ~0.4 s). A region with no words is a
    non-lexical vocalisation: `Segment(text="", n_words=0)`. Words farther than `gap` from
    every region are kept as word-only segments so lexical content is never dropped.
    """
    regs = merge_regions([(float(s), float(e)) for s, e in regions if e > s], gap)
    attached: list[list[Word]] = [[] for _ in regs]
    orphans: list[Word] = []
    for w in sorted((w for w in words if w.text.strip()), key=lambda w: (w.start, w.end)):
        mid = (w.start + w.end) / 2.0
        idx = next((i for i, (s, e) in enumerate(regs) if s <= mid <= e), None)
        if idx is None:
            near, dist = _nearest_region(regs, w)
            idx = near if near is not None and dist < gap else None
        if idx is None:
            orphans.append(w)
        else:
            attached[idx].append(w)
    segs: list[Segment] = []
    for (s, e), ws in zip(regs, attached):
        text = " ".join(w.text.strip() for w in ws)
        segs.append(Segment(start=s, end=e, text=text, n_words=count_words(text)))
    segs.extend(words_to_segments(orphans, gap))
    return sorted(segs, key=lambda x: (x.start, x.end))


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
    segs: list[Segment] = field(default_factory=list)     # source (unclipped) segment of each span

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
                part.segs.append(s)
    return parts


#: Mirrors `timing.is_backchannel` (kept here to avoid a circular import): < 1 s (+0.1 s slack), < 2 words.
_BACKCHANNEL_MAX_DUR_S = 1.1
_BACKCHANNEL_MAX_WORDS = 2
_NOTE_MAX_CHARS = 70


def _short_quote(text: str, limit: int = _NOTE_MAX_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return f'"{text}"'
    head = text[: limit - 3]
    head = head.rsplit(" ", 1)[0] if " " in head else head     # cut at a word boundary
    return f'"{head.rstrip()}..."'


def span_note(seg: Segment, a: float, b: float) -> str:
    """What the agent was doing acoustically in the span [a, b] of `seg` (judge payload v2).

    A wordless VAD region is flagged as a non-lexical vocalisation so the judge does not read a
    breath or "mhm" as talk-over; a short one-word segment is flagged as a backchannel; a span that
    is only part of a longer segment says so and gives the segment's full extent.
    """
    if seg.n_words == 0:
        return 'non-lexical vocalisation, no words (breath / "mhm" / laugh)'
    q = _short_quote(seg.text)
    if seg.n_words < _BACKCHANNEL_MAX_WORDS and seg.dur < _BACKCHANNEL_MAX_DUR_S:
        q = f"backchannel {q}"
    if (b - a) < seg.dur - 1e-6:
        return f"part of {q} [{seg.start:.2f}-{seg.end:.2f}]"
    return q


def _span_line(s: float, e: float, note: str = "") -> str:
    line = f"[{s:6.2f}, {e:.2f}] {e - s:.2f}s"
    return f"{line}  {note}" if note else line


def format_partition(parts: Partition, annotate: bool = True) -> str:
    """Render the partition as the judge payload block (paper F.5.1 example):

        -- PRE-DYNAMIC (0.00 -> 37.00s) -- active 10.00s of 37.00s (27%)
        [ 20.24, 24.32] 4.08s
        -- DYNAMIC WINDOW (37.00 -> 46.00s) -- active 0.00s of 9.00s (0%)
        (no agent speech overlaps the dynamic window)
        -- POST-DYNAMIC (46.00 -> 61.00s) -- active 0.00s of 15.00s (0%)

    With `annotate` (payload v2) every span line also carries `span_note`: the words spoken,
    `backchannel "Yeah"`, or `non-lexical vocalisation, no words (...)`.
    """
    lines: list[str] = []
    for part in (parts.pre, parts.inside, parts.post):
        lines.append(
            f"-- {part.name} ({part.t0:.2f} -> {part.t1:.2f}s) -- "
            f"active {part.active_s:.2f}s of {part.dur:.2f}s ({part.activity * 100:.0f}%)"
        )
        if part is parts.inside and not part.spans:
            lines.append("(no agent speech overlaps the dynamic window)")
        for (s, e), seg in zip(part.spans, part.segs):
            lines.append(_span_line(s, e, span_note(seg, s, e) if annotate else ""))
    return "\n".join(lines)
