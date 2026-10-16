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
| WS1 seamless data | done | agent (session 1) | 2026-10-15 | fetch/movement/trim/to_sample/quality gate; 14 tests incl. network. Movement features absent for all annotated nat/test files (see data-sources.md) |
| WS2 mining | todo | — | — | needs WS1 |
| WS3 harness (Gemini Live) | in progress | agent (session 1) | 2026-10-15 | no GOOGLE_API_KEY yet: live smoke test deferred; |
| WS4 scoring: ASR + timing | in progress | agent (session 1) | 2026-10-15 | |
| WS5 judge + calibration | todo | — | — | needs WS4 |
| WS6 providers: OpenAI RT, Tavus/Anam, gen judge | todo | — | — | needs WS3, WS5 |
| WS7 NVIDIA adapter | blocked (external) | — | 2026-10-15 | access requested 2026-10-15, awaiting approval; **not on the critical path** — all other WS run on Seamless |
| WS8 report + publish | todo | — | — | last |

## Decisions log
- 2026-10-15 — Perception bucket first; generation is a stretch (needs video-out agents).
- 2026-10-15 — Seamless `naturalistic` split only (improvised uses actors).
- 2026-10-15 — ASR: faster-whisper (paper: Parakeet 0.6B v2). Judge: GPT-4o primary (as paper) + Claude second judge for agreement. AV captioner: Gemini Flash (paper: Qwen3.5-397B + Nemotron-Omni).
- 2026-10-15 — Clip time origin = first user audio chunk sent to agent.

## Open questions
- Which provider API keys are available? (fugubook `.env` has TAVUS/ANAM/OPENAI/GOOGLE per survey.)
- NVIDIA access: requested 2026-10-15, pending. Non-blocking.
