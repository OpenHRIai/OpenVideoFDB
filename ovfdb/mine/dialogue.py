"""Dialogue-channel candidate finders (plans/WS2-mining.md, day 1).

Pure functions over the two participants' VAD regions and transcript
utterances: segments in, ``Candidate`` list out. No media, no network, so
everything here is unit-testable with synthetic fixtures
(``tests/test_mining_rules.py``).

Role convention (same as the spec table): **A = the participant who becomes
the user**, **B = the partner** (human ground-truth "agent"). Every finder
takes ``(vad_a, utts_a, vad_b, utts_b)`` with A as user; ``find_all`` runs each
finder with both role assignments and tags the result with ``user_role``
(``'a'`` or ``'b'`` = which of the two input files is the user).

Definitions
-----------
* backchannel = utterance ``< 1 s`` and ``< 2 words``.
* turn = maximal run of one speaker's VAD regions separated by ``< 0.6 s``
  of silence, split where a non-backchannel utterance of the other speaker
  starts overlapping it.
* All times are raw file seconds (the VAD/transcript timeline); the clip
  module re-bases them.

Rule ambiguities and how they were resolved are documented on each finder.

Selection is **user-cue-only** (v1 rules, 2026-10-16): a candidate is chosen
from what A does (and from B's state *before* the cue, which is part of the cue
itself), never from how B reacted afterwards. Windows are fixed stretches after
the cue (``HANDOFF_S``, ``YIELD_S``, ``BC_SLOT_AFTER_S``). The v0 rules
conditioned on B's reaction (partner silent through the pause, stopped within
1.5 s, replied inside the window, produced the backchannel), which made the
human reference pass every timing rule by construction (paper: 90 % / 78 %).
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

from ovfdb.data.seamless import Utterance
from ovfdb.schema import Bucket, DynamicType, Segment

TURN_GAP = 0.6            # silence that still joins two VAD regions into one turn
BACKCHANNEL_MAX_DUR = 1.0
BACKCHANNEL_MAX_WORDS = 2  # strictly fewer than this many words
HANDOFF_S = 1.5           # Turn-taking window after the user's turn end (paper GT median onset 640 ms)
YIELD_S = 1.5             # Verbal Interruption window after the user's onset (= the yield-required limit)
BC_SLOT_BEFORE_S = 0.25   # Verbal Backchanneling window: this much before the user's intra-turn gap ...
BC_SLOT_AFTER_S = 1.0     # ... to this much after it (listeners backchannel at or just after a clause end)

LAUGH_TOKEN_RE = re.compile(r"\[laugh[a-z]*\]|\(laugh[a-z]*\)|<laugh[a-z]*>|\bha(?:ha)+\b|\bhehe+\b", re.IGNORECASE)


@dataclass
class Turn:
    speaker: str                 # 'a' | 'b' (in the finder's frame: 'a' = user)
    start: float
    end: float
    segs: list[Segment] = field(default_factory=list)

    @property
    def dur(self) -> float:
        return self.end - self.start


@dataclass
class Candidate:
    dynamic_type: DynamicType
    bucket: Bucket
    user_role: str               # 'a' | 'b': which input file becomes the user
    ds_raw: float                # dynamic window start, raw file seconds
    de_raw: float
    evidence: dict = field(default_factory=dict)

    @property
    def key(self) -> tuple:
        return (self.dynamic_type.value, self.bucket.value, self.user_role, round(self.ds_raw, 2), round(self.de_raw, 2))


# --- helpers ------------------------------------------------------------------

def n_words(utt: Utterance) -> int:
    if utt.words:
        return len(utt.words)
    return len(utt.transcript.split())


def is_backchannel(utt: Utterance) -> bool:
    """Spec: utterance < 1 s and < 2 words (so exactly one token, e.g. "mhm", "yeah")."""
    return (utt.end - utt.start) < BACKCHANNEL_MAX_DUR and n_words(utt) < BACKCHANNEL_MAX_WORDS


def merge_regions(vad: list[Segment], gap: float = TURN_GAP) -> list[list[Segment]]:
    """Group VAD regions separated by less than ``gap`` seconds of silence."""
    runs: list[list[Segment]] = []
    for seg in sorted(vad, key=lambda s: s.start):
        if runs and seg.start - runs[-1][-1].end < gap:
            runs[-1].append(seg)
        else:
            runs.append([seg])
    return runs


def _speaking(vad: list[Segment], t0: float, t1: float) -> bool:
    """True when any VAD region overlaps the open interval (t0, t1)."""
    return any(s.start < t1 and s.end > t0 for s in vad)


def _speech_in(vad: list[Segment], t0: float, t1: float) -> float:
    """Seconds of VAD speech inside [t0, t1]."""
    return sum(max(0.0, min(s.end, t1) - max(s.start, t0)) for s in vad)


def _utts_overlapping(utts: list[Utterance], t0: float, t1: float) -> list[Utterance]:
    return [u for u in utts if u.start < t1 and u.end > t0]


def _text_in(utts: list[Utterance], t0: float, t1: float) -> str:
    return " ".join(u.transcript for u in _utts_overlapping(utts, t0, t1)).strip()


def _words_in(utts: list[Utterance], t0: float, t1: float) -> int:
    return sum(1 for u in utts for w in u.words if w.start < t1 and w.end > t0)


def speaker_turns(vad: list[Segment], other_utts: list[Utterance], speaker: str) -> list[Turn]:
    """Turns of one speaker: 0.6 s-merged VAD runs, split at the onset of any
    overlapping non-backchannel utterance of the other speaker."""
    cuts = sorted(u.start for u in other_utts if not is_backchannel(u))
    turns: list[Turn] = []
    for run in merge_regions(vad):
        cur: list[Segment] = []
        for seg in run:
            # a cut strictly inside the run so far, between the previous region and this one
            if cur and any(cur[-1].end <= c <= seg.start for c in cuts):
                turns.append(Turn(speaker, cur[0].start, cur[-1].end, cur))
                cur = []
            cur.append(seg)
        if cur:
            turns.append(Turn(speaker, cur[0].start, cur[-1].end, cur))
    return turns


def turns(vad_a: list[Segment], utts_a: list[Utterance], vad_b: list[Segment], utts_b: list[Utterance]) -> list[Turn]:
    """Both speakers' turns, time-ordered."""
    return sorted(speaker_turns(vad_a, utts_b, "a") + speaker_turns(vad_b, utts_a, "b"), key=lambda t: (t.start, t.end))


