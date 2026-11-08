"""Unit tests for ovfdb.score.cues (WS10 §3 metrics) on synthetic tracks and segment lists."""

import numpy as np
import pytest

from ovfdb.schema import Segment
from ovfdb.score import cues

FPS = 10


def seg(a, b, text="some words here now", n_words=None):
    return Segment(a, b, text, len(text.split()) if n_words is None else n_words)


def bc(a, b=None):
    return Segment(a, b if b is not None else a + 0.4, "mhm", 1)


# --- event mining ---------------------------------------------------------------------------------

def test_mine_complete_incomplete_onset():
    # agent speaks 2-5, user takes over at 5.8 and keeps it; agent pauses 12-13.5 and resumes; agent onset at 20
    agent = [seg(2.0, 5.0), seg(10.0, 12.0), seg(13.5, 15.0), seg(20.0, 23.0)]
    user = [seg(5.8, 9.0), seg(16.0, 19.0)]
    ev = cues.mine_events(agent, user, clip_end=30.0, seed=0)
    assert ev.completes == [5.0, 15.0]                       # 15.0: user onset at 16 within 3 s, agent silent ≥ 1 s after
    assert ev.incompletes == [(12.0, 13.5)]
    assert ev.onsets == [2.0, 10.0, 13.5, 20.0]             # 13.5: the agent was silent 1.5 s ≥ LISTEN_S, so it counts
    assert len(ev.midturn) == len(ev.completes) and len(ev.listening) == len(ev.onsets)
    for t in ev.midturn:                                     # inside agent speech with ≥ 1 s left
        assert any(s.start <= t and s.end - t >= cues.MIDTURN_AHEAD_S for s in agent)
    for t in ev.listening:                                   # not speaking, far from the next own onset
        assert not any(s.start <= t < s.end for s in agent)
        assert all(s.start - t >= 1.0 + cues.LISTEN_NEG_MARGIN_S for s in agent if s.start > t)


def test_mine_rules_edges():
    # too short to hold the floor -> no offset event; user backchannel does not make a complete; merged gaps
    agent = [seg(2.0, 2.6), seg(5.0, 6.0), seg(6.1, 8.0)]       # 5.0-8.0 is one utterance after merging (gap 0.1 < 0.2)
    user = [bc(8.3), seg(12.0, 14.0)]
    ev = cues.mine_events(agent, user, clip_end=20.0)
    assert ev.completes == []                                # the real user onset (12.0) is 4 s after the offset: too late
    assert ev.incompletes == []                              # the agent never resumes
    assert ev.onsets == [2.0, 5.0]                           # 6.1 merged away
    # the same but the agent resumes 2 s later: incomplete pause
    ev2 = cues.mine_events(agent + [seg(10.0, 11.5)], user, clip_end=20.0)
    assert ev2.incompletes == [(8.0, 10.0)]
    # onset after a backchannel of the agent's own still counts as listening ≥ 1 s (backchannels are not real speech)
    ev3 = cues.mine_events([seg(0.0, 3.0), bc(5.0), seg(6.0, 8.0)], [seg(3.5, 5.8)], clip_end=10.0)
    assert ev3.onsets == [0.0, 6.0]


def test_merge_segments():
    m = cues.merge_segments([seg(0, 1, "a b", 2), seg(1.1, 2, "c", 1), seg(2.5, 3, "d", 1)])
    assert [(s.start, s.end, s.n_words) for s in m] == [(0, 2, 3), (2.5, 3, 1)]


# --- metrics on synthetic tracks -----------------------------------------------------------------

def rising_track(events, n, rise_s=0.3, fps=FPS, base=0.1, high=0.9):
    """Flat ``base``, jumping to ``high`` from ``rise_s`` before each event (that frame included) through the event frame."""
    tr = np.full(n, base)
    for t in events:
        k0 = int(np.floor(t * fps + 1e-9))
        tr[max(k0 - round(rise_s * fps), 0): k0 + 1] = high
    return tr


def test_rising_track_gives_auc_one_and_horizon_300ms():
    completes = [5.0, 15.0, 25.0, 35.0]
    negatives = [2.0, 12.0, 22.0, 32.0]
    tr = rising_track(completes, n=400)
    assert cues.cue_auc(tr, FPS, completes, negatives, lead=cues.YIELD_LEAD_S) == 1.0
    hz = cues.horizon(tr, FPS, completes, theta=0.5)
    assert hz.detection_rate == 1.0
    assert hz.median_ms == pytest.approx(300.0)
    assert hz.median_detected_ms == pytest.approx(300.0)


def test_flat_track_is_chance_and_missed():
    completes = [5.0, 15.0, 25.0]
    negatives = [2.0, 12.0, 22.0]
    tr = np.full(300, 0.2)
    assert cues.cue_auc(tr, FPS, completes, negatives, lead=0.3) == 0.5
    hz = cues.horizon(tr, FPS, completes, theta=0.5)
    assert hz.detection_rate == 0.0 and hz.median_ms == 0.0
    assert np.isnan(hz.median_detected_ms)


