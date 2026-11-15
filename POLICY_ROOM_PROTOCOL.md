# Policy evidence room — exploratory engineering protocol

Version 1; authored 14 November 2026, before its live outputs.
V2 development-only addendum below was written after the v1 pilot and before v2 calls.

## Question and scope

Can an AI policy reviewer identify what a triage evaluation establishes, obtain
useful records, and recommend proportionate verification? This is a synthetic
decision-support experiment, **not clinical validation or a patient intervention**.
The triage system and its records are fixed authored inputs, not another live AI.

The previous scaffolded experiment is preserved. Its 72 responses all passed;
the open-brief development pilot's six responses also passed. Those results
motivate changing the task, not weakening the model or tuning until a prompt wins.

## Research basis

See `EXPERIMENT_REDESIGN.md` for inspected sources, interpretation and limits.
Case metadata maps each workflow to those sources; all organizations, numbers,
audit findings and policies in this experiment are invented.

- NICE HTG746 [S1]: conditional adoption, pathway and population safeguards.
- ACCESS [S2]: screening completion is not specialist follow-through.
- CXR silent-trial institutional abstract [S3]: reference-label quality; no claim
  of demonstrated live deployment benefit. Abstract only.
- Obermeyer [S4]: utilization/cost is not interchangeable with clinical need.
- DECIDE-AI [S5], STARD-AI [S6]: workflow, ascertainment, applicability, reference
  standards. Reporting guidance does not validate our prompting intervention.
- SDBench official site [S7]: staged information acquisition; **no fabricated
  answers to evidence requests**.

No new medical research claims are needed for this implementation. Official
OpenAI Structured Outputs documentation was inspected on 14 November 2026 for
schema/error handling. Requests reuse the existing Responses-compatible gateway.

## Design

Two development dossiers; six evaluation dossiers (three workflow families).
One fixed model/settings; three arms: ordinary, generic critique, observability.
One repetition: 6 development + 18 evaluation conversations, 3 calls each.
This small descriptive experiment is not powered for a superiority claim.

1. **Discovery:** a committee dossier; only recommendation and justification.
   No missing-patient checklist, audit menu or scoring key is shown.
2. **Acquisition:** six source-document titles become visible. Select zero to two
   documents, with a free-text question for each. Return exact authored documents.
   All arms have identical access. IDs, ordering and costs are fixed within case.
3. **Decision:** assess the board's exact claim as `supported`, `not_established`
   or `contradicted`; recommendation, justification, verification plan and what
   would change the decision. This is not a binary approve/reject task.

Initial and final outputs use fresh API requests with explicit visible history;
no hidden reasoning state or provider conversation state is carried forward.
All stages use the same arm, model, reasoning effort and output cap. No external
tools; no case requires exact sample-size calculation. This is not an arithmetic
comparison with the historical benchmark.

**Practical deviation from the proposal:** select documents after discovery,
instead of using a human free-text request mapper. This is reproducible and
removes mapper discretion, but titles cue acquisition and one batch prevents
adaptive second requests. Conclusions about unprompted recognition use stage 1
only. Requests for unavailable evidence receive explicit unavailable-record
content; the harness never fabricates patients or test results.

## Cases and controls (hidden from reviewer)

| Case | Split | Mechanism | Evidence after useful acquisition |
|---|---|---|---|
| P01 | development | CXR AI labels share a reference failure | claim contradicted |
| P02 | development | discharge audit; adequate bounded benefit | claim supported |
| Q01 | evaluation | skin triage, selected verification | claim not established |
| Q02 | evaluation | skin triage, adequate scoped assurance | claim supported initially |
| Q03 | evaluation | eye screening, delayed/unavailable care ascertainment | claim not established |
| Q04 | evaluation | eye screening, independently documented care failure | claim contradicted |
| Q05 | evaluation | metabolic testing, proxy and selective labels | claim not established |
| Q06 | evaluation | metabolic testing, representative but imprecise audit | claim not established |

Q06 deliberately replaces a second favorable control with an underpowered
control: missing-patient rhetoric must not substitute for precision analysis.
Q02 is already sufficient for its narrow claim; requesting more is optional,
and a proportionate positive recommendation must not require an arbitrary RCT.
Adequate measurement can reveal an unsuccessful policy (P01/Q04).