# --- finders (A = user) ---------------------------------------------------------

def find_pause_handling(vad_a, utts_a, vad_b, utts_b, min_gap=1.0, max_gap=4.0, min_turn=1.0,
                        floor_s=1.0) -> list[Candidate]:
    """Pause Handling (P): inside A's turn a silence of 1.0–4.0 s after which A
    resumes (same thought, checked by the VLM). Window = the silence.

    User-cue-only: A held the floor going into the pause (B has no VAD in the
    last ``floor_s`` of A's turn) and A speaks again for >= ``min_turn`` s.
    What B did *during or after* the pause is not consulted --- a partner who
    talks through the pause is the interesting "human slipped" case.

    Because turns are cut at 0.6 s of silence, "a pause inside A's turn" is read
    as two consecutive A VAD runs (each >= ``min_turn`` s); B's non-backchannel
    onsets split A's runs, so A's runs are rebuilt here without B's cuts.
    """
    ta = speaker_turns(vad_a, [], "a")              # A's runs only; B's talk does not cut them
    out = []
    for prev, nxt in itertools.pairwise(ta):
        gap = nxt.start - prev.end
        if not (min_gap <= gap <= max_gap):
            continue
        if prev.dur < min_turn or nxt.dur < min_turn:
            continue
        if _speaking(vad_b, prev.end - floor_s, prev.end):
            continue                                 # B was talking as A trailed off: not A's floor
        before = _text_in(utts_a, prev.start, prev.end)
        out.append(Candidate(
            DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION, "a", prev.end, nxt.start,
            {"rule": "pause_handling", "gap_s": round(gap, 2), "turn_before_s": round(prev.dur, 2),
             "turn_after_s": round(nxt.dur, 2), "text_before": before[-160:],
             "text_after": _text_in(utts_a, nxt.start, nxt.end)[:120],
             "b_text_before": _text_in(utts_b, prev.start - 8.0, prev.end)[-160:],
             "score": round(min(gap, 2.5) + min(prev.dur, 10) / 10, 3)},
        ))
    return out


