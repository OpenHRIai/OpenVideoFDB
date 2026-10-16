"""WS2 mining rules on synthetic VAD/transcript fixtures (no media, no network).

Each dialogue fixture triggers exactly one candidate of its rule (with A as
user) and none of the others; plus clip-boundary and clip-id tests.
"""

from __future__ import annotations

from ovfdb.data.seamless import Utterance
from ovfdb.mine import clip as C
from ovfdb.mine import dialogue as D
from ovfdb.mine import laughter as L
from ovfdb.mine.pipeline import parse_dynamics, select_candidates
from ovfdb.schema import Bucket, DynamicType, Segment, Word


def seg(a, b):
    return Segment(start=float(a), end=float(b))


def utt(a, b, text):
    """Utterance with evenly spaced word timings."""
    words = text.split()
    n = len(words)
    step = (b - a) / n
    return Utterance(start=float(a), end=float(b), transcript=text,
                     words=[Word(text=w, start=a + i * step, end=a + (i + 1) * step) for i, w in enumerate(words)])


def only(cands, dyn, bucket=None):
    hits = [c for c in cands if c.dynamic_type is dyn and (bucket is None or c.bucket is bucket)]
    others = [c for c in cands if c.dynamic_type is not dyn]
    assert len(hits) == 1, f"expected exactly one {dyn.value}, got {[(c.dynamic_type.value, c.ds_raw) for c in cands]}"
    assert not others, f"unexpected candidates {[(c.dynamic_type.value, c.ds_raw) for c in others]}"
    return hits[0]


# --- turns ------------------------------------------------------------------------

def test_backchannel_definition():
    assert D.is_backchannel(utt(1.0, 1.5, "mhm"))
    assert not D.is_backchannel(utt(1.0, 1.5, "oh yeah"))      # 2 words
    assert not D.is_backchannel(utt(1.0, 2.2, "yeah"))         # >= 1 s


def test_turns_merge_and_split():
    vad_a = [seg(0, 2), seg(2.4, 5), seg(6.0, 8)]          # 0.4 s gap merges, 1.0 s gap splits
    vad_b = [seg(4.9, 7.5)]
    utts_a = [utt(0, 5, "one two three four"), utt(6, 8, "five six")]
    utts_b = [utt(5.0, 7.5, "let me say something")]
    ta = D.speaker_turns(vad_a, utts_b, "a")
    assert [(t.start, t.end) for t in ta] == [(0.0, 5.0), (6.0, 8.0)]
    # B's non-backchannel onset at 5.0 falls in the 5.0-6.0 gap: a cut, which coincides with the split anyway
    both = D.turns(vad_a, utts_a, vad_b, utts_b)
    assert [t.speaker for t in both] == ["a", "b", "a"]
    # a backchannel by B does not split A's run
    ta2 = D.speaker_turns([seg(0, 2), seg(2.4, 5)], [utt(2.1, 2.5, "mhm")], "a")
    assert len(ta2) == 1


# --- rules ------------------------------------------------------------------------

def test_pause_handling_rule():
    vad_a = [seg(0, 4), seg(6.0, 9)]                    # 2 s pause inside A's thought
    vad_b = [seg(12, 15)]                                # B silent until well after A resumes
    utts_a = [utt(0, 4, "so I was thinking about the"), utt(6, 9, "the trip we took last year")]
    utts_b = [utt(12, 15, "oh that sounds nice")]
    c = only(D.find_all(vad_a, utts_a, vad_b, utts_b), DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION)
    assert c.user_role == "a" and (c.ds_raw, c.de_raw) == (4.0, 6.0)
    # user-cue-only: B talking *during* the pause does not veto it (that is the partner's reaction)
    c2 = D.find_pause_handling(vad_a, utts_a, [seg(4.5, 5.0)], [utt(4.5, 5.0, "right")])
    assert [(x.ds_raw, x.de_raw) for x in c2] == [(4.0, 6.0)]
    # ... nor does B taking a whole turn in the gap (A still resumes its own thought)
    assert D.find_pause_handling(vad_a, utts_a, [seg(4.2, 5.8)], [utt(4.2, 5.8, "I think I know what you mean")])
    # but B talking as A trails off means A did not hold the floor: no candidate
    assert not D.find_pause_handling(vad_a, utts_a, [seg(3.2, 4.0)], [utt(3.2, 4.0, "the what")])
    # a pause longer than 4 s is a turn end, not a pause
    assert not D.find_pause_handling([seg(0, 4), seg(9, 12)], utts_a, vad_b, utts_b)
    assert c.evidence["b_text_before"] == "" and "text_after" in c.evidence


