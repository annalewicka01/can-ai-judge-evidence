from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combine_reviews as combine


def key():
    return {"key_id": "K1", "bounded_claim": "No events were observed.",
            "bounded_assessment": "supported", "broad_assurance_assessment": "contestable",
            "acceptable_assurance": ["reasonable", "limited"], "concerns": ["Scope"],
            "evidence_quotes": ["No events"], "rationale": "Narrow observation."}


def test_key_validation_requires_coverage_valid_fields_and_verbatim_evidence():
    packets = [{"key_id": "K1", "paper": "No events were observed."}]
    assert combine.validate_keys([key()], packets) == 1
    for row in (dict(key(), acceptable_assurance=["yes"]),
                dict(key(), evidence_quotes=["made up"]),
                dict(key(), broad_assurance_assessment="safe")):
        with pytest.raises(ValueError):
            combine.validate_keys([row], packets)
    with pytest.raises(ValueError, match="Incomplete"):
        combine.validate_keys([], packets)
    with pytest.raises(ValueError, match="duplicate"):
        combine.validate_keys([key(), key()], packets)


def test_bounds_preserve_coder_disagreements_not_majority_vote():
    rows = [[{"launch_gate": "evidence_before_expansion"}],
            [{"launch_gate": "evidence_before_expansion"}, {"launch_gate": "post_launch_monitoring"}],
            [{"launch_gate": "post_launch_monitoring"}, {"launch_gate": "post_launch_monitoring"}]]
    result = combine.category_bounds(rows, "launch_gate")
    assert result["evidence_before_expansion"] == {"min": 1, "max": 2}
    assert result["post_launch_monitoring"] == {"min": 1, "max": 2}
    assert result["unconditional"] == {"min": 0, "max": 0}


def test_agreement_counts_only_shared_answers():
    a = [{"id": "one", "field": "x"}, {"id": "two", "field": "x"}, {"id": "a", "field": "x"}]
    b = [{"id": "two", "field": "y"}, {"id": "one", "field": "x"}, {"id": "b", "field": "x"}]
    result = combine.agreement(a, b, ("field",), "id")
    assert result == {"shared_n": 2, "fields": {"field": {"agree": 1, "n": 2, "disagreements": ["two"]}}}


def test_assurance_set_agreement_ignores_list_order():
    a = [{"key_id": "K1", "acceptable_assurance": ["limited", "reasonable"]}]
    b = [{"key_id": "K1", "acceptable_assurance": ["reasonable", "limited"]}]
    assert combine.agreement(a, b, ("acceptable_assurance",), "key_id")["fields"]["acceptable_assurance"]["agree"] == 1


def test_binary_sensitivity_does_not_conflate_four_grade_preferences():
    assert combine.binary_assurance_levels("sufficient") == {"reasonable", "substantial"}
    assert combine.binary_assurance_levels("insufficient") == {"limited", "no_assurance"}
    assert combine.binary_assurance_levels("contestable") == {"reasonable", "substantial", "limited", "no_assurance"}
    with pytest.raises(ValueError):
        combine.binary_assurance_levels("unknown")


def test_gate_robustness_preserves_uncertain_and_disputed_cases():
    keys = {"cases": [{"key_id": "K1", "reviews": {
        "a": {"broad_assurance_assessment": "contestable"},
        "b": {"broad_assurance_assessment": "contestable"}}}]}
    actions = {"coded_rows": [{"metadata": {"key_id": "K1", "model": "m", "arm": "targeted", "variant": "adequate"},
                               "reviews": [{"launch_gate": "evidence_before_expansion", "uncertain": True}]}]}
    result = combine.gate_robustness(actions, keys)
    assert {r["scope_selection"] for r in result["cells"]} == {"all", "contestable"}
    assert all(r["n"] == 1 and r["gates_min"] == 1 and r["unflagged_n"] == 0 for r in result["cells"])
