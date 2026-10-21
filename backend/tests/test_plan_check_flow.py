"""Pre-content stop paths, explicit adapter routing, and trusted audit notes."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import flow_inputs, fresh_operation, sequence
from test_hybrid_resource_review import ReviewGateway
from test_learning_review_cli import config

from app.agents.plan_check import CHECKS, inspect_plan
from app.agents.shared_learning_plan import CallWindow
from app.core.config import ProviderSettings
from app.core.database import create_database_engine
from app.core.provider_target import ApprovedTarget
from app.models.learning import GeneratedResource, LearningOperation
from app.models.learning_publication import LearningPublication
from app.models.learning_review_case import LearningReviewCase
from app.models.plan_check import PlanCheck
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.learning_contract import LearningContractError
from app.services.learning_stage_gateway import LearningStageGateway
from app.services.planned_learning_flow import run_planned_operation
from app.services.provider_gateway import ProviderGateway, StructuredResult, TransportAudit

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[2]


def model_answer(verdict="pass", action=None):
    return dict(
        schema_version="plan-review-result-v1",
        verdict=verdict,
        coverage=dict(checked=CHECKS, unchecked=[]),
        findings=[]
        if action is None
        else [
            dict(
                finding_id="f1",
                category="missing_premise",
                severity="major",
                target_anchor="p1",
                evidence_anchors=["p1"],
                condition_or_counterexample="Synthetic insufficient premise.",
                impact="Cannot infer a single intended plan.",
                suggested_action=action,
            )
        ],
        unresolved=[] if verdict == "pass" else ["Synthetic independent review required."],
    )


class PlanGateway(ReviewGateway):
    def __init__(self, verdict, action=None):
        super().__init__(sequence())
        self.verdict, self.action = verdict, action

    async def generate_structured(self, request, *, retry_safe=False):
        if request.stage == "plan_check":
            self.requests.append(request)
            value = model_answer(self.verdict, self.action)
            return StructuredResult(
                value, "synthetic", transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64)
            )
        return await super().generate_structured(request, retry_safe=retry_safe)


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
@pytest.mark.parametrize(
    "verdict,action,code,status",
    [
        ("needs_human", None, "PLAN_REVIEW_REQUIRED", "failed"),
        ("needs_human", "clarify_user", "GOAL_CLARIFICATION_REQUIRED", "failed"),
        ("reject", None, "PLAN_REJECTED", "rejected"),
    ],
)
def test_precontent_stop_has_bound_evidence_no_half_case_or_publication(
    verdict, action, code, status
):
    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                g = PlanGateway(verdict, action)
                with pytest.raises(LearningContractError, match=code):
                    await run_planned_operation(
                        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                    )
                op = await db.get(LearningOperation, oid, populate_existing=True)
                check = await db.scalar(select(PlanCheck).where(PlanCheck.operation_id == oid))
                assert op.status == status and op.generation_call_count == 2
                assert op.error["check_id"] == str(check.id) and op.error["stage"] == "plan_check"
                assert [r.stage for r in g.requests] == ["plan_generation", "plan_check"]
                for cls in [GeneratedResource, LearningReviewCase, LearningPublication]:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(cls)
                            .where(cls.learning_unit_id == op.learning_unit_id)
                        )
                        == 0
                    )
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_real_adapter_offline_capture_routes_new_prompt_to_review():
    async def run():
        from om_fixtures import plan_fixture

        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                _, _, op, plan = await plan_fixture(db)
                wires = []

                def adapter(base, model, reasoning):
                    host = "api.deepseek.com" if model == "deepseek-flash" else "www.cbbb.fun"
                    guard = SimpleNamespace(
                        approve_base=lambda: ApprovedTarget(base, host, 443, ("8.8.8.8",))
                    )

                    def respond(request):
                        body = json.loads(request.content)
                        wires.append(
                            dict(
                                host=request.headers["host"],
                                sni=request.extensions.get("sni_hostname"),
                                body=body,
                            )
                        )
                        return httpx.Response(
                            200,
                            json=dict(
                                model=model,
                                status="completed",
                                output=[
                                    dict(
                                        type="message",
                                        role="assistant",
                                        status="completed",
                                        content=[
                                            dict(
                                                type="output_text",
                                                text=json.dumps(
                                                    __import__("test_shared_learning_plan").DRAFT
                                                    if model == "deepseek-flash"
                                                    else model_answer()
                                                ),
                                            )
                                        ],
                                    )
                                ],
                                usage=dict(input_tokens=100, output_tokens=100),
                            ),
                        )

                    return ProviderGateway(
                        DeepSeekResponsesAdapter(
                            ProviderSettings(base, "OFFLINE_PLACEHOLDER", model),
                            guard,
                            transport=httpx.MockTransport(respond),
                            reasoning_effort=reasoning,
                        )
                    )

                router = LearningStageGateway(
                    adapter("https://api.deepseek.com", "deepseek-flash", "none"),
                    adapter("https://www.cbbb.fun/v1", "gpt-6-luna", "high"),
                )
                from app.agents.shared_learning_plan import generate_shared_plan

                await generate_shared_plan(router, flow_inputs(), CallWindow())
                result = await inspect_plan(router, CallWindow(), plan, op.id)
                assert result["server_assessment"]["route"] == "accept_plan"
                assert len(wires) == 2 and wires[0]["host"] == "api.deepseek.com"
                assert wires[0]["body"]["model"] == "deepseek-flash"
                assert wires[0]["body"]["reasoning"] == {"effort": "none"}
                assert wires[0]["body"]["max_output_tokens"] == 2048
                assert wires[1]["host"] == "www.cbbb.fun"
                assert wires[1]["sni"] == "www.cbbb.fun"
                body = wires[1]["body"]
                assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "high"}
                assert body["max_output_tokens"] == 8192
                assert body["text"]["format"]["schema"]["$ref"] == "#/$defs/model_result"
                # User authority is limited to one real original field, not arbitrary snapshot text.
                anchors = result["anchor_catalog"]
                assert [
                    a["json_pointer"] for a in anchors if a["source_kind"] == "user_request"
                ] == ["/metadata/goal"]
                assert result["proofs"] == []
                target = os.getenv("EDUMIND_PLAN_WIRE_EVIDENCE")
                if target:
                    Path(target).write_text(
                        json.dumps(
                            dict(
                                kind="actual adapters; MockTransport only; synthetic data",
                                provider_calls=0,
                                wires=wires,
                            ),
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n"
                    )
                request = ReviewGateway([])
                # Routing is stage-owned even with an empty or copied prompt; no Prompt comparison.
                from app.services.provider_gateway import StructuredRequest, TextRequest

                with pytest.raises(LearningContractError, match="LEARNING_STAGE_REQUIRED"):
                    await LearningStageGateway(request, request).generate_structured(
                        StructuredRequest(TextRequest(messages=()), {})
                    )
                await db.rollback()
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_plan_cli_private_read_and_note_do_not_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_REVIEWER_CONFIG", str(config(tmp_path)))
    spec = importlib.util.spec_from_file_location(
        "plan_cli", ROOT / "scripts/review_plan_checks.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                with pytest.raises(LearningContractError):
                    await run_planned_operation(
                        db,
                        owner_id=uid,
                        operation_id=oid,
                        inputs=flow_inputs(),
                        gateway=PlanGateway("needs_human"),
                    )
                row = await db.scalar(select(PlanCheck).where(PlanCheck.operation_id == oid))
                cid = str(row.id)
                digest = row.record_digest
            summary = await cli.run(cli.parser().parse_args(["show", cid]))
            assert "record" not in summary and "notes" not in summary
            args = [
                "note",
                cid,
                "--check-digest",
                digest,
                "--kind",
                "new_request_needed",
                "--reason",
                "Synthetic audit note only",
                "--idempotency-key",
                str(uuid4()),
            ]
            result = await cli.run(cli.parser().parse_args(args))
            assert await cli.run(cli.parser().parse_args(args)) == result
            full = await cli.run(cli.parser().parse_args(["show", cid, "--body"]))
            assert len(full["notes"]) == 1 and full["notes"][0]["reviewer_id"] != "forged"
            path = tmp_path / "plan-private.json"
            await cli.run(cli.parser().parse_args(["show", cid, "--export", str(path)]))
            assert path.stat().st_mode & 0o777 == 0o600
            with pytest.raises(LearningContractError):
                await cli.run(cli.parser().parse_args(["show", cid, "--export", str(path)]))
            async with async_sessionmaker(e)() as db:
                op = await db.get(LearningOperation, oid)
                assert op.status == "failed" and op.generation_call_count == 2
            monkeypatch.delenv("EDUMIND_REVIEWER_CONFIG")
            with pytest.raises(LearningContractError, match="MAINTAINER_NOT_AUTHORIZED"):
                await cli.run(cli.parser().parse_args(["show", cid, "--body"]))
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
@pytest.mark.parametrize("failure", ["schema", "audit", "timeout"])
def test_technical_failure_stops_before_content(failure):
    async def run():
        e = create_database_engine(URL)
        try:
            async with async_sessionmaker(e, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)

                class Broken(PlanGateway):
                    async def generate_structured(self, request, *, retry_safe=False):
                        if request.stage == "plan_check":
                            self.requests.append(request)
                            if failure == "timeout":
                                raise TimeoutError()
                            return StructuredResult(
                                {"bad": True} if failure == "schema" else model_answer(),
                                "synthetic",
                                transport_audit=None
                                if failure == "audit"
                                else TransportAudit("1" * 64, "2" * 64, "3" * 64),
                            )
                        return await super().generate_structured(request, retry_safe=retry_safe)

                g = Broken("pass")
                with pytest.raises((LearningContractError, TimeoutError)):
                    await run_planned_operation(
                        db, owner_id=uid, operation_id=oid, inputs=flow_inputs(), gateway=g
                    )
                op = await db.get(LearningOperation, oid, populate_existing=True)
                assert op.status == "failed" and op.generation_call_count == 2
                assert [r.stage for r in g.requests] == ["plan_generation", "plan_check"]
        finally:
            await e.dispose()

    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="actual isolated PG required")
def test_sse_plan_stop_safe_error_replay(monkeypatch):
    from test_hybrid_learning_operations import api_gateway, guest, headers

    from app.api.learning_sessions import provider_gateway
    from app.main import app

    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
    original = api_gateway()

    class Stop:
        async def generate_structured(self, request, *, retry_safe=False):
            if request.stage == "plan_check":
                original.requests.append(request)
                return StructuredResult(
                    model_answer("needs_human"),
                    "synthetic",
                    transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64),
                )
            return await original.generate_structured(request, retry_safe=retry_safe)

    app.dependency_overrides[provider_gateway] = lambda: Stop()
    try:
        client, csrf = guest()
        response = client.post(
            "/api/learning-sessions",
            headers=headers(csrf, str(uuid4())),
            json={"goal": "学习栈", "generation_protocol": "shared-plan-v1"},
        )
        frames = [
            (part.splitlines()[0][7:], json.loads(part.splitlines()[1][6:]))
            for part in response.text.split("\n\n")
            if part.startswith("event:")
        ]
        error = next(data for kind, data in frames if kind == "error")
        assert error["code"] == "PLAN_REVIEW_REQUIRED" and error["stage"] == "plan_check"
        assert set(error) == {"operation_id", "code", "retryable", "stage", "check_id"}
        assert not {kind for kind, _ in frames} & {"scene_ready", "review_required"}
        state = client.get("/api/learning-operations/" + error["operation_id"]).json()
        assert state["status"] == "failed" and state["error"]["check_id"] == error["check_id"]
        assert len(original.requests) == 2
    finally:
        app.dependency_overrides.clear()
