"""Only T108's versioned Provider boundary; no network, credentials or model success."""

import json
from copy import deepcopy

import pytest

from app.agents import free_course_planning as local
from app.agents import head_course_planning_wire as wire
from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError
from scripts import head_course_goal as entry
from scripts import head_course_goal_fixture as fixture


def inputs():
    return dict(
        course_id="fixture-course",
        operation_id="fixture-operation",
        request_id="fixture-request",
        original_goal=m.GOAL,
        teaching_language="zh-CN",
        code_language="C",
        request_sources={"request_1": dict(request_id="fixture-request", version=1, text=m.GOAL)},
        learner_evidence={},
        profile_id=None,
        profile_version=None,
        head_support=m.SUPPORT,
    )


def test_normal_plan_preserves_all_model_content_and_original():
    raw = fixture.wire_plan()
    before = deepcopy(raw)
    assert wire.to_local(raw, inputs()) == fixture.plan()
    assert raw == before
    suggestion = dict(
        id="extra",
        description="模型建议的学习目标",
        source="planner_suggestion",
        source_key="",
        source_excerpt="",
    )
    raw["plans"][0]["objectives"].append(suggestion)
    raw["plans"][0]["scenes"][0]["objective_ids"].append("extra")
    mapped = wire.mapping_record(raw, inputs())
    assert mapped["wire_version"] == wire.VERSION
    assert mapped["local_schema_version"] == local.SCHEMA_VERSION
    obj = mapped["value"]["plan"]["objectives"][-1]
    assert obj == {**suggestion, "source_key": None, "source_excerpt": None}
    assert raw["plans"][0]["objectives"][-1] == suggestion


def clarification():
    return dict(
        protocol_version=wire.VERSION,
        needs_clarification=True,
        plans=[],
        questions=["所要求的场景是否含尚未提供的必需材料？"],
        reason="required_material_missing",
        source_keys=["request_1"],
    )


def test_clarification_preserved_and_not_fabricated_as_plan():
    raw = clarification()
    result = wire.to_local(raw, inputs())
    assert result == {k: v for k, v in raw.items() if k not in ("protocol_version", "plans")} | {
        "plan": None
    }
    assert raw["plans"] == []


@pytest.mark.parametrize(
    "kind",
    [
        "source_key",
        "quote",
        "empty_quote",
        "orphan",
        "coverage",
        "dependency",
        "old_example",
        "forms",
        "suggestion_evidence",
        "version",
        "unknown_field",
    ],
)
def test_invalid_content_rejected_without_automatic_repairs(kind):
    raw = fixture.wire_plan()
    p = raw["plans"][0]
    obj, scene = p["objectives"][0], p["scenes"][0]
    if kind == "source_key":
        obj["source_key"] = "not_a_source"
    elif kind == "quote":
        obj["source_excerpt"] = "不存在于原始目标的引文"
    elif kind == "empty_quote":
        obj["source_excerpt"] = ""
    elif kind == "orphan":
        scene["objective_ids"].append("invented")
    elif kind == "coverage":
        scene["objective_ids"] = ["link"]
    elif kind == "dependency":
        scene["depends_on"] = ["head"]
    elif kind == "old_example":
        p["shared_example"] = "C01"
    elif kind == "forms":
        scene["forms"] = ["text"]
    elif kind == "suggestion_evidence":
        obj["source"] = "planner_suggestion"
    elif kind == "version":
        raw["protocol_version"] = "unknown"
    else:
        raw["extra"] = "must not be ignored"
    before = deepcopy(raw)
    with pytest.raises(SnapshotError, match="SCHEMA_INVALID"):
        wire.to_local(raw, inputs())
    assert raw == before


@pytest.mark.parametrize("kind", ["plan", "empty_questions", "bad_source", "empty_reason", "false"])
def test_clarification_branch_stays_strict(kind):
    raw = clarification()
    if kind == "plan":
        raw["plans"] = fixture.wire_plan()["plans"]
    elif kind == "empty_questions":
        raw["questions"] = []
    elif kind == "bad_source":
        raw["source_keys"] = ["unknown"]
    elif kind == "empty_reason":
        raw["reason"] = ""
    else:
        raw["needs_clarification"] = False
    with pytest.raises(SnapshotError, match="SCHEMA_INVALID"):
        wire.to_local(raw, inputs())


def assert_simple_schema(schema):
    # This is a test assertion, not a runtime schema compiler or permissive transformer.
    assert schema["type"] in {"object", "array", "string", "boolean", "integer", "number"}
    assert not set(schema) & {"anyOf", "oneOf", "allOf", "$ref", "$defs", "if", "then", "else"}
    if schema["type"] == "object":
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        for child in schema["properties"].values():
            assert_simple_schema(child)
    elif schema["type"] == "array":
        assert_simple_schema(schema["items"])


