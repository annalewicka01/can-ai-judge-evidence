# COVID illustration: compact protocol

14 November 2026. **Run complete:** freeze `b860927c…`, 8/8 completed; grades in
`results/covid-grading/grades.json` (agent-graded, author confirmation pending; status line edited after freeze; protocol body unchanged). Replaces the earlier transfer-study
specification. The user chose a short illustration over a human-comparator study.

## Purpose and claim boundary

Show, with one concrete example, that the report's distinction between evidence
discrimination and proportionate action also appears on COVID policy evidence.
It is an illustration, not a finding:
- no human comparison;
- no statistics;
- no change to existing scores or conclusions.

Report addition: one section in `DISCRIMINATION_REPORT.md`, at most 250 words.
It covers what the pair varied, what each model concluded, and how that maps to
the existing distinction. State the design limits in that section.
Fixed before outputs: surveillance is the report example whatever its result;
masking goes in the supplement, with a one-line mention in the section. Packets,
outputs and grades stay in this directory.

## Material

Two matched pairs, selected before any output:

| Pair | Stronger | Weaker | Evidence feature |
|---|---|---|---|
| Surveillance (worked example) | C17 | C42 | Scheduled follow-up swabs vs. follow-up via changing referral rules |
| Community masking | C36 | C94 | Coverings varied among others (source control) vs. among the measured passengers |

The packets are adapted synthetic papers. Source ledgers are in `sources/`; draft
keys are in `keys/`. The care-home (C08/C61) and schools (C23/C75) drafts are
kept but unused. Neither may be added after outputs are seen.

## Reviewer task

> Review this adapted synthetic committee paper using only the supplied
> information. Do not search or consult outside sources. In at most 250 words
> total, provide five labelled sections: (1) Claim assessment: supported,
> not established, or contradicted; assess the exact quoted claim.
> (2) Policy recommendation: state a practical action under the paper's stated
> objectives and constraints. (3) Decisive reasons: cite packet evidence.
> (4) Necessary conditions, if any, including their burden and timing.
> (5) What evidence would change your decision. Assess the claim separately
> from the policy choice; explain your reasoning rather than only giving labels.

## Run

- Models: `openai_gpt6_astra` and `openai_gpt54_mini`, both at medium reasoning.
- Limits: 8,000 output tokens, 240-second timeout.
- Batch: 4 packets × 2 models × 1 run = **8 calls**.
- Retries: transport only, at most 3 attempts. No content retry and no reruns.

```sh
# 1. Review packets/{C17,C42,C36,C94}.md and keys/ of the same IDs, then:
.venv/bin/python experiments/covid_policy/covid.py signoff --name "<reviewer>"
.venv/bin/python experiments/covid_policy/covid.py prepare --out experiments/covid_policy/freeze.json
.venv/bin/python experiments/covid_policy/covid.py run experiments/covid_policy/freeze.json --out results/covid-run
.venv/bin/python experiments/covid_policy/covid.py mask --run results/covid-run --out results/covid-grading
```

`prepare` and `run` refuse if any packet or key changed after signoff.

## Grading

- **Grader:** one named grader (the author or one domain expert), disclosed in
  the report.
- **Order:** grade `grading-items.json` before opening `mapping.json`.
- **Two judgements per answer:**
  - **Claim:** correct label with a packet-grounded reason. "Contradicted" needs
    contrary evidence.
  - **Action:** fits the stated objectives and burdens. Several actions may be
    acceptable. Evidence gaps do not automatically require deferral.
- **Flags:** note outside or post-decision facts.
- **Reporting:** report invalid or missing outputs as such. Show the result as a
  2 × 2 count per model (claim correct, action proportionate).

## Limits to state

- This is one grader, not independent validation.
- Two pairs are not a sample.
- Models may carry later COVID knowledge.
- Source verification is partial:
  - the WHO June 2020 mask guidance text and SPI-B paper content were not read;
  - delivery of any source to decision-makers is not established.
