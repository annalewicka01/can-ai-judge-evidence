"""Synthetic regression checks for retrospective descriptive analyses."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired_analysis as pa


def row(family="F1", variant="D", arm="ordinary", repeat=0, iteration=2, correct=True,
        status="completed", model="mini", condition="single"):
    return {"iteration": iteration, "index": 0, "family": family, "paper_id": family + variant,
            "mechanism_family": "F3" if family == "F3b" else family,
            "pathway": pa.PATHWAYS[family], "variant": variant, "arm": arm, "repeat": repeat,
            "model": model, "condition": condition, "status": status,
            "correct": correct if status == "completed" else None,
            "decision_error": False if status == "completed" else None,
            "assurance": ("limited" if correct else "reasonable") if status == "completed" else None,
            "decision": "approve_with_conditions" if status == "completed" else None}


def paired_rows(**kwargs):
    return [row(variant=v, arm=a, **kwargs) for v in ("D", "A") for a in ("ordinary", "targeted")]


def test_distinct_iterations_and_repeats_are_not_collapsed():
    rows = [r for iteration in (2, 3) for repeat in (0, 1)
            for r in paired_rows(iteration=iteration, repeat=repeat)]
    result = pa.paired_correctness(rows)
    assert result["cells"]["mini|single|ordinary"]["pair_instances"] == 4
    assert len(result["instances"]) == 8


def test_missing_pair_raises_instead_of_silently_changing_denominator():
    with pytest.raises(ValueError, match="Incomplete D/A"):
        pa.paired_correctness([row()])


def test_duplicate_response_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        pa.analyze_board([row(), row()])


def test_failures_remain_in_denominators_and_pair_completion():
    rows = [row(), row(variant="A", status="format_failure")]
    cell = pa.summarize_cells(rows)["mini|single|ordinary"]
    assert cell["A"]["n"] == 1 and cell["A"]["completed"] == 0
    assert cell["A"]["rate_all_scheduled"] == 0 and cell["A"]["rate_assessed"] is None
    assert cell["balanced_accuracy_all_scheduled"] == 0.5
    pair = pa.paired_correctness(rows)["cells"]["mini|single|ordinary"]
    assert pair["pair_instances"] == 1 and pair["both_completed"] == 0


def test_transitions_separate_fixes_regressions_and_stability():
    rows = []
    for repeat, (before, after) in enumerate(((True, True), (False, True), (True, False), (False, False))):
        rows.extend([row(repeat=repeat, correct=before), row(repeat=repeat, arm="targeted", correct=after)])
    result = pa.arm_transitions(rows)["cells"]["mini|single|D"]
    assert all(result[k] == 1 for k in ("both_correct", "fixed", "regressed", "both_wrong"))
    assert result["n"] == 4


def test_missing_arm_pair_raises():
    with pytest.raises(ValueError, match="Incomplete arm"):
        pa.arm_transitions([row()])


def test_repeat_consistency_does_not_count_missing_response_as_disagreement():
    rows = [row(repeat=0), row(repeat=1, status="format_failure"),
            row(variant="A", repeat=0), row(variant="A", repeat=1)]
    cell = pa.repeat_consistency(rows)["cells"]["mini|single|ordinary"]
    assert cell["groups_with_repeats"] == 2
    assert cell["complete_assessed_groups"] == 1
    assert cell["same_correctness"] == 1


def test_mechanism_family_link_not_applied_to_pair_identity():
    rows = paired_rows(family="F3") + paired_rows(family="F3b", iteration=3)
    assert pa.macro_rates(rows, "mechanism_family")["mini|single|ordinary"]["group_n"] == 1
    assert pa.paired_correctness(rows)["cells"]["mini|single|ordinary"]["pair_instances"] == 2


def test_pathway_macro_weights_pathways_not_repeats():
    rows = paired_rows(family="F1") + paired_rows(family="G1")
    rows += paired_rows(family="F2", correct=False)
    result = pa.macro_rates(rows, "pathway")["mini|single|ordinary"]
    assert result["group_n"] == 2
    assert result["macro_balanced_accuracy"] == 0.5
    assert pa.summarize_cells(rows)["mini|single|ordinary"]["balanced_accuracy_all_scheduled"] == pytest.approx(2/3)


def test_exclusion_original_F3_keeps_corrected_F3b():
    rows = paired_rows(family="F3") + paired_rows(family="F3b", iteration=3)
    kept = [r for r in rows if r["family"] not in pa.EXCLUSIONS["exclude_original_F3"]]
    assert {r["family"] for r in kept} == {"F3b"}


def test_missing_judge_grade_has_explicit_denominator():
    rows = paired_rows(iteration=5)
    rows[0]["correct"] = None
    result = pa.summarize_cells(rows)["mini|single|ordinary"]
    assert result["D"]["n"] == 1 and result["D"]["completed"] == 1
    assert result["D"]["assessed"] == 0 and result["D"]["unassessed_completed"] == 1
    assert result["D"]["rate_assessed"] is None
    transitions = pa.arm_transitions(rows)["cells"]["mini|single|D"]
    assert transitions["unassessed"] == 1 and transitions["fixed"] == 0


def test_leave_one_pathway_out_keeps_other_pathways():
    rows = paired_rows(family="F1") + paired_rows(family="G1") + paired_rows(family="F2")
    out = pa.leave_one_group_out(rows, "pathway")
    remaining = next(x for x in out if x["excluded_group"] == "skin")
    assert remaining["contrasts"]["mini|single"]["n_each_arm"] == 2


def make_run(tmp_path, iteration=2, grade=None):
    directory = tmp_path / f"disc-iter{iteration}"
    directory.mkdir()
    job = {"paper_id": "F1D", "model": "openai_gpt54_mini", "arm": "ordinary", "repeat": 0}
    freeze = {"jobs": [job], "bank": [{"id": "F1D", "family": "F1", "variant": "deficient"}]}
    freeze["freeze_sha256"] = pa.digest(freeze)
    answer = {"assurance_level": "limited", "recommended_decision": "defer"}
    result = dict(job, status="completed", answer=answer,
                  score={"assurance_correct": True, "decision_error": False})
    if iteration == 5:
        result["decision_error"] = False
    (directory / "freeze.json").write_text(json.dumps(freeze))
    (directory / "results.json").write_text(json.dumps([result]))
    if grade is not None:
        (directory / "judge.json").write_text(json.dumps({"0": grade}))
    return directory


def test_loader_recomputes_score_and_rejects_tampering(tmp_path):
    directory = make_run(tmp_path)
    rows, _ = pa.load_iteration(tmp_path, 2)
    assert rows[0]["correct"] is True
    result = json.loads((directory / "results.json").read_text())
    result[0]["score"]["assurance_correct"] = False
    (directory / "results.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Stored score mismatch"):
        pa.load_iteration(tmp_path, 2)


def test_loader_rejects_coordinate_and_count_mismatch(tmp_path):
    directory = make_run(tmp_path)
    result = json.loads((directory / "results.json").read_text())
    result[0]["repeat"] = 9
    (directory / "results.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="coordinate mismatch"):
        pa.load_iteration(tmp_path, 2)
    (directory / "results.json").write_text("[]")
    with pytest.raises(ValueError, match="count mismatch"):
        pa.load_iteration(tmp_path, 2)


def test_loader_missing_or_invalid_judge(tmp_path):
    directory = make_run(tmp_path, iteration=5)
    rows, _ = pa.load_iteration(tmp_path, 5)
    assert rows[0]["correct"] is None
    (directory / "judge.json").write_text(json.dumps({"0": {"gap_identified": "true", "error": False}}))
    with pytest.raises(ValueError, match="Invalid judge"):
        pa.load_iteration(tmp_path, 5)


def test_pushback_counts_held_wrong_not_only_capitulation():
    rows = []
    for a, b in ((True, True), (True, False), (False, True), (False, False)):
        r = row()
        r.update(turn1_correct=a, turn2_correct=b, turn1_decision="defer", turn2_decision="defer")
        rows.append(r)
    out = pa.pushback_summary(rows)["mini|D"]
    assert all(out[k] == 1 for k in ("held_correct", "capitulated", "corrected", "held_wrong"))
