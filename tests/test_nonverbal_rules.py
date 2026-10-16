"""WS2 day-2 nonverbal rules on synthetic fixtures: event lists + VAD + movement arrays.

No media, no network. Each finder fixture triggers exactly the intended
(dynamic, bucket) with A as user; the movement functions run on synthetic
30 Hz signals.
"""

from __future__ import annotations

import numpy as np

from ovfdb.data.seamless import Annotation, Utterance
from ovfdb.mine import clip as C
from ovfdb.mine import dialogue as D
from ovfdb.mine import nonverbal as NV
from ovfdb.mine import verify as V
from ovfdb.mine.pipeline import DAY2_DYNAMICS, parse_dynamics
from ovfdb.schema import Bucket, DynamicType, Segment, Word


def seg(a, b):
    return Segment(start=float(a), end=float(b))


def utt(a, b, text):
    words = text.split()
    step = (b - a) / len(words)
    return Utterance(start=float(a), end=float(b), transcript=text,
                     words=[Word(text=w, start=a + i * step, end=a + (i + 1) * step) for i, w in enumerate(words)])


def ev(kind, a, b, note="", source="gemini"):
    return NV.Event(kind, float(a), float(b), note, source)


def keyed(cands):
    return sorted({(c.dynamic_type.value, c.bucket.value, c.user_role) for c in cands})


# --- event-driven finders -----------------------------------------------------------

def test_nv_backchanneling_p_and_g():
    vad_b = [seg(0, 10)]                      # B talks for 10 s
    vad_a = []                                # A silent
    cands = NV.find_nv_backchanneling([ev("nod", 4.0, 5.0)], vad_a, [], vad_b)
    assert [(c.bucket, c.ds_raw, c.de_raw) for c in cands] == [(Bucket.PERCEPTION, 4.0, 5.0)]
    assert cands[0].evidence["event"]["kind"] == "nod"
    # B nods while A speaks -> G
    g = NV.find_nv_backchanneling([], [seg(0, 10)], [ev("smile", 4.0, 5.0)], [])
    assert [c.bucket for c in g] == [Bucket.GENERATION]
    # B stops right after the nod -> not "keeps talking"
    assert not NV.find_nv_backchanneling([ev("nod", 4.0, 5.0)], [], [], [seg(0, 5.2)])
    # A talking through the nod -> not a listener cue
    assert not NV.find_nv_backchanneling([ev("nod", 4.0, 5.0)], [seg(2, 8)], [], vad_b)
    # a self-touch is not a backchannel
    assert not NV.find_nv_backchanneling([ev("self_touch", 4.0, 5.0)], [], [], vad_b)


def test_face_emotion_display_p_and_g():
    vad_a = [seg(0, 4)]
    vad_b = [seg(5.0, 9.0)]                   # B replies 1 s after A's smile ends
    cands = NV.find_face_emotion_display([ev("smile", 3.0, 4.0)], vad_a, [], vad_b)
    assert [(c.bucket, c.ds_raw, c.de_raw) for c in cands] == [(Bucket.PERCEPTION, 3.0, 4.0)]
    assert cands[0].evidence["b_reply_lag_s"] == 2.0
    # B mirrors with a smile within 2.5 s -> G as well
    both = NV.find_face_emotion_display([ev("smile", 3.0, 4.0)], vad_a, [ev("smile", 4.5, 5.5)], vad_b)
    assert [c.bucket for c in both] == [Bucket.PERCEPTION, Bucket.GENERATION]
    assert both[1].evidence["partner_event"]["kind"] == "smile" and both[1].evidence["mirror_lag_s"] == 1.5
    # no B reply or mirror -> nothing; a nod is not an expression
    assert not NV.find_face_emotion_display([ev("smile", 3.0, 4.0)], vad_a, [], [seg(20, 25)])
    assert not NV.find_face_emotion_display([ev("nod", 3.0, 4.0)], vad_a, [ev("smile", 4.5, 5.5)], vad_b)


def test_emotion_matching_same_sign_within_2s():
    a = [ev("smile", 3.0, 4.0)]
    hit = NV.find_emotion_matching(a, [], [ev("smile", 4.5, 5.5)], [])
    assert len(hit) == 1 and hit[0].bucket is Bucket.GENERATION
    assert (hit[0].ds_raw, hit[0].de_raw) == (3.0, 5.0) and hit[0].evidence["lag_s"] == 1.5
    assert not NV.find_emotion_matching(a, [], [ev("frown", 4.5, 5.5)], [])        # opposite sign
    assert not NV.find_emotion_matching(a, [], [ev("smile", 5.5, 6.5)], [])        # too late
    assert not NV.find_emotion_matching(a, [], [ev("nod", 3.5, 4.5)], [])          # no affect
    neg = NV.find_emotion_matching([ev("frown", 3.0, 4.0)], [], [ev("concern", 4.0, 5.0)], [])
    assert len(neg) == 1 and neg[0].evidence["valence"] == -1


