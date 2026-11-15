# A quick check of the answer keys

Two reviews:

1. **A joint human review.** A doctor with 30 years' experience (a neonatologist, so outside these specialties) and the project owner (MPhil in computational biology, not a clinician) review together. The owner translates the papers into Polish as they go.
2. **Claude Opus 5.5**, the same model family as the earlier LLM judge.

This is a small fairness check done over one weekend, not a clinical validation study.

Work through FORM.md and the files in papers/, on screen or printed. Each file contains one pair. Four to six pairs is enough to help. Keep answer_key.json, responses/opus_raw/ and RESULTS.md away from reviewers until they finish.

F3b replaces the original F3, which is omitted. The text is frozen here; running code is not needed to read it. Passage markers preserve where the differing paragraphs belong. X/Y order uses a fixed seed recorded only in answer_key.json.

Copy responses/TEMPLATE.csv to joint.csv and fill it in.

From the repository root:

```
.venv/bin/python review/llm_review.py
.venv/bin/python review/score.py
.venv/bin/python -m pytest review -q
```

The live command reads CAJE_API_KEY (or OPENAI_API_KEY) and CAJE_ENDPOINT. The gateway listed the reviewer model as anthropic_claude_opus_5_5. Sampling is left at the gateway default. Running again makes another paid review.