## Prespecified measurements

Mechanical, auditable outputs (not a validated holistic quality score):

- Completed conversations, format errors, transport errors, actual tokens.
- Number and identity of selected documents; acquisition of a decisive record
  where it is necessary for the claim's classification.
- Final claim label versus the **available-evidence** key, not secret world truth.
  Without a decisive record a reviewer must not guess its hidden result.
- Final claim label versus the full-bank key, separately reported. Agreement
  with full-bank truth without evidence is not earned evidence-grounded success.

Agent-coded, provisional qualitative outcomes, with quotations:

- Discovery 0/1/2: misses specific issue / notices it / links it to useful
  evidence or correctly accepts adequate evidence.
- Feasible verification: names population/outcome/route, respects known limits;
  states unresolved inputs rather than inventing sample sizes or thresholds.
- Unsupported claims, unwarranted escalation, appropriate updating, preservation
  of narrower real benefits. Document uncertainty and alternative valid actions.

An agent cannot supply the proposed two independent human coders. Export shuffled
arm-masked coding packets; leave human scores empty. Automated labels and our
qualitative audit support an engineering report only. No clinical or publishable
prompt-superiority claim without independent domain review/double coding.

## Engineering loop and stopping rule

Freeze source, bank, protocol, prompt/schema, settings, seed and job order before
development calls. Never edit completed-run files. Retain every failure/retry.

1. Run offline invariants and fake-transport integration tests; then six live
   development conversations. Same settings across arms; no content retries.
2. Gate expansion on functioning transport, no answer leakage, coherent keys,
   and at least one **substantive** error, acquisition difference affecting
   available evidence, or incorrect updating/over-escalation. Longer prose alone
   is not interesting. A null arm difference with a shared failure is interesting.
3. If gate passes, run all six evaluation dossiers once across all three arms.
   No selection of favorable cases. Run complete offline suite and replay audit.
4. If gate fails because everything is adequate and saturated, allow **one**
   redesign using development cases only (e.g. competing demands or less explicit
   source aggregation). Record its rationale/version before calls. Do not alter
   evaluation dossiers based on their outputs. If it still saturates, report the
   ceiling rather than keeping a paid search open until something fails.
5. If a harness/key error is found, preserve affected results, correct it with a
   regression test, issue a new freeze, and clearly mark invalidated observations.
   An outcome-driven rubric change is exploratory reanalysis, never a silent fix.

Default cap: 24 conversations / 72 successful stage calls; up to two transport
attempts per stage. One permitted development redesign adds at most 6 conversations
/18 successful calls. Max output 6000 tokens/call; reasoning medium; no temperature
submitted. Dollar cost unknown at gateway; report token usage, not invented prices.
Use the existing `openai_gpt6_astra` alias and explicitly disclose snapshot drift.
Network access/credential failure is a blocker, not permission to simulate results.

## Interpretation

Unit of diversity is three evaluation families, not eighteen independent clinical
settings. Counts only; no p-value fishing, prompt ranking on tiny differences, or
real-world safety conclusions. Sequential differences combine information choice
and interpretation. A future fixed-information replay can isolate interpretation;
a real human committee study is needed to establish usefulness to policymakers.

## V2 development-only addendum

The v1 live pilot completed with six correct final labels, all designated records
acquired, and no substantive failure found by the provisional agent review.
Therefore it did not pass the expansion gate. See `POLICY_ROOM_ITERATIONS.md`.

The one permitted redesign splits decisive facts across two records in each
development case, removes prewritten verdicts, varies catalogue positions and
adds realistic competing operational concerns. P01 now requires clinical-review
findings plus actual queue assignments (R4 and R6). P02 requires the statistical
analysis plus the prior acceptance criterion (R2 and R4). One record alone leaves
the exact claim unestablished. Clinically meaningful findings and assignments
use shared examination identifiers, not an unexplained code-guessing exercise.

Evaluation dossiers and their evidence/rubrics are unchanged. Source/API code,
prompt arms and settings are unchanged. The second pilot has six conversations;
the same gate and the original overall call cap apply. If it saturates, stop
live expansion rather than inventing an advantage. This is a joint development
redesign, not an isolated causal test of document order or evidence fragmentation.
