"""Cue-signalling metrics (WS10, `plans/WS10-cue-judge.md` §3): pure functions over probability tracks + segments.

A cue judge (phase 1/2 of WS10) emits three 10 Hz probability tracks for one participant — here the agent —
from that participant's own face (and optionally audio):

    p_eager      P(turn ends within 400 ms | still speaking)        yield cue
    p_end        P(turn has ended | silence so far τ)               hold cue (its complement)
    p_start(h)   P(own onset within h | listening), h ∈ {0.4, 1} s  start cue / floor bid

This module does not know where the tracks come from. It (1) mines the events the metrics are scored on from
the agent's and the user's speech segments with the WS9 outcome rules (A = agent, B = user), (2) turns tracks
and events into the numbers of §3 — yield-cue AUC and horizon, start-cue AUC and bid lead, hold-cue false-alarm
rate, visual gain — and (3) fits the human-reference thresholds and clip-level bootstrap CIs. Controls
(shuffled video, frozen video, time shifts) are built by the caller by handing in a different track; nothing
here is specific to a modality.

Conventions: times in seconds from clip start; a track value for time ``t`` is the frame ``floor(t * fps)``;
NaN frames are dropped from every statistic. Everything is numpy-only so it can be tested on synthetic tracks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from ovfdb.schema import Segment
from ovfdb.score.timing import is_backchannel

# --- WS9 outcome rules, applied with A = agent, B = user -------------------------------------------------------

MIN_GAP_S = 0.2          #: agent regions closer than this are one utterance
FLOOR_S = 1.0            #: the agent must have held the floor this long before an offset is a turn end
MAX_RESPONSE_S = 3.0     #: complete: the user's real onset follows the agent's offset within this
MIN_YIELD_S = 1.0        #: ... and the agent stays silent this long after the user's onset
MAX_PAUSE_S = 5.0        #: incomplete: the agent resumes within this, before any real user onset
LISTEN_S = 1.0           #: an agent onset counts when the agent has been silent (no real speech) this long
START_LEAD_S = 0.3       #: start-cue AUC(0.4) is scored this far before the onset
START_LEAD_1S = 0.5      #: start-cue AUC(1) is scored this far before the onset
YIELD_LEAD_S = 0.3       #: yield-cue AUC is scored this far before the offset
MIDTURN_AHEAD_S = 1.0    #: a mid-turn negative has at least this much agent speech ahead
LISTEN_NEG_MARGIN_S = 2.0  #: listening negatives have ≥ h + margin to the agent's next own onset
BACKCHANNEL_EXCLUDE_S = 0.5  #: listening negatives keep clear of the agent's own backchannels by this


def merge_segments(segs: Sequence[Segment], gap: float = MIN_GAP_S) -> list[Segment]:
    """Join segments of one party whose gap is < ``gap`` (word counts and text concatenate)."""
    out: list[Segment] = []
    for s in sorted(segs, key=lambda s: s.start):
        if out and s.start - out[-1].end < gap:
            p = out[-1]
            out[-1] = Segment(p.start, max(p.end, s.end), (p.text + " " + s.text).strip(), p.n_words + s.n_words)
        else:
            out.append(Segment(s.start, s.end, s.text, s.n_words))
    return out


@dataclass
class CueEvents:
    """Scoring events for one clip (times in s). ``midturn`` and ``listening`` are the matched negatives."""

    completes: list[float] = field(default_factory=list)                 # agent offsets the user takes up
    incompletes: list[tuple[float, float]] = field(default_factory=list)  # (offset, resume) agent pauses
    onsets: list[float] = field(default_factory=list)                    # agent real onsets after listening
    midturn: list[float] = field(default_factory=list)                   # frames with ≥ 1 s agent speech ahead
    listening: list[float] = field(default_factory=list)                 # listening frames far from any onset

    def counts(self) -> dict[str, int]:
        return {k: len(getattr(self, k)) for k in ("completes", "incompletes", "onsets", "midturn", "listening")}


def mine_events(agent: Sequence[Segment], user: Sequence[Segment], clip_end: float, *, h: float = 1.0,
                fps: int = 10, seed: int = 0) -> CueEvents:
    """WS9 outcome rules on the agent's offsets and onsets, plus 1:1 matched negatives.

    complete:   agent utterance ≥ FLOOR_S ends at t; the user's first real (non-backchannel) onset after t is
                within MAX_RESPONSE_S and the agent does not speak again for MIN_YIELD_S after that onset.
    incomplete: agent utterance ≥ FLOOR_S ends at t; the agent resumes within MAX_PAUSE_S before any real
                user onset.  Anything else (long silence, clip end, overlap) is not an event.
    onset:      a real agent utterance starts at t and the agent's previous real speech ended ≥ LISTEN_S before.
    midturn:    one random frame per complete inside agent speech with ≥ MIDTURN_AHEAD_S of speech left.
    listening:  one random frame per onset where the agent is not speaking, ≥ LISTEN_S since its last real
                speech, ≥ h + LISTEN_NEG_MARGIN_S to its next own onset, and ≥ BACKCHANNEL_EXCLUDE_S from any
                of its own backchannels (§7: exclusion variant).
    """
    rng = np.random.default_rng(seed)
    a = merge_segments(agent)
    u = merge_segments(user)
    a_real = [s for s in a if not is_backchannel(s)]
    a_bc = [s for s in a if is_backchannel(s)]
    u_real_on = np.array(sorted(s.start for s in u if not is_backchannel(s)))
    a_starts = np.array([s.start for s in a])
    ev = CueEvents()
    for s in a:
        if s.dur < FLOOR_S or is_backchannel(s):
            continue
        t = s.end
        nxt_a = a_starts[a_starts > t + 1e-9]
        a_resume = float(nxt_a[0]) if len(nxt_a) else np.inf
        nxt_u = u_real_on[u_real_on > t - 1e-9]
        u_on = float(nxt_u[0]) if len(nxt_u) else np.inf
        if u_on - t <= MAX_RESPONSE_S and u_on < a_resume and a_resume - u_on >= MIN_YIELD_S:
            ev.completes.append(t)
        elif a_resume - t <= MAX_PAUSE_S and a_resume < u_on and a_resume <= clip_end:
            ev.incompletes.append((t, a_resume))
    prev_real_end = -np.inf
    for s in a:
        if not is_backchannel(s):
            if s.start - prev_real_end >= LISTEN_S:
                ev.onsets.append(s.start)
            prev_real_end = max(prev_real_end, s.end)
    # negatives on the frame grid
    n = int(np.floor(clip_end * fps))
    t = np.arange(n) / fps
    speaking = np.zeros(n, bool)
    ahead = np.zeros(n)
    for s in a:
        k0, k1 = int(np.floor(s.start * fps)), int(np.ceil(s.end * fps))
        speaking[max(k0, 0): min(k1, n)] = True
        ahead[max(k0, 0): min(k1, n)] = s.end - t[max(k0, 0): min(k1, n)]
    mid = np.flatnonzero(speaking & (ahead >= MIDTURN_AHEAD_S))
    if len(mid) and ev.completes:
        ev.midturn = sorted(float(t[i]) for i in rng.choice(mid, size=len(ev.completes), replace=len(mid) < len(ev.completes)))
    real_ends = np.array(sorted(s.end for s in a_real))
    real_starts = np.array(sorted(s.start for s in a_real))
    j = np.searchsorted(real_ends, t, side="right") - 1
    since_real = np.where(j >= 0, t - real_ends[np.clip(j, 0, None)], np.inf)
    k = np.searchsorted(real_starts, t, side="left")
    to_next = np.where(k < len(real_starts), real_starts[np.clip(k, None, max(len(real_starts) - 1, 0))] - t, np.inf)
    near_bc = np.zeros(n, bool)
    for s in a_bc:
        k0, k1 = int(np.floor((s.start - BACKCHANNEL_EXCLUDE_S) * fps)), int(np.ceil((s.end + BACKCHANNEL_EXCLUDE_S) * fps))
        near_bc[max(k0, 0): min(k1, n)] = True
    lis = np.flatnonzero(~speaking & (since_real >= LISTEN_S) & (to_next >= h + LISTEN_NEG_MARGIN_S) & ~near_bc)
    if len(lis) and ev.onsets:
        ev.listening = sorted(float(t[i]) for i in rng.choice(lis, size=len(ev.onsets), replace=len(lis) < len(ev.onsets)))
    return ev


# --- track access -------------------------------------------------------------------------------------------------

def frame_of(t: float | np.ndarray, fps: int) -> np.ndarray:
    return np.floor(np.asarray(t, dtype=float) * fps + 1e-9).astype(int)


def value_at(track: np.ndarray, times: Sequence[float], fps: int, lead: float = 0.0) -> np.ndarray:
    """Track values ``lead`` seconds before each time; NaN outside the track."""
    track = np.asarray(track, dtype=float)
    out = np.full(len(times), np.nan)
    if len(times) == 0 or len(track) == 0:
        return out
    k = frame_of(np.asarray(times) - lead, fps)
    ok = (k >= 0) & (k < len(track))
    out[ok] = track[k[ok]]
    return out


# --- statistics ----------------------------------------------------------------------------------------------------

def auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Mann–Whitney AUC with ties at 0.5; NaNs dropped; NaN when a class is empty."""
    p = np.asarray(pos, float); q = np.asarray(neg, float)
    p, q = p[np.isfinite(p)], q[np.isfinite(q)]
    if len(p) == 0 or len(q) == 0:
        return float("nan")
    allv = np.concatenate([p, q])
    order = np.argsort(allv, kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):                                   # average ranks over ties
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[:len(p)].sum() - len(p) * (len(p) + 1) / 2) / (len(p) * len(q)))


