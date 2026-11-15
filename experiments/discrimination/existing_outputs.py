"""Offline, reproducible packets for retrospective discrimination analysis.

Never invokes a model or modifies the frozen runs. Run `prepare` before coding;
`verify` checks that the analysis inputs still match the packet manifest.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random

SEED = 2026111409
ASSURANCE = ("substantial", "reasonable", "limited", "no_assurance")
ACTION_ENUMS = {
    "launch_gate": ("evidence_before_expansion", "operational_before_expansion",
                    "post_launch_monitoring", "mixed_or_ambiguous", "unconditional", "no_decision"),
    "gap_handling": ("specific_action", "specific_question_only", "generic",
                     "already_resolved_concern", "no_material_gap", "unclear"),
    "owner": ("explicit_role", "generic_accountability", "absent"),
    "timing": ("explicit_date_or_interval", "before_launch_only", "vague", "absent"),
    "stopping_rule": ("operational_trigger", "mentioned_without_trigger", "absent"),
    "feasibility": ("anchored_in_paper", "not_established", "conflicts_with_paper"),
    "extra_burden": ("none_identified", "routine_monitoring", "additional_evidence_or_delay", "unclear"),
    "residual_uncertainty": ("specific", "generic", "absent"),
}
KEY_FIELDS = ("bounded_claim", "bounded_assessment", "broad_assurance_assessment",
              "acceptable_assurance", "concerns", "evidence_quotes", "rationale")


def read_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    """Generated analysis artifacts only; never source edits or frozen run writes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def selected_results(run_dir):
    recovered = run_dir / "results-recovered.json"
    return recovered if recovered.exists() else run_dir / "results.json"


def text_parts(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in text_parts(v)]
    if isinstance(value, list):
        return [s for v in value for s in text_parts(v)]
    return []


def normalized_answers(runs):
    answers, sources = [], set()
    for iteration in range(2, 7):
        directory = Path(runs) / f"disc-iter{iteration}"
        freeze_path, result_path = directory / "freeze.json", selected_results(directory)
        freeze, rows = read_json(freeze_path), read_json(result_path)
        sources.update((freeze_path, result_path))
        bank = {p["id"]: p for p in freeze["bank"]}
        for i, row in enumerate(rows):
            if row["status"] != "completed":
                continue
            paper = bank[row["paper_id"]]
            stages = ("turn1", "turn2") if iteration == 6 else ("answer",)
            for stage in stages:
                answers.append({
                    "iteration": iteration, "index": i, "stage": stage,
                    "paper_id": row["paper_id"], "family": paper["family"],
                    "variant": paper["variant"], "paper": paper["paper"],
                    "model": row["model"], "arm": row.get("arm", "ordinary"),
                    "condition": row.get("condition", "single"), "repeat": row.get("repeat", 0),
                    "answer": row[stage], "source": str(result_path),
                })
    return answers, sources


