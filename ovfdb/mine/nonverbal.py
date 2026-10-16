"""Nonverbal candidate finders (plans/WS2-mining.md, day 2).

Six dynamics: Nonverbal Backchanneling (P, G), Face Emotion Display (P, G),
Emotion Matching (G), Gaze Avoidance with Pause (P), Adaptor Handling (P),
Nonverbal Interruption (P). No human labels: the VLM verification in
``verify.py`` is the annotator; this module only proposes windows.

Everything is expressed over one representation, a per-participant list of
timestamped ``Event`` s (nod, smile, gaze_away, self_touch, hand_raise, ...),
so three event sources share the same pure finders:

1. **Gemini event list** (``detect_events_gemini``): one gemini-2.5-flash call
   per interaction over a low-res side-by-side composite of the *whole*
   recording (A left, B right, 5 fps sampling), asking for every nod /
   head-shake / smile / frown / laugh / gaze-away / hand-raise / self-touch
   as ``MM:SS.s``. Cached in ``data/mining/nonverbal/<a>__<b>.json``.
2. **3P-V text annotations** (``events_from_annotations``): regex over the
   human third-party descriptions for self-directed gestures (Adaptor).
3. **Movement features** (``events_from_movement``): head-pitch oscillation
   (nods), emotion-valence z-spikes (expressions), gaze deviation from the
   speaker's own median (gaze-away), from the 30 Hz ``movement`` arrays that
   exist for ``has_imitator_movement=1`` files. The array functions are pure
   (numpy in, events out) and unit-tested on synthetic signals.

Role convention is the same as ``dialogue.py``: A = the participant who
becomes the user, B = the partner (= human-GT agent). ``find_all`` runs every
finder with both role assignments and tags ``user_role``.

Timing semantics per dynamic (paper App. C.2 / Table 2):

* NV Backchanneling P: A nods/smiles while B is mid-turn and B keeps talking
  (continue-speaking, agent speaks first). G: B nods/smiles while A speaks.
* Face Emotion Display P: A shows an expression; B replies (B speech onset
  within 3 s). G: B mirrors it (B facial event within 2.5 s).
* Emotion Matching G: B's same-sign expression follows A's within 2 s.
* Gaze Avoidance with Pause P: a Pause Handling pause during which A looks away.
* Adaptor Handling P: A self-touches while B is speaking (continue-speaking;
  preferred) or, lower-scored, while A speaks; B does not react.
* NV Interruption P: A raises a hand / shakes head / "stop" while B speaks
  and before any A speech; B stops and A takes the floor within 2.5 s.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ovfdb.data.seamless import Annotation
from ovfdb.mine.dialogue import Candidate, _speech_in, find_pause_handling, merge_regions
from ovfdb.schema import Bucket, DynamicType, Segment

log = logging.getLogger("ovfdb.mine")
CACHE_DIR = Path("data/mining/nonverbal")
GEMINI_FPS = 2.0
CHUNK_S = 40.0        # seconds of video per Gemini call
SBS_HEIGHT = 480
SBS_FPS = 10

#: Event kinds the Gemini pass may return, with their affect sign (+1 / -1 / 0).
KINDS: dict[str, int] = {
    "nod": 0, "head_shake": 0, "smile": 1, "laugh": 1, "frown": -1, "grimace": -1, "surprise": 0,
    "eyebrow_raise": 0, "gaze_away": 0, "hand_raise": 0, "stop_gesture": 0, "self_touch": 0, "point": 0,
    "concern": -1, "expression_pos": 1, "expression_neg": -1,
}
BACKCHANNEL_KINDS = {"nod", "smile", "eyebrow_raise"}
EXPRESSION_KINDS = {"smile", "laugh", "frown", "grimace", "surprise", "eyebrow_raise", "concern",
                    "expression_pos", "expression_neg"}
AFFECT_KINDS = {k for k, v in KINDS.items() if v != 0}
INTERRUPT_KINDS = {"hand_raise", "stop_gesture", "head_shake", "point"}
ADAPTOR_KINDS = {"self_touch"}
GAZE_KINDS = {"gaze_away"}

ADAPTOR_RE = re.compile(
    r"\b(rub|rubs|rubbing|scratch|scratches|scratching|touch|touches|touching|adjust|adjusts|adjusting|"
    r"fidget|fidgets|fidgeting|hair|face|glasses|neck|ear|nose|chin|forehead|yawn|yawns|cough|coughs)\b",
    re.IGNORECASE,
)
#: Notes / 3P-V lines that describe communicative or static hand use, not an adaptor
#: (the Gemini pass likes to label "hands clasped" and "gestures with his hand" as self_touch).
ADAPTOR_EXCLUDE_RE = re.compile(r"\b(gestur|wave|point|clap|clasp|cross|fold|rest|hold|behind|hip|pocket)", re.IGNORECASE)


@dataclass
class Event:
    kind: str
    start: float
    end: float
    note: str = ""
    source: str = "gemini"          # gemini | 3pv | movement
    score: float = 1.0
    extra: dict = field(default_factory=dict)

    @property
    def dur(self) -> float:
        return self.end - self.start

    @property
    def valence(self) -> int:
        return KINDS.get(self.kind, 0)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "start": round(self.start, 2), "end": round(self.end, 2), "note": self.note[:160],
                "source": self.source, **{k: v for k, v in self.extra.items() if k not in ("kind", "start", "end")}}


# --- pure helpers ---------------------------------------------------------------

def _frac_speaking(vad: list[Segment], t0: float, t1: float) -> float:
    return _speech_in(vad, t0, t1) / max(t1 - t0, 1e-6)


def _run_containing(vad: list[Segment], t: float) -> tuple[float, float] | None:
    """[start, end] of the 0.6 s-merged VAD run that covers time ``t``."""
    for run in merge_regions(vad):
        if run[0].start <= t <= run[-1].end:
            return run[0].start, run[-1].end
    return None


def _next_onset(vad: list[Segment], t: float, horizon: float) -> float | None:
    """Earliest VAD region start in [t, t + horizon]."""
    on = [s.start for s in vad if t <= s.start <= t + horizon]
    return min(on) if on else None


def merge_events(events: list[Event], gap: float = 0.3) -> list[Event]:
    """Merge same-kind events that overlap or are < ``gap`` apart (pure)."""
    out: list[Event] = []
    for e in sorted(events, key=lambda e: (e.kind, e.start)):
        if out and out[-1].kind == e.kind and e.start - out[-1].end < gap:
            p = out[-1]
            out[-1] = Event(p.kind, p.start, max(p.end, e.end), p.note or e.note, p.source, max(p.score, e.score), p.extra)
        else:
            out.append(Event(e.kind, e.start, e.end, e.note, e.source, e.score, dict(e.extra)))
    return sorted(out, key=lambda e: e.start)


# --- finders (A = user) ----------------------------------------------------------

def _ev_dict(e: Event, prefix: str = "event") -> dict:
    return {prefix: e.to_dict()}


def find_nv_backchanneling(ev_a, vad_a, ev_b, vad_b, before=1.0, after=1.5, min_frac=0.6, max_own_speech=1.0) -> list[Candidate]:
    """Nonverbal Backchanneling.

    P: A nods / smiles / raises eyebrows while B has been talking for >= 1 s
    and keeps talking >= 1.5 s after (speech fraction >= 0.6 in both
    stretches); A produces at most a backchannel's worth of speech (< 1 s)
    around the event. Window = the event.
    G: the mirror image — B nods/smiles while A is mid-turn; the agent's
    expected output is B's cue.
    """
    out = []
    for bucket, (ev_x, vad_x, vad_y) in ((Bucket.PERCEPTION, (ev_a, vad_a, vad_b)), (Bucket.GENERATION, (ev_b, vad_b, vad_a))):
        for e in ev_x:
            if e.kind not in BACKCHANNEL_KINDS:
                continue
            pre = _frac_speaking(vad_y, e.start - before, e.start)
            post = _frac_speaking(vad_y, e.end, e.end + after)
            if pre < min_frac or post < min_frac:
                continue
            own = _speech_in(vad_x, e.start - 0.3, e.end + 0.3)
            if own >= max_own_speech:
                continue
            rule = "nv_backchanneling_p" if bucket is Bucket.PERCEPTION else "nv_backchanneling_g"
            out.append(Candidate(DynamicType.NONVERBAL_BACKCHANNELING, bucket, "a", e.start, e.end,
                                 {"rule": rule, **_ev_dict(e), "other_speaking_before": round(pre, 2),
                                  "other_speaking_after": round(post, 2), "own_speech_s": round(own, 2),
                                  "score": round(e.score + pre + post - own, 3)}))
    return out


def find_face_emotion_display(ev_a, vad_a, ev_b, vad_b, reply_within=3.0, mirror_within=2.5, min_reply=1.0) -> list[Candidate]:
    """Face Emotion Display.

    P: A shows a facial expression and B replies — a B VAD run starts within
    ``reply_within`` s of the event (and lasts >= 1 s). Window = the expression.
    G: A shows an expression and B visibly reacts — a B facial event starts
    within ``mirror_within`` s of A's event start. Window = the expression.
    """
    out = []
    b_face = [e for e in ev_b if e.kind in EXPRESSION_KINDS or e.kind == "nod"]
    for e in ev_a:
        if e.kind not in EXPRESSION_KINDS:
            continue
        base = {**_ev_dict(e), "a_speaking_frac": round(_frac_speaking(vad_a, e.start, e.end), 2)}
        on = _next_onset(vad_b, e.start - 0.5, e.dur + 0.5 + reply_within)
        if on is not None:
            run = _run_containing(vad_b, on)
            if run and run[1] - on >= min_reply:
                out.append(Candidate(DynamicType.FACE_EMOTION_DISPLAY, Bucket.PERCEPTION, "a", e.start, e.end,
                                     {"rule": "face_emotion_display_p", **base, "b_reply_onset_s": round(on, 2),
                                      "b_reply_lag_s": round(on - e.start, 2),
                                      "score": round(e.score + (1.0 if e.valence != 0 else 0.3) + min(e.dur, 2) / 2, 3)}))
        mirror = next((m for m in b_face if e.start - 0.3 <= m.start <= e.start + mirror_within), None)
        if mirror is not None:
            out.append(Candidate(DynamicType.FACE_EMOTION_DISPLAY, Bucket.GENERATION, "a", e.start, e.end,
                                 {"rule": "face_emotion_display_g", **base, **_ev_dict(mirror, "partner_event"),
                                  "mirror_lag_s": round(mirror.start - e.start, 2),
                                  "score": round(e.score + (1.0 if e.valence != 0 else 0.3) + min(e.dur, 2) / 2
                                                 + (0.5 if mirror.kind in EXPRESSION_KINDS else 0.0), 3)}))
    return out


def find_emotion_matching(ev_a, vad_a, ev_b, vad_b, within=2.0) -> list[Candidate]:
    """Emotion Matching (G): A's affect-carrying expression (smile, laugh,
    frown, ...) is followed within ``within`` s by a B expression of the same
    sign. Window = A's event start -> B's event start + 0.5 s (so the judge
    sees the mirroring begin inside the window)."""
    out = []
    b_aff = [e for e in ev_b if e.valence != 0]
    for e in ev_a:
        if e.valence == 0:
            continue
        m = next((m for m in b_aff if m.valence == e.valence and e.start <= m.start <= e.start + within), None)
        if m is None:
            continue
        de = max(e.end, m.start + 0.5)
        out.append(Candidate(DynamicType.EMOTION_MATCHING, Bucket.GENERATION, "a", e.start, de,
                             {"rule": "emotion_matching", **_ev_dict(e), **_ev_dict(m, "partner_event"),
                              "valence": e.valence, "lag_s": round(m.start - e.start, 2),
                              "score": round(e.score + m.score + (within - (m.start - e.start)) / within, 3)}))
    return out


def find_gaze_avoidance(ev_a, vad_a, utts_a, vad_b, utts_b, slack=0.5) -> list[Candidate]:
    """Gaze Avoidance with Pause (P): a Pause Handling pause (``dialogue.find_pause_handling``)
    during which A also looks away (a gaze_away event overlapping the pause
    +- ``slack``). Window = the pause."""
    out = []
    gaze = [e for e in ev_a if e.kind in GAZE_KINDS]
    for p in find_pause_handling(vad_a, utts_a, vad_b, utts_b):
        hit = [g for g in gaze if g.start < p.de_raw + slack and g.end > p.ds_raw - slack]
        if not hit:
            continue
        g = max(hit, key=lambda g: min(g.end, p.de_raw) - max(g.start, p.ds_raw))
        overlap = max(0.0, min(g.end, p.de_raw) - max(g.start, p.ds_raw))
        ev = {k: v for k, v in p.evidence.items() if k != "rule"}
        out.append(Candidate(DynamicType.GAZE_AVOIDANCE_WITH_PAUSE, Bucket.PERCEPTION, "a", p.ds_raw, p.de_raw,
                             {"rule": "gaze_avoidance_with_pause", **ev, **_ev_dict(g),
                              "gaze_overlap_s": round(overlap, 2),
                              "score": round(p.evidence.get("score", 0.0) + g.score + overlap, 3)}))
    return out


def find_adaptor(ev_a, vad_a, ev_b, vad_b, lookback=3.0, min_partner=0.3, min_self=0.5) -> list[Candidate]:
    """Adaptor Handling (P): A makes a self-directed gesture (scratch, rub,
    hair, glasses, fidget). Preferred: B was speaking in the 3 s before
    (activity >= 30 %, the paper's continue-speaking precondition) and keeps
    the floor; fallback (lower score): A is speaking through the gesture.
    Window = the gesture."""
    out = []
    for e in ev_a:
        if e.kind not in ADAPTOR_KINDS:
            continue
        partner_pre = _frac_speaking(vad_b, e.start - lookback, e.start)
        partner_in = _frac_speaking(vad_b, e.start, e.end)
        self_in = _frac_speaking(vad_a, e.start, e.end)
        if partner_pre >= min_partner:
            mode, score = "partner_speaking", 1.0 + partner_pre + partner_in
        elif self_in >= min_self:
            mode, score = "user_speaking", self_in
        else:
            continue
        out.append(Candidate(DynamicType.ADAPTOR_HANDLING, Bucket.PERCEPTION, "a", e.start, e.end,
                             {"rule": "adaptor_handling", **_ev_dict(e), "mode": mode,
                              "partner_speaking_before": round(partner_pre, 2), "partner_speaking_in": round(partner_in, 2),
                              "user_speaking_in": round(self_in, 2), "score": round(e.score + score, 3)}))
    return out


def find_nv_interruption(ev_a, vad_a, ev_b, vad_b, min_b_before=1.0, max_a_before=0.2, within=2.5) -> list[Candidate]:
    """Nonverbal Interruption (P): A raises a hand / shakes head / signals
    stop while B has been talking >= 1 s, with no A speech in the second
    before the gesture; B's VAD run ends within ``within`` s of the gesture
    start and A starts speaking within ``within`` s. Window = gesture start ->
    B's offset (the yield the agent is scored on)."""
    out = []
    for e in ev_a:
        if e.kind not in INTERRUPT_KINDS:
            continue
        run = _run_containing(vad_b, e.start)
        if run is None or e.start - run[0] < min_b_before:
            continue
        if _speech_in(vad_a, e.start - 1.0, e.start) > max_a_before:
            continue
        b_off = run[1]
        if b_off - e.start > within:
            continue
        a_on = _next_onset(vad_a, e.start, within)
        if a_on is None:
            continue
        out.append(Candidate(DynamicType.NONVERBAL_INTERRUPTION, Bucket.PERCEPTION, "a", e.start, max(b_off, e.start + 0.5),
                             {"rule": "nonverbal_interruption", **_ev_dict(e), "b_stop_s": round(b_off - e.start, 2),
                              "a_onset_s": round(a_on - e.start, 2), "b_speaking_before_s": round(e.start - run[0], 2),
                              "score": round(e.score + (within - (b_off - e.start)) / within + min(e.start - run[0], 5) / 5, 3)}))
    return out


FINDERS = {
    DynamicType.NONVERBAL_BACKCHANNELING: find_nv_backchanneling,
    DynamicType.FACE_EMOTION_DISPLAY: find_face_emotion_display,
    DynamicType.EMOTION_MATCHING: find_emotion_matching,
    DynamicType.GAZE_AVOIDANCE_WITH_PAUSE: find_gaze_avoidance,
    DynamicType.ADAPTOR_HANDLING: find_adaptor,
    DynamicType.NONVERBAL_INTERRUPTION: find_nv_interruption,
}
DYNAMICS = tuple(FINDERS)


def find_all(ev_a: list[Event], vad_a, utts_a, ev_b: list[Event], vad_b, utts_b,
             dynamics: set[DynamicType] | None = None) -> list[Candidate]:
    """Run the requested nonverbal finders with both role assignments; tag ``user_role``."""
    wanted = set(dynamics) if dynamics is not None else set(FINDERS)
    out: list[Candidate] = []
    for role, (ea, va, ua, eb, vb, ub) in {"a": (ev_a, vad_a, utts_a, ev_b, vad_b, utts_b),
                                           "b": (ev_b, vad_b, utts_b, ev_a, vad_a, utts_a)}.items():
        for dyn in wanted:
            if dyn not in FINDERS:
                continue
            if dyn is DynamicType.GAZE_AVOIDANCE_WITH_PAUSE:
                cands = find_gaze_avoidance(ea, va, ua, vb, ub)
            else:
                cands = FINDERS[dyn](ea, va, eb, vb)
            for c in cands:
                c.user_role = role
                out.append(c)
    # NV Backchanneling G is "B's cue while A speaks": when found in the 'a' frame it is the
    # same clip as the P candidate in the 'b' frame; keep both, the pipeline dedupes by bucket.
    return sorted(out, key=lambda c: (c.user_role, c.ds_raw))


# --- source 2: 3P-V annotations ---------------------------------------------------

def events_from_annotations(anns: list[Annotation], max_len: float = 8.0) -> list[Event]:
    """Adaptor events from third-party text ("rubs their head with their right hand")."""
    out = []
    for a in anns:
        if not ADAPTOR_RE.search(a.annotation) or ADAPTOR_EXCLUDE_RE.search(a.annotation):
            continue
        end = min(a.end_ts, a.start_ts + max_len)
        if end <= a.start_ts:
            end = a.start_ts + 1.0
        out.append(Event("self_touch", float(a.start_ts), float(end), a.annotation, "3pv", 1.0))
    return out


# --- source 3: movement features (pure numpy) ---------------------------------------

def _bandpass(x: np.ndarray, hz: float, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, filtfilt

    b, a = butter(2, [lo / (hz / 2), hi / (hz / 2)], btype="band")
    return filtfilt(b, a, x) if len(x) > 3 * max(len(a), len(b)) else x - x.mean()


def _frames_to_events(mask: np.ndarray, hz: float, kind: str, min_dur: float, score: np.ndarray | None = None,
                      source: str = "movement") -> list[Event]:
    out = []
    i, n = 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if (j - i) / hz >= min_dur:
            sc = float(np.max(score[i:j])) if score is not None else 1.0
            out.append(Event(kind, i / hz, j / hz, "", source, round(sc, 3)))
        i = j
    return out


def nod_events(head: np.ndarray, hz: float = 30.0, dim: int = 2, band=(1.0, 4.0), win_s: float = 1.5,
               min_cycles: int = 2, z: float = 3.0, valid: np.ndarray | None = None) -> list[Event]:
    """Nods from head rotation: band-passed (1-4 Hz) pitch whose RMS over a
    1.5 s window exceeds median + ``z`` * MAD and that completes >= ``min_cycles``
    cycles (zero crossings) inside the window. ``head`` is (T, >=dim+1)."""
    x = np.asarray(head, dtype=float)
    x = x[:, dim] if x.ndim == 2 else x
    if len(x) < int(2 * win_s * hz):
        return []
    if valid is not None:
        x = np.where(np.asarray(valid).reshape(-1) > 0, x, np.nan)
        x = np.nan_to_num(x, nan=float(np.nanmedian(x)) if np.isfinite(np.nanmedian(x)) else 0.0)
    bp = _bandpass(x, hz, *band)
    w = max(3, int(win_s * hz))
    w_rms = max(3, int(0.4 * hz))            # short window so event edges stay within ~0.3 s
    rms = np.sqrt(np.convolve(bp ** 2, np.ones(w_rms) / w_rms, mode="same"))
    med = np.median(rms)
    mad = np.median(np.abs(rms - med)) + 1e-9
    thr = med + z * 1.4826 * mad
    zc = (np.sign(bp[1:]) != np.sign(bp[:-1])).astype(float)
    cycles = np.convolve(zc, np.ones(w), mode="same") / 2.0   # two crossings per cycle, over win_s
    cycles = np.concatenate([cycles[:1], cycles])
    mask = (rms > thr) & (cycles >= min_cycles)
    return _frames_to_events(mask, hz, "nod", min_dur=0.3, score=(rms - med) / (1.4826 * mad))


def valence_spike_events(valence: np.ndarray, hz: float = 30.0, z: float = 2.0, min_dur: float = 0.5,
                         smooth_s: float = 0.15, valid: np.ndarray | None = None) -> list[Event]:
    """Facial-affect events: stretches >= ``min_dur`` where the smoothed emotion
    valence is >= ``z`` robust standard deviations above (``expression_pos``) or
    below (``expression_neg``) the file median."""
    v = np.asarray(valence, dtype=float).reshape(-1)
    if len(v) < 3:
        return []
    if valid is not None:
        v = np.where(np.asarray(valid).reshape(-1) > 0, v, np.nan)
        v = np.nan_to_num(v, nan=float(np.nanmedian(v)) if np.isfinite(np.nanmedian(v)) else 0.0)
    w = max(1, int(smooth_s * hz))
    s = np.convolve(v, np.ones(w) / w, mode="same")
    med = np.median(s)
    mad = np.median(np.abs(s - med)) + 1e-9
    zs = (s - med) / (1.4826 * mad)
    return (_frames_to_events(zs >= z, hz, "expression_pos", min_dur, score=zs)
            + _frames_to_events(zs <= -z, hz, "expression_neg", min_dur, score=-zs))


def gaze_away_events(gaze: np.ndarray, hz: float = 30.0, k: float = 2.0, min_dur: float = 0.4,
                     smooth_s: float = 0.3, valid: np.ndarray | None = None) -> list[Event]:
    """Gaze-aversion events: stretches >= ``min_dur`` where the smoothed gaze
    encoding is >= ``k`` robust standard deviations (Mahalanobis-like, per
    axis MAD) from the participant's own median gaze. Seamless participants
    look at each other, so the median is "at the partner" (protocol §10)."""
    g = np.asarray(gaze, dtype=float)
    g = g.reshape(len(g), -1)
    if len(g) < 3:
        return []
    if valid is not None:
        ok = np.asarray(valid).reshape(-1) > 0
        g = np.where(ok[:, None], g, np.nan)
        g = np.where(np.isnan(g), np.nanmedian(g, axis=0), g)
    w = max(1, int(smooth_s * hz))
    s = np.stack([np.convolve(g[:, d], np.ones(w) / w, mode="same") for d in range(g.shape[1])], axis=1)
    med = np.median(s, axis=0)
    mad = np.median(np.abs(s - med), axis=0) * 1.4826 + 1e-6
    dist = np.sqrt((((s - med) / mad) ** 2).sum(axis=1))
    return _frames_to_events(dist >= k, hz, "gaze_away", min_dur, score=dist / k)


def gaze_deviation(gaze: np.ndarray, hz: float, t0: float, t1: float) -> float:
    """Mean robust distance of gaze in [t0, t1] from the file median (pure)."""
    g = np.asarray(gaze, dtype=float).reshape(len(gaze), -1)
    med = np.median(g, axis=0)
    mad = np.median(np.abs(g - med), axis=0) * 1.4826 + 1e-6
    i0, i1 = max(0, int(t0 * hz)), min(len(g), int(t1 * hz))
    if i1 <= i0:
        return 0.0
    return float(np.sqrt((((g[i0:i1] - med) / mad) ** 2).sum(axis=1)).mean())


def events_from_movement(feats: dict[str, np.ndarray], hz: float = 30.0) -> list[Event]:
    """All movement-derived events for one file from ``seamless.load_movement`` output."""
    valid = feats.get("is_valid")
    out: list[Event] = []
    if "head_encodings" in feats:
        out += nod_events(feats["head_encodings"], hz, valid=valid)
    if "emotion_valence" in feats:
        out += valence_spike_events(feats["emotion_valence"], hz, valid=valid)
    if "gaze_encodings" in feats:
        out += gaze_away_events(feats["gaze_encodings"], hz, valid=valid)
    return merge_events(out)


def movement_events(file_id: str) -> list[Event]:
    """Movement-derived events for a file, or [] when it has no movement features."""
    from ovfdb.data import seamless as sm

    if not sm.has_movement(file_id):
        return []
    feats = sm.load_movement(file_id, ("head_encodings", "emotion_valence", "gaze_encodings", "is_valid"))
    return events_from_movement(feats) if feats else []


# --- source 1: Gemini event list over the whole interaction -------------------------

_GEMINI_PROMPT = (
    "This is a side-by-side video of a face-to-face conversation: LEFT pane = person A, RIGHT pane = person B. "
    "Both voices are mixed in one audio track; use lip movement to attribute speech.\n"
    "List EVERY clearly visible nonverbal event of either person over the whole video, as a JSON list of objects "
    '{"who": "A" | "B", "kind": <kind>, "start": "MM:SS.s", "end": "MM:SS.s", "note": <short description>}.\n'
    "Allowed kinds (use exactly these strings):\n"
    "  nod            - head nod(s) while listening or agreeing\n"
    "  head_shake     - head shake (disagreement / 'no' / 'stop')\n"
    "  smile          - a smile or grin\n"
    "  laugh          - visible/audible laughter\n"
    "  frown          - frown, scowl, pained or concerned expression\n"
    "  surprise       - raised brows + open mouth, surprise\n"
    "  eyebrow_raise  - eyebrow flash while listening\n"
    "  gaze_away      - looks away from the other person (up, down, to the side) for a moment\n"
    "  hand_raise     - raises a hand / palm toward the other person (wanting to speak or 'wait')\n"
    "  stop_gesture   - explicit 'stop' / 'hold on' gesture\n"
    "  self_touch     - touches own face, hair, neck, ear, glasses, scratches, fidgets with clothing\n"
    "  point          - points at the other person\n"
    "Timestamps are minutes:seconds.tenths from the start of THIS video (e.g. \"00:23.4\"); be as precise as you can "
    "and give a start and end for each event (a nod lasts ~0.5-2 s, a smile 1-4 s; never report one event spanning "
    "the whole video - list each occurrence separately). Include short events; expect roughly 5-20 events in a "
    "40 s piece of lively conversation. Do not include speech itself, posture shifts, or hand gestures that "
    "illustrate speech. Return [] if nothing is visible."
)


def parse_ts(v) -> float | None:
    from ovfdb.mine.laughter import parse_ts as _p

    return _p(v)


MAX_EVENT_S = 8.0     # a "nod" spanning the whole video is the model being lazy, not an event


def events_from_gemini_json(raw: list, who: str, offset: float = 0.0) -> list[Event]:
    """Gemini list -> Events for pane ``who`` ('A' | 'B'); malformed rows and events longer
    than MAX_EVENT_S are dropped; ``offset`` (chunk start) is added to the times (pure)."""
    out = []
    for d in raw if isinstance(raw, list) else []:
        if not isinstance(d, dict) or str(d.get("who", "")).strip().upper() != who:
            continue
        kind = str(d.get("kind", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if kind not in KINDS:
            continue
        s, e = parse_ts(d.get("start")), parse_ts(d.get("end"))
        if s is None:
            continue
        if e is None or e <= s:
            e = s + 0.8
        if e - s > MAX_EVENT_S:
            continue
        note = str(d.get("note", ""))
        if kind == "self_touch" and ADAPTOR_EXCLUDE_RE.search(note):
            continue
        out.append(Event(kind, s + offset, e + offset, note, "gemini", 1.0))
    return merge_events(out)


def pair_sbs(a_mp4: Path | str, b_mp4: Path | str, out: Path | str, height: int = SBS_HEIGHT, fps: int = SBS_FPS) -> Path:
    """Low-res A|B composite of the whole interaction (hardware decode when available). Idempotent."""
    out = Path(out)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    fc = (f"[0:v]fps={fps},scale=-2:{height},setsar=1[l];[1:v]fps={fps},scale=-2:{height},setsar=1[r];"
          f"[l][r]hstack=inputs=2[v];[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[a]")
    tail = ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(out)]
    for hw in (["-hwaccel", "videotoolbox"], []):
        cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", *hw, "-i", str(a_mp4), *hw, "-i", str(b_mp4), *tail]
        p = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if p.returncode == 0 and out.exists():
            return out
    raise RuntimeError(f"ffmpeg pair sbs failed: {p.stderr[-1500:]}")


def chunk_bounds(duration: float, chunk_s: float = CHUNK_S, min_tail: float = 10.0) -> list[tuple[float, float]]:
    """[t0, t1) chunks of ``chunk_s``; a final piece shorter than ``min_tail`` joins the previous one (pure)."""
    out: list[tuple[float, float]] = []
    t = 0.0
    while t < duration:
        t1 = min(duration, t + chunk_s)
        if duration - t1 < min_tail:
            t1 = duration
        out.append((t, t1))
        t = t1
    return out


def _cut(src: Path, dst: Path, t0: float, t1: float) -> Path:
    if not dst.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-ss", f"{t0:.2f}", "-i", str(src), "-t", f"{t1 - t0:.2f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "48k",
                        "-movflags", "+faststart", str(dst)], check=True, capture_output=True)
    return dst


def detect_events_gemini(a: str, b: str, a_mp4: Path | str, b_mp4: Path | str,
                         cache_dir: Path | str = CACHE_DIR, workers: int = 4) -> tuple[list[Event], list[Event], dict]:
    """gemini-2.5-flash event lists over the A|B composite of the whole recording, in
    CHUNK_S-second pieces (one call each, ``GEMINI_FPS`` sampling, in parallel): on a
    single 2-minute call the model returns a handful of events and "continuous
    nodding"; on 40 s pieces it lists them. Returns (events_a, events_b, usage); cached per pair."""
    from concurrent.futures import ThreadPoolExecutor

    from ovfdb.data.seamless import media_duration
    from ovfdb.mine import gemini as G

    cache_dir = Path(cache_dir)
    cache = cache_dir / f"{a}__{b}.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
    else:
        sbs = pair_sbs(a_mp4, b_mp4, cache_dir / "sbs" / f"{a}__{b}.mp4")
        dur = media_duration(sbs)
        chunks = chunk_bounds(dur)

        def one(ch):
            t0, t1 = ch
            piece = _cut(sbs, cache_dir / "sbs" / f"{a}__{b}_{int(t0):04d}.mp4", t0, t1)
            out, usage = G.generate(_GEMINI_PROMPT, piece, mime="video/mp4", fps=GEMINI_FPS, temperature=0.2,
                                    thinking_budget=0)
            return {"t0": t0, "t1": t1, "events": out if isinstance(out, list) else [], "usage": usage}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            parts = list(pool.map(one, chunks))
        usage = {"prompt_tokens": sum(p["usage"].get("prompt_tokens", 0) for p in parts),
                 "output_tokens": sum(p["usage"].get("output_tokens", 0) for p in parts), "model": G.MODEL,
                 "calls": len(parts)}
        raw = {"chunks": parts, "usage": usage, "fps": GEMINI_FPS, "duration_s": dur}
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw, indent=1, ensure_ascii=False))
        for p in cache_dir.glob(f"sbs/{a}__{b}_*.mp4"):
            p.unlink()
    ea, eb = [], []
    for part in raw.get("chunks", [{"t0": 0.0, "events": raw.get("events", [])}]):
        ea += events_from_gemini_json(part["events"], "A", part["t0"])
        eb += events_from_gemini_json(part["events"], "B", part["t0"])
    return merge_events(ea), merge_events(eb), raw.get("usage", {})


