# WS5 — LLM judge (perception) + captioner + calibration

**Goal:** port the App. F perception judge, produce AV captions, and validate
with human-GT vs random baselines. **Depends on:** WS4 (segments/overlap
summary), WS3 `human_gt.py`. **Est.:** 4 h.
**Files:** `ovfdb/score/judge.py`, `ovfdb/score/rubrics/*.txt`,
`ovfdb/score/caption.py`, `ovfdb/score/report.py`, `tests/test_judge_payload.py`.

## Rubrics (`rubrics/`)
Copy **verbatim** from `docs/reference/videofdb_paper_arxiv_2605.30256v2.txt`:
`perception_preamble.txt` (F.5.2), `fluency.txt` (F.5.3), one file per
category rubric (F.5.4): `pause_handling.txt`, `gaze_avoidance.txt`,
`nonverbal_backchanneling.txt`, `nonverbal_interruption_flow.txt`,
`nonverbal_interruption_grounding.txt`, `face_emotion_display.txt` (also used
for Emotion Matching), `laughter.txt`, `adaptor_handling.txt`. Fix the
LaTeXML artefacts (`‘‘ ’’` → `"`, `--->` → `->`).

## Payload (`judge.py`)
`build_user_message(sample, run, segs, overlap, yield_block) -> str` following
the template in `docs/protocol.md` §5. `agent_role_for(dynamic, bucket)` per
§3. `score(sample, run, axes, judge="gpt-4o") -> dict[axis, JudgeResult]`
where each call = preamble + fluency/category rubric as system, payload as
user, JSON output `{"analysis","rating","reasoning"}`; validate 0–5 int;
retry once on parse failure. Judges: `gpt-4o` (paper), `claude-sonnet-4-6`
(second judge), optional `gemini-2.5-pro`. Cache by hash of (payload, rubric,
judge) in `runs/<name>/<clip>/judge/<axis>_<judge>.json`.

## Captioner (`caption.py`)
`av_caption(clip) -> str`: Gemini Flash over the SBS video (user left, partner
right) asking for a timestamped description of speech, facial expression, gaze,
gestures, laughter for both panes. Stored on the `Sample` (`av_caption`), so
run once per clip, not per agent run. For NVIDIA samples use the shipped
`qwen_caption_full`.

## Calibration (do this before any model run)
1. Build runs `runs/gt` (`HumanGT`) and `runs/random` (`RandomPartner`, seed 0)
   on the current manifest.
2. ASR → timing → judge for both. Report per-axis means ± sd and the GT–random
   gap. Paper GT ≈ Fluency 4.5, Flow 4.5, Grounding 4.2; timing 90 % / 1400 ms.
3. Cross-judge: gpt-4o vs claude on both runs; report % within 1 point (paper
   77–89 %).
4. If GT < 3.8 on any axis or GT–random gap < 1.0, inspect payloads before
   tuning anything; the usual culprits are ASR segmenting, the overlap line,
   or caption quality.

## Report (`report.py`)
`summarise(run_dirs) -> DataFrame` per provider×mode: Fluency, Flow, Grounding,
Overall (mean of available axes), TOR-Alignment %, median latency ms, n; 95 %
bootstrap CIs (1000 resamples over clips). `--per-dynamic` variant (Table 11
style). Markdown + CSV output.

## Acceptance
- `tests/test_judge_payload.py`: payload for a synthetic sample contains the
  role line, the in-window overlap line, PRE/IN/POST partition, and the yield
  block only for YIELDING roles.
- `uv run ovfdb score runs/gt` and `runs/random` complete; summary shows a
  clear GT > random separation.