def prepare(runs, out):
    runs, out = Path(runs), Path(out)
    if out.resolve().is_relative_to(runs.resolve()):
        raise ValueError("Packets must be outside frozen runs")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Output directory is nonempty; use verify, not overwrite")
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    key_rows, sources = [], set()
    for iteration in (2, 3):
        path = runs / f"disc-iter{iteration}" / "freeze.json"
        sources.add(path)
        key_rows += [dict(p, iteration=iteration) for p in read_json(path)["bank"]]
    rng.shuffle(key_rows)
    key_packets, key_map, paper_lookup = [], [], {}
    for i, p in enumerate(key_rows, 1):
        key_id = f"K{i:03d}"
        key_packets.append({"key_id": key_id, "paper": p["paper"]})
        key_map.append({"key_id": key_id, "iteration": p["iteration"],
                        "paper_id": p["id"], "family": p["family"], "original_variant": p["variant"]})
        paper_lookup[p["paper"]] = key_id
    save(out / "key-packets.json", key_packets)
    save(out / "private-key-map.json", key_map)
    for reviewer in (1, 2):
        save(out / f"human-key-reviewer-{reviewer}.json", [
            {"key_id": p["key_id"], **{k: None for k in KEY_FIELDS}} for p in key_packets])

    answers, answer_sources = normalized_answers(runs)
    sources.update(answer_sources)
    rng.shuffle(answers)
    packets, private, primary = [], [], []
    for i, r in enumerate(answers, 1):
        answer_id = f"A{i:04d}"
        # All later banks are exact reuses of these iteration-2/3 texts.
        key_id = paper_lookup[r["paper"]]
        packet = {"answer_id": answer_id, "key_id": key_id, "answer": r["answer"]}
        packets.append(packet)
        selected = r["iteration"] in (2, 3) and r["arm"] in ("ordinary", "targeted")
        private.append({"answer_id": answer_id, "key_id": key_id, "primary": selected,
                        **{k: v for k, v in r.items() if k not in ("answer", "paper")}})
        if selected:
            primary.append((r, packet))
    save(out / "action-packets-all.json", packets)
    save(out / "private-answer-map.json", private)
    strata = defaultdict(list)
    for row, packet in primary:
        strata[(row["iteration"], row["model"], row["arm"], row["variant"])].append(packet)
    partitions = {"a": [], "b": []}
    overlap = []
    for j, (_, items) in enumerate(sorted(strata.items())):
        rng.shuffle(items)
        half = len(items) // 2
        partitions["a"].extend(items[:half])
        partitions["b"].extend(items[half:])
        shared = items[0] if j % 2 == 0 else items[half]
        partitions["b" if j % 2 == 0 else "a"].append(shared)
        overlap.append(shared["answer_id"])
    for reviewer, items in partitions.items():
        rng.shuffle(items)
        save(out / f"action-packets-{reviewer}.json", items)
    save(out / "private-overlap.json", overlap)
    primary_ids = {p["answer_id"] for _, p in primary}
    for reviewer in (1, 2):
        save(out / f"human-action-reviewer-{reviewer}.json", [
            {"answer_id": p["answer_id"], **{k: None for k in ACTION_ENUMS},
             "evidence_quote": None, "rationale": None, "uncertain": None}
            for p in packets if p["answer_id"] in primary_ids])
    summary = Path(runs).parent / "results" / "discrimination-summary.json"
    if summary.exists():
        sources.add(summary)
    plan = Path(__file__).with_name("EXISTING_OUTPUTS_ANALYSIS.md")
    sources.add(plan)
    manifest = {
        "analysis": "retrospective-existing-output-v1", "date": "2026-11-14", "seed": SEED,
        "independent_clinical_validation": False, "new_model_api_calls": 0,
        "keys": len(key_packets), "completed_answer_objects": len(packets),
        "primary_action_answers": len(primary), "overlap_answers": len(overlap),
        "agent_assignment_sizes": {k: len(v) for k, v in partitions.items()},
        "source_sha256": {str(p.resolve()): sha256(p) for p in sorted(sources)},
        "packet_sha256": {p.name: sha256(p) for p in sorted(out.glob("*.json"))},
    }
    save(out / "manifest.json", manifest)
    return manifest


def verify(out):
    out = Path(out)
    manifest = read_json(out / "manifest.json")
    root = Path(__file__).resolve().parents[2]
    for path, expected in manifest["source_sha256"].items():
        parts = Path(path).parts
        # Manifests predate the rename from would-we-notice.
        name = next((n for n in ("can-ai-judge-evidence", "would-we-notice") if n in parts), None)
        relative = Path(*parts[parts.index(name) + 1:]) if name else Path(path)
        if sha256(root / relative) != expected:
            raise ValueError(f"Input changed: {path}")
    for name, expected in manifest["packet_sha256"].items():
        path = out / name
        if not path.exists() and name.startswith("human-"):
            path = root / "archive" / "old-human-review" / name
        if sha256(path) != expected:
            raise ValueError(f"Packet changed: {name}")
    return {"sources_verified": len(manifest["source_sha256"]),
            "packets_verified": len(manifest["packet_sha256"])}


def validate_action_rows(rows, packets):
    by_id = {p["answer_id"]: p for p in packets}
    seen = set()
    for row in rows:
        identifier = row["answer_id"]
        if identifier in seen or identifier not in by_id:
            raise ValueError(f"Unknown or duplicate answer: {identifier}")
        seen.add(identifier)
        for field, allowed in ACTION_ENUMS.items():
            if row.get(field) not in allowed:
                raise ValueError(f"Invalid {field} on {identifier}")
        if type(row.get("uncertain")) is not bool:
            raise ValueError(f"Invalid uncertainty on {identifier}")
        quote = row.get("evidence_quote")
        if not isinstance(quote, str) or not quote or not any(
                quote in part for part in text_parts(by_id[identifier]["answer"])):
            raise ValueError(f"Quote is not verbatim on {identifier}")
        if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
            raise ValueError(f"Missing rationale on {identifier}")
    if seen != set(by_id):
        raise ValueError(f"Incomplete coding: {len(seen)}/{len(by_id)}")
    return {"validated": len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--out", type=Path, default=Path("results/discrimination-extra"))
    p = sub.add_parser("verify")
    p.add_argument("out", type=Path)
    p = sub.add_parser("validate-actions")
    p.add_argument("coding", type=Path)
    p.add_argument("packets", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.runs, args.out)
    elif args.command == "verify":
        result = verify(args.out)
    else:
        result = validate_action_rows(read_json(args.coding), read_json(args.packets))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
