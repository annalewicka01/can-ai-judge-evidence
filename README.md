# can-ai-judge-evidence

Can an AI reviewer tell when a health-policy evaluation could not have shown
harm, and will it say so? A two-day hackathon project using synthetic NHS-style
committee papers. Paper: *No Harm Found? Testing AI Reviewers of Health-Policy
Evidence*, [paper/can-ai-judge-evidence.pdf](paper/can-ai-judge-evidence.pdf).

- `experiments/discrimination/`: matched committee papers, runners, judge, grading and analysis.
- `experiments/covid_policy/`: COVID-19 transfer check: sources, packets, keys, runner.
- `runs.tar.gz`: frozen requests, raw responses and grading inputs (extract to `runs/` first).
- `results/`: saved tables, action coding and COVID grades.
- `review/`: blind review of the answer keys (Claude Opus 5.5 and a joint human review).
- `archive/old-human-review/`: human-review packets read by the analysis.
- `scripts/`: offline reproduction and the evidence-hash baseline.
- `src/`, `tests/`: shared harness and its tests.
- `paper/`: the paper and Figure 1 (`figure.py`).

## Reproduce

```sh
tar -xzf runs.tar.gz
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python scripts/reproduce.py
.venv/bin/python -m pytest -q
```

Reproduction makes no API calls. It checks frozen digests and saved evidence
hashes, regenerates the tables and prints every number in the paper.

## Live runs

Runners call an OpenAI-compatible Responses endpoint. Set `CAJE_API_KEY` (or
`OPENAI_API_KEY`) and, for a gateway, `CAJE_ENDPOINT`. The models were used
under gateway aliases (`openai_gpt6_astra`, `openai_gpt54_mini`,
`openai_gpt41_nano`).

## Notes on saved records

- After the runs, the gateway URL in saved freezes and manifests was replaced by
  `https://gateway.example/v1/responses`, and their seals and the hash baseline
  were recomputed. No request or response content changed.
- Files edited after the COVID run are listed with their frozen and current
  hashes in `scripts/post_run_edits.json`.
- Frozen records use the project's earlier name, `would-we-notice`, in paths.
