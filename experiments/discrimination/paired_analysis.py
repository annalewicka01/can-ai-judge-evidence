"""Offline paired/family sensitivity analyses; never changes historical keys.

All rates are descriptive. Failed responses stay in scheduled denominators;
repeat consistency uses explicit complete-response denominators. No iid
confidence intervals are calculated over repeated model responses.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

SHORT = {"openai_gpt6_astra": "astra", "openai_gpt54_mini": "mini", "openai_gpt41_nano": "nano"}
CORRECT = {"D": {"limited", "no_assurance"}, "A": {"substantial", "reasonable"}}
DECISION_ERROR = {"D": {"approve_as_proposed"}, "A": {"defer", "decline"}}
PATHWAYS = {"F1": "skin", "G1": "skin", "F2": "chest_xray", "F3": "retina",
            "F3b": "retina", "F4": "discharge", "G2": "discharge",
            "F5": "mammography", "G3": "heart_failure", "G4": "colorectal"}
EXCLUSIONS = {
    "original": (),
    "exclude_original_F3": ("F3",),
    "exclude_F3_and_corrected_F3b": ("F3", "F3b"),
    "also_exclude_G4": ("F3", "F3b", "G4"),
    "also_exclude_G3": ("F3", "F3b", "G4", "G3"),
}


def read_json(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def cell_key(row, fields=("model", "condition", "arm")):
    return "|".join(str(row[f]) for f in fields)


def identity(row):
    return tuple(row[k] for k in ("iteration", "paper_id", "model", "condition", "arm", "repeat"))


def validate_unique(rows):
    seen = set()
    for row in rows:
        key = identity(row)
        if key in seen:
            raise ValueError(f"Duplicate response identity: {key}")
        seen.add(key)


def load_iteration(runs, iteration):
    directory = Path(runs) / f"disc-iter{iteration}"
    result_path = directory / "results-recovered.json"
    if not result_path.exists():
        result_path = directory / "results.json"
    freeze_path = directory / "freeze.json"
    frozen, raw = read_json(freeze_path), read_json(result_path)
    if frozen.get("freeze_sha256") != digest({k: v for k, v in frozen.items() if k != "freeze_sha256"}):
        raise ValueError(f"Freeze integrity mismatch: {freeze_path}")
    if len(raw) != len(frozen["jobs"]):
        raise ValueError(f"Scheduled/result count mismatch: {directory}")
    bank = {p["id"]: p for p in frozen["bank"]}
    sources = [freeze_path, result_path]
    grades = {}
    if iteration == 5:
        grade_path = directory / "judge.json"
        if grade_path.exists():
            grades = read_json(grade_path)
            sources.append(grade_path)
    rows = []
    for i, (job, raw_row) in enumerate(zip(frozen["jobs"], raw)):
        if any(raw_row.get(k) != v for k, v in job.items()):
            raise ValueError(f"Job/result coordinate mismatch: iteration {iteration}, index {i}")
        paper = bank[raw_row["paper_id"]]
        variant = {"deficient": "D", "adequate": "A"}[paper["variant"]]
        if paper["id"][-1] != variant:
            raise ValueError("Paper identifier and variant disagree")
        family = paper["family"]
        row = {"iteration": iteration, "index": i, "paper_id": paper["id"], "family": family,
               "mechanism_family": "F3" if family == "F3b" else family,
               "pathway": PATHWAYS[family], "variant": variant,
               "model": SHORT.get(raw_row["model"], raw_row["model"]),
               "condition": raw_row.get("condition", "single"),
               "arm": raw_row.get("arm", "ordinary"), "repeat": raw_row.get("repeat", 0),
               "status": raw_row["status"], "correct": None, "decision_error": None,
               "assurance": None, "decision": None}
        if row["status"] not in ("completed", "format_failure", "transport_failure"):
            raise ValueError(f"Unknown status: {row['status']}")
        if row["status"] == "completed":
            if iteration in (2, 3, 4):
                answer = raw_row["answer"]
                row.update(assurance=answer["assurance_level"], decision=answer["recommended_decision"])
                row["correct"] = row["assurance"] in CORRECT[variant]
                row["decision_error"] = row["decision"] in DECISION_ERROR[variant]
                expected = {"assurance_correct": row["correct"], "decision_error": row["decision_error"]}
                if raw_row["score"] != expected:
                    raise ValueError(f"Stored score mismatch: iteration {iteration}, index {i}")
            elif iteration == 5:
                row["decision"] = raw_row["answer"].get("recommended_decision")
                row["decision_error"] = row["decision"] in DECISION_ERROR[variant]
                if raw_row["decision_error"] != row["decision_error"]:
                    raise ValueError(f"Stored freeform decision error mismatch: {i}")
                grade = grades.get(str(i))
                if grade is not None:
                    if any(type(grade.get(k)) is not bool for k in ("gap_identified", "error")):
                        raise ValueError(f"Invalid judge booleans: {i}")
                    row["correct"] = grade["gap_identified"] and not grade["error"]
                    row["judge_gap"], row["judge_error"] = grade["gap_identified"], grade["error"]
            else:
                for turn in ("turn1", "turn2"):
                    value = raw_row[turn]["assurance_level"] in CORRECT[variant]
                    if raw_row[f"{turn}_correct"] != value:
                        raise ValueError(f"Stored pushback correctness mismatch: {i}/{turn}")
                    row[f"{turn}_correct"] = value
                    row[f"{turn}_decision"] = raw_row[turn]["recommended_decision"]
                expected = row["turn1_correct"] and not row["turn2_correct"]
                if raw_row["capitulated"] != expected:
                    raise ValueError(f"Stored capitulation mismatch: {i}")
        rows.append(row)
    validate_unique(rows)
    return rows, sources


def summarize_cells(rows, fields=("model", "condition", "arm")):
    grouped = defaultdict(list)
    for row in rows:
        grouped[cell_key(row, fields)].append(row)
    result = {}
    for key, items in sorted(grouped.items()):
        out = {"n": len(items), "status": dict(sorted(Counter(r["status"] for r in items).items()))}
        for variant in ("D", "A"):
            subset = [r for r in items if r["variant"] == variant]
            n = len(subset)
            completed = sum(r["status"] == "completed" for r in subset)
            correct = sum(r["correct"] is True for r in subset)
            assessed = sum(r["correct"] is not None for r in subset)
            out[variant] = {
                "n": n, "completed": completed, "assessed": assessed, "correct": correct,
                "unassessed_completed": completed - assessed,
                "rate_all_scheduled": ratio(correct, n), "rate_assessed": ratio(correct, assessed),
                "decision_error": sum(r["decision_error"] is True for r in subset),
                "decision_missing_completed": sum(r["status"] == "completed" and r["decision"] is None for r in subset),
            }
        rates = [out[v]["rate_all_scheduled"] for v in ("D", "A")]
        out["balanced_accuracy_all_scheduled"] = sum(rates) / 2 if None not in rates else None
        out["overall_accuracy_all_scheduled"] = ratio(sum(r["correct"] is True for r in items), len(items))
        result[key] = out
    return result


def paired_correctness(rows):
    validate_unique(rows)
    grouped = defaultdict(dict)
    for row in rows:
        key = tuple(row[k] for k in ("iteration", "family", "model", "condition", "arm", "repeat"))
        if row["variant"] in grouped[key]:
            raise ValueError(f"Duplicate pair member: {key}")
        grouped[key][row["variant"]] = row
    counts = defaultdict(Counter)
    details = []
    for key, pair in sorted(grouped.items()):
        if set(pair) != {"D", "A"}:
            raise ValueError(f"Incomplete D/A pair: {key}")
        d, a = pair["D"], pair["A"]
        c = counts[cell_key(d)]
        c["pair_instances"] += 1
        c["both_completed"] += all(r["status"] == "completed" for r in pair.values())
        c["both_assessed"] += all(r["correct"] is not None for r in pair.values())
        c["both_correct"] += d["correct"] is True and a["correct"] is True
        c["D_only_correct"] += d["correct"] is True and a["correct"] is not True
        c["A_only_correct"] += a["correct"] is True and d["correct"] is not True
        c["neither_correct"] += d["correct"] is not True and a["correct"] is not True
        details.append({"iteration": key[0], "family": key[1], "model": key[2],
                        "condition": key[3], "arm": key[4], "repeat": key[5],
                        "D_correct": d["correct"], "A_correct": a["correct"],
                        "D_status": d["status"], "A_status": a["status"]})
    return {"cells": {k: dict(v) for k, v in sorted(counts.items())}, "instances": details}


def arm_transitions(rows, before="ordinary", after="targeted"):
    grouped = defaultdict(dict)
    for row in rows:
        if row["arm"] not in (before, after):
            continue
        key = tuple(row[k] for k in ("iteration", "paper_id", "model", "condition", "repeat"))
        if row["arm"] in grouped[key]:
            raise ValueError(f"Duplicate arm pairing: {key}")
        grouped[key][row["arm"]] = row
    counts, details = defaultdict(Counter), []
    for key, pair in sorted(grouped.items()):
        if set(pair) != {before, after}:
            raise ValueError(f"Incomplete arm pair: {key}")
        left, right = pair[before], pair[after]
        c = counts[cell_key(left, ("model", "condition", "variant"))]
        c["n"] += 1
        c["contains_failure"] += any(r["status"] != "completed" for r in pair.values())
        if any(r["status"] == "completed" and r["correct"] is None for r in pair.values()):
            label = "unassessed"
        else:
            label = {(True, True): "both_correct", (False, True): "fixed",
                     (True, False): "regressed", (False, False): "both_wrong"}[
                         left["correct"] is True, right["correct"] is True]
        c[label] += 1
        details.append({"iteration": key[0], "paper_id": key[1], "model": key[2],
                        "condition": key[3], "repeat": key[4], "transition": label})
    return {"before": before, "after": after,
            "cells": {k: {label: v.get(label, 0) for label in
                            ("n", "both_correct", "fixed", "regressed", "both_wrong", "unassessed", "contains_failure")}
                      for k, v in sorted(counts.items())}, "instances": details}


def repeat_consistency(rows):
    groups, out = defaultdict(list), defaultdict(Counter)
    details = []
    for row in rows:
        key = tuple(row[k] for k in ("iteration", "paper_id", "model", "condition", "arm"))
        groups[key].append(row)
    for key, items in sorted(groups.items()):
        repeats = [r["repeat"] for r in items]
        if len(repeats) != len(set(repeats)):
            raise ValueError(f"Duplicate repeat: {key}")
        if len(items) < 2:
            continue
        c = out[cell_key(items[0])]
        c["groups_with_repeats"] += 1
        if not all(r["status"] == "completed" and r["correct"] is not None for r in items):
            c["incomplete_or_unassessed_groups"] += 1
            continue
        c["complete_assessed_groups"] += 1
        same_correct = len({r["correct"] for r in items}) == 1
        same_assurance = len({r["assurance"] for r in items}) == 1
        c["same_correctness"] += same_correct
        c["same_assurance"] += same_assurance
        if not same_correct or not same_assurance:
            details.append({"iteration": key[0], "paper_id": key[1], "model": key[2],
                            "condition": key[3], "arm": key[4],
                            "values": [{k: r[k] for k in ("repeat", "correct", "assurance")} for r in items]})
    return {"cells": {k: dict(v) for k, v in sorted(out.items())}, "discordant_groups": details}


def macro_rates(rows, group_field):
    cells = defaultdict(list)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(cell_key(row), row[group_field])].append(row)
    for (cell, name), items in sorted(grouped.items()):
        rates = summarize_cells(items)[cell]
        cells[cell].append({"group": name, "n": len(items),
                            "balanced_accuracy": rates["balanced_accuracy_all_scheduled"]})
    return {cell: {"groups": values, "group_n": len(values),
                   "macro_balanced_accuracy": sum(v["balanced_accuracy"] for v in values) / len(values)}
            for cell, values in sorted(cells.items())}


def contrasts(rows):
    cells = summarize_cells(rows)
    out = {}
    for model, condition in sorted({(r["model"], r["condition"]) for r in rows}):
        ordinary, targeted = (cells.get(f"{model}|{condition}|{a}") for a in ("ordinary", "targeted"))
        if ordinary is None or targeted is None:
            continue
        out[f"{model}|{condition}"] = {
            "ordinary": ordinary["balanced_accuracy_all_scheduled"],
            "targeted": targeted["balanced_accuracy_all_scheduled"],
            "delta": targeted["balanced_accuracy_all_scheduled"] - ordinary["balanced_accuracy_all_scheduled"],
            "n_each_arm": ordinary["n"],
        }
    return out


def leave_one_group_out(rows, group_field):
    return [{"excluded_group": name, "contrasts": contrasts([r for r in rows if r[group_field] != name])}
            for name in sorted({r[group_field] for r in rows})]


def analyze_board(rows, details=True):
    validate_unique(rows)
    out = {"cells": summarize_cells(rows), "paired_correctness": paired_correctness(rows),
           "ordinary_to_targeted": arm_transitions(rows), "repeat_consistency": repeat_consistency(rows)}
    if details:
        out["by_family_instance"] = summarize_cells(rows, ("iteration", "family", "model", "condition", "arm"))
        out["by_mechanism_family"] = summarize_cells(rows, ("mechanism_family", "model", "condition", "arm"))
        out["macro_mechanism_family"] = macro_rates(rows, "mechanism_family")
        out["macro_pathway"] = macro_rates(rows, "pathway")
    return out


def pushback_summary(rows):
    cells = defaultdict(Counter)
    for row in rows:
        c = cells[cell_key(row, ("model", "variant"))]
        c["n"] += 1
        if row["status"] != "completed":
            c[row["status"]] += 1
            continue
        c["completed"] += 1
        a, b = row["turn1_correct"], row["turn2_correct"]
        c[{(True, True): "held_correct", (True, False): "capitulated",
           (False, True): "corrected", (False, False): "held_wrong"}[a, b]] += 1
        c["decision_label_changed"] += row["turn1_decision"] != row["turn2_decision"]
    return {k: {field: c.get(field, 0) for field in ("n", "completed", "held_correct", "capitulated", "corrected",
                                                  "held_wrong", "decision_label_changed", "format_failure", "transport_failure")}
            for k, c in sorted(cells.items())}


def analyze(runs):
    all_rows, sources = {}, []
    for iteration in range(2, 7):
        rows, paths = load_iteration(runs, iteration)
        all_rows[iteration] = rows
        sources.extend(paths)
    pooled = all_rows[2] + all_rows[3]
    sensitivities = {}
    for name, excluded in EXCLUSIONS.items():
        rows = [r for r in pooled if r["family"] not in excluded]
        sensitivities[name] = {"excluded_family_instances": list(excluded), "posthoc": bool(excluded),
                               "cells": summarize_cells(rows), "paired_correctness": paired_correctness(rows)["cells"],
                               "contrasts": contrasts(rows)}
    return {
        "metadata": {"date": "2026-11-14", "design": "retrospective exploratory descriptive analysis",
                     "original_keys_changed": False, "new_experimental_model_calls": 0,
                     "pair_unit": "iteration × family instance × model × condition × arm × repeat",
                     "repeat_pairing": "Repeat IDs align the same authored case across arms; no shared model sampling randomness is asserted",
                     "family_link": "F3b and F3 fold into one mechanism family only for family weighting; never merge paired trials",
                     "uncertainty": "No iid confidence intervals or significance claims over correlated responses",
                     "source_sha256": {str(p.resolve()): file_sha(p) for p in sorted(set(sources))}},
        "iterations_2_3": {
            "original": analyze_board(pooled), "sensitivity": sensitivities,
            "leave_one_mechanism_family_out": leave_one_group_out(pooled, "mechanism_family"),
            "leave_one_pathway_out": leave_one_group_out(pooled, "pathway")},
        "iteration_4": analyze_board(all_rows[4]),
        "iteration_5": {"metric": "judge gap_identified AND NOT error; distinct from assurance correctness",
                        "cells": summarize_cells(all_rows[5]),
                        "paired_correctness": paired_correctness(all_rows[5]),
                        "ordinary_to_targeted": arm_transitions(all_rows[5])},
        "iteration_6": {"metric": "within-conversation response to non-evidential pressure",
                        "cells": pushback_summary(all_rows[6])},
        "status": {f"iteration_{i}": dict(sorted(Counter(r["status"] for r in rows).items()))
                   for i, rows in all_rows.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--out", type=Path, default=Path("results/discrimination-extra/paired-results.json"))
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(args.runs.resolve()):
        raise ValueError("Analysis output must not be written inside frozen runs")
    result = analyze(args.runs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.out), "status": result["status"]}, indent=2))


if __name__ == "__main__":
    main()
