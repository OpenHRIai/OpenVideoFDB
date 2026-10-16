"""ovfdb.score.segments: word normalisation / counting and VAD + ASR merging (pure, no media)."""

from __future__ import annotations

import pytest

from ovfdb.schema import Segment, Word
from ovfdb.score import segments, timing


@pytest.mark.parametrize("text, tokens", [
    ("Mm -hmm.", ["mmhmm"]),
    ("Mm-hmm", ["mmhmm"]),
    ("uh huh", ["uhhuh"]),
    ("mm hmm", ["mmhmm"]),
    ("mhm", ["mhm"]),
    ("Yeah. Yeah.", ["yeah"]),
    ("yeah yeah I agree", ["yeah", "i", "agree"]),
    ("Oh yeah", ["oh", "yeah"]),
    ("no no no", ["no"]),
    ("It's fine.", ["it's", "fine"]),
    ("", []),
    ("...", []),
])
def test_normalise_tokens(text, tokens):
    assert segments.normalise_tokens(text) == tokens
    assert segments.count_words(text) == len(tokens)


def test_count_words_feeds_is_backchannel():
    # the three GT Verbal Backchanneling failures from calibration_v0 (whisper text, VAD-free durations)
    assert timing.is_backchannel(Segment(30.98, 31.16, "Yeah. Yeah.", segments.count_words("Yeah. Yeah.")))
    assert timing.is_backchannel(Segment(13.94, 14.0, "Mm -hmm.", segments.count_words("Mm -hmm.")))
    assert timing.is_backchannel(Segment(4.33, 5.37, "yeah", 1))                 # 1.04 s: within 0.1 s slack
    assert not timing.is_backchannel(Segment(4.33, 5.44, "yeah", 1))             # 1.11 s: over
    assert not timing.is_backchannel(Segment(1.0, 1.5, "oh yeah", segments.count_words("oh yeah")))
    assert timing.is_backchannel(Segment(1.0, 1.5, "", 0))                       # wordless VAD region ("mhm")


def test_words_to_segments_counts_normalised_words():
    segs = segments.words_to_segments([Word("Yeah.", 0.0, 0.2), Word("Yeah.", 0.3, 0.5)])
    assert segs == [Segment(0.0, 0.5, "Yeah. Yeah.", 1)]


def test_merge_regions():
    assert segments.merge_regions([(3.0, 4.0), (0.0, 1.0), (1.2, 2.0)], gap=0.5) == [(0.0, 2.0), (3.0, 4.0)]
    assert segments.merge_regions([(0.0, 1.0), (1.5, 2.0)], gap=0.5) == [(0.0, 1.0), (1.5, 2.0)]   # == gap splits
    assert segments.merge_regions([], gap=0.5) == []


def test_merge_vad_and_words_attaches_words_by_midpoint():
    regions = [(1.0, 2.0), (3.0, 3.4), (5.0, 6.0)]
    words = [Word("so", 1.1, 1.3), Word("anyway", 1.4, 2.1), Word("I", 5.0, 5.2), Word("think", 5.3, 5.9)]
    segs = segments.merge_vad_and_words(regions, words)
    assert segs == [Segment(1.0, 2.0, "so anyway", 2), Segment(3.0, 3.4, "", 0), Segment(5.0, 6.0, "I think", 2)]


def test_merge_vad_and_words_lagging_word_attaches_to_nearest_region():
    # whisper "Okay," at 18.08-18.48 for the region 17.64-18.01 (GT clip V00_S0314_I00000309_P0421_c02)
    segs = segments.merge_vad_and_words([(17.64, 18.01)], [Word("Okay,", 18.08, 18.48)])
    assert segs == [Segment(17.64, 18.01, "Okay,", 1)]
    # farther than the gap: kept as a word-only segment, region stays wordless
    segs = segments.merge_vad_and_words([(17.64, 18.01)], [Word("Okay,", 18.6, 19.0)])
    assert segs == [Segment(17.64, 18.01, "", 0), Segment(18.6, 19.0, "Okay,", 1)]


def test_merge_vad_and_words_merges_close_regions_and_handles_empties():
    segs = segments.merge_vad_and_words([(1.0, 1.4), (1.6, 2.0)], [Word("yeah", 1.0, 1.3), Word("yeah", 1.7, 2.0)])
    assert segs == [Segment(1.0, 2.0, "yeah yeah", 1)]
    assert segments.merge_vad_and_words([], []) == []
    assert segments.merge_vad_and_words([], [Word("hi", 0.0, 0.2)]) == [Segment(0.0, 0.2, "hi", 1)]
    assert segments.merge_vad_and_words([(2.0, 2.0), (0.0, 1.0)], []) == [Segment(0.0, 1.0, "", 0)]
    blank = segments.merge_vad_and_words([(0.0, 1.0)], [Word("  ", 0.1, 0.2)])
    assert blank == [Segment(0.0, 1.0, "", 0)]