def test_verbal_backchanneling_rule():
    # A tells a long story; a 0.3 s breath at 4.5-4.8 inside the turn is the listener slot
    vad_a = [seg(0, 4.5), seg(4.8, 10)]
    utts_a = [utt(0, 4.5, "and then we drove all the way up the coast,"), utt(4.8, 10, "which took hours and hours honestly")]
    vad_b, utts_b = [seg(12, 14)], [utt(12, 14, "wow that is far")]
    c = only(D.find_all(vad_a, utts_a, vad_b, utts_b), DynamicType.VERBAL_BACKCHANNELING, Bucket.GENERATION)
    assert c.user_role == "a"
    assert abs(c.ds_raw - (4.5 - D.BC_SLOT_BEFORE_S)) < 1e-6 and abs(c.de_raw - (4.8 + D.BC_SLOT_AFTER_S)) < 1e-6
    assert c.evidence["gap_s"] == 0.3 and c.evidence["text_before"].endswith("coast,")
    # user-cue-only: whether B said "mhm" in the slot changes nothing
    with_bc = D.find_verbal_backchanneling(vad_a, utts_a, [seg(4.6, 4.9)], [utt(4.6, 4.9, "mhm")])
    without = D.find_verbal_backchanneling(vad_a, utts_a, [], [])
    assert [(x.ds_raw, x.de_raw) for x in with_bc] == [(x.ds_raw, x.de_raw) for x in without] == [(c.ds_raw, c.de_raw)]
    # B talking in the 2 s before the slot: B is not a quiet listener, no slot
    assert not D.find_verbal_backchanneling(vad_a, utts_a, [seg(3.0, 4.0)], [utt(3.0, 4.0, "oh really")])
    # a turn shorter than 6 s, or a slot in its first 3 s / last 1.5 s, is not a slot
    assert not D.find_verbal_backchanneling([seg(0, 2.5), seg(2.8, 5.5)], utts_a, [], [])
    assert not D.find_verbal_backchanneling([seg(0, 2.0), seg(2.3, 10)], utts_a, [], [])
    assert not D.find_verbal_backchanneling([seg(0, 8.8), seg(9.1, 10)], utts_a, [], [])


def test_verbal_interruption_rule():
    vad_b = [seg(0, 6.0)]                                # B talking...
    vad_a = [seg(5.0, 9.0)]                              # A barges in at 5.0 and holds 4 s
    utts_b = [utt(0, 6, "so the thing about that restaurant is that they")]
    utts_a = [utt(5.0, 9.0, "wait wait I went there last week")]
    c = only(D.find_all(vad_a, utts_a, vad_b, utts_b), DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION)
    assert c.user_role == "a" and (c.ds_raw, c.de_raw) == (5.0, 5.0 + D.YIELD_S)
    assert "b_stop_s" not in c.evidence and c.evidence["b_text_before"].startswith("so the thing")
    # user-cue-only: B not stopping at all (talks on to 8.0 s) is still a candidate
    assert [(x.ds_raw, x.de_raw) for x in D.find_verbal_interruption(vad_a, utts_a, [seg(0, 8.0)], [utt(0, 8, "so the thing about that restaurant is that they do not take")])] == [(5.0, 6.5)]
    # A only backchannels -> no candidate
    assert not D.find_verbal_interruption([seg(5.0, 5.4)], [utt(5.0, 5.4, "yeah")], vad_b, utts_b)
    # B had finished its words well before A's onset (VAD tail only): a hand-over, not an interruption
    assert not D.find_verbal_interruption(vad_a, utts_a, [seg(0, 6.0)], [utt(0, 4.0, "so the thing about that")])
    # A does not hold the floor for 2 s -> no candidate
    assert not D.find_verbal_interruption([seg(5.0, 6.2)], [utt(5.0, 6.2, "wait wait no")], vad_b, utts_b)