def test_all_three_actual_builders_use_explicit_protocols():
    request = entry.planning_body(inputs())
    assert request["text"]["format"]["schema"] == wire.SCHEMA
    assert request["text"]["format"]["schema"] != local.SCHEMA
    assert "anyOf" in json.dumps(local.SCHEMA)  # local conditional contract retained
    assert_simple_schema(request["text"]["format"]["schema"])
    prompt = request["input"][0]["content"]
    assert "null source_key/source_excerpt" not in prompt
    assert wire.VERSION in prompt
    assert json.loads(request["input"][1]["content"])["prompt_version"] == wire.PROMPT_VERSION
    payload = m.content_payload(inputs(), fixture.plan()["plan"])
    parent = fixture.record(payload)["candidate"]
    issues = [dict(path=["lifecycle"], quote="离线夹具", severity="minor", area="difficulty")]
    for body in (m.body(payload), m.body(payload, parent, issues)):
        assert body["text"]["format"]["schema"] == m.SCHEMA
        assert_simple_schema(body["text"]["format"]["schema"])
        assert body["model"] == request["model"] == "deepseek-flash"
    # No wire change to ordinary planning.
    normal = {k: v for k, v in inputs().items() if k != "head_support"}
    assert local.build_request(normal).json_schema == local.SCHEMA


def test_old_authorization_cannot_enable_new_wire(tmp_path, monkeypatch):
    import time

    monkeypatch.setattr(entry, "package_digest", lambda: "a" * 64)
    tmp_path.chmod(0o700)
    old = dict(
        package_sha256="a" * 64,
        version=m.VERSION,
        accept_ADR0052_A_D_and_batch_C2=True,
        explicit_user_authorization=True,
        starts_epoch=int(time.time()),
        expires_epoch=int(time.time()) + 600,
    )
    with pytest.raises(SnapshotError, match="HEAD_EXACT_AUTHORIZATION_REQUIRED"):
        entry.approval_check(tmp_path, old)


def test_simplified_plan_rejection_saves_original_and_stops(tmp_path, monkeypatch):
    import time

    import httpx
    from cryptography.fernet import Fernet

    monkeypatch.setattr(entry, "package_digest", lambda: "a" * 64)
    tmp_path.chmod(0o700)
    # Only a fresh offline fixture vault. No real original, key, app owner or response.
    rawkey = Fernet.generate_key()
    cipher = Fernet(rawkey)
    (tmp_path / "raw.key").write_bytes(rawkey)
    (tmp_path / "raw.key").chmod(0o600)
    context = dict(
        owner="00000000-0000-0000-0000-000000000001",
        course_id="00000000-0000-0000-0000-000000000002",
        operation_id="00000000-0000-0000-0000-000000000003",
        planning_inputs=inputs(),
    )
    (tmp_path / "context.json").write_bytes(entry.canonical(context))

    async def prepared(*args):
        return context

    monkeypatch.setattr(entry, "prepare", prepared)
    approval = dict(
        package_sha256="a" * 64,
        version=m.VERSION,
        accept_ADR0052_R03_and_batch_C2=True,
        planning_wire_version=wire.VERSION,
        planning_prompt_version=wire.PROMPT_VERSION,
        explicit_user_authorization=True,
        starts_epoch=int(time.time()),
        expires_epoch=int(time.time()) + 600,
    )
    calls = []
    original = b'{"error":{"type":"fixture_schema_rejection"}}'

    def rejected(request):
        calls.append(json.loads(request.content))
        assert calls[-1] == entry.planning_body(inputs())
        return httpx.Response(400, stream=httpx.ByteStream(original))

    with pytest.raises(SnapshotError, match="HEAD_HTTP_OR_ENCODING"):
        entry.send(
            "plan",
            tmp_path,
            approval,
            transport=httpx.MockTransport(rejected),
            key="offline-fixture-not-a-provider-key",
        )
    assert entry.raw_io.decrypt(tmp_path / "plan.raw.enc", cipher) == original
    assert (tmp_path / "STOP").exists() and (tmp_path / "ACTIVE").exists()
    assert not (tmp_path / "plan.output.json").exists()
    for stage in ("plan", "generate", "repair"):
        with pytest.raises(SnapshotError, match="HEAD_VAULT_STOPPED_OR_UNSAFE"):
            entry.send(
                stage,
                tmp_path,
                approval,
                transport=httpx.MockTransport(rejected),
                key="offline-fixture-not-a-provider-key",
            )
    assert len(calls) == 1