def cue_auc(track: np.ndarray, fps: int, positives: Sequence[float], negatives: Sequence[float], lead: float) -> float:
    """AUC of the track ``lead`` s before each positive event vs at each negative frame (metrics 1 and 3)."""
    return auc(value_at(track, positives, fps, lead), value_at(track, negatives, fps))


@dataclass
class Horizon:
    """Per-event lead (s) of the signal: how long before the event the track stayed ≥ θ; 0 when missed."""

    horizons_s: np.ndarray
    detected: np.ndarray

    @property
    def detection_rate(self) -> float:
        return float(self.detected.mean()) if len(self.detected) else float("nan")

    @property
    def median_ms(self) -> float:
        return float(np.median(self.horizons_s) * 1000) if len(self.horizons_s) else float("nan")

    @property
    def median_detected_ms(self) -> float:
        d = self.horizons_s[self.detected]
        return float(np.median(d) * 1000) if len(d) else float("nan")


def horizon(track: np.ndarray, fps: int, events: Sequence[float], theta: float, max_s: float = 10.0) -> Horizon:
    """Metric 2 (yield horizon) and the bid lead of metric 3: how long before each event the track has stayed
    ≥ ``theta`` up to the event's frame (a track above θ from ``t − 0.3`` on gives 0.3 s). Missed (below θ at the
    event) = 0; detected only at the event frame = 0 too, but ``detected`` tells the two apart."""
    track = np.asarray(track, float)
    hs = np.zeros(len(events)); det = np.zeros(len(events), bool)
    kmax = round(max_s * fps)
    for i, t in enumerate(events):
        k0 = int(frame_of(t, fps))
        if k0 < 0 or k0 >= len(track) or not (track[k0] >= theta):
            continue
        k = k0
        while k - 1 >= 0 and k0 - (k - 1) <= kmax and track[k - 1] >= theta:
            k -= 1
        det[i] = True
        hs[i] = (k0 - k) / fps
    return Horizon(hs, det)


