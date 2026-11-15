"""Offline packet and coding-validation checks; no API calls."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import existing_outputs as analysis


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


@pytest.fixture
def prepared(tmp_path):
    runs = tmp_path / "runs"
    banks = {}
    for iteration in (2, 3):
        banks[iteration] = [
            {"id": f"F{iteration}{v}", "family": f"F{iteration}", "variant": variant,
             "paper": f"Synthetic paper {iteration} {v}"}
            for v, variant in (("D", "deficient"), ("A", "adequate"))]
    for iteration in range(2, 7):
        bank = banks[iteration] if iteration in (2, 3) else banks[3]
        rows = []
        for paper in bank:
            for arm in ("ordinary", "targeted"):
                for repeat in range(2):
                    answer = {"summary": "Obtain evidence before expansion.",
                              "recommended_decision": "approve_with_conditions"}
                    row = {"paper_id": paper["id"], "model": "test_model", "arm": arm,
                           "repeat": repeat, "status": "completed"}
                    if iteration == 6:
                        row.update(turn1=answer, turn2=answer)
                    else:
                        row["answer"] = answer
                    rows.append(row)
        directory = runs / f"disc-iter{iteration}"
        write(directory / "freeze.json", {"bank": bank})
        write(directory / "results.json", rows)
    out = tmp_path / "out"
    analysis.prepare(runs, out)
    return runs, out


def test_prepare_masks_keys_outputs_and_covers_all_answers(prepared):
    _, out = prepared
    keys = analysis.read_json(out / "key-packets.json")
    answers = analysis.read_json(out / "action-packets-all.json")
    assert len(keys) == 4 and len(answers) == 48
    assert all(set(x) == {"key_id", "paper"} for x in keys)
    assert all(set(x) == {"answer_id", "key_id", "answer"} for x in answers)
    assert {x["key_id"] for x in answers} <= {x["key_id"] for x in keys}


def test_partitions_cover_primary_and_overlap_once_per_stratum(prepared):
    _, out = prepared
    a = {p["answer_id"] for p in analysis.read_json(out / "action-packets-a.json")}
    b = {p["answer_id"] for p in analysis.read_json(out / "action-packets-b.json")}
    primary = {p["answer_id"] for p in analysis.read_json(out / "private-answer-map.json") if p["primary"]}
    assert a | b == primary
    assert a & b == set(analysis.read_json(out / "private-overlap.json"))
    assert len(primary) == 16 and len(a & b) == 8


def test_human_forms_are_empty_and_packets_cannot_be_overwritten(prepared):
    runs, out = prepared
    for path in out.glob("human-*.json"):
        for row in analysis.read_json(path):
            assert all(v is None for k, v in row.items() if k not in ("key_id", "answer_id"))
    with pytest.raises(FileExistsError):
        analysis.prepare(runs, out)


def test_verify_detects_packet_and_source_changes(prepared):
    runs, out = prepared
    assert analysis.verify(out)["sources_verified"] == 11
    path = out / "key-packets.json"
    before = path.read_text()
    path.write_text(before + " ")
    with pytest.raises(ValueError, match="Packet changed"):
        analysis.verify(out)
    path.write_text(before)
    (runs / "disc-iter2" / "results.json").write_text("[]")
    with pytest.raises(ValueError, match="Input changed"):
        analysis.verify(out)


def test_recovery_is_preferred(tmp_path):
    directory = tmp_path / "disc-iter2"
    write(directory / "results.json", [])
    assert analysis.selected_results(directory).name == "results.json"
    write(directory / "results-recovered.json", [])
    assert analysis.selected_results(directory).name == "results-recovered.json"


def test_prepare_rejects_frozen_or_nonempty_output(tmp_path):
    runs = tmp_path / "runs"
    with pytest.raises(ValueError, match="outside frozen"):
        analysis.prepare(runs, runs / "analysis")
    out = tmp_path / "occupied"
    out.mkdir()
    (out / "user_file.txt").write_text("preserve me")
    with pytest.raises(FileExistsError):
        analysis.prepare(runs, out)
    assert (out / "user_file.txt").read_text() == "preserve me"


def coding():
    return {"answer_id": "A1", **{k: v[0] for k, v in analysis.ACTION_ENUMS.items()},
            "evidence_quote": "Obtain evidence", "rationale": "Explicit action.", "uncertain": False}


def test_action_validation_requires_full_coverage_enum_boolean_and_verbatim_quote():
    packets = [{"answer_id": "A1", "answer": {"summary": "Obtain evidence before expansion."}}]
    assert analysis.validate_action_rows([coding()], packets) == {"validated": 1}
    with pytest.raises(ValueError, match="Incomplete"):
        analysis.validate_action_rows([], packets)
    with pytest.raises(ValueError, match="duplicate"):
        analysis.validate_action_rows([coding(), coding()], packets)
    for field, value in (("launch_gate", "good"), ("uncertain", "false"),
                         ("evidence_quote", "Invented quotation"), ("rationale", "")):
        bad = copy.deepcopy(coding())
        bad[field] = value
        with pytest.raises(ValueError):
            analysis.validate_action_rows([bad], packets)