def find_verbal_backchanneling(vad_a, utts_a, vad_b, utts_b, min_turn=6.0, min_before=3.0, min_after=1.5,
                               max_gap=0.6, min_gap=0.15, listener_s=2.0) -> list[Candidate]:
    """Verbal Backchanneling (G): a listener slot inside A's long turn. Window =
    an intra-turn gap of A (clause boundary) from ``BC_SLOT_BEFORE_S`` before it
    to ``BC_SLOT_AFTER_S`` after it (~1.3-1.9 s).

    User-cue-only: A has held the floor for >= ``min_before`` s, keeps going
    for >= ``min_after`` s, the whole turn is >= ``min_turn`` s, and B was a
    silent listener for ``listener_s`` before the slot. Whether B actually said
    "mhm" is NOT used (v0 built the window around B's backchannel, so GT
    passed by construction; paper human reference = 69 %).
    """
    out = []
    for run in merge_regions(vad_a):
        t_start, t_end = run[0].start, run[-1].end
        if t_end - t_start < min_turn:
            continue
        for s0, s1 in itertools.pairwise(run):
            gap = s1.start - s0.end
            if not (min_gap <= gap <= max_gap):
                continue
            if s0.end - t_start < min_before or t_end - s1.start < min_after:
                continue
            if _speaking(vad_b, s0.end - listener_s, s0.end):
                continue                             # B was not listening quietly: no clean slot
            ds, de = s0.end - BC_SLOT_BEFORE_S, s1.start + BC_SLOT_AFTER_S
            text_before = _text_in(utts_a, max(t_start, s0.end - 6.0), s0.end)
            clause_end = text_before.rstrip().endswith((",", ".", "?", "!", ";", "and", "but", "so", "like"))
            out.append(Candidate(
                DynamicType.VERBAL_BACKCHANNELING, Bucket.GENERATION, "a", ds, de,
                {"rule": "verbal_backchanneling", "gap_s": round(gap, 2), "host_turn": [round(t_start, 2), round(t_end, 2)],
                 "turn_before_s": round(s0.end - t_start, 2), "text_before": text_before[-160:],
                 "text_after": _text_in(utts_a, s1.start, min(t_end, s1.start + 4.0))[:120],
                 "b_text_before": _text_in(utts_b, t_start - 8.0, t_start)[-160:],
                 "score": round((1.0 if clause_end else 0.0) + min(t_end - t_start, 20) / 20 + min(gap, 0.6), 3)},
            ))
    return out


