# WS4 — ASR + deterministic timing metrics

**Goal:** turn `agent.wav` into word-timestamped segments and compute the
App. C.2 timing metrics. **Depends on:** WS0. **Unblocks:** WS5. **Est.:** 3 h.
**Files:** `ovfdb/score/asr.py`, `ovfdb/score/segments.py`,
`ovfdb/score/timing.py`, `tests/test_timing.py`.

## ASR (`asr.py`)
- `transcribe(wav_path) -> list[Word]` with `faster-whisper` (`word_timestamps=True`,
  model `small.en` default, `large-v3` flag). Optional backend `deepgram`
  (port of fugubook `DeepgramSTT`) behind the same function.
- `words_to_segments(words, gap=0.5) -> list[Segment(start, end, text, n_words)]`.
- `is_backchannel(seg) = seg.dur < 1.0 and seg.n_words < 2` — note the paper
  says "< 2 words", i.e. single-word only. Keep as constants.

## Timing (`timing.py`) — pure functions, no I/O
Implement exactly `docs/protocol.md` §4:
```python
def timing_class(dynamic_type, bucket) -> TimingClass | None
def overlap_summary(segs, ds, de) -> OverlapSummary   # total in-window s, per-segment overlaps, PRE/IN/POST activity %
def yield_analysis(segs, ds, de, pre_s=5.0, post_s=14.0) -> YieldAnalysis  # for YIELDING roles; produces the verdict text block (F.2.3)
def evaluate(segs, ds, de, cls, agent_speaks_first) -> TimingResult(passed: bool, takeover: int, latency_ms: float|None, details: dict)
def aggregate(results) -> {dynamic: {"tor_alignment": %, "median_latency_ms": ...}, "overall": ...}
```
Rules:
- stay-silent: pass if in-window speech ≤ 1.0 s OR every overlapping segment is a backchannel.
- continue-speaking: pre-activity (3 s before ds) ≥ 30 % ⇒ require in-window activity ≥ 50 %; else vacuous pass.
- yield-required: latency = end of the segment overlapping ds (or the last one ending before ds) − ds; pass if ≤ 1.5 s. No agent speech near ds ⇒ fail with `details.trivially_silent=True`.
- smooth-handoff: latency = first onset after ds − ds (0 if speaking at ds); pass if onset ≤ de.
- backchannel-produced: pass if ≥ 1 in-window backchannel and no in-window non-backchannel segment.
- `takeover` = 0 if in-window output is silence/backchannels only, else 1.

## Acceptance
`tests/test_timing.py` covers each class with ≥ 3 synthetic cases (pass,
fail, edge), including the vacuous continue-speaking case and the
"already speaking at ds" handoff. `aggregate` on the synthetic set returns the
expected percentages.

## CLI
`uv run ovfdb score-timing runs/<name>` → `runs/<name>/<clip>/timing.json` + `runs/<name>/timing_summary.json`.
