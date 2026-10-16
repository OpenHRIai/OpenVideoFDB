# WS2 — Mining the 11 dynamics without human annotation

**Goal:** turn Seamless interaction pairs into candidate clips per dynamic,
verify with a VLM, spot-check in a tiny review page, emit `manifest/ovfdb_v0.jsonl`.
**Depends on:** WS1. **Est.:** 5 h over two days.
**Files:** `ovfdb/mine/dialogue.py`, `ovfdb/mine/nonverbal.py`,
`ovfdb/mine/verify.py`, `ovfdb/mine/clip.py`, `ovfdb/mine/prompts.py`,
`ovfdb/review/app.py`, `tests/test_mining_rules.py`.

## Definitions (both participants' VAD + transcript are available)
A = the participant who becomes the **user**, B = the partner (becomes human-GT
"agent"). Backchannel = utterance `< 1 s` and `< 2 words`. Turn = maximal run of
VAD regions of one speaker separated by `< 0.6 s` of silence and not overlapped
by a non-backchannel utterance of the other.

## Day 1 — dialogue-channel dynamics (`dialogue.py`, pure functions over segments)
| Dynamic | Bucket | Rule (user = A unless noted) | Window |
|---|---|---|---|
| Pause Handling | P | inside A's turn: silence ≥ 1.0 s (≤ 4 s), A resumes, B silent throughout + 1 s after | the silence |
| Verbal Backchanneling | G | B emits a backchannel fully inside A's turn, A keeps talking | B's backchannel ±0.3 s |
| Verbal Interruption | G | user = B's partner... i.e. **agent is the one being interrupted**: A starts a non-backchannel utterance while B is speaking; B stops within 1.5 s; A holds ≥ 2 s | A's onset → B's offset |
| Turn-taking | G | B's turn ends, gap 0.2–1.5 s, A's turn starts, no overlap; then A ends and B replies (handoff is A→B scored) | A's turn end → B's onset |
| Laughter | P/G | laughter detector on A's audio (try `laughter-detection` or YAMNet "Laughter" class ≥ 0.5 for ≥ 0.4 s) and B was speaking in the previous 3 s (P) / A laughs while speaking own turn and B reacts (G) | laugh |

Clip boundaries (`clip.py`): start = beginning of the turn 1–3 turns before the
window (prefer 2), end = end of the next turn after the window or window+8 s,
whichever is first; cap total at 60 s. Record `agent_speaks_first` = B is
speaking at clip start or B must speak before A's cue (Verbal Interruption,
NV Backchanneling-P, Adaptor, NV Interruption).

## Day 2 — nonverbal dynamics (`nonverbal.py`, movement features + 3P-V + VLM)
| Dynamic | Bucket | Candidate signal |
|---|---|---|
| Nonverbal Backchanneling | P (A nods while B speaks) / G (B nods while A speaks) | head-pitch oscillation ≥ 2 cycles within 1.5 s from `head_encodings`/`alignment_head_rotation` while own VAD silent and other speaking |
| Face Emotion Display | P / G | `emotion_scores`/`emotion_valence` z-score spike ≥ 2 lasting ≥ 0.5 s |
| Emotion Matching | G | A's affect spike followed within 2 s by B's same-sign valence change |
| Gaze Avoidance with Pause | P | Pause Handling candidate ∧ `gaze_encodings` distance from A's own median ≥ k during the pause |
| Adaptor Handling | P | 3P-V text regex `(rub|scratch|touch|adjust|fidget|hair|face|glasses|neck)` on A while A is speaking |
| Nonverbal Interruption | P | B speaking, A silent, A's motion energy spike (`alignment_translation`/keypoints) then A starts speaking within 2 s; VLM must confirm a hand-raise/head-shake |

## VLM verification (`verify.py`)
For each candidate: composite the trimmed clip side-by-side (A left, B right)
at 480p, send to Gemini Flash with the dynamic definition from
`docs/protocol.md` §1 and the candidate window; ask for JSON
`{"is_dynamic": bool, "confidence": 0-1, "start_s", "end_s", "notes"}`.
Keep `is_dynamic && confidence ≥ 0.7`; adopt the VLM's refined window if it
moves by < 1.5 s. Log everything to `data/mining/verify.jsonl`.

## Review page (`review/app.py`)
Streamlit or Flask: iterate candidates per dynamic, play SBS clip with window
markers, buttons accept / reject / relabel. Writes `data/mining/review.jsonl`.
Budget: ~3 per dynamic, 30–60 min of human time total.

## Prompts (`prompts.py`)
Implement F.4: transcript of both channels up to the window → GPT-4o →
`system_prompt` ending in "Start speaking now to begin/continue the conversation"
when `agent_speaks_first`, else a short persona + context prompt. Also produce
`av_caption` (Gemini Flash, full clip, both panes) for the judge.

## Output
`manifest/ovfdb_v0.jsonl`, one `Sample` per line (see schema), media under
`data/clips/<clip_id>/{user.wav,user.mp4,partner.wav,partner.mp4}`. Targets:
day 1 ≥ 50 clips over 5 dynamics; day 2 ≥ 100 clips, ≥ 8 per dynamic, each
sample appearing in the buckets Table 8 allows.

## Acceptance
- `tests/test_mining_rules.py`: synthetic VAD/transcripts hit each dialogue rule.
- `uv run ovfdb mine --dynamics pause_handling,verbal_backchanneling --limit 20`
  produces candidates + verify log without manual steps.
