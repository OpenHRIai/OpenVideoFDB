# Judge rubrics

Verbatim copies of the VideoFDB judge prompts, Appendix F.5 (perception) and F.6 (generation) of
*VideoFDB: Evaluating Full-Duplex Vision-Speech Capabilities in Conversational
Agents* (arXiv 2605.30256v2), licensed CC BY 4.0. Extracted from
`docs/reference/videofdb_paper_arxiv_2605.30256v2.txt` (second occurrence of
each heading); the only edits are LaTeXML artefact fixes: ``‘‘ ’’`` → `"`,
`---` → `—`, `--` → `–`, doubled `> >` → `>`, `→ \to` → `->`, curly
apostrophes → `'`, and line breaks restored at bullets / paragraph starts.

| File | Paper section | Served as |
|---|---|---|
| `perception_preamble.txt` | F.5.2 Shared system preamble (`_PREAMBLE`) | system prompt, every axis |
| `fluency.txt` | F.5.3 Universal Fluency axis (`_FLUENCY`) | `fluency` |
| `pause_handling.txt` | F.5.4 (P) Pause Handling | `conversational_flow` |
| `gaze_avoidance_with_pause.txt` | F.5.4 (P) Gaze Avoidance with Pause | `conversational_flow` |
| `nonverbal_backchanneling.txt` | F.5.4 (P) Nonverbal Backchanneling | `conversational_flow` |
| `nonverbal_interruption_flow.txt` | F.5.4 (P) Nonverbal Interruption (conversational_flow) | `conversational_flow` |
| `nonverbal_interruption_grounding.txt` | F.5.4 (P) Nonverbal Interruption (semantic_grounding) | `semantic_grounding` |
| `face_emotion_display.txt` | F.5.4 (P) Face Emotion Display (also Emotion Matching) | `semantic_grounding` |
| `laughter.txt` | F.5.4 (P) Laughter | `semantic_grounding` |
| `adaptor_handling.txt` | F.5.4 (P) Adaptor Handling | `semantic_grounding` |

Dispatch lives in `ovfdb/score/judge.py` (`CATEGORY_AXES`). The system prompt for
one call is `perception_preamble + (fluency | category rubric) + output-schema
reminder`; the user message follows the F.5.1 template (`build_user_message`).

## Generation judge (F.6, `generation_*.txt`)

Same extraction and artefact fixes as above. Served by `ovfdb/score/judge_generation.py`
(`GENERATION_RUBRICS`): system prompt = `generation_preamble` + (universal axis | category
rubric) + output-schema reminder (universal `{analysis, rating, reasoning}` for the two
universal axes, decomposed `{analysis, cue_produced, cue_timing, cue_appropriateness,
reasoning}` + the F.3 consistency rules for the category rubrics).

| File | Paper section | Served as |
|---|---|---|
| `generation_preamble.txt` | F.6.2 Shared system preamble | system prompt, every generation axis |
| `generation_affect_match.txt` | F.6.3 Affect Match (Agent -> User) | `affect_match` |
| `generation_fluency.txt` | F.6.3 Generation Fluency | `generation_fluency` |
| `generation_laughter.txt` | F.6.4 (G) Laughter | `cue_appropriateness` |
| `generation_nonverbal_backchanneling.txt` | F.6.4 (G) Nonverbal Backchanneling | `cue_appropriateness` |
| `generation_verbal_backchanneling.txt` | F.6.4 (G) Verbal Backchanneling | `cue_appropriateness` |
| `generation_verbal_interruption.txt` | F.6.4 (G) Verbal Interruption | `cue_appropriateness` |
| `generation_face_emotion_display.txt` | F.6.4 (G) Emotion Matching; Face Emotion Display (one rubric for both dynamics) | `cue_appropriateness` |
| `generation_turn_taking.txt` | F.6.4 (G) Turn-taking | `cue_appropriateness` |