# --- driver used by the pipeline -----------------------------------------------------

def events_for_pair(a: str, b: str, a_mp4, b_mp4, anns: dict[str, list[Annotation]] | None = None,
                    use_gemini: bool = True, use_movement: bool = True) -> dict[str, list[Event]]:
    """Merge the three event sources per file id."""
    ev: dict[str, list[Event]] = {a: [], b: []}
    if use_gemini:
        ea, eb, _ = detect_events_gemini(a, b, a_mp4, b_mp4)
        ev[a] += ea
        ev[b] += eb
    for fid in (a, b):
        if anns and anns.get(fid):
            ev[fid] += events_from_annotations(anns[fid])
        if use_movement:
            try:
                ev[fid] += movement_events(fid)
            except Exception as e:  # noqa: BLE001 - movement features are optional
                log.warning("movement events unavailable for %s: %s", fid, e)
    return {k: dedupe_sources(v) for k, v in ev.items()}


def dedupe_sources(events: list[Event], overlap: float = 0.5) -> list[Event]:
    """Drop movement / 3P-V events that overlap a Gemini event of a compatible
    kind (the Gemini one carries a note the VLM prompt can use). Pure."""
    gem = [e for e in events if e.source == "gemini"]
    compatible = {"expression_pos": {"smile", "laugh"}, "expression_neg": {"frown", "grimace", "concern"},
                  "nod": {"nod"}, "gaze_away": {"gaze_away"}, "self_touch": {"self_touch"}}
    out = list(gem)
    for e in events:
        if e.source == "gemini":
            continue
        kinds = compatible.get(e.kind, {e.kind})
        if any(g.kind in kinds and min(g.end, e.end) - max(g.start, e.start) > overlap * min(g.dur, e.dur) for g in gem):
            continue
        out.append(e)
    return sorted(out, key=lambda e: e.start)
