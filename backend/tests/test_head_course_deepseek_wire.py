"""Offline replay and boundary checks for the fixed DeepSeek response contract."""

from copy import deepcopy
from pathlib import Path

import pytest

from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import head_course_deepseek_wire as direct

ACCEPTANCE = Path(__file__).resolve().parents[2] / "docs/acceptance"


def archived(stage):
    folder, stem = {
        "plan": ("head-fixed-live-r01", "plan"),
        "generate": ("head-fixed-repeat-r03", "repeat"),
    }[stage]
    base = ACCEPTANCE / f"phase-1.5-{folder}"
    return (
        direct.wire.strict_json((base / f"{stem}.request.json").read_bytes()),
        (base / f"{stem}.raw.json").read_bytes(),
    )


@pytest.mark.parametrize("stage", ["plan", "generate"])
def test_sealed_deepseek_responses_pass(stage):
    request, raw = archived(stage)
    result, observation = direct.observe_generation(request, raw)
    assert result.model_id == "deepseek-flash"
    assert observation["direct_response_contract"] == direct.VERSION
    assert observation["instruction_echo"] == "unavailable"


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (["model"], "gpt-6.1-sol", "ENVELOPE"),
        (["store"], None, "ENVELOPE"),
        (["temperature"], 1.0, "ENVELOPE"),
        (["max_output_tokens"], None, "ENVELOPE"),
        (["unknown"], 1, "ENVELOPE"),
        (["background"], True, "ENVELOPE"),
        (["tools"], [{"type": "web_search"}], "ENVELOPE"),
        (["reasoning", "effort"], "low", "REASONING"),
        (["instructions"], "unexpected suffix", "INSTRUCTIONS"),
        (["text", "format", "strict"], 1, "SCHEMA_ECHO"),
        (["text", "format", "schema"], {}, "SCHEMA_ECHO"),
        (["usage", "output_tokens_details", "reasoning_tokens"], 303, "USAGE"),
        (["usage", "output_tokens"], 8001, "USAGE"),
        (["usage", "input_tokens_details", "cached_tokens"], True, "USAGE"),
    ],
)
def test_conflicts_fail_before_content_is_used(path, value, error):
    request, raw = archived("generate")
    response = direct.wire.strict_json(raw)
    target = response
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(SnapshotError, match=f"HEAD_DIRECT_{error}"):
        direct.observe_generation(request, canonical(response))


def test_revision_echo_and_usage_are_bound_to_4000_cap():
    request, raw = archived("generate")
    response = direct.wire.strict_json(raw)
    request = deepcopy(request)
    request["max_output_tokens"] = 4000
    with pytest.raises(SnapshotError, match="HEAD_DIRECT_ENVELOPE"):
        direct.observe_generation(request, raw)
    response["max_output_tokens"] = 4000
    response["usage"]["output_tokens"] = 4001
    with pytest.raises(SnapshotError, match="HEAD_DIRECT_USAGE"):
        direct.observe_generation(request, canonical(response))