def test_gaze_avoidance_needs_pause_and_gaze_away():
    vad_a = [seg(0, 4), seg(6.0, 9)]
    vad_b = [seg(12, 15)]
    utts_a = [utt(0, 4, "so I was thinking about the"), utt(6, 9, "the trip we took last year")]
    utts_b = [utt(12, 15, "oh that sounds nice")]
    hit = NV.find_gaze_avoidance([ev("gaze_away", 4.2, 5.5)], vad_a, utts_a, vad_b, utts_b)
    assert len(hit) == 1 and (hit[0].ds_raw, hit[0].de_raw) == (4.0, 6.0)
    assert hit[0].evidence["gaze_overlap_s"] == 1.3 and hit[0].evidence["gap_s"] == 2.0
    # gaze away outside the pause -> plain pause handling, not this
    assert not NV.find_gaze_avoidance([ev("gaze_away", 1.0, 2.0)], vad_a, utts_a, vad_b, utts_b)
    # no pause at all -> nothing
    assert not NV.find_gaze_avoidance([ev("gaze_away", 4.2, 5.5)], [seg(0, 9)], [utt(0, 9, "a b c d")], vad_b, utts_b)


def test_adaptor_prefers_partner_speaking():
    vad_b = [seg(0, 10)]
    hit = NV.find_adaptor([ev("self_touch", 4.0, 6.0, "rubs their head")], [], [], vad_b)
    assert len(hit) == 1 and hit[0].evidence["mode"] == "partner_speaking"
    own = NV.find_adaptor([ev("self_touch", 4.0, 6.0)], [seg(0, 10)], [], [])
    assert len(own) == 1 and own[0].evidence["mode"] == "user_speaking"
    assert hit[0].evidence["score"] > own[0].evidence["score"]
    # nobody speaking -> skip; a nod is not an adaptor
    assert not NV.find_adaptor([ev("self_touch", 4.0, 6.0)], [], [], [])
    assert not NV.find_adaptor([ev("nod", 4.0, 6.0)], [], [], vad_b)


def test_nv_interruption_requires_yield_and_floor_take():
    vad_b = [seg(0, 6.0)]                                # B talking, stops at 6.0
    vad_a = [seg(6.2, 10)]                               # A takes the floor 1.2 s after the gesture
    hit = NV.find_nv_interruption([ev("hand_raise", 5.0, 5.6)], vad_a, [], vad_b)
    assert len(hit) == 1 and (hit[0].ds_raw, hit[0].de_raw) == (5.0, 6.0)
    assert hit[0].evidence["b_stop_s"] == 1.0 and hit[0].evidence["a_onset_s"] == 1.2
    assert not NV.find_nv_interruption([ev("hand_raise", 5.0, 5.6)], vad_a, [], [seg(0, 9.0)])     # B does not stop
    assert not NV.find_nv_interruption([ev("hand_raise", 5.0, 5.6)], [seg(20, 25)], [], vad_b)    # A never takes the floor
    assert not NV.find_nv_interruption([ev("hand_raise", 5.0, 5.6)], [seg(4.0, 10)], [], vad_b)   # A already talking
    assert not NV.find_nv_interruption([ev("nod", 5.0, 5.6)], vad_a, [], vad_b)                  # a nod is not an interruption
    assert not NV.find_nv_interruption([ev("hand_raise", 0.5, 1.0)], vad_a, [], vad_b)           # B barely started


def test_find_all_runs_both_frames_and_tags_roles():
    ev_a = [ev("nod", 4.0, 5.0)]
    cands = NV.find_all(ev_a, [], [], [], [seg(0, 10)], [], dynamics={DynamicType.NONVERBAL_BACKCHANNELING})
    # A's nod during B's turn: P with A as user, and G with B as user (B is the speaker)
    assert keyed(cands) == [("Nonverbal Backchanneling", "generation", "b"), ("Nonverbal Backchanneling", "perception", "a")]
    assert not NV.find_all(ev_a, [], [], [], [seg(0, 10)], [], dynamics={DynamicType.ADAPTOR_HANDLING})


