"""Actions are deterministic references, not model-generated scripts."""

from copy import deepcopy

import pytest
from test_planned_scene_generation import fill, workspace

from app.services.learning_contract import LearningContractError
from app.services.teaching_actions import assemble_actions, validate_actions


def test_deterministic_action_sequence_and_resource_binding():
    candidates = fill(workspace())
    actions = assemble_actions(candidates)
    assert actions == assemble_actions(candidates)
    assert {a["kind"] for a in actions["actions"]} == {"show_resource", "highlight", "ask_exercise"}
    assert [a["scene_key"] for a in actions["actions"] if a["kind"] == "show_resource"] == [
        "explanation",
        "code",
        "exercise",
    ]
    assert validate_actions(actions, candidates) == actions
    assert all(a["start_utf8"] == 0 and a["end_utf8"] > 0 for a in actions["anchor_catalog"])


@pytest.mark.parametrize("change", ["role", "id", "text", "anchor", "content"])
def test_modified_actions_or_resources_fail(change):
    candidates = fill(workspace())
    actions = assemble_actions(candidates)
    if change == "role":
        actions["actions"][0]["scene_key"] = "code"
    if change == "id":
        actions["actions"][0]["resource_id"] = candidates[1].id
    if change == "text":
        actions["actions"][0]["speech"] = "invented fact"
    if change == "anchor":
        actions["anchor_catalog"][0]["end_utf8"] += 1
    if change == "content":
        candidates[0].envelope["content"]["markdown"] = "changed"
    with pytest.raises(LearningContractError):
        validate_actions(actions, candidates)


def test_incomplete_or_changed_generation_invalidates_actions():
    w = workspace()
    old = fill(w)
    actions = assemble_actions(old)
    with pytest.raises(LearningContractError):
        assemble_actions(old[:2])
    w.stage("explanation", deepcopy(old[0].envelope))
    with pytest.raises(LearningContractError):
        validate_actions(actions, w.candidates())
