"""Assigned scene forms are explicit in the prompt without weakening admission."""

import asyncio
import json
from copy import deepcopy

import pytest
from test_free_scene_generation import Gateway, authorize, inputs, response

from app.agents.free_scene_generation import build_request, generate_once, validate_response
from app.services.free_course_snapshots import SnapshotError
from app.services.free_scene_validation import check_scene


@pytest.mark.parametrize(
    "forms",
    [
        ["text"],
        ["code"],
        ["exercise"],
        ["visualization"],
        ["text", "code", "exercise"],
        ["text", "code", "exercise", "visualization"],
    ],
)
def test_actual_request_has_exact_forms_not_generic_all_four(forms):
    data = inputs(n=1, forms=forms)
    original = deepcopy(data)
    request = build_request(data)
    payload = json.loads(request.prompt.messages[-1].content)
    expected = set(forms) | {"text"}
    contract = payload["response_contract"]
    assert payload["prompt_version"] == "free-scene-generation-v3"
    assert set(contract["allowed_block_kinds"]) == expected
    assert set(contract["required_block_kinds"]) == expected
    assert (
        set(contract["forbidden_block_kinds"])
        == {"text", "code", "exercise", "visualization"} - expected
    )
    assert payload["request"] == data["request"]
    assert payload["plan"] == data["plan"]
    assert data == original
    assert request.json_schema == build_request(original).json_schema


def test_unrequested_visualization_still_rejected_without_silent_removal():
    data = inputs(n=1, forms=["text", "code", "exercise"])
    raw = response()
    before = deepcopy(raw)
    with pytest.raises(SnapshotError, match="SCHEMA_INVALID"):
        validate_response(raw, data)
    result = asyncio.run(generate_once(Gateway(raw), data, authorize_send=authorize))
    assert result.state == "failed" and result.reason_code == "SCHEMA_INVALID"
    assert result.response == raw == before
    assert check_scene(raw, data)["state"] == "rejected"


def test_missing_required_exercise_still_rejected():
    data = inputs(n=1, forms=["text", "code", "exercise"])
    raw = response(["text", "code"])
    assert check_scene(raw, data)["state"] == "rejected"


def test_mock_provider_uses_explicit_contract_and_original_admission_succeeds():
    class ContractGateway(Gateway):
        async def generate_structured(self, request, *, retry_safe=False):
            contract = json.loads(request.prompt.messages[-1].content)["response_contract"]
            self.value = response(contract["allowed_block_kinds"])
            return await super().generate_structured(request, retry_safe=retry_safe)

    data = inputs(n=1, forms=["text", "code", "exercise"])
    gateway = ContractGateway()
    result = asyncio.run(generate_once(gateway, data, authorize_send=authorize))
    assert result.state == "candidate" and len(gateway.requests) == 1
    assert {b["kind"] for b in result.response["blocks"]} == {"text", "code", "exercise"}
    assert check_scene(result.response, data)["state"] == "accepted"


def test_response_contract_is_bound_to_selected_scene_not_other_plan_scenes():
    data = inputs(n=2, forms=["text", "code", "exercise", "visualization"])
    data["plan"]["scenes"][-1]["forms"] = ["text"]
    payload = json.loads(build_request(data).prompt.messages[-1].content)
    assert payload["response_contract"]["allowed_block_kinds"] == ["text"]
    assert "visualization" in payload["response_contract"]["forbidden_block_kinds"]