def threshold_at_far(neg_scores: Sequence[float], far: float = 0.10) -> float:
    """θ such that a share ``far`` of the negatives (human reference) exceeds it: the 1 − far quantile."""
    q = np.asarray(neg_scores, float); q = q[np.isfinite(q)]
    return float(np.quantile(q, 1 - far)) if len(q) else float("nan")


def hold_far(p_end: np.ndarray, fps: int, incompletes: Sequence[tuple[float, float]],
             theta: float | Callable[[float], float]) -> float:
    """Metric 4: share of incomplete pauses on which p_end(τ) reaches θ(τ) at some silence length τ before the
    agent resumes. ``theta`` is a number or a function of τ (s)."""
    p = np.asarray(p_end, float)
    th = theta if callable(theta) else (lambda _tau: float(theta))
    if not incompletes:
        return float("nan")
    hits = 0
    for off, res in incompletes:
        k0, k1 = int(frame_of(off, fps)), int(frame_of(res, fps))
        ks = np.arange(max(k0, 0), min(k1, len(p)))
        if len(ks) and any(p[k] >= th((k - k0) / fps) for k in ks if np.isfinite(p[k])):
            hits += 1
    return hits / len(incompletes)


def visual_gain(av: dict[str, float], a: dict[str, float]) -> dict[str, float]:
    """Metric 5: AV minus A for every metric both dicts share."""
    return {k: float(av[k] - a[k]) for k in av if k in a and np.isfinite(av[k]) and np.isfinite(a[k])}


