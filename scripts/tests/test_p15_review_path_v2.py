"""Offline path representation and source-binding tests."""

from copy import deepcopy

import pytest

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_review_path_v2 as v2
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest
from scripts.tests.test_p15_combined_candidate_contract import response
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


def case(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    artifact = c.assemble(
        value,
        c.identity("dev", "slot", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    return artifact, catalog


@pytest.mark.parametrize("arm", ["B", "C"])
def test_full_candidate_reference_and_all_target_paths_round_trip(arm):
    artifact, catalog = case(arm)
    body, binding = v2.review_body(artifact, catalog)
    request = c.strict_json(body)
    payload = c.strict_json(request["input"][1]["content"].encode())
    assert payload["artifact"] == artifact
    assert payload["reference"] == catalog["example"]
    assert len(payload["target_catalog"]) == len(binding["targets"])
    v2.verify_targets(artifact, binding, payload["target_catalog"])
    for key, path in payload["target_catalog"].items():
        assert (
            digest(v2.pointer_value(artifact, path))
            == binding["targets"][key]["value_digest"]
        )
    opinion = dict(
        candidate_id=binding["candidate_id"], verdict="pass", uncertainty="", issues=[]
    )
    result, observation = v2.observe_review(
        body, response(body, opinion), binding, v2.reservation(body)
    )
    assert result == opinion and observation["semantic_pass"] is False


@pytest.mark.parametrize("change", ["omission", "wrong_path", "tamper"])
def test_missing_wrong_or_modified_target_is_rejected(change):
    artifact, catalog = case("C")
    _, binding = v2.review_body(artifact, catalog)
    targets = {key: row["path"] for key, row in binding["targets"].items()}
    first, second = list(targets)[:2]
    if change == "omission":
        del targets[first]
    elif change == "wrong_path":
        targets[first] = targets[second]
    else:
        artifact = deepcopy(artifact)
        artifact["raw_output"]["paragraphs"][0]["text"] += "tampered"
    with pytest.raises(c.ContractError):
        v2.verify_targets(artifact, binding, targets)


def test_cross_version_and_wrong_reservation_are_rejected():
    artifact, catalog = case("C")
    body, binding = v2.review_body(artifact, catalog)
    opinion = dict(
        candidate_id=binding["candidate_id"], verdict="pass", uncertainty="", issues=[]
    )
    raw = response(body, opinion)
    with pytest.raises(c.ContractError):
        v2.observe_review(body, raw, binding, v2.reservation(body) - 1)
    artifact2 = deepcopy(artifact)
    artifact2["identity"]["revision"] = 1
    artifact2["artifact_digest"] = digest(
        {k: v for k, v in artifact2.items() if k != "artifact_digest"}
    )
    with pytest.raises(c.ContractError):
        v2.observe_review(body, raw, c.make_binding(artifact2), v2.reservation(body))


@pytest.mark.parametrize("arm", ["B", "C"])
def test_self_consistent_but_forged_source_is_rejected(arm):
    artifact, catalog = case(arm)
    artifact["source"]["blocks"][0]["markdown"] += "篡改"
    artifact["artifact_digest"] = digest(
        {k: v for k, v in artifact.items() if k != "artifact_digest"}
    )
    with pytest.raises(c.ContractError, match="ARTIFACT_RECONSTRUCTION"):
        v2.review_body(artifact, catalog)


@pytest.mark.parametrize("arm", ["B", "C"])
def test_long_fields_actions_and_repair_parent_fit_new_policy(arm):
    catalog = c.make_catalog(SPEC)
    value = content() if arm == "C" else b_fixture(SPEC)
    template = value["paragraphs"][0]
    value["paragraphs"] = [
        dict(template, key=f"p{i}", text="a" * 4000) for i in range(8)
    ]
    for question in value["questions"].values():
        question.update(stem="问" * 1200 + '"\\\n' * 100, explanation="a" * 4000)
    if arm == "B":
        state = deepcopy(value["actions"]["states"][-1])
        value["actions"] = {
            "states": [dict(deepcopy(state), order=i, step=i) for i in range(64)],
            "advances": [dict(order=64 + i, step=i) for i in range(64)],
            "highlights": [dict(order=128 + i, step=i, line=1) for i in range(52)],
        }
        value["code"] = value["code"] + "\n/*" + "c" * 12000 + "*/"
    stage = "C_content" if arm == "C" else "B_generate"
    c.validate(stage, value, catalog=catalog if arm == "C" else None)
    first = c.assemble(
        value,
        c.identity("dev", "capacity", arm, 0, SPEC, None),
        catalog if arm == "C" else None,
    )
    first_body, first_binding = v2.review_body(first, catalog)
    repaired = deepcopy(value)
    repaired["paragraphs"][0]["text"] = "修" * 4000
    c.validate(
        "C_repair" if arm == "C" else "B_repair",
        repaired,
        catalog=catalog if arm == "C" else None,
    )
    second = c.assemble(
        repaired,
        c.identity("dev", "capacity", arm, 1, SPEC, first["artifact_digest"]),
        catalog if arm == "C" else None,
    )
    second_body, second_binding = v2.review_body(second, catalog)
    assert second["identity"]["parent_digest"] == first["artifact_digest"]
    assert max(len(first_body), len(second_body)) <= v2.POLICY.request_bytes
    for body, binding in ((first_body, first_binding), (second_body, second_binding)):
        opinion = dict(
            candidate_id=binding["candidate_id"],
            verdict="pass",
            uncertainty="",
            issues=[],
        )
        value, _ = v2.observe_review(
            body, response(body, opinion), binding, v2.reservation(body)
        )
        assert value == opinion
    print(f"{arm}: first={len(first_body)} repaired={len(second_body)} bytes")
