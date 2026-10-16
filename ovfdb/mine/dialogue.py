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

def find_pause_handling(vad_a, utts_a, vad_b, utts_b, min_gap=1.0, max_gap=4.0, min_turn=1.0) -> list[Candidate]:
    """Pause Handling (P): inside A's turn a silence of 1.0–4.0 s, A resumes, B
    silent throughout and for 1 s after A resumes. Window = the silence.

    Because turns are cut at 0.6 s of silence, "a pause inside A's turn" is
    read as two consecutive A turns (each >= ``min_turn`` s) with no B turn
    between them; B must have no VAD at all in [pause start, resume + 1 s].
    """
    ta = speaker_turns(vad_a, utts_b, "a")
    out = []
    for prev, nxt in itertools.pairwise(ta):
        gap = nxt.start - prev.end
        if not (min_gap <= gap <= max_gap):
            continue
        if prev.dur < min_turn or nxt.dur < min_turn:
            continue
        if _speaking(vad_b, prev.end - 0.5, nxt.start + 1.0):
            continue
        before = _text_in(utts_a, prev.start, prev.end)
        out.append(Candidate(
            DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION, "a", prev.end, nxt.start,
            {"rule": "pause_handling", "gap_s": round(gap, 2), "turn_before_s": round(prev.dur, 2),
             "turn_after_s": round(nxt.dur, 2), "text_before": before[-160:],
             "text_after": _text_in(utts_a, nxt.start, nxt.end)[:120],
             "score": round(min(gap, 2.5) + min(prev.dur, 10) / 10, 3)},
        ))
    return out


def find_verbal_backchanneling(vad_a, utts_a, vad_b, utts_b, pad=0.3, min_before=1.0, min_after=1.0) -> list[Candidate]:
    """Verbal Backchanneling (G): B emits a backchannel fully inside A's turn and
    A keeps talking. Window = B's backchannel ± 0.3 s.

    Seamless ASR rarely transcribes "mhm"/"uh-huh", so a backchannel is a B
    VAD region < 1 s with at most one transcript word inside it (the
    transcript text, if any, is kept as evidence). The VLM confirms it is a
    verbal acknowledgement rather than a cough or laugh.
    """
    ta = speaker_turns(vad_a, utts_b, "a")
    out = []
    for run in merge_regions(vad_b):
        r0, r1 = run[0].start, run[-1].end
        if r1 - r0 >= BACKCHANNEL_MAX_DUR or _words_in(utts_b, r0, r1) >= BACKCHANNEL_MAX_WORDS:
            continue
        host = next((t for t in ta if t.start + min_before <= r0 and r1 + min_after <= t.end), None)
        if host is None:
            continue
        # A must actually be talking around the backchannel (not in a within-turn pause)
        if _speech_in(vad_a, r0 - 1.0, r1 + 1.0) < 0.8:
            continue
        out.append(Candidate(
            DynamicType.VERBAL_BACKCHANNELING, Bucket.GENERATION, "a", r0 - pad, r1 + pad,
            {"rule": "verbal_backchanneling", "backchannel_s": round(r1 - r0, 2),
             "backchannel_text": _text_in(utts_b, r0, r1), "host_turn": [round(host.start, 2), round(host.end, 2)],
             "score": round(1.0 + min(host.dur, 20) / 20, 3)},
        ))
    return out


