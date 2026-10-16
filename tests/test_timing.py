"""Unit tests for ovfdb.score.timing (WS4). Fill in as rules are implemented.

Each timing class needs >= 3 synthetic cases (pass, fail, edge).
"""

import pytest

from ovfdb.schema import Segment, TimingClass
from ovfdb.score import timing


def seg(start, end, text="hello there friend", n_words=None):
    n = len(text.split()) if n_words is None else n_words
    return Segment(start=start, end=end, text=text, n_words=n)


def test_is_backchannel():
    assert timing.is_backchannel(seg(1.0, 1.5, "mhm"))
    assert not timing.is_backchannel(seg(1.0, 2.5, "mhm"))          # too long
    assert not timing.is_backchannel(seg(1.0, 1.5, "oh yeah"))      # 2 words is not < 2


@pytest.mark.xfail(raises=NotImplementedError, strict=True)
def test_stay_silent_pass_on_silence():
    r = timing.evaluate([seg(12.0, 15.0)], ds=5.0, de=8.0, cls=TimingClass.STAY_SILENT, clip_end=20.0)
    assert r.passed and r.takeover == 0


@pytest.mark.xfail(raises=NotImplementedError, strict=True)
def test_yield_required_latency():
    r = timing.evaluate([seg(2.0, 6.0)], ds=5.0, de=7.0, cls=TimingClass.YIELD_REQUIRED, clip_end=20.0)
    assert r.passed and r.latency_ms == pytest.approx(1000.0)