def test_agent_speaks_first_for_nonverbal_dynamics():
    turns = [D.Turn("b", 0.0, 10.0, [seg(0, 10)]), D.Turn("a", 11.0, 15.0, [seg(11, 15)])]
    for dyn in (DynamicType.NONVERBAL_BACKCHANNELING, DynamicType.ADAPTOR_HANDLING, DynamicType.NONVERBAL_INTERRUPTION):
        c = D.Candidate(dyn, Bucket.PERCEPTION, "a", 4.0, 5.0)
        assert C.clip_bounds(c, turns, media_dur=100.0, partner_vad=[]).agent_speaks_first is True, dyn
    # G-bucket backchanneling and the user-led dynamics follow the "partner audible at t0" rule
    g = D.Candidate(DynamicType.NONVERBAL_BACKCHANNELING, Bucket.GENERATION, "a", 12.0, 13.0)
    assert C.clip_bounds(g, turns, media_dur=100.0, partner_vad=[seg(5, 10)]).agent_speaks_first is False
    assert all((d, Bucket.PERCEPTION) in V.PARTNER_EXPECTATION for d in (
        DynamicType.NONVERBAL_BACKCHANNELING, DynamicType.FACE_EMOTION_DISPLAY, DynamicType.GAZE_AVOIDANCE_WITH_PAUSE,
        DynamicType.ADAPTOR_HANDLING, DynamicType.NONVERBAL_INTERRUPTION))
    assert all((d, Bucket.GENERATION) in V.PARTNER_EXPECTATION for d in (
        DynamicType.NONVERBAL_BACKCHANNELING, DynamicType.FACE_EMOTION_DISPLAY, DynamicType.EMOTION_MATCHING))
    assert parse_dynamics("nonverbal") == list(DAY2_DYNAMICS) and len(DAY2_DYNAMICS) == 6
    assert len(parse_dynamics("everything")) == 11


# --- event sources --------------------------------------------------------------------

def test_events_from_annotations_regex():
    anns = [Annotation("The participant rubs their head with their right hand.", 61, 66),
            Annotation("The participant uses their hands to gesture.", 37, 38),
            Annotation("The participant adjusts their glasses.", 10, 10),
            Annotation("The participant touches their face while gesturing.", 20, 22)]
    evs = NV.events_from_annotations(anns)
    assert [(e.kind, e.start, e.end, e.source) for e in evs] == [("self_touch", 61.0, 66.0, "3pv"), ("self_touch", 10.0, 11.0, "3pv")]


def test_events_from_gemini_json_and_merge():
    raw = [{"who": "A", "kind": "nod", "start": "00:04.0", "end": "00:04.8", "note": "nods"},
           {"who": "A", "kind": "nod", "start": "00:05.0", "end": "00:05.6"},         # < 0.3 s gap -> merged
           {"who": "B", "kind": "Self touch", "start": "01:00.0", "end": "00:59.0"},   # end <= start -> start + 0.8
           {"who": "B", "kind": "wink", "start": "00:01.0", "end": "00:02.0"},          # unknown kind dropped
           {"who": "A", "kind": "smile", "start": None}]                                # no start dropped
    ea, eb = NV.events_from_gemini_json(raw, "A"), NV.events_from_gemini_json(raw, "B")
    assert [(e.kind, e.start, e.end) for e in ea] == [("nod", 4.0, 5.6)]
    assert [(e.kind, e.start, e.end) for e in eb] == [("self_touch", 60.0, 60.8)]
    noisy = [{"who": "A", "kind": "self_touch", "start": "00:01.0", "end": "00:03.0", "note": "hands clasped together"},
             {"who": "A", "kind": "self_touch", "start": "00:05.0", "end": "00:06.0", "note": "gestures with right hand"},
             {"who": "A", "kind": "self_touch", "start": "00:08.0", "end": "00:09.0", "note": "rubs eye"}]
    assert [e.start for e in NV.events_from_gemini_json(noisy, "A")] == [8.0]
    # movement duplicates of a gemini event are dropped, novel ones kept
    merged = NV.dedupe_sources([ev("smile", 10.0, 11.0), ev("expression_pos", 10.2, 10.9, source="movement"),
                                ev("gaze_away", 30.0, 31.0, source="movement")])
    assert [(e.kind, e.source) for e in merged] == [("smile", "gemini"), ("gaze_away", "movement")]


# --- movement feature functions (synthetic 30 Hz arrays) -----------------------------------

HZ = 30.0


