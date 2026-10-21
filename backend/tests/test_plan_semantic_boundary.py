"""Mechanical preflight and semantic evidence tests; synthetic answers are not quality proof."""

import asyncio
import json
import os
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_learning_plan_persistence import PLAN, REFS
from test_plan_check_flow import model_answer

from app.agents.plan_check import inspect_plan
from app.agents.shared_learning_plan import CallWindow
from app.core.database import create_database_engine
from app.models.learning_plan import LearningPlanVersion
from app.services.learning_contract import LearningContractError, digest
from app.services.learning_policy import POLICY, POLICY_VERSION
from app.services.plan_check import (
    anchor_text,
    owned_plan_check,
    owned_review_binding,
    record_digest,
    save_plan_check,
)
from app.services.provider_gateway import StructuredResult, TransportAudit

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")


def refresh(row):
    row.plan_digest = digest("plan", "learning-plan-v1", plan=row.plan_json)
    row.input_digest = digest("input", "learning-input-v1", snapshot=row.input_snapshot)
    row.references_digest = digest(
        "references", "learning-references-v1", references=row.references_snapshot
    )
    row.policy_digest = digest("policy", row.policy_version, policy=row.policy_snapshot)
    return row


def fixture():
    plan = deepcopy(PLAN)
    snapshot = dict(
        metadata={
            k: plan[k]
            for k in (
                "node_id",
                "goal",
                "graph_version",
                "graph_digest",
                "profile_version",
                "profile_evidence_digest",
                "code_language",
            )
        },
        references=deepcopy(REFS),
        node_ids=[plan["node_id"], *plan["prerequisite_node_ids"]],
        learner_evidence={},
        reference_context=dict(
            source=deepcopy(plan["references"][0]),
            node=dict(
                id=plan["node_id"],
                name="栈",
                description="后进先出：push(4),push(11),pop()返回11。",
                learning_objectives=["不应自动成为本节目标"],
            ),
        ),
    )
    return refresh(
        LearningPlanVersion(
            id=uuid4(),
            user_id=uuid4(),
            learning_unit_id=uuid4(),
            origin_operation_id=uuid4(),
            version=1,
            schema_version="learning-plan-v1",
            plan_json=plan,
            input_snapshot=snapshot,
            references_snapshot=deepcopy(REFS),
            policy_version=POLICY_VERSION,
            policy_snapshot=deepcopy(POLICY),
        )
    )


def binding(row, operation_id=None):
    return dict(
        owner_id=row.user_id,
        unit_id=row.learning_unit_id,
        operation_id=operation_id or row.origin_operation_id,
        plan_id=row.id,
        origin_operation_id=row.origin_operation_id,
        plan_version=row.version,
        plan_digest=row.plan_digest,
        input_digest=row.input_digest,
        reference_digest=row.references_digest,
        policy_digest=row.policy_digest,
    )


class Capture:
    def __init__(self, conflict=False):
        self.requests = []
        self.conflict = conflict

    async def generate_structured(self, request, *, retry_safe=False):
        self.requests.append(request)
        assert not retry_safe
        value = model_answer()
        if self.conflict:
            payload = json.loads(request.prompt.messages[-1].content)
            target = next(
                a for a in payload["anchor_catalog"] if a["source_field"] == "/objectives/0/text"
            )
            value = model_answer("issue")
            value["findings"] = [
                dict(
                    finding_id="conflict",
                    category="plan_internal_conflict",
                    severity="major",
                    target_anchor=target["anchor_id"],
                    evidence_anchors=[target["anchor_id"]],
                    condition_or_counterexample=(
                        "Synthetic: objective17 contradicts actual input/trace19."
                    ),
                    impact="Conflicting commitments.",
                    suggested_action="human_review",
                )
            ]
        return StructuredResult(
            value, "synthetic", transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64)
        )


def test_correct_preflight_semantic_input_and_persistent_source_map():
    row = fixture()
    g = Capture()
    result = asyncio.run(
        inspect_plan(g, CallWindow(), row, row.origin_operation_id, expected_binding=binding(row))
    )
    assert (
        result["server_assessment"]["route"] == "accept_plan"
        and result["schema_version"] == "plan-check-record-v2"
    )
    request = g.requests[0]
    payload = json.loads(request.prompt.messages[-1].content)
    assert payload["unverified_plan"]["shared_example"] == row.plan_json["shared_example"]
    assert (
        payload["authoritative_teaching_goal"]["user_request"]
        == row.input_snapshot["metadata"]["goal"]
    )
    assert (
        payload["relevant_references"]["node"]["description"]
        == row.input_snapshot["reference_context"]["node"]["description"]
    )

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(v) for v in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(v) for v in value))
        return set()

    assert not keys(payload) & {
        "source_digest",
        "digest",
        "input_digest",
        "policy_digest",
        "owner_id",
        "operation_id",
        "plan_id",
        "plan_version",
        "graph_digest",
        "graph_version",
        "path_version_id",
        "reference_bindings",
    }
    wire_anchors = payload["anchor_catalog"]
    full = result["anchor_catalog"]
    assert len(wire_anchors) == len(full)
    for a, b in zip(wire_anchors, full, strict=True):
        assert a["source_text"] == anchor_text(row, b) and a["anchor_id"] == b["anchor_id"]
        assert "source_digest" in b and "source_digest" not in a
    assert any(a["source_kind"] == "reference_context" for a in wire_anchors)
    assert set(request.json_schema["$defs"]) == {"model_result", "finding"}


