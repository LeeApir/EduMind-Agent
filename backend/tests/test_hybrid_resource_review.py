"""Synthetic evidence/coverage checks, distinct from actual model accuracy."""

import asyncio
from copy import deepcopy

import pytest
from test_learning_unit_generator import valid_results
from test_planned_scene_generation import workspace

from app.agents.hybrid_resource_review import RESOURCE_CHECKS, review_resource, route_review
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import LearningContractError
from app.services.provider_gateway import StructuredResult, TransportAudit
from app.services.teaching_actions import anchor_catalog


def answer(verdict="pass", scope="resource"):
    findings = (
        []
        if verdict in ("pass", "needs_human")
        else [
            {
                "category": "fact",
                "severity": "major",
                "anchors": ["a1"],
                "condition_or_counterexample": (
                    "For input x=1 the stated count 2 conflicts with actual count 1."
                ),
                "impact": "The learner receives a false algorithmic count.",
            }
        ]
    )
    return {
        "schema_version": "resource-review-v4",
        "scope": scope,
        "verdict": verdict,
        "findings": findings,
        "coverage": {"checked": sorted(RESOURCE_CHECKS), "unchecked": []},
        "unresolved": ["Need independent source."] if verdict == "needs_human" else [],
    }


class ReviewGateway:
    def __init__(self, values):
        self.values = list(values)
        self.requests = []

    async def generate_structured(self, request, *, retry_safe=False):
        assert not retry_safe
        self.requests.append(request)
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return StructuredResult(
            value, "synthetic", transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64)
        )


def candidate_workspace():
    w = workspace()
    w.stage("explanation", dict(next(iter(valid_results().values())).value))
    return w


@pytest.mark.parametrize("change", ["empty", "coverage", "unknown"])
def test_local_human_routing_does_not_change_model_result(change):
    w = candidate_workspace()
    catalog = anchor_catalog(w.candidates())
    a = answer("revise")
    if change == "empty":
        a["findings"][0]["condition_or_counterexample"] = "fact"
    if change == "coverage":
        a = answer()
        a["coverage"]["checked"] = ["facts"]
    if change == "unknown":
        a = answer()
        a["unresolved"] = ["unknown premise"]
    original = deepcopy(a)
    assert route_review(a, scope="resource", catalog=catalog)["verdict"] == "needs_human"
    assert a == original


def test_anchoring_and_old_schema_are_hard_protocol_failures():
    catalog = anchor_catalog(candidate_workspace().candidates())
    for bad in [dict(answer(), schema_version="resource-review-v3"), answer("revise")]:
        if bad["findings"]:
            bad["findings"][0]["anchors"] = ["no-such-anchor"]
        with pytest.raises(LearningContractError):
            route_review(bad, scope="resource", catalog=catalog)


def test_two_corrections_review_full_candidates_and_exhaust_to_human():
    w = candidate_workspace()
    envelope = w.candidates()[0].envelope
    g = ReviewGateway([answer("revise"), envelope, answer("revise"), envelope, answer("revise")])
    window = CallWindow()
    records = asyncio.run(review_resource(g, window, w, "explanation"))
    assert len(records) == 3 and window.used == 5 and not g.values
    assert records[-1]["result"]["verdict"] == "revise"
    assert records[-1]["local_routing"]["verdict"] == "needs_human"
    assert records[-1]["request_digest"] == "1" * 64
    assert len({r["anchor_catalog"][0]["resource_id"] for r in records}) == 3
    assert len(w.history()) == 3
    assert w.context("code")


def test_clean_pass_and_severe_reject_and_call_failure():
    for verdict in ["pass", "reject", "needs_human"]:
        w = candidate_workspace()
        g = ReviewGateway([answer(verdict)])
        history = asyncio.run(review_resource(g, CallWindow(), w, "explanation"))
        assert history[0]["local_routing"]["verdict"] == verdict
        if verdict == "reject":
            with pytest.raises(LearningContractError):
                w.context("code")
    w = candidate_workspace()
    g = ReviewGateway([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(review_resource(g, CallWindow(), w, "explanation"))
    with pytest.raises(LearningContractError):
        w.context("code")


def test_transport_audit_matches_actual_bytes_without_credentials():
    import hashlib

    import httpx
    from test_deepseek_responses import adapter, prompt, response

    seen = {}

    def respond(request):
        raw = httpx.Response(200, json=response('{"answer":"ok"}'))
        seen["request"] = hashlib.sha256(request.content).hexdigest()
        seen["response"] = hashlib.sha256(raw.content).hexdigest()
        return raw

    from app.services.provider_gateway import StructuredRequest

    result = asyncio.run(
        adapter(httpx.MockTransport(respond)).generate_structured(
            StructuredRequest(prompt(), {"type": "object"})
        )
    )
    assert result.transport_audit.request_digest == seen["request"]
    assert result.transport_audit.response_digest == seen["response"]
    assert len(result.transport_audit.config_digest) == 64


def test_malformed_empty_coverage_and_injected_candidate_code_fail():
    w = candidate_workspace()
    a = answer()
    a["coverage"]["checked"] = []
    with pytest.raises(LearningContractError):
        route_review(a, scope="resource", catalog=anchor_catalog(w.candidates()))
    c = w.candidates()[0]
    w.disposition(c.role, c.id, "pass")
    code = dict(list(valid_results().values())[1].value)
    code["content"] = dict(code["content"], source='eval("1+1")')
    w.stage("code", code)
    g = ReviewGateway([])
    with pytest.raises(LearningContractError):
        asyncio.run(review_resource(g, CallWindow(), w, "code"))
    assert not g.requests


@pytest.mark.skipif(
    not __import__("os").getenv("EDUMIND_TEST_DATABASE_URL"), reason="actual PG required"
)
def test_review_records_are_bound_and_append_only():
    import os

    from om_fixtures import plan_fixture
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import create_database_engine
    from app.services.learning_review_records import plan_binding, save_review

    async def exercise():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                user, unit, op, plan = await plan_fixture(db)
                w = candidate_workspace()
                w.binding = plan_binding(plan, op.id)
                w.stage("explanation", w.candidates()[0].envelope)
                records = await review_resource(
                    ReviewGateway([answer()]), CallWindow(), w, "explanation"
                )
                row = await save_review(db, records[0])
                await db.commit()
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text(
                                "UPDATE learning_review_records SET record='{}'::jsonb WHERE id=:id"
                            ),
                            {"id": row.id},
                        )
                bad = deepcopy(records[0])
                bad["binding"]["plan_digest"] = "f" * 64
                with pytest.raises(LearningContractError):
                    await save_review(db, bad)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_missing_reference_context_is_not_automatic_pass():
    w = candidate_workspace()
    w.reference_context = None
    w.input_snapshot["reference_context"] = None
    from app.services.learning_contract import digest

    w.binding["input_digest"] = digest("input", "learning-input-v1", snapshot=w.input_snapshot)
    w.stage("explanation", w.candidates()[0].envelope)
    records = asyncio.run(
        review_resource(ReviewGateway([answer()]), CallWindow(), w, "explanation")
    )
    assert records[0]["result"]["verdict"] == "pass"
    assert records[0]["local_routing"]["verdict"] == "needs_human"
