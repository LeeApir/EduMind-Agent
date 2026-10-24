"""Strict wire projection and unchanged local contracts; explicit HTTPX Mock only."""

import asyncio
import json
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "backend/tests"),
]
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from acceptance_support.p15_strict_schema import guidance, project, validate_wire  # noqa: E402
from acceptance_support.p15_strict_transport import SCHEMAS, StrictDiagnosticAdapter  # noqa: E402
from test_free_course_planning import candidate  # noqa: E402
from test_free_scene_generation import response  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest  # noqa: E402


@pytest.mark.parametrize("stage", list(SCHEMAS))
def test_all_three_real_contracts_project_without_mutation(stage):
    original = deepcopy(SCHEMAS[stage])
    wire, changes = project(original)
    assert original == SCHEMAS[stage]
    validate_wire(wire)
    Draft202012Validator.check_schema(wire)
    assert changes and guidance(original).endswith(
        json.dumps(original, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )


CASES = [
    "plan_ok",
    "plan_mixed",
    "plan_source",
    "plan_duplicate",
    "scene_ok",
    "scene_no_text",
    "scene_action",
    "scene_empty",
    "scene_index",
    "scene_unique",
    "review_ok",
    "review_empty",
]


def sample(mode):
    if mode.startswith("plan"):
        stage = "free_course_plan_generation"
        value = candidate(1)
        if mode == "plan_mixed":
            value["needs_clarification"] = True
        elif mode == "plan_source":
            value["plan"]["objectives"][0].update(source_key=None, source_excerpt=None)
        elif mode == "plan_duplicate":
            value["plan"]["scenes"][0]["forms"] = ["text", "text"]
    elif mode.startswith("scene"):
        stage = "free_scene_generation"
        value = response()
        if mode == "scene_no_text":
            value["blocks"] = value["blocks"][1:]
        elif mode == "scene_action":
            value["actions"][0]["step_index"] = 1
        elif mode == "scene_empty":
            value["blocks"][0]["markdown"] = ""
        elif mode == "scene_index":
            value["actions"][0].update(type="show_step", step_index=99)
        elif mode == "scene_unique":
            value["blocks"][-1]["steps"][0]["highlight_ids"] = ["x", "x"]
    else:
        stage = "development_review_probe"
        value = dict(review_version="resource-review-v3", verdict="pass", issues=[])
        if mode == "review_empty":
            value.update(
                verdict="revise",
                issues=[dict(area="fact", severity="major", message="")],
            )
    return stage, value


@pytest.mark.parametrize("mode", CASES)
def test_actual_strict_wire_then_full_original_validation(tmp_path, mode):
    stage, value = sample(mode)
    schema = SCHEMAS[stage]
    wire_schema, _ = project(schema)
    # Adversarial outputs deliberately satisfy the relaxed wire but violate original constraints.
    Draft202012Validator(wire_schema).validate(value)
    valid = mode.endswith("_ok")
    assert Draft202012Validator(schema).is_valid(value) is valid
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"] == wire_schema
        assert body["input"][1] == {"role": "system", "content": guidance(schema)}
        assert body["input"][-1]["content"] == "SYNTHETIC_INPUT_ONLY"
        assert body["reasoning"] == {"effort": "none"}
        validate_wire(body["text"]["format"]["schema"])
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(
                200, json=dict(object="response.input_tokens", input_tokens=100)
            )
        return httpx.Response(
            200,
            json=dict(
                model="gpt-6-luna",
                status="completed",
                output=[
                    dict(
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[dict(type="output_text", text=json.dumps(value))],
                    )
                ],
                usage=dict(input_tokens=100, output_tokens=100),
            ),
        )

    ledger = Ledger(tmp_path / "TEST_ONLY.sqlite")
    limits = Limits(4, 100000, 16000, None, 600)
    approval = dict(
        scope="PHASE-1.5-T038",
        batch_id="TEST_ONLY",
        package_sha256="a" * 64,
        limits=asdict(limits),
        fee_cap_waiver=True,
        evidence_ref="synthetic_not_real_approval",
    )
    ledger.start(
        "TEST_ONLY", "a" * 64, limits, approval, pinned_approval_sha256=digest(approval)
    )
    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
        )
    )
    adapter = StrictDiagnosticAdapter(
        ProviderSettings("https://www.cbbb.fun/v1", "TEST_ONLY_SECRET", "gpt-6-luna"),
        guard,
        ledger,
        "TEST_ONLY",
        "a" * 64,
        tmp_path,
        lambda: httpx.MockTransport(handler),
    )
    request = StructuredRequest(
        TextRequest(
            (
                ChatMessage("system", "Original trusted instructions"),
                ChatMessage("user", "SYNTHETIC_INPUT_ONLY"),
            ),
            max_output_tokens=8000,
        ),
        schema,
        stage,
    )
    try:
        reply = asyncio.run(adapter.send(request, retry_safe=False))
        assert (
            reply.evidence == "complete_response"
            and reply.input_tokens == reply.output_tokens == 100
        )
        assert reply.value == (value if valid else {})
        assert len(seen) == 2 and seen[0] == seen[1]
        assert ledger.usage("TEST_ONLY")["requests"] == 2
        assert ledger.usage("TEST_ONLY")["input_tokens"] == 100
        audit = json.loads(next(tmp_path.glob("*-projection.json")).read_text())
        assert audit["local_schema_sha256"] == digest(schema) and audit[
            "wire_schema_sha256"
        ] == digest(wire_schema)
        assert "TEST_ONLY_SECRET" not in "".join(
            p.read_text() for p in tmp_path.glob("*.json")
        )
        if not valid:
            with pytest.raises(ValidationError):
                Draft202012Validator(schema).validate(value)
    finally:
        ledger.close()