@pytest.mark.parametrize(
    "bad",
    [
        "owner",
        "unit",
        "operation",
        "origin_operation",
        "plan_id",
        "version",
        "version_bool",
        "schema",
        "plan_digest",
        "input_digest",
        "references_digest",
        "policy_digest",
        "policy_version",
        "reference_item_digest",
        "reference_item_version",
        "input_reference",
        "reference_context_version",
        "metadata",
    ],
)
def test_bad_binding_is_rejected_before_gateway(bad):
    row = fixture()
    expected = binding(row)
    operation = row.origin_operation_id
    if bad in ("owner", "unit", "plan_id"):
        setattr(
            row, {"owner": "user_id", "unit": "learning_unit_id", "plan_id": "id"}[bad], uuid4()
        )
    elif bad == "operation":
        operation = uuid4()
    elif bad == "origin_operation":
        row.origin_operation_id = uuid4()
    elif bad == "version":
        row.version = 2
    elif bad == "version_bool":
        row.version = True
    elif bad == "schema":
        row.schema_version = "unknown"
    elif bad in ("plan_digest", "input_digest", "references_digest", "policy_digest"):
        setattr(row, bad, "0" * 64)
    elif bad == "policy_version":
        row.policy_version = "unknown"
        refresh(row)
    elif bad == "reference_item_digest":
        row.plan_json["references"][0]["digest"] = "f" * 64
        refresh(row)
        expected = binding(row)
    elif bad == "reference_item_version":
        row.plan_json["references"][0]["version"] = "wrong"
        refresh(row)
        expected = binding(row)
    elif bad == "input_reference":
        row.input_snapshot["references"][next(iter(REFS))]["digest"] = "f" * 64
        refresh(row)
        expected = binding(row)
    elif bad == "reference_context_version":
        row.input_snapshot["reference_context"]["source"]["version"] = "wrong"
        refresh(row)
        expected = binding(row)
    elif bad == "metadata":
        row.plan_json["graph_version"] = "wrong"
        refresh(row)
        expected = binding(row)
    g = Capture()
    with pytest.raises(LearningContractError):
        asyncio.run(inspect_plan(g, CallWindow(), row, operation, expected_binding=expected))
    assert not g.requests


def test_digest_literals_in_user_or_teaching_content_are_not_redacted():
    row = fixture()
    text = "比较SHA256字符串" + ("a" * 64) + "；source_digest一词属于本课讲解。"
    row.plan_json["goal"] = text
    row.input_snapshot["metadata"]["goal"] = text
    row.plan_json["shared_example"]["input_description"] = text
    refresh(row)
    g = Capture()
    asyncio.run(inspect_plan(g, CallWindow(), row, row.origin_operation_id))
    payload = json.loads(g.requests[0].prompt.messages[-1].content)
    assert (
        payload["authoritative_teaching_goal"]["user_request"] == text
        and payload["unverified_plan"]["shared_example"]["input_description"] == text
    )


