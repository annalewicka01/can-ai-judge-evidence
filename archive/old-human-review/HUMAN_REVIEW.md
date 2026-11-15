# Independent human review: ready, not performed

All current substantive assessments are **agent reviews**. No clinician,
epidemiologist or service reviewer has validated these keys or action codes.
Separate agents are not substitutes for independent professional expertise.

## Key review first

Give each reviewer only:

- `key-packets.json` — 20 masked papers; no historical labels or model answers.
- A copy of `human-key-reviewer-1.json` or `human-key-reviewer-2.json`.
- The common question: what narrow claim does the evidence support, and how
  much assurance does this paper justify for the proposed deployment?

Do not provide `private-*`, existing reports, scores, agent reviews or action
answers until both key reviews are locked. Identify reviewer qualifications,
conflicts, involvement in case creation and prior exposure to the results.

For each paper, state the bounded claim, assess it as supported/unsupported/
contradicted/unclear, and assess broad assurance as sufficient/insufficient/
contestable. Give acceptable assurance categories (substantial/reasonable/
limited/no_assurance), specific concerns, exact evidence quotations and reasons.
Do not assume that meeting a local numeric criterion establishes all deployment
risks, or that useful evidence must establish zero risk.

## Action review second

After locking keys, use the 240-answer primary comparison selected in
`human-action-reviewer-*.json`. Obtain matching IDs from `action-packets-all.json`
and paper text via `key_id` in `key-packets.json`. The complete file contains
873 answers; only the selected 240 were included in current agent content coding.

Use the rubric in `../../experiments/discrimination/EXISTING_OUTPUTS_ANALYSIS.md`.
Read the whole recommendation, not just the decision label. Distinguish evidence
required before expansion from monitoring after launch. Score ownership, timing,
stopping rules, feasibility evidence, burden and residual uncertainty separately.
An extra request is not automatically unnecessary; absence of resource evidence
is not proof of infeasibility. Prompt/model masking is imperfect because answer
wording can reveal the prompt.

## Preserve and adjudicate

Keep the supplied empty forms unchanged; save completed copies under new names.
Freeze both reviewers' independent ratings before discussion. Report agreement
before adjudication, preserve each original rating and record any adjudication
with a reason. Unresolved preference-dependent judgments remain unresolved.
Do not overwrite historical keys or silently replace original benchmark scores.

No recruitment, data sharing, payment or human coding has been initiated.