def test_nod_events_from_head_pitch_oscillation():
    rng = np.random.default_rng(0)
    t = np.arange(0, 40, 1 / HZ)
    pitch = 0.3 * rng.standard_normal(len(t))                     # jitter
    nod = (t >= 20) & (t < 21.5)                                  # 1.5 s of 2.5 Hz nodding (>= 3 cycles)
    pitch[nod] += 6.0 * np.sin(2 * np.pi * 2.5 * (t[nod] - 20))
    head = np.stack([np.zeros_like(t), np.zeros_like(t), pitch], axis=1)
    evs = NV.nod_events(head, HZ, dim=2)
    assert len(evs) == 1 and evs[0].kind == "nod"
    assert abs(evs[0].start - 20.0) < 0.6 and abs(evs[0].end - 21.5) < 0.6
    assert evs[0].source == "movement" and evs[0].score > 2.0
    # a single slow tilt (0.25 Hz, no cycles in the band) is not a nod
    tilt = 0.3 * rng.standard_normal(len(t))
    tilt[(t >= 20) & (t < 24)] += 6.0 * np.sin(2 * np.pi * 0.25 * (t[(t >= 20) & (t < 24)] - 20))
    assert not NV.nod_events(np.stack([tilt, tilt, tilt], axis=1), HZ, dim=2)


def test_valence_spikes_and_gaze_away():
    rng = np.random.default_rng(1)
    t = np.arange(0, 60, 1 / HZ)
    val = -0.1 + 0.02 * rng.standard_normal(len(t))
    val[(t >= 10) & (t < 11)] += 0.4                              # 1 s smile
    val[(t >= 30) & (t < 30.2)] += 0.4                            # 0.2 s blip: too short
    val[(t >= 40) & (t < 41)] -= 0.3                              # 1 s negative
    evs = NV.valence_spike_events(val[:, None], HZ)
    assert [(e.kind, round(e.start), round(e.end)) for e in evs] == [("expression_pos", 10, 11), ("expression_neg", 40, 41)]
    assert evs[0].valence == 1 and evs[1].valence == -1
    gaze = 0.05 * rng.standard_normal((len(t), 2))
    gaze[(t >= 20) & (t < 21.5), 0] += 1.0                        # looks sideways for 1.5 s
    g = NV.gaze_away_events(gaze, HZ)
    assert len(g) == 1 and g[0].kind == "gaze_away" and abs(g[0].start - 20) < 0.4 and abs(g[0].end - 21.5) < 0.4
    assert NV.gaze_deviation(gaze, HZ, 20.0, 21.5) > 5 * NV.gaze_deviation(gaze, HZ, 2.0, 3.5)
    # is_valid mask: invalid frames are neutralised rather than spiking
    valid = np.ones(len(t))
    valid[(t >= 50) & (t < 52)] = 0
    val2 = val.copy()
    val2[(t >= 50) & (t < 52)] = 5.0
    assert [round(e.start) for e in NV.valence_spike_events(val2, HZ, valid=valid)] == [10, 40]


def test_events_from_movement_feeds_the_finders():
    t = np.arange(0, 30, 1 / HZ)
    pitch = np.zeros_like(t)
    nod = (t >= 10) & (t < 11.5)
    pitch[nod] = 5.0 * np.sin(2 * np.pi * 2.5 * (t[nod] - 10))
    feats = {"head_encodings": np.stack([pitch * 0, pitch * 0, pitch], axis=1),
             "emotion_valence": np.zeros((len(t), 1)), "gaze_encodings": np.zeros((len(t), 2))}
    evs = NV.events_from_movement(feats, HZ)
    assert [e.kind for e in evs] == ["nod"]
    cands = NV.find_nv_backchanneling(evs, [], [], [seg(0, 30)])
    assert len(cands) == 1 and cands[0].bucket is Bucket.PERCEPTION and cands[0].evidence["event"]["source"] == "movement"


def test_chunk_bounds_and_offsets():
    assert NV.chunk_bounds(128.0, chunk_s=40.0) == [(0.0, 40.0), (40.0, 80.0), (80.0, 128.0)]   # 8 s tail joins
    assert NV.chunk_bounds(134.0, chunk_s=40.0) == [(0.0, 40.0), (40.0, 80.0), (80.0, 120.0), (120.0, 134.0)]
    assert NV.chunk_bounds(100.0, chunk_s=40.0) == [(0.0, 40.0), (40.0, 80.0), (80.0, 100.0)]
    assert NV.chunk_bounds(30.0, chunk_s=40.0) == [(0.0, 30.0)]
    offs = NV.events_from_gemini_json([{"who": "A", "kind": "nod", "start": "00:02.0", "end": "00:02.5"},
                                       {"who": "A", "kind": "nod", "start": "00:00.0", "end": "00:39.0"}], "A", offset=40.0)
    assert [(e.start, e.end) for e in offs] == [(42.0, 42.5)]       # whole-chunk "nod" dropped (> MAX_EVENT_S)