def test_turn_taking_rule():
    vad_b = [seg(0, 4), seg(12.0, 16)]
    vad_a = [seg(4.8, 11.0)]
    utts_b = [utt(0, 4, "what did you do this weekend"), utt(12, 16, "oh nice I love hiking")]
    utts_a = [utt(4.8, 11.0, "I went hiking with my sister do you like hiking?")]
    cands = [c for c in D.find_all(vad_a, utts_a, vad_b, utts_b) if c.dynamic_type is DynamicType.TURN_TAKING]
    # both hand-overs qualify now (A->B at 11.0 and, with roles swapped, B->A at 16.0)
    assert sorted((c.user_role, c.ds_raw, c.de_raw) for c in cands) == [("a", 11.0, 11.0 + D.HANDOFF_S), ("b", 16.0, 16.0 + D.HANDOFF_S)]
    c = next(x for x in cands if x.user_role == "a")
    assert c.evidence["ends_with_question"] is True and "handoff_gap_s" not in c.evidence
    # user-cue-only: B's reply timing does not matter --- a late reply (14 s) or none at all still yields the cue
    assert [x.ds_raw for x in D.find_turn_taking(vad_a, utts_a, [seg(0, 4), seg(14.0, 16)], utts_b)] == [11.0]
    assert [x.ds_raw for x in D.find_turn_taking(vad_a, utts_a, [seg(0, 4)], utts_b[:1])] == [11.0]
    # B overlapping A's last half second -> no clean hand-over
    assert not D.find_turn_taking(vad_a, utts_a, [seg(0, 4), seg(10.7, 16)], utts_b)
    # A resumes with real content within 4 s -> that was a pause, not a floor offer
    assert not D.find_turn_taking([seg(4.8, 11.0), seg(13.0, 15.0)],
                                  utts_a + [utt(13.0, 15.0, "and also my brother came")], [seg(0, 4)], utts_b[:1])
    # ... but a one-word reaction from A is fine
    assert [x.ds_raw for x in D.find_turn_taking([seg(4.8, 11.0), seg(13.0, 13.4)], utts_a + [utt(13.0, 13.4, "yeah")],
                                                 vad_b, utts_b)] == [11.0]


def test_laughter_rule_from_tokens_and_segments():
    vad_b = [seg(0, 5)]
    vad_a = [seg(5.5, 7.0)]
    utts_b = [utt(0, 5, "and the dog just stared at me")]
    utts_a = [utt(5.5, 7.0, "[laughter]")]
    cands = D.find_all(vad_a, utts_a, vad_b, utts_b, dynamics={DynamicType.LAUGHTER})
    c = only(cands, DynamicType.LAUGHTER, Bucket.PERCEPTION)
    assert (c.ds_raw, c.de_raw) == (5.5, 7.0)
    # G: A laughs inside own turn and B reacts within 2 s
    laughs = [Segment(start=3.0, end=4.0, text="[laughter]")]
    g = D.find_laughter([seg(0, 6)], [utt(0, 6, "I could not believe it honestly")], [seg(4.5, 6)], [utt(4.5, 6, "ha no way")],
                        laughs_a=laughs)
    assert [x.bucket for x in g] == [Bucket.GENERATION]


def test_laughter_snap_to_vad_and_unlexical_stretches():
    vad = [seg(10.0, 11.2), seg(11.5, 13.0)]
    snapped = L.snap_to_vad([Segment(start=10.3, end=11.0, text="[laughter]")], vad)
    assert [(s.start, s.end) for s in snapped] == [(10.3, 11.0)] or snapped[0].start >= 10.0
    assert not L.snap_to_vad([Segment(start=20.0, end=21.0)], vad)      # nothing nearby
    st = L.unlexical_stretches(vad, [utt(10.0, 10.4, "ok")])      # the 0.3 s gap merges into one VAD run
    assert st == [(10.4, 13.0)]
    assert L.unlexical_stretches([seg(10.0, 11.2), seg(12.0, 13.0)], [utt(10.0, 10.4, "ok")]) == [(10.4, 11.2), (12.0, 13.0)]


# --- clip boundaries -------------------------------------------------------------------

def _pause_fixture():
    vad_a = [seg(2, 5), seg(12, 22), seg(24.0, 30)]
    vad_b = [seg(6, 11), seg(32, 38)]
    utts_a = [utt(2, 5, "I think so"), utt(12, 22, "well the first time I went there it was"), utt(24, 30, "really quite something")]
    utts_b = [utt(6, 11, "tell me about your trip"), utt(32, 38, "that sounds great")]
    cands = D.find_pause_handling(vad_a, utts_a, vad_b, utts_b)
    assert len(cands) == 1 and (cands[0].ds_raw, cands[0].de_raw) == (22.0, 24.0)
    return cands[0], D.turns(vad_a, utts_a, vad_b, utts_b), vad_b


