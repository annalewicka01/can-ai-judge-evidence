# Existing-output analysis plan

14 November 2026. Retrospective exploratory analysis, authorized after inspecting
the original results. This is not a preregistration or an independent confirmation.
No new model API calls, changes to frozen keys, or resampling of responses.

## Scope

1. Two separate agent reviews of all 20 distinct iteration-2/3 papers, masked to
   historical identifiers, assigned variants, model outputs, original keys and
   arm-level results. Judge bounded claims separately from broad safety assurance.
   These are provisional agent assessments, **not independent clinical expert
   validation**. Export identical packets and empty forms for two human reviewers.
2. Content-code the complete primary ordinary-versus-targeted comparison in
   iterations 2/3: 240 answers, all three models, both repeats, both variants.
   Two agents split this census, with one shared answer per iteration/model/arm/
   variant stratum (24 duplicate assessments). Mask model, arm, old score and
   historical identifiers. Wording may reveal prompting. Lock key assessments
   before showing outputs. Export packets for all completed iterations 2–6;
   unreviewed arms/iterations must not be portrayed as content-coded.
3. Recompute descriptive family-level results, D/A joint correctness, paired
   ordinary-to-targeted transitions, repeat consistency, disputed-key exclusion
   sensitivity and leave-one-family/pathway-out contrasts. Repeated outputs are
   not independent clinical cases. Keep original scores beside every alternative.

## Action-coding rubric

- `launch_gate`: `evidence_before_expansion` (explicitly obtain relevant evidence
  before requested expansion), `operational_before_expansion` (explicit operational
  prerequisites, not the missing evidence), `post_launch_monitoring` (proceed with
  surveillance), `mixed_or_ambiguous` (timing not explicit/conflicting),
  `unconditional` (no substantive gate), `no_decision` (no recommendation).
  A defer label alone does not prove that the missing evidence is an explicit
  prerequisite. Assess recommendation plus rationale, not the label alone.
- `gap_handling`: `specific_action`, `specific_question_only`, `generic`,
  `already_resolved_concern`, `no_material_gap`, `unclear`. This describes textual
  handling, not clinical acceptability. Do not equate routine monitoring with an
  invented gap in otherwise adequate evidence.
- `owner`: `explicit_role`, `generic_accountability`, `absent`.
- `timing`: `explicit_date_or_interval`, `before_launch_only`, `vague`, `absent`.
- `stopping_rule`: `operational_trigger`, `mentioned_without_trigger`, `absent`.
- `feasibility`: `anchored_in_paper`, `not_established`, `conflicts_with_paper`.
  Silence on cost/resources is not evidence of feasibility or infeasibility.
- `extra_burden`: `none_identified`, `routine_monitoring`,
  `additional_evidence_or_delay`, `unclear`. Do not call burden unnecessary without
  a separate justification and a validated scope/key.
- `residual_uncertainty`: `specific`, `generic`, `absent`.
- One short verbatim decisive `evidence_quote`, brief `rationale`, and `uncertain`
  flag. Agents preserve disagreements; adjudication, if any, is separate.

## Human review status

Human reviewer fields remain null. No recruitment, clinician sign-off or
inter-rater human agreement is claimed. Any compatible-assurance sensitivity
using agent assessments is explicitly provisional; original key remains primary.

## Provenance and verification

Save hashes of selected result files, frozen banks and original summary; record
packet mappings separately. Verify input hashes unchanged after analysis. Tests
cover pairing, denominator handling, failures, repeat keys, exclusions, masking,
coverage and coding enums/quotes. Export machine-readable outputs and a concise
report, with all missing/unreviewed states explicit.