def test_horizon_is_measured_to_the_event_frame_only():
    tr = np.zeros(100); tr[40:46] = 1.0                      # above θ from 4.0 s through the 4.5 s frame -> 500 ms; event at 6.0 -> missed
    hz = cues.horizon(tr, FPS, [4.5, 6.0], theta=0.5)
    assert list(hz.detected) == [True, False]
    assert hz.horizons_s[0] == pytest.approx(0.5)
    hz2 = cues.horizon(tr, FPS, [4.0], theta=0.5)            # above only at the event frame: detected, zero lead
    assert hz2.detected[0] and hz2.horizons_s[0] == 0.0


def test_shuffled_control_at_chance():
    rng = np.random.default_rng(1)
    n_clips, n = 40, 600
    scores = []
    perm = cues.shuffle_pairs(n_clips, seed=3)
    assert (perm != np.arange(n_clips)).all()
    events = [sorted(rng.uniform(5, 55, size=6)) for _ in range(n_clips)]
    negs = [sorted(rng.uniform(5, 55, size=6)) for _ in range(n_clips)]
    tracks = [rising_track(ev, n) + rng.normal(0, 0.01, n) for ev in events]
    own = [(cues.value_at(tracks[i], events[i], FPS, 0.3), cues.value_at(tracks[i], negs[i], FPS)) for i in range(n_clips)]
    shuf = [(cues.value_at(tracks[perm[i]], events[i], FPS, 0.3), cues.value_at(tracks[perm[i]], negs[i], FPS)) for i in range(n_clips)]
    assert cues.pooled_auc(own) > 0.95
    scores = cues.pooled_auc(shuf)
    assert 0.4 < scores < 0.6


def test_auc_ties_and_nans():
    assert cues.auc([1, 1], [1, 1]) == 0.5
    assert cues.auc([1, 2, np.nan], [0, 0]) == 1.0
    assert np.isnan(cues.auc([], [0.0]))


def test_threshold_and_hold_far():
    neg = np.linspace(0, 1, 101)
    assert cues.threshold_at_far(neg, far=0.10) == pytest.approx(0.9)
    p_end = np.zeros(200); p_end[55:60] = 0.8                 # a crossing during the first pause only
    far = cues.hold_far(p_end, FPS, [(5.0, 7.0), (10.0, 12.0)], theta=0.5)
    assert far == 0.5
    # θ as a function of τ: demanding more early on hides the crossing at τ = 0.5 s
    assert cues.hold_far(p_end, FPS, [(5.0, 7.0), (10.0, 12.0)], theta=lambda tau: 0.9 if tau < 1.0 else 0.5) == 0.0
    assert np.isnan(cues.hold_far(p_end, FPS, [], theta=0.5))


def test_visual_gain_and_bootstrap():
    assert cues.visual_gain({"yield_auc": 0.7, "start_auc_1": 0.65, "x": float("nan")}, {"yield_auc": 0.6, "start_auc_1": 0.65}) == {
        "yield_auc": pytest.approx(0.1), "start_auc_1": pytest.approx(0.0)}
    clips = [(np.array([0.9, 0.8]), np.array([0.1, 0.2])) for _ in range(5)] + [(np.array([0.1]), np.array([0.9]))]
    point, lo, hi = cues.clip_bootstrap(cues.pooled_auc, clips, n_boot=200, seed=0)
    assert lo <= point <= hi and 0.8 < point < 1.0
    p1, lo1, hi1 = cues.clip_bootstrap(cues.pooled_auc, clips[:1], n_boot=10)
    assert p1 == 1.0 and np.isnan(lo1) and np.isnan(hi1)


def test_summarise_end_to_end():
    agent = [seg(2.0, 5.0), seg(10.0, 12.0), seg(13.5, 15.0), seg(20.0, 23.0)]
    user = [seg(5.8, 9.0), seg(16.0, 19.0)]
    ev = cues.mine_events(agent, user, clip_end=30.0, seed=0)
    n = 300
    tracks = {"p_eager": rising_track(ev.completes, n), "p_start_1": rising_track(ev.onsets, n, rise_s=0.5),
              "p_start_0.4": rising_track(ev.onsets, n, rise_s=0.3), "p_end": np.zeros(n)}
    th = cues.Thresholds(eager=0.5, bid=0.5, end=0.5)
    out = cues.summarise(tracks, FPS, ev, th)
    assert out["n"]["completes"] == 2 and out["yield_auc"] == 1.0 and out["start_auc_1"] == 1.0 and out["start_auc_0.4"] == 1.0
    assert out["yield_detection"] == 1.0 and out["yield_horizon_ms"] == pytest.approx(300.0)
    assert out["bid_detection"] == 1.0 and out["bid_lead_ms"] == pytest.approx(500.0)
    assert out["hold_far"] == 0.0
