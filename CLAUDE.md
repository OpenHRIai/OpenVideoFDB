# OpenVideoFDB — session guide

Open reimplementation of VideoFDB (arXiv 2605.30256): a benchmark for full-duplex
audio-visual conversational agents. One maintainer, built over ~2 days across many
Claude sessions running in sequence and in parallel.

## Read first, every session
1. `PLAN.md` — the overall plan and the workstream dependency graph.
2. `STATUS.md` — what is done / in progress / blocked. **Claim your workstream
   there before starting and update it before you stop.**
3. `plans/WS<n>-*.md` for the workstream you are working on. It is the spec:
   deliverables, interface contract, acceptance test.
4. `docs/protocol.md` — the VideoFDB protocol (taxonomy, timing classes, judge
   payloads, output schemas). `docs/data-sources.md` — dataset layouts and URLs.
   Verbatim paper text (CC BY 4.0) is in `docs/reference/`; grep it for exact
   rubric wording instead of re-fetching arXiv.

## Rules for parallel sessions
- One workstream per session. Touch only the files your WS spec lists plus
  `STATUS.md`. If you must change a shared contract (`ovfdb/schema.py`,
  `ovfdb/harness/base.py`), note it at the top of `STATUS.md` under "Contract
  changes" with the date so other sessions rebase.
- Shared contract = `ovfdb/schema.py`. All data (NVIDIA or Seamless-derived)
  is normalised to `Sample`; all agent runs produce `AgentRun`; all scoring
  consumes those two. Don't invent parallel representations.
- Commit on your WS branch or on `main` with small commits; prefix messages
  with the WS id, e.g. `WS2: pause-handling candidate finder`.
- Data never goes in git: `data/`, `runs/`, `*.mp4`, `*.wav`, `*.parquet`
  are ignored. The NVIDIA dataset is gated and non-redistributable — only
  the loader lives here. Seamless-derived clips are CC-BY-NC and may be
  published with attribution.
- Secrets in `.env` (see `.env.example`), loaded with `python-dotenv`.

## Stack
- Python 3.12, `uv` for env/deps (`uv sync`, `uv run ...`), `ruff` for lint.
- `ffmpeg`/`ffprobe` on PATH. `faster-whisper` for ASR. `google-genai`,
  `openai`, `anthropic` SDKs for agents/judges.
- CLI entry: `uv run ovfdb <command>` (see `ovfdb/cli.py`).
- Tests: `uv run pytest`. Timing metrics and mining rules must have unit
  tests with synthetic segment lists; nothing else needs tests on day 1.

## Conventions
- All times are seconds as `float`, relative to clip start (t=0 = first
  user audio sample sent to the agent). Never wall-clock in stored data.
- Audio stored as 16 kHz mono PCM16 WAV unless a provider needs otherwise.
- Clip ids: Seamless `file_id` + `_c<nn>` for the clip index within that
  interaction; NVIDIA ids pass through unchanged.
- Keep functions pure where possible (segment lists in, numbers out) so
  they can be tested without media.
