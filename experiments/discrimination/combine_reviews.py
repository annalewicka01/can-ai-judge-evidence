"""Validate and combine provisional, masked agent reviews without re-keying runs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import json

from existing_outputs import (ACTION_ENUMS, ASSURANCE, KEY_FIELDS, read_json, save,
                              sha256, validate_action_rows, verify)


def validate_keys(rows, packets):
    papers = {p["key_id"]: p["paper"] for p in packets}
    seen = set()
    for row in rows:
        key = row["key_id"]
        if key not in papers or key in seen:
            raise ValueError(f"Unknown/duplicate key {key}")
        seen.add(key)
        if not set(KEY_FIELDS) <= set(row):
            raise ValueError(f"Missing key fields on {key}")
        if row["bounded_assessment"] not in ("supported", "unsupported", "contradicted", "unclear"):
            raise ValueError(f"Invalid bounded assessment on {key}")
        if row["broad_assurance_assessment"] not in ("sufficient", "insufficient", "contestable"):
            raise ValueError(f"Invalid broad assessment on {key}")
        levels = row["acceptable_assurance"]
        if not isinstance(levels, list) or len(set(levels)) != len(levels) or not set(levels) <= set(ASSURANCE):
            raise ValueError(f"Invalid assurance set on {key}")
        if not isinstance(row["concerns"], list):
            raise ValueError(f"Invalid concerns on {key}")
        if not row["evidence_quotes"] or not all(
                isinstance(q, str) and q and q in papers[key] for q in row["evidence_quotes"]):
            raise ValueError(f"Nonverbatim evidence on {key}")
        if not all(isinstance(row[f], str) and row[f].strip() for f in ("bounded_claim", "rationale")):
            raise ValueError(f"Empty interpretation on {key}")
    if seen != set(papers):
        raise ValueError(f"Incomplete keys {len(seen)}/{len(papers)}")
    return len(rows)


def lock_keys(out):
    out = Path(out)
    packets = read_json(out / "key-packets.json")
    counts = {}
    for coder in ("a", "b"):
        counts[coder] = validate_keys(read_json(out / f"agent-keys-{coder}.json"), packets)
    hashes = {f"agent-keys-{c}.json": sha256(out / f"agent-keys-{c}.json") for c in ("a", "b")}
    path = out / "key-review-lock.json"
    if path.exists():
        if read_json(path)["sha256"] != hashes:
            raise ValueError("Locked key review changed")
    else:
        save(path, {"sha256": hashes, "review_counts": counts,
                    "before_action_coding": not any((out / f"agent-actions-{c}.json").exists() for c in ("a", "b")),
                    "human_validation": False})
    return read_json(path)


def agreement(rows_a, rows_b, fields, identifier):
    a, b = ({r[identifier]: r for r in rows} for rows in (rows_a, rows_b))
    shared = sorted(set(a) & set(b))
    def agrees(key, field):
        left, right = a[key][field], b[key][field]
        return set(left) == set(right) if field == "acceptable_assurance" else left == right
    return {
        "shared_n": len(shared),
        "fields": {f: {"agree": sum(agrees(k, f) for k in shared), "n": len(shared),
                        "disagreements": [k for k in shared if not agrees(k, f)]} for f in fields},
    }


def possible_values(codings, field):
    return {row[field] for row in codings}


def category_bounds(coded, field):
    """Lower=all reviewers agree; upper=at least one supports. No adjudication."""
    lower, upper = Counter(), Counter()
    for rows in coded:
        values = possible_values(rows, field)
        for v in values:
            upper[v] += 1
        if len(values) == 1:
            lower[next(iter(values))] += 1
    return {v: {"min": lower[v], "max": upper[v]} for v in ACTION_ENUMS[field]}


def binary_assurance_levels(category):
    if category == "contestable":
        return set(ASSURANCE)
    if category == "sufficient":
        return {"reasonable", "substantial"}
    if category == "insufficient":
        return {"limited", "no_assurance"}
    raise ValueError(f"Unknown broad assessment: {category}")


def summarize_keys(out):
    out = Path(out)
    lock_keys(out)
    reviews = {c: read_json(out / f"agent-keys-{c}.json") for c in ("a", "b")}
    by = {c: {r["key_id"]: r for r in rows} for c, rows in reviews.items()}
    mapping = read_json(out / "private-key-map.json")
    cases = []
    for p in mapping:
        a, b = by["a"][p["key_id"]], by["b"][p["key_id"]]
        cases.append({**p, "reviews": {"a": a, "b": b}, "human_adjudication": None,
                      "both_allow": sorted(set(a["acceptable_assurance"]) & set(b["acceptable_assurance"])),
                      "either_allows": sorted(set(a["acceptable_assurance"]) | set(b["acceptable_assurance"]))})
    exception = out / "key-review-lock-exception.json"
    return {"status": "provisional_agent_review_not_clinical_validation", "cases": cases,
            "lock_exception": read_json(exception) if exception.exists() else None,
            "agreement": agreement(reviews["a"], reviews["b"],
                                   ("bounded_assessment", "broad_assurance_assessment", "acceptable_assurance"), "key_id"),
            "bounded_agreement_caveat": "Reviewers also authored claim scope; matching categories need not mean identical claims.",
            "human_reviewers_completed": 0}


def compatible_assurance(keys, out):
    by_key = {r["key_id"]: r for r in keys["cases"]}
    packets = {r["answer_id"]: r for r in read_json(out / "action-packets-all.json")}
    cells = defaultdict(Counter)
    for row in read_json(out / "private-answer-map.json"):
        if row["iteration"] not in (2, 3):
            continue
        c = cells[(row["model"], row["arm"], row["variant"])]
        level = packets[row["answer_id"]]["answer"]["assurance_level"]
        key = by_key[row["key_id"]]
        allowed = ("limited", "no_assurance") if row["variant"] == "deficient" else ("reasonable", "substantial")
        c["n"] += 1
        c["original_correct"] += level in allowed
        # Keep the original binary endpoint for the principal scope sensitivity.
        # Four-level preferences are a separate, stricter construct.
        binary_sets = []
        for review in key["reviews"].values():
            category = review["broad_assurance_assessment"]
            binary_sets.append(binary_assurance_levels(category))
        c["both_agents_binary_compatible"] += all(level in s for s in binary_sets)
        c["either_agent_binary_compatible"] += any(level in s for s in binary_sets)
        c["both_agents_specific_grade_allowed"] += level in key["both_allow"]
        c["either_agent_specific_grade_allowed"] += level in key["either_allows"]
    return {"interpretation": "Provisional sensitivity, not corrected accuracy. Binary compatibility retains original polarity; contestable keys allow either polarity. Specific-grade compatibility is a separate stricter construct and must not replace binary accuracy.",
            "cells": [{"model": k[0], "arm": k[1], "variant": k[2], **dict(v)} for k, v in sorted(cells.items())]}


def summarize_actions(out):
    out = Path(out)
    reviews = {c: read_json(out / f"agent-actions-{c}.json") for c in ("a", "b")}
    for c, rows in reviews.items():
        validate_action_rows(rows, read_json(out / f"action-packets-{c}.json"))
    hashes = {f"agent-actions-{c}.json": sha256(out / f"agent-actions-{c}.json") for c in ("a", "b")}
    lock = out / "action-review-lock.json"
    if lock.exists():
        if read_json(lock)["sha256"] != hashes:
            raise ValueError("Locked action coding changed")
    else:
        save(lock, {"sha256": hashes, "review_counts": {c: len(rows) for c, rows in reviews.items()},
                    "human_validation": False})
    joint = defaultdict(list)
    for c, rows in reviews.items():
        for r in rows:
            joint[r["answer_id"]].append({"reviewer": c, **r})
    metadata = {r["answer_id"]: r for r in read_json(out / "private-answer-map.json") if r["primary"]}
    if set(joint) != set(metadata):
        raise ValueError("Action coverage differs from frozen primary cohort")
    expected_overlap = set(read_json(out / "private-overlap.json"))
    actual_overlap = {k for k, v in joint.items() if len(v) == 2}
    if actual_overlap != expected_overlap:
        raise ValueError("Overlap changed")
    cells, families = defaultdict(list), defaultdict(list)
    for identifier, rows in joint.items():
        meta = metadata[identifier]
        cells[(meta["model"], meta["arm"], meta["variant"])].append(rows)
        families[(meta["model"], meta["arm"], meta["family"], meta["variant"])].append(rows)
    fields = tuple(ACTION_ENUMS)
    agreements = agreement(reviews["a"], reviews["b"], fields, "answer_id")
    disagreements = [k for k in sorted(expected_overlap) if any(
        len(possible_values(joint[k], f)) > 1 for f in fields)]
    def tabulate(groups):
        return [{"group": list(k), "n": len(rows),
                 "uncertain_any_reviewer": sum(any(r["uncertain"] for r in rr) for rr in rows),
                 "fields": {f: category_bounds(rows, f) for f in fields}}
                for k, rows in sorted(groups.items())]
    pairs = defaultdict(dict)
    for identifier, meta in metadata.items():
        identity = (meta["iteration"], meta["paper_id"], meta["model"], meta["repeat"])
        if meta["arm"] in pairs[identity]:
            raise ValueError("Duplicate action pair")
        pairs[identity][meta["arm"]] = identifier
    transitions = defaultdict(lambda: {"n": 0, "min": Counter(), "max": Counter()})
    for identity, pair in pairs.items():
        if set(pair) != {"ordinary", "targeted"}:
            raise ValueError("Incomplete ordinary/targeted action pair")
        ordinary, targeted = (possible_values(joint[pair[a]], "launch_gate") for a in ("ordinary", "targeted"))
        possibilities = {(o == "evidence_before_expansion", t == "evidence_before_expansion")
                         for o in ordinary for t in targeted}
        variant = metadata[pair["ordinary"]]["variant"]
        cell = transitions[(identity[2], variant)]
        cell["n"] += 1
        labels = {(False, False): "neither", (False, True): "added", (True, False): "removed", (True, True): "both"}
        for p in possibilities:
            cell["max"][labels[p]] += 1
        if len(possibilities) == 1:
            cell["min"][labels[next(iter(possibilities))]] += 1
    return {
        "status": "masked_agent_content_coding_not_human_validation",
        "review_sha256": hashes,
        "scope": "iterations 2/3, ordinary and targeted, all three models, all repeats",
        "unique_answers": len(joint), "review_assignments": sum(map(len, reviews.values())),
        "overlap_answers": len(expected_overlap), "single_coded_answers": len(joint) - len(expected_overlap),
        "disagreement_answers": disagreements,
        "agreement": agreements, "bounds_meaning": "Minimum counts require all assigned reviewers; maximum counts need any. Bounds capture observed disagreement on double-coded answers only, not unseen uncertainty on single-coded answers or confidence intervals.",
        "cells": tabulate(cells), "families": tabulate(families),
        "evidence_gate_transitions": [{"model": k[0], "variant": k[1], "n": c["n"],
                                       "transitions": {t: {"min": c["min"][t], "max": c["max"][t]}
                                                       for t in ("neither", "added", "removed", "both")}}
                                      for k, c in sorted(transitions.items())],
        "coded_rows": [{"answer_id": k, "metadata": metadata[k], "reviews": rows, "adjudication": None}
                       for k, rows in sorted(joint.items())],
    }


def gate_robustness(actions, keys):
    """Descriptive checks for flagged interpretations and provisional key scope."""
    by_key = {r["key_id"]: r for r in keys["cases"]}
    cells = defaultdict(Counter)
    for row in actions["coded_rows"]:
        meta, reviews = row["metadata"], row["reviews"]
        scopes = {r["broad_assurance_assessment"] for r in by_key[meta["key_id"]]["reviews"].values()}
        scope = next(iter(scopes)) if len(scopes) == 1 else "disagreed"
        gates = {r["launch_gate"] == "evidence_before_expansion" for r in reviews}
        uncertain = any(r["uncertain"] for r in reviews)
        for selection in ("all", scope):
            c = cells[(meta["model"], meta["arm"], meta["variant"], selection)]
            c["n"] += 1
            c["gates_min"] += gates == {True}
            c["gates_max"] += True in gates
            c["uncertainty_flagged"] += uncertain
            c["unflagged_n"] += not uncertain
            c["unflagged_gates_min"] += gates == {True} and not uncertain
    return {"interpretation": "Post-hoc robustness checks; uncertainty flags can concern any coding field. Scope is provisional agent consensus, not expert validation. Counts are not clinical correctness scores.",
            "cells": [{"model": k[0], "arm": k[1], "original_variant": k[2], "scope_selection": k[3], **dict(v)}
                      for k, v in sorted(cells.items())]}


def combine(out):
    out = Path(out)
    verified = verify(out)
    keys = summarize_keys(out)
    actions = summarize_actions(out)
    actions["gate_robustness"] = gate_robustness(actions, keys)
    result = {"analysis_date": "2026-11-14", "exploratory": True, "verified": verified,
              "keys": keys, "assurance_sensitivity": compatible_assurance(keys, out),
              "actions": actions, "human_validation_complete": False,
              "original_keys_modified": False}
    save(out / "review-results.json", result)
    return {"keys": len(keys["cases"]), "actions": result["actions"]["unique_answers"],
            "human_validation_complete": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("lock-keys", "summarize-keys", "combine"))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "lock-keys":
        result = lock_keys(args.out)
    elif args.command == "summarize-keys":
        result = summarize_keys(args.out)
        result["assurance_sensitivity"] = compatible_assurance(result, args.out)
        save(args.out / "key-results.json", result)
        result = {"keys": len(result["cases"]), "agreement": result["agreement"],
                  "human_reviewers_completed": 0}
    else:
        result = combine(args.out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
