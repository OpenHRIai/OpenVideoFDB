# STATUS — shared progress board

Update this file at the start (claim) and end (report) of every session.
Keep entries terse. Dates are absolute (YYYY-MM-DD).

## Contract changes
_Record any edit to `ovfdb/schema.py` or `ovfdb/harness/base.py` here so other sessions rebase._
- 2026-10-15 — initial schema (WS0).

## Board
| WS | Status | Session / owner | Last update | Notes / blockers |
|----|--------|-----------------|-------------|------------------|
| WS0 scaffold | done | session 1 | 2026-10-15 | schema, stubs, docs, plans |
| WS1 seamless data | todo | — | — | `ovfdb/data/seamless.py` has URL builder + filelist; fetch/trim/pairing to do |
| WS2 mining | todo | — | — | needs WS1 |
| WS3 harness (Gemini Live) | todo | — | — | |
| WS4 scoring: ASR + timing | todo | — | — | |
| WS5 judge + calibration | todo | — | — | needs WS4 |
| WS6 providers: OpenAI RT, Tavus/Anam, gen judge | todo | — | — | needs WS3, WS5 |
| WS7 NVIDIA adapter | todo | — | — | **request HF access first** (gated, manual approval) |
| WS8 report + publish | todo | — | — | last |

## Decisions log
- 2026-10-15 — Perception bucket first; generation is a stretch (needs video-out agents).
- 2026-10-15 — Seamless `naturalistic` split only (improvised uses actors).
- 2026-10-15 — ASR: faster-whisper (paper: Parakeet 0.6B v2). Judge: GPT-4o primary (as paper) + Claude second judge for agreement. AV captioner: Gemini Flash (paper: Qwen3.5-397B + Nemotron-Omni).
- 2026-10-15 — Clip time origin = first user audio chunk sent to agent.

## Open questions
- Which provider API keys are available? (fugubook `.env` has TAVUS/ANAM/OPENAI/GOOGLE per survey.)
- NVIDIA access approved? (date requested: ____ )