def find_verbal_interruption(vad_a, utts_a, vad_b, utts_b, max_stop=1.5, min_hold=2.0, min_b_before=1.0,
                             yield_silence=2.0) -> list[Candidate]:
    """Verbal Interruption (G): A starts a non-backchannel utterance while B is
    speaking; B stops within 1.5 s; A holds the floor >= 2 s. Window = A's
    onset -> B's offset. The user is A (the interrupter); the agent is B (the
    one being interrupted) so ``agent_speaks_first`` is True downstream.

    Extra guards: B must have been speaking for >= 1 s before A's onset (so
    this is not B's backchannel), B must still produce transcript words after
    A's onset (mid-sentence rather than a completed turn, which the VLM
    otherwise rejects as a plain turn-take), and B must not start another
    non-backchannel utterance within ``yield_silence`` s of stopping.
    """
    b_runs = merge_regions(vad_b)
    out = []
    for u in utts_a:
        if is_backchannel(u) or n_words(u) < 2:
            continue
        run = next((r for r in b_runs if r[0].start < u.start < r[-1].end), None)
        if run is None:
            continue
        b_on, b_off = run[0].start, run[-1].end
        if u.start - b_on < min_b_before:
            continue
        stop = b_off - u.start
        if not (0.0 < stop <= max_stop):
            continue
        # B must still be articulating words after A's onset (mid-sentence, not a finished turn)
        if not any(w.start > u.start + 0.1 and w.start < b_off for v in utts_b for w in v.words):
            continue
        # A holds: A's VAD run containing the onset lasts >= min_hold past it
        a_run = next((r for r in merge_regions(vad_a) if r[0].start <= u.start + 0.2 and r[-1].end > u.start), None)
        hold = (a_run[-1].end - u.start) if a_run else (u.end - u.start)
        if hold < min_hold:
            continue
        if any(not is_backchannel(v) and b_off < v.start < b_off + yield_silence for v in utts_b):
            continue
        out.append(Candidate(
            DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION, "a", u.start, b_off,
            {"rule": "verbal_interruption", "b_stop_s": round(stop, 2), "a_hold_s": round(hold, 2),
             "b_speaking_before_s": round(u.start - b_on, 2), "a_text": u.transcript[:120],
             "b_text": _text_in(utts_b, b_on, b_off)[-160:],
             "score": round(min(hold, 6) / 6 + min(u.start - b_on, 5) / 5, 3)},
        ))
    return out


def find_turn_taking(vad_a, utts_a, vad_b, utts_b, min_gap=0.2, max_gap=1.5, min_a_turn=1.5, min_b_reply=1.0) -> list[Candidate]:
    """Turn-taking (G): B's turn ends, gap 0.2–1.5 s, A's turn starts (no
    overlap); then A ends and B replies after a 0.2–1.5 s gap, no overlap.
    Window = A's turn end -> B's reply onset (the scored A->B handoff).

    A's turn must be a real contribution (>= 1.5 s, >= 2 words) and B's reply
    a non-backchannel of >= 1 s. ``ends_with_question`` is recorded as evidence
    for ranking (explicit floor offers verify best).
    """
    all_turns = turns(vad_a, utts_a, vad_b, utts_b)
    out = []
    for i in range(1, len(all_turns) - 1):
        b1, a, b2 = all_turns[i - 1], all_turns[i], all_turns[i + 1]
        if (b1.speaker, a.speaker, b2.speaker) != ("b", "a", "b"):
            continue
        g1, g2 = a.start - b1.end, b2.start - a.end
        if not (min_gap <= g1 <= max_gap and min_gap <= g2 <= max_gap):
            continue
        if a.dur < min_a_turn or _words_in(utts_a, a.start, a.end) < 2:
            continue
        if b2.dur < min_b_reply or _words_in(utts_b, b2.start, b2.end) < 2:
            continue
        a_text = _text_in(utts_a, a.start, a.end)
        out.append(Candidate(
            DynamicType.TURN_TAKING, Bucket.GENERATION, "a", a.end, b2.start,
            {"rule": "turn_taking", "gap_before_s": round(g1, 2), "handoff_gap_s": round(g2, 2),
             "a_turn_s": round(a.dur, 2), "b_reply_s": round(b2.dur, 2),
             "ends_with_question": a_text.rstrip().endswith("?"), "a_text": a_text[-160:],
             "b_text": _text_in(utts_b, b2.start, b2.end)[:120],
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
      speaking) and B reacts — B has a VAD onset within 2 s after the laugh.
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
        b_reacts = any(lg.start <= s.start <= lg.end + react_window for s in vad_b)
        if own_turn and b_reacts:
            out.append(Candidate(DynamicType.LAUGHTER, Bucket.GENERATION, "a", lg.start, lg.end,
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
