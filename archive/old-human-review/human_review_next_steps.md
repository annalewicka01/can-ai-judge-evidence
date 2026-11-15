# Human review: proposed next steps

14 November 2026. **Planning note; no recruitment, coding or model runs done.**

## Evidence status

This agent's web searches and primary-page opens returned empty tool outputs.
No new GRRAS/HEDS source was independently verified, and no web citation IDs
are supplied. Do not cite either guideline as having validated the procedure
below. This is our proposed operationalization of the existing
[frozen expansion protocol](../experiments/policy_expansion/PROTOCOL.md), not a
source-validated scale. Previously inspected clinical reporting sources and
their limits remain in [EXPERIMENT_REDESIGN.md](../archive/EXPERIMENT_REDESIGN.md).

## 1. Recruit and separate responsibilities

- Obtain two reviewers able to understand both clinical evidence and service
  operations; ideally one clinician/epidemiologist and one clinical-service
  reviewer with evaluation experience.
- They independently score the same components. Do not treat unlike expertise
  as interchangeable: route unresolved technical questions to a qualified
  adjudicator, preserving the original disagreement.
- Document qualifications, involvement in case authoring and conflicts.
  Prefer reviewers who did not create these cases or inspect arm-level results.

## 2. Prepare the packets

- Reuse the 30 existing human-coding packets; give new random packet IDs and
  remove model/prompt-arm identifiers, aggregate scores and agent judgments.
- Include the dossier, exact model-visible records and staged outputs. Keep
  author-only facts separate so reviewers cannot penalize an answer for not
  knowing evidence it never received.
- Prepare multiple defensible evidence requests/actions, not a single required
  document pair or a universal approve/reject policy answer.
- Stage discovery scoring before revealing later records/answers to the coder.
  Otherwise later information can contaminate assessment of initial recognition.
- Note masking limitations: wording may reveal the targeted prompt; this is
  arm-masked grading, not a guarantee of perfect blinding.

## 3. Calibrate before grading the expansion

- Use three selected conversations from the *historical development runs*,
  excluded from the 30 expansion conversations being graded. These are
  calibration examples—not fresh experimental holdouts.
- Reviewers first score independently, then discuss ambiguities and revise
  anchors. Cover missing evidence, adequate evidence and an adverse finding
  where available across the historical versions.
- Freeze the rubric before opening the remaining evaluation packets. If a
  material rubric change later becomes necessary, record it and recode every
  affected answer; do not change only the awkward answer's score.

## 4. Score separate constructs

Retain the protocol's 0/1/2 discovery scale: misses issue / names concern /
links concern to useful evidence or appropriately accepts adequacy.

Develop similarly explicit anchors for evidence use, updating and verification
feasibility. Keep unsupported assurances, invented facts/numbers and unnecessary
escalation as separately reported flags, with a cited response excerpt and
reason. Record not-applicable or insufficient-information cases explicitly.
Do not silently average these different constructs into one 'safety' score.

## 5. Preserve disagreement and adjudicate

- Lock both reviewers' first-pass ratings before discussion.
- Report per-component rating distributions, exact agreement and all important
  disagreements. If adding a chance-corrected agreement statistic, prespecify
  its variant, weights and treatment of missing ratings with statistical advice.
- Report agreement *before* adjudication, then retain a separate adjudicated
  field, reason and any unresolved preference-dependent disagreement.
- Agreement at a ceiling is not proof that the rubric measures useful policy
  judgment; inspect concrete examples and whether components discriminate.
  This is a logical limit on what agreement establishes, not an empirical
  finding from newly collected human ratings.

## Deliverable and stopping point

Deliver a dated rubric, 60 independent packet reviews, disagreement table and
separate adjudication record. Preserve raw outputs and existing agent judgments.
Use this to improve measurement before launching the proposed evidence-access
comparison. Human coding is not yet authorized for execution/recruitment by this
planning note and does not itself test benefit to real committee decisions.