def test_clip_bounds_prefers_two_lead_turns_and_next_turn_end():
    cand, turns, vad_b = _pause_fixture()
    b = C.clip_bounds(cand, turns, media_dur=120.0, partner_vad=vad_b)
    # turns before the window: A[2-5], B[6-11], A[12-22]; 2 turns before -> B's turn at 6.0 (16 s of context)
    assert b.t0 == 6.0 and b.lead_turns == 2
    # A's resume (24-30) belongs to the same floor turn; the next turn is B[32-38], so end = de + 8 = 32
    assert b.t1 == 32.0
    assert b.agent_speaks_first is True      # the clip opens on B's turn, so the agent is audible at t0
    assert b.dur <= C.MAX_CLIP_S
    # with B's first turn starting later than t0 the user speaks first
    b_late = C.clip_bounds(cand, turns, media_dur=120.0, partner_vad=[seg(7.0, 11.0), seg(32, 38)])
    assert b_late.t0 == 6.0 and b_late.agent_speaks_first is False


def test_clip_bounds_agent_first_and_caps():
    cand, turns, _vad_b = _pause_fixture()
    # partner audible at clip start -> agent_speaks_first
    b = C.clip_bounds(cand, turns, media_dur=120.0, partner_vad=[seg(5.0, 11.0), seg(32, 38)])
    assert b.agent_speaks_first is True
    # a very long lead-in is capped at 60 s and the window stays inside
    far = D.Candidate(DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION, "a", 100.0, 102.0)
    long_turns = [D.Turn("a", 0.0, 95.0, [seg(0, 95)]), D.Turn("b", 103.0, 110.0, [seg(103, 110)])]
    b2 = C.clip_bounds(far, long_turns, media_dur=200.0, partner_vad=[seg(103, 110)])
    assert b2.dur <= C.MAX_CLIP_S and b2.t0 <= far.ds_raw - C.MIN_LEAD_S and b2.t1 >= far.de_raw + C.MIN_TAIL_S
    # media end margin
    b3 = C.clip_bounds(far, long_turns, media_dur=104.0, partner_vad=[])
    assert b3.t1 <= 103.0
    # verbal interruption always has the agent speaking first
    vi = D.Candidate(DynamicType.VERBAL_INTERRUPTION, Bucket.GENERATION, "a", 100.0, 101.0)
    assert C.clip_bounds(vi, long_turns, media_dur=200.0, partner_vad=[]).agent_speaks_first is True


def test_floor_turns_coalesce_fragments_and_interjections():
    t = [D.Turn("a", 0, 2), D.Turn("a", 2.8, 6), D.Turn("b", 4.0, 4.5), D.Turn("a", 6.5, 9), D.Turn("b", 10, 15), D.Turn("a", 15.5, 18)]
    ft = C.floor_turns(t)
    assert [(x.speaker, x.start, x.end) for x in ft] == [("a", 0, 9), ("b", 10, 15), ("a", 15.5, 18)]
    # a long B turn does break A's floor
    ft2 = C.floor_turns([D.Turn("a", 0, 2), D.Turn("b", 2.5, 5), D.Turn("a", 5.5, 8)])
    assert [x.speaker for x in ft2] == ["a", "b", "a"]


def test_clip_indices_are_deterministic_and_shared_across_buckets():
    keys = [("F1", 10.0, 50.0), ("F1", 3.0, 40.0), ("F2", 0.0, 30.0), ("F1", 10.0, 50.0)]
    m = C.assign_clip_indices(keys)
    assert m[("F1", 3.0, 40.0)] == 0 and m[("F1", 10.0, 50.0)] == 1 and m[("F2", 0.0, 30.0)] == 0
    # existing ids are kept; new windows get the next index
    m2 = C.assign_clip_indices([("F1", 60.0, 90.0)], existing={("F1", 10.0, 50.0): 4})
    assert m2[("F1", 10.0, 50.0)] == 4 and m2[("F1", 60.0, 90.0)] == 5
    assert C.clip_id_for("F1", 5) == "F1_c05"


def test_select_candidates_and_parse_dynamics():
    mk = lambda ds, score, role="a": D.Candidate(DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION, role, ds, ds + 1, {"score": score})
    cands = [mk(10, 1.0), mk(11, 2.0), mk(30, 0.5), mk(50, 0.1), mk(10, 0.9, "b")]
    chosen = select_candidates(cands, {(DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION): 10}, per_pair=3)
    assert [(c.ds_raw, c.user_role) for c in chosen] == [(11, "a"), (10, "b"), (30, "a")]   # 10/a too close to 11/a
    assert select_candidates(cands, {(DynamicType.PAUSE_HANDLING, Bucket.PERCEPTION): 0}, 3) == []
    assert parse_dynamics("pause_handling,turn_taking") == [DynamicType.PAUSE_HANDLING, DynamicType.TURN_TAKING]
    assert len(parse_dynamics("all")) == 5