def find_verbal_interruption(vad_a, utts_a, vad_b, utts_b, min_hold=2.0, min_b_before=1.0,
                             articulating_s=0.4) -> list[Candidate]:
    """Verbal Interruption (G): A starts a non-backchannel utterance while B is
    mid-sentence and then holds the floor >= 2 s. Window = A's onset ->
    onset + ``YIELD_S`` (the yield-required limit). The user is A (the
    interrupter); the agent is B, so ``agent_speaks_first`` is True downstream.

    User-cue-only: B had been speaking for >= ``min_b_before`` s and was still
    articulating a word within ``articulating_s`` of A's onset (mid-sentence,
    not a finished turn); A's VAD run lasts >= ``min_hold`` past the onset.
    Whether B stopped, and when, is NOT used (v0 required a stop within 1.5 s,
    i.e. the pass rule itself; paper human reference = 70 %).
    """
    b_runs = merge_regions(vad_b)
    out = []
    for u in utts_a:
        if is_backchannel(u) or n_words(u) < 2:
            continue
        run = next((r for r in b_runs if r[0].start < u.start < r[-1].end), None)
        if run is None:
            continue
        b_on = run[0].start
        if u.start - b_on < min_b_before:
            continue
        if not any(abs(w.start - u.start) <= articulating_s or w.start <= u.start < w.end
                   for v in utts_b for w in v.words):
            continue                                 # B had no word at the onset: a trailing-off turn
        a_run = next((r for r in merge_regions(vad_a) if r[0].start <= u.start + 0.2 and r[-1].end > u.start), None)
        hold = (a_run[-1].end - u.start) if a_run else (u.end - u.start)
        if hold < min_hold:
            continue
        out.append(Candidate(
            DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION, "a", u.start, u.start + YIELD_S,
            {"rule": "verbal_interruption", "a_hold_s": round(hold, 2),
             "b_speaking_before_s": round(u.start - b_on, 2), "a_text": u.transcript[:120],
             "b_text_before": _text_in(utts_b, b_on, u.start)[-160:],
             "score": round(min(hold, 6) / 6 + min(u.start - b_on, 5) / 5, 3)},
        ))
    return out


def find_turn_taking(vad_a, utts_a, vad_b, utts_b, min_gap=0.2, max_gap=1.5, min_a_turn=1.5,
                     user_quiet_s=4.0, no_overlap_s=0.5) -> list[Candidate]:
    """Turn-taking (G): B's turn ends, gap 0.2–1.5 s, A's turn starts; A then
    finishes and offers the floor. Window = A's turn end -> end + ``HANDOFF_S``.

    User-cue-only: A's turn is a real contribution (>= 1.5 s, >= 2 words), B
    was not overlapping A's last ``no_overlap_s`` (pre-cue), and A does not
    start another >= 2-word utterance within ``user_quiet_s`` after ending
    (otherwise it is a within-turn pause, not a floor offer; a 1-word "yeah"
    reacting to the partner is allowed). Whether/when B replied is NOT used
    (v0 ended the window at B's onset; paper human reference = 100 % / 640 ms).
    """
    all_turns = turns(vad_a, utts_a, vad_b, utts_b)
    out = []
    for i in range(1, len(all_turns)):
        b1, a = all_turns[i - 1], all_turns[i]
        if (b1.speaker, a.speaker) != ("b", "a"):
            continue
        g1 = a.start - b1.end
        if not (min_gap <= g1 <= max_gap):
            continue
        if a.dur < min_a_turn or _words_in(utts_a, a.start, a.end) < 2:
            continue
        if _speaking(vad_b, a.end - no_overlap_s, a.end):
            continue
        if any(u.start > a.end and u.start < a.end + user_quiet_s and n_words(u) >= 2 for u in utts_a):
            continue
        a_text = _text_in(utts_a, a.start, a.end)
        out.append(Candidate(
            DynamicType.TURN_TAKING, Bucket.GENERATION, "a", a.end, a.end + HANDOFF_S,
            {"rule": "turn_taking", "gap_before_s": round(g1, 2), "a_turn_s": round(a.dur, 2),
             "ends_with_question": a_text.rstrip().endswith("?"), "a_text": a_text[-160:],
             "b_text_before": _text_in(utts_b, b1.start, b1.end)[-160:],
             "score": round((1.0 if a_text.rstrip().endswith("?") else 0.0) + min(a.dur, 10) / 10, 3)},
        ))
    return out


