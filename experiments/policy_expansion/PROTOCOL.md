# Breadth and messy-evidence expansion

14 November 2026. Written before these batches' model responses.

## Authorization and changed stopping rule

The user requested: "okay, proceed with step 1 and 2", referring to running
the six untested cases and adding messy/unavailable evidence. This prospectively
supersedes the earlier decision not to expand after two saturated development
workflows. The earlier negative gates and all outputs remain unchanged. We are
not relabelling either pilot as a positive gate.

Rationale: two easy development workflows cannot establish whether the broader
case mechanisms are informative. The new objective is a descriptive breadth and
stress test, not finding a favorable prompt difference. No human experiment or
summary-only versus evidence-access comparison is authorized in this phase.

## Fixed scope

1. **Breadth:** Q01–Q06 exactly as authored in the original bank. Three arms,
   one repetition = 18 conversations / 54 successful stage calls.
2. **Stress:** four new source-informed synthetic dossiers M01–M04. Three arms,
   one repetition = 12 conversations / 36 successful stage calls.

Freeze both banks before inspecting any new live response. Run all cases and
arms regardless of interim results. No adaptive prompt or case rewriting. The
six breadth objects must retain semantic SHA256
896d161228d4763be06b2c5a97d6a8610df4b3625bec34a1cbb0c3faa4b4c58c.

All cases retain the existing three-stage workflow: initial recommendation,
at most two of six source documents with free-text questions, final exact-claim
assessment plus verification advice. The ordinary/generic/targeted prompts,
6000-token cap, requested medium reasoning, no temperature and existing
openai_gpt6_astra gateway alias remain fixed. The alias is not an immutable
dated snapshot. Upstream triage decisions are authored, not generated live.

Transport amendment: allow three attempts per stage, rather than two, because
previous runs had transient SSL failures. Identical payloads only; never retry a
completed malformed or unfavorable answer. No content repair. Failures remain
in denominators and are separately reported. If a transport failure remains,
report it; any further recovery needs a documented, bounded exception preserving
all prior responses. No unlimited polling or resampling.

Maximum planned new successful responses: 90. Maximum ordinary HTTP attempts:
270. Report returned tokens, not invented gateway prices. Do not repeat these
batches simply because they saturate.

## New cases (private authoring key)

| ID | Workflow | Stressor | Full-bank claim assessment |
|---|---|---|---|
| M01 | skin-lesion triage | reassuring reports condition on linkage; outside outcomes unavailable | not_established |
| M02 | retinal screening | referral closure versus care completion; reconcile cohort and follow-through | contradicted |
| M03 | metabolic case-finding | fewer codes mistaken for prevention; baseline/outside outcomes unavailable | not_established |
| M04 | discharge follow-up | alarming old audit conflicts with current adequate evaluation | supported |

Cases include competing operational considerations and qualified reports, not
just longer narratives. Records never fabricate requested evidence. An explicit
unavailability notice is a valid answer. Unknowns are not coded as healthy,
non-attending or harmed unless the record supports that conclusion. Different
document titles/positions prevent a universal first-document rule.

M02 requires both cohort membership and clinical follow-through records before
rejecting the precise all-completed claim. M04's current signed evaluation is
sufficient for its narrowly scoped claim; an older report must not automatically
override it. Other policy actions can remain conditional on resources and values.

## Source grounding and synthetic status

Use the sources already independently inspected in EXPERIMENT_REDESIGN.md:
NICE HTG746 (S1), ACCESS (S2), Obermeyer (S4), DECIDE-AI (S5), STARD-AI (S6).
Their roles are pathway/conditional-adoption realism, screening versus completed
care, proxy-target criticism, and workflow/ascertainment reporting. They do not
validate these invented cases or establish an effect of our prompting method.
No scenario is alleged to describe a named product's actual failure. All patients,
counts, dates, staffing limits and contradictory records here are invented.

## Measurement and interpretation

Mechanical secondary outcomes: final label conditional on records received;
match to full-bank label; designated record-set coverage; format failures;
transport failures; number of requested records and reported tokens. A designated
record set is an authoring diagnostic, **not proof that every other request is
useless**. Especially where the initial and final keys are both not_established,
missing that set does not by itself establish poor reasoning.

Primary substantive review remains provisional single-agent coding until human
review is available. For each response inspect:

- Specific population/outcome gap or adequate ascertainment recognized.
- Which contradictory statement is resolved, and why scope/date/source matters.
- Useful acquisition or honest identification of unavailable evidence.
- Unsupported assurance, invented facts/precision, and unjustified harm claims.
- Feasible verification respecting decision time, consent and staff constraints.
- Preservation of supported narrower benefits; appropriate updating and restraint
  on adequate controls.

Use the existing 0/1/2 discovery rubric and explicit case-specific anchors.
Retain examples and borderline judgments. Do not silently award human scores or
claim inter-rater agreement; exported human-coder fields remain empty. An answer
can have the right coarse label and still fail a substantive item. Proposed
actions are not graded against a single optimal policy when preferences differ.

All counts are descriptive. Six breadth dossiers are three workflow families;
four stress dossiers overlap these settings and add one follow-up setting. Arms
are not independent clinical populations. A breadth/stress contrast changes
case content and cannot identify a causal effect of messiness. Known breadth
catalogue/verdict cues remain limitations. Report nulls and adverse differences.

## Reproducibility

The isolated runner reuses the unchanged policy_room stage generator, decoder,
scorer and replay code. Its manifest records explicit user-authorized expansion,
not a fabricated successful pilot gate. A freeze includes exact source, protocol,
both banks, runtime, settings and seeded job order. The old frozen experiments
are not edited. New output directories are exclusive-create.