def clip_bootstrap(stat: Callable[[list], float], clips: list, n_boot: int = 500, seed: int = 0,
                   ci: float = 0.95) -> tuple[float, float, float]:
    """(point, lo, hi): ``stat`` on all clips, and its percentile CI when clips are resampled with replacement
    (the clip is the unit of resampling, §3)."""
    point = float(stat(clips))
    if len(clips) < 2:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    vals = np.array([stat([clips[i] for i in rng.integers(len(clips), size=len(clips))]) for _ in range(n_boot)], float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return point, float("nan"), float("nan")
    a = (1 - ci) / 2
    return point, float(np.quantile(vals, a)), float(np.quantile(vals, 1 - a))


def pooled_auc(clips: list[tuple[np.ndarray, np.ndarray]]) -> float:
    """AUC over the pooled (positive scores, negative scores) of a list of clips; the statistic for clip_bootstrap."""
    return auc(np.concatenate([c[0] for c in clips]) if clips else [], np.concatenate([c[1] for c in clips]) if clips else [])


def shuffle_pairs(n: int, seed: int = 0) -> np.ndarray:
    """A derangement of range(n) (no clip keeps its own index) for the shuffled-video control; n ≥ 2."""
    rng = np.random.default_rng(seed)
    perm = np.arange(n)
    if n < 2:
        return perm
    while True:
        rng.shuffle(perm)
        if (perm != np.arange(n)).all():
            return perm


# --- per-clip summary ------------------------------------------------------------------------------------------------

@dataclass
class Thresholds:
    """Human-fitted thresholds (metrics 2, 3, 4)."""

    eager: float                                      # θ_eager, 10 % of mid-turn negatives above
    bid: float                                        # θ_bid on p_start(1), 10 % false bids
    end: float | Callable[[float], float]             # θ(τ) for p_end


def clip_scores(tracks: dict[str, np.ndarray], fps: int, ev: CueEvents) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """(positive, negative) score arrays per metric for one clip, the input of pooled_auc / clip_bootstrap.
    ``tracks`` keys: ``p_eager``, ``p_start_0.4``, ``p_start_1`` (any may be missing)."""
    out = {}
    if "p_eager" in tracks:
        out["yield_auc"] = (value_at(tracks["p_eager"], ev.completes, fps, YIELD_LEAD_S), value_at(tracks["p_eager"], ev.midturn, fps))
    if "p_start_0.4" in tracks:
        out["start_auc_0.4"] = (value_at(tracks["p_start_0.4"], ev.onsets, fps, START_LEAD_S), value_at(tracks["p_start_0.4"], ev.listening, fps))
    if "p_start_1" in tracks:
        out["start_auc_1"] = (value_at(tracks["p_start_1"], ev.onsets, fps, START_LEAD_1S), value_at(tracks["p_start_1"], ev.listening, fps))
    return out


def summarise(tracks: dict[str, np.ndarray], fps: int, ev: CueEvents, th: Thresholds | None = None) -> dict:
    """Metrics 1–4 for one clip (no CIs; aggregate across clips with clip_bootstrap on clip_scores)."""
    out: dict = {"n": ev.counts()}
    for k, (p, q) in clip_scores(tracks, fps, ev).items():
        out[k] = auc(p, q)
    if th is not None:
        if "p_eager" in tracks:
            hz = horizon(tracks["p_eager"], fps, ev.completes, th.eager)
            out.update(yield_detection=hz.detection_rate, yield_horizon_ms=hz.median_ms, yield_horizon_detected_ms=hz.median_detected_ms)
        if "p_start_1" in tracks:
            hz = horizon(tracks["p_start_1"], fps, ev.onsets, th.bid)
            out.update(bid_detection=hz.detection_rate, bid_lead_ms=hz.median_ms, bid_lead_detected_ms=hz.median_detected_ms)
        if "p_end" in tracks:
            out["hold_far"] = hold_far(tracks["p_end"], fps, ev.incompletes, th.end)
    return out