@pytest.mark.parametrize(
    "mode",
    [
        "unknown_keyword",
        "external_ref",
        "unknown_ref",
        "not_closed",
        "optional_field",
        "root_union",
    ],
)
def test_unfrozen_or_unsafe_constructs_refused(mode):
    schema = deepcopy(SCHEMAS["free_course_plan_generation"])
    if mode == "unknown_keyword":
        schema["dependentSchemas"] = {"x": {}}
    elif mode == "external_ref":
        schema["$defs"]["PlanCandidate"] = {"$ref": "https://example.invalid/schema"}
    elif mode == "unknown_ref":
        schema["$defs"]["PlanCandidate"] = {"$ref": "#/$defs/Missing"}
    elif mode == "not_closed":
        schema["additionalProperties"] = True
    elif mode == "optional_field":
        schema["required"].pop()
    else:
        schema = {"anyOf": [schema]}
    with pytest.raises(ValueError):
        project(schema)


def test_unknown_stage_or_changed_schema_stops_before_transport_factory(tmp_path):
    def forbidden():
        pytest.fail("Unfrozen schema must not construct a transport")

    adapter = StrictDiagnosticAdapter(
        None, None, None, "TEST_ONLY", "a" * 64, tmp_path, forbidden
    )
    for stage, schema in [
        ("unapproved", SCHEMAS["free_course_plan_generation"]),
        ("free_course_plan_generation", {"type": "object"}),
    ]:
        request = StructuredRequest(
            TextRequest((ChatMessage("user", "fixture"),)), schema, stage
        )
        with pytest.raises(Refused, match="UNFROZEN_DOMAIN_SCHEMA"):
            asyncio.run(adapter.send(request, retry_safe=False))


@pytest.mark.parametrize("old_grant", [False, True])
def test_r03_missing_approval_or_r02_grant_refused_before_any_side_effect(
    tmp_path, monkeypatch, old_grant
):
    import run_p15_strict_diagnostic as cli

    manifest = dict(
        batch_id="p15-development-r03",
        limits=dict(
            requests=404,
            input_tokens=3440000,
            output_tokens=832000,
            fee_micros=None,
            wall_seconds=10800,
        ),
    )
    monkeypatch.setattr(cli, "load_package", lambda _: (manifest, "b" * 64))
    if old_grant:
        source = (
            ROOT
            / "docs/acceptance/phase-1.5-development-diagnostic-r02/execution-approval.json"
        )
        (tmp_path / "execution-approval.json").write_bytes(source.read_bytes())
    with pytest.raises(Refused, match="EXACT_T038_HUMAN_APPROVAL_REQUIRED"):
        cli.gate(tmp_path)
    assert not (tmp_path / "ledger.sqlite").exists()
    assert not cli.OUTPUT.exists()
    assert cli.BASE.name.endswith("-r03") and cli.OUTPUT.name.endswith("-r03")