def find_laughter(vad_a, utts_a, vad_b, utts_b, laughs_a: list[Segment] | None = None,
                  prev_window=3.0, react_window=2.0) -> list[Candidate]:
    """Laughter: ``laughs_a`` are A's laughter segments (from transcript tokens
    via ``laughter_from_transcript`` or from the audio heuristic in
    ``ovfdb.mine.laughter``). Window = the laugh.

    * P bucket: B was speaking in the 3 s before the laugh (the user laughs at
      the agent's words).
    * G bucket: the laugh lies inside/adjacent to A's own turn (A laughed while
      speaking); window = laugh start -> laugh end + ``react_window`` so the
      partner has room to laugh back. Whether B reacted is NOT used (v0
      required a B onset within 2 s).
    A laugh can yield both rows (same clip in both buckets, as Table 8 allows).
    """
    laughs = list(laughs_a) if laughs_a is not None else laughter_from_transcript(utts_a)
    ta = speaker_turns(vad_a, utts_b, "a")
    out = []
    for lg in laughs:
        base = {"laugh_s": round(lg.dur, 2), "laugh_text": lg.text, "laugh_words": lg.n_words}
        if _speaking(vad_b, lg.start - prev_window, lg.start):
            out.append(Candidate(DynamicType.LAUGHTER, Bucket.PERCEPTION, "a", lg.start, lg.end,
                                 {**base, "rule": "laughter_p", "b_text_before": _text_in(utts_b, lg.start - prev_window, lg.start)[-120:],
                                  "score": round(min(lg.dur, 2.0), 3)}))
        own_turn = any(t.start - 0.6 <= lg.start <= t.end + 0.6 for t in ta)
        if own_turn:
            out.append(Candidate(DynamicType.LAUGHTER, Bucket.GENERATION, "a", lg.start, lg.end + react_window,
                                 {**base, "rule": "laughter_g", "a_text": _text_in(utts_a, lg.start - 3, lg.end)[-120:],
                                  "score": round(min(lg.dur, 2.0), 3)}))
    return out


def laughter_from_transcript(utts: list[Utterance]) -> list[Segment]:
    """Laughter segments from transcript tokens ("[laughter]", "haha", "(laughs)")."""
    out = []
    for u in utts:
        hits = [w for w in u.words if LAUGH_TOKEN_RE.search(w.text)]
        if hits:
            out.append(Segment(start=min(w.start for w in hits), end=max(w.end for w in hits),
                               text=" ".join(w.text for w in hits), n_words=len(hits)))
        elif LAUGH_TOKEN_RE.search(u.transcript) and not u.words:
            out.append(Segment(start=u.start, end=u.end, text=u.transcript, n_words=1))
    return out


# --- driver -------------------------------------------------------------------

FINDERS = {
    DynamicType.PAUSE_HANDLING: find_pause_handling,
    DynamicType.VERBAL_BACKCHANNELING: find_verbal_backchanneling,
    DynamicType.VERBAL_INTERRUPTION: find_verbal_interruption,
    DynamicType.TURN_TAKING: find_turn_taking,
    DynamicType.LAUGHTER: find_laughter,
}


def find_all(vad_a, utts_a, vad_b, utts_b, dynamics: set[DynamicType] | None = None,
             laughs_a: list[Segment] | None = None, laughs_b: list[Segment] | None = None) -> list[Candidate]:
    """Run the requested finders with both role assignments.

    ``user_role`` on each Candidate says which input file is the user ('a' =
    the first file passed here). Laughter segments are per file and only used
    when that file plays the user.
    """
    wanted = dynamics or set(FINDERS)
    out: list[Candidate] = []
    for role, (va, ua, vb, ub, laughs) in {
        "a": (vad_a, utts_a, vad_b, utts_b, laughs_a),
        "b": (vad_b, utts_b, vad_a, utts_a, laughs_b),
    }.items():
        for dyn in wanted:
            fn = FINDERS[dyn]
            cands = fn(va, ua, vb, ub, laughs_a=laughs) if dyn is DynamicType.LAUGHTER else fn(va, ua, vb, ub)
            for c in cands:
                c.user_role = role
                out.append(c)
    return sorted(out, key=lambda c: (c.user_role, c.ds_raw))
