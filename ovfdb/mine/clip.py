"""Clip boundaries, ``agent_speaks_first`` and deterministic clip ids (plans/WS2-mining.md).

Pure functions: a ``Candidate`` + both speakers' turns + the media duration
in, a ``ClipBounds`` out. Trimming itself is ``ovfdb.data.seamless.to_sample``.

User / partner assignment per dynamic
-------------------------------------
``Candidate.user_role`` already names the user file; this module never swaps
roles. For the record, with A = user and B = partner (= the human-GT agent):

* Pause Handling (P): A pauses mid-turn; B (agent) must stay silent.
* Verbal Backchanneling (G): A speaks; B (agent) emits the backchannel.
* Verbal Interruption (G): B (agent) is talking and **A interrupts** — the agent
  is the one being interrupted, so it must already be speaking at the cue:
  ``agent_speaks_first=True`` always.
* Turn-taking (G): B spoke, A took the floor and now offers it back; B (agent)
  must start within the handoff window. The agent spoke earlier in the clip,
  so ``agent_speaks_first`` is True only if B is audible at clip start.
* Laughter (P/G): A laughs; B (agent) continues warmly (P) / laughs back (G).

Boundaries
----------
start = beginning of the turn 1–3 turns before the window (prefer 2); end =
end of the next turn after the window or window end + 8 s, whichever comes
first; total capped at 60 s (shrinking the lead-in first, then the tail);
>= 1 s margin from the media ends. ``agent_speaks_first`` = B is speaking at
clip start, or the dynamic requires the agent to speak before the user's
cue (Verbal Interruption, NV Backchanneling-P, Adaptor Handling, NV
Interruption).
"""

from __future__ import annotations

from dataclasses import dataclass

from ovfdb.mine.dialogue import Candidate, Turn
from ovfdb.schema import Bucket, DynamicType, Segment

MAX_CLIP_S = 60.0
TAIL_S = 8.0
EDGE_MARGIN_S = 1.0
MIN_LEAD_S = 3.0          # never start closer than this to the window
MIN_TAIL_S = 1.5          # always keep some follow-up after the window
PREFERRED_LEAD_TURNS = (2, 3, 1)
MIN_PREFERRED_LEAD_S = 12.0  # take a 3rd floor turn when two give less context than this
MAX_LEAD_S = 40.0         # a "lead-in" longer than this falls back to fewer turns

#: Dynamics where the agent must be mid-turn when the user's cue arrives.
AGENT_FIRST_DYNAMICS: set[tuple[DynamicType, Bucket]] = {
    (DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION),
    (DynamicType.NONVERBAL_BACKCHANNELING, Bucket.PERCEPTION),
    (DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION),
    (DynamicType.NONVERBAL_INTERRUPTION, Bucket.PERCEPTION),
}


@dataclass
class ClipBounds:
    t0: float
    t1: float
    ds: float
    de: float
    agent_speaks_first: bool
    lead_turns: int

    @property
    def dur(self) -> float:
        return self.t1 - self.t0


def floor_turns(turns: list[Turn], max_interjection: float = 1.0) -> list[Turn]:
    """Coalesce VAD-level turns into conversational floor turns (pure).

    Consecutive turns of the same speaker merge; turns of the other speaker
    shorter than ``max_interjection`` (backchannels, "huh?") do not break a
    floor turn. These are the "turns" the 1-3 lead-in / 1 follow-up rule
    counts, so a clip spans real exchanges (paper median 46 s) rather than
    0.6 s-merged VAD bursts.
    """
    out: list[Turn] = []
    for t in sorted(turns, key=lambda t: (t.start, t.end)):
        if out and out[-1].speaker == t.speaker:
            cur = out[-1]
            out[-1] = Turn(cur.speaker, cur.start, max(cur.end, t.end), cur.segs + t.segs)
        else:
            out.append(t)
    # second pass: drop interjections sandwiched between two turns of the other speaker and re-merge
    merged: list[Turn] = []
    i = 0
    while i < len(out):
        t = out[i]
        if (0 < i < len(out) - 1 and t.dur < max_interjection and out[i - 1].speaker == out[i + 1].speaker != t.speaker
                and merged and merged[-1].speaker == out[i - 1].speaker):
            nxt = out[i + 1]
            cur = merged[-1]
            merged[-1] = Turn(cur.speaker, cur.start, max(cur.end, nxt.end), cur.segs + nxt.segs)
            i += 2
            continue
        if merged and merged[-1].speaker == t.speaker:
            cur = merged[-1]
            merged[-1] = Turn(cur.speaker, cur.start, max(cur.end, t.end), cur.segs + t.segs)
        else:
            merged.append(t)
        i += 1
    return merged


