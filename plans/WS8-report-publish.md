# WS8 — Results table, README, publish

**Depends on:** everything. **Est.:** 2 h.
**Files:** `README.md`, `results/`, `scripts/publish_hf.py`.

## Deliverables
1. `results/v0/summary.md` — Table-1 layout: rows = provider×mode (+ Human GT,
   Random), columns = Fluency / Conv. Flow / Vis. Grounding / Overall /
   TOR-Align % / median latency ms / n, with 95 % CIs. Per-dynamic table too.
   Judge-agreement table (gpt-4o vs claude, % within 1 point).
2. `README.md` — what this is, how it differs from NVIDIA's VideoFDB
   (`docs/protocol.md` §10), how to run the three commands (`mine`, `run`,
   `score`), how to add a provider (implement `Agent`), licences, citation of
   both the VideoFDB paper and Seamless Interaction.
3. HF dataset `<org>/open-videofdb` with `manifest/ovfdb_v0.jsonl`, trimmed
   clips (`clips/<clip_id>/{user,partner}.{wav,mp4}`), the AV captions and
   system prompts, README card with CC-BY-NC 4.0 + attribution. Script:
   `scripts/publish_hf.py --repo <org>/open-videofdb`.
4. GitHub repo public; tag `v0`.

## Acceptance
- A fresh clone + `uv sync` + the README commands reproduce the GT/random
  rows from the published manifest.