def test_semantic_contradiction_is_not_removed_or_mechanically_auto_passed():
    row = fixture()
    row.plan_json["objectives"][0]["text"] = "固定数组4,6,9之和为17。"
    row.plan_json["shared_example"]["input_description"] = "a={4,6,9}"
    row.plan_json["shared_example"]["steps"][0]["expected_state"] = "s=19"
    refresh(row)
    g = Capture(conflict=True)
    result = asyncio.run(inspect_plan(g, CallWindow(), row, row.origin_operation_id))
    payload = json.loads(g.requests[0].prompt.messages[-1].content)
    assert payload["unverified_plan"]["objectives"][0]["text"].endswith("17。")
    assert payload["unverified_plan"]["shared_example"]["steps"][0]["expected_state"] == "s=19"
    assert result["model_result"]["findings"][0]["category"] == "plan_internal_conflict"
    assert result["server_assessment"]["route"] == "needs_human"


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_owned_preflight_and_v2_reference_anchor_readback_with_legacy_compatibility():
    from om_fixtures import plan_fixture
    from test_plan_check_persistence import bound_record

    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                user, unit, op, row = await plan_fixture(db)
                # Add the context as a new immutable plan, retaining the old version.
                from app.services.learning_plans import save_plan

                snap = deepcopy(row.input_snapshot)
                snap["reference_context"] = {"node": {"name": "栈", "description": "后进先出。"}}
                new = await save_plan(
                    db,
                    owner_id=user.id,
                    unit_id=unit.id,
                    operation_id=op.id,
                    plan=row.plan_json,
                    input_snapshot=snap,
                    references=row.references_snapshot,
                    node_ids={"stack"},
                    policy_version=POLICY_VERSION,
                    policy=POLICY,
                )
                await db.commit()
                oldg = Capture()
                with pytest.raises(LearningContractError):
                    bound = await owned_review_binding(
                        db, row, owner_id=user.id, operation_id=op.id
                    )
                    await inspect_plan(oldg, CallWindow(), row, op.id, expected_binding=bound)
                assert not oldg.requests
                for owner, operation in [(uuid4(), op.id), (user.id, uuid4())]:
                    with pytest.raises(LearningContractError):
                        await owned_review_binding(db, new, owner_id=owner, operation_id=operation)
                bound = await owned_review_binding(db, new, owner_id=user.id, operation_id=op.id)
                result = await inspect_plan(
                    Capture(), CallWindow(), new, op.id, expected_binding=bound
                )
                saved = await save_plan_check(db, result)
                await db.commit()
                found = await owned_plan_check(db, owner_id=user.id, check_id=saved.id)
                assert found.record["schema_version"] == "plan-check-record-v2"
                assert any(
                    a["source_kind"] == "reference_context" for a in found.record["anchor_catalog"]
                )
                legacy = bound_record(row, op)
                savedold = await save_plan_check(db, legacy)
                await db.commit()
                assert (
                    await owned_plan_check(db, owner_id=user.id, check_id=savedold.id)
                ).record_digest == record_digest(legacy)
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_actual_projected_adapter_sends_only_semantic_payload_and_output_schema():
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    import httpx

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from acceptance_support.plan_admission import CandidateReviewAdapter

    from app.core.config import ProviderSettings
    from app.core.provider_target import ApprovedTarget
    from app.services.provider_gateway import ProviderGateway

    row = fixture()
    wires = []

    def reply(request):
        wires.append(json.loads(request.content))
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
                        content=[dict(type="output_text", text=json.dumps(model_answer()))],
                    )
                ],
                usage=dict(input_tokens=1, output_tokens=1),
            ),
        )

    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
        )
    )
    gateway = ProviderGateway(
        CandidateReviewAdapter(
            ProviderSettings("https://www.cbbb.fun/v1", "OFFLINE_PLACEHOLDER", "gpt-6-luna"),
            guard,
            transport=httpx.MockTransport(reply),
            reasoning_effort="high",
        )
    )
    result = asyncio.run(inspect_plan(gateway, CallWindow(), row, row.origin_operation_id))
    assert result["server_assessment"]["route"] == "accept_plan" and len(wires) == 1
    encoded = json.dumps(wires[0])
    assert all(
        str(value) not in encoded
        for value in (
            row.id,
            row.user_id,
            row.learning_unit_id,
            row.plan_digest,
            row.references_digest,
            row.policy_digest,
            row.input_digest,
        )
    )
    schema = wires[0]["text"]["format"]["schema"]
    assert "binding" not in schema.get("$defs", {}) and "anchor" not in schema.get("$defs", {})
    assert "source_digest" not in encoded and wires[0]["reasoning"] == {"effort": "high"}
    assert wires[0]["max_output_tokens"] == 8192


@pytest.mark.parametrize("mutation", [None, "body", "node_id"])
def test_real_graph_reference_body_identity_and_digest_checked_before_call(mutation):
    from dataclasses import asdict

    from app.services.knowledge_graph import default_knowledge_graph_repository

    row = fixture()
    graph = default_knowledge_graph_repository()
    node = asdict(graph.get_node("stack"))
    ref = dict(
        reference_id=f"graph-node:{graph.graph_version}:stack",
        version=graph.graph_version,
        digest=digest("graph-node", "graph-reference-v1", node=node),
    )
    row.plan_json["references"] = [ref]
    row.references_snapshot = {ref["reference_id"]: deepcopy(ref)}
    row.input_snapshot["references"] = deepcopy(row.references_snapshot)
    row.plan_json["graph_version"] = graph.graph_version
    row.input_snapshot["metadata"]["graph_version"] = graph.graph_version
    row.input_snapshot["reference_context"] = dict(source=deepcopy(ref), node=node)
    if mutation == "body":
        row.input_snapshot["reference_context"]["node"]["description"] = "Unbound different body"
    elif mutation == "node_id":
        row.input_snapshot["reference_context"]["node"]["id"] = "queue"
    refresh(row)
    g = Capture()
    if mutation:
        with pytest.raises(LearningContractError, match="PLAN_REFERENCE_BINDING_MISMATCH"):
            asyncio.run(inspect_plan(g, CallWindow(), row, row.origin_operation_id))
        assert not g.requests
    else:
        assert (
            asyncio.run(inspect_plan(g, CallWindow(), row, row.origin_operation_id))[
                "server_assessment"
            ]["route"]
            == "accept_plan"
        )