def _turn_window(turns: list[Turn], ds: float, de: float) -> tuple[list[Turn], Turn | None]:
    ft = floor_turns(turns)
    before = sorted((t for t in ft if t.start < ds), key=lambda t: t.start)
    after = sorted((t for t in ft if t.start >= de), key=lambda t: t.start)
    return before, (after[0] if after else None)


def clip_bounds(cand: Candidate, all_turns: list[Turn], media_dur: float, partner_vad: list[Segment] | None = None,
                max_clip: float = MAX_CLIP_S) -> ClipBounds:
    """Choose [t0, t1] around ``cand``'s window.

    ``all_turns`` are both speakers' turns in the candidate's frame
    (``speaker == 'a'`` is the user); ``partner_vad`` is B's VAD, used for
    ``agent_speaks_first``.
    """
    ds, de = cand.ds_raw, cand.de_raw
    before, nxt = _turn_window(all_turns, ds, de)

    # --- end
    t1 = de + TAIL_S
    if nxt is not None:
        t1 = min(t1, nxt.end)
    t1 = max(t1, de + MIN_TAIL_S)
    t1 = min(t1, media_dur - EDGE_MARGIN_S)

    # --- start: prefer the 2nd turn before the window; take the 3rd when two turns
    # give less than MIN_PREFERRED_LEAD_S of context; fall back to the 1st
    t0, lead = None, 0
    fitting = []
    for k in PREFERRED_LEAD_TURNS:
        if len(before) >= k:
            cand_t0 = before[-k].start
            if ds - cand_t0 <= MAX_LEAD_S and t1 - cand_t0 <= max_clip:
                fitting.append((k, cand_t0))
    for k, cand_t0 in fitting:
        if k in (2, 3) and ds - cand_t0 >= MIN_PREFERRED_LEAD_S:
            t0, lead = cand_t0, k
            break
    if t0 is None and fitting:
        lead, t0 = max(fitting, key=lambda kt: ds - kt[1])   # longest context among 1-3 turns
    if t0 is None:
        # fall back to the closest preceding turn start that fits, else a fixed lead-in
        fits = [t.start for t in before if t1 - t.start <= max_clip and ds - t.start >= MIN_LEAD_S]
        t0, lead = (max(fits), 1) if fits else (ds - min(15.0, max_clip - (t1 - ds)), 0)
    t0 = min(t0, ds - MIN_LEAD_S)
    t0 = max(t0, EDGE_MARGIN_S)

    # --- cap: shrink lead-in, then tail
    if t1 - t0 > max_clip:
        t0 = max(t0, t1 - max_clip)
        if ds - t0 < MIN_LEAD_S:
            t0 = ds - MIN_LEAD_S
            t1 = min(t1, t0 + max_clip)
    t0, t1 = round(t0, 3), round(t1, 3)

    b_vad = partner_vad if partner_vad is not None else [s for t in all_turns if t.speaker == "b" for s in t.segs]
    agent_first = (cand.dynamic_type, cand.bucket) in AGENT_FIRST_DYNAMICS or any(
        s.start <= t0 + 0.25 and s.end > t0 for s in b_vad)
    return ClipBounds(t0=t0, t1=t1, ds=ds, de=de, agent_speaks_first=bool(agent_first), lead_turns=lead)


def window_key(user_id: str, b: ClipBounds) -> tuple[str, float, float]:
    """Clips with the same user file and [t0, t1] share one clip id (a clip can
    appear in both buckets, like NVIDIA's shared ``sample_id``)."""
    return (user_id, round(b.t0, 2), round(b.t1, 2))


def assign_clip_indices(keys: list[tuple[str, float, float]],
                        existing: dict[tuple[str, float, float], int] | None = None) -> dict[tuple[str, float, float], int]:
    """Deterministic clip index per user file: existing windows keep their index,
    new windows get the next free indices in (t0, t1) order."""
    out = dict(existing or {})
    next_idx: dict[str, int] = {}
    for (uid, _, _), idx in out.items():
        next_idx[uid] = max(next_idx.get(uid, 0), idx + 1)
    for key in sorted(set(keys), key=lambda k: (k[0], k[1], k[2])):
        if key in out:
            continue
        uid = key[0]
        out[key] = next_idx.get(uid, 0)
        next_idx[uid] = out[key] + 1
    return out


def clip_id_for(user_id: str, index: int) -> str:
    return f"{user_id}_c{index:02d}"
