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
3. **Manifest-only publication (decision 2026-10-15).** Publish
   `manifest/ovfdb_v0.jsonl` (Seamless file_ids, raw t0/t1, windows, labels,
   our system prompts and AV captions) to GitHub and as an HF dataset
   `<org>/open-videofdb`, plus `ovfdb mine --from-manifest` that re-fetches
   from Meta's public mirror and trims locally (WS1 `to_sample` is
   deterministic). Do NOT re-host Seamless media: CC-BY-NC 4.0 would permit
   it, but it adds participant-privacy exposure for no benefit (NVIDIA shows no
   clip samples for the same reason). README card: CC-BY-NC 4.0 for the
   manifest/captions, attribution to Meta Seamless Interaction, note that the
   NC restriction applies to all derived data; code stays MIT.
   Script: `scripts/publish_hf.py --repo <org>/open-videofdb`.
4. GitHub repo public; tag `v0`.

## Acceptance
- A fresh clone + `uv sync` + the README commands reproduce the GT/random
  rows from the published manifest.
