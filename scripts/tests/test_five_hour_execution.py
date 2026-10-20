"""Offline transport and durable-limit regressions; never a model-quality result."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.five_hour_runtime import ORDER, RunLedger  # noqa: E402
from acceptance_support.qwen_review_budget import sha  # noqa: E402
from acceptance_support.luna_high_candidate import offline_router  # noqa: E402
from acceptance_support.om_diagnostic import valid_review  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402
from run_five_hour_acceptance import (  # noqa: E402
    AuditTransport,
    BASE,
    independent_review,
    generated_course,
    execute_case,
    check_audit_coverage,
    load_keys,
    env_metadata,
    inspect_body,
)


def ledger(tmp_path, now=None):
    now = now or [1000.0]
    return RunLedger(tmp_path / "ledger.sqlite", "a" * 64, t0=1000, now=lambda: now[0])


def complete_case(run_ledger, name, count):
    run_ledger.start_case(name)
    for _ in range(count):
        n = run_ledger.reserve(name, "b" * 64)
        run_ledger.complete_call(n, "c" * 64)
    run_ledger.finish_case(name, "d" * 64)
    run_ledger.assess(name, "e" * 64)


def test_order_assessment_and_crash_cannot_replay(tmp_path):
    run_ledger = ledger(tmp_path)
    with pytest.raises(ValueError, match="PREVIOUS_GPT"):
        run_ledger.start_case("U02")
    run_ledger.start_case("U01")
    run_ledger.reserve("U01", "b" * 64)
    recovered = RunLedger(run_ledger.path, run_ledger.digest, now=lambda: 1001)
    with pytest.raises(ValueError, match="REPLAY"):
        recovered.start_case("U01")
    with pytest.raises(ValueError, match="UNKNOWN_SEND"):
        recovered.finish_case("U01", "d" * 64)
    with pytest.raises(ValueError, match="UNKNOWN_SEND"):
        recovered.reserve("U01", "b" * 64)


def test_capacity_reserved_without_creating_fake_calls(tmp_path):
    run_ledger = ledger(tmp_path)
    assert run_ledger.snapshot()["calls"] == []
    for name in ORDER[:12]:
        complete_case(run_ledger, name, 1)
    complete_case(run_ledger, "A01", 20)  # twelve shared extras
    run_ledger.start_case("A02")
    for _ in range(12):  # remaining four extras
        n = run_ledger.reserve("A02", "b" * 64)
        run_ledger.complete_call(n, "c" * 64)
    with pytest.raises(ValueError, match="SHARED_EXTRA"):
        run_ledger.reserve("A02", "b" * 64)
    run_ledger.finish_case("A02", "d" * 64)
    run_ledger.assess("A02", "e" * 64)
    complete_case(run_ledger, "A03", 8)
    complete_case(run_ledger, "A04", 8)
    assert len(run_ledger.snapshot()["calls"]) == 60


def test_unused_baseline_not_reallocated(tmp_path):
    run_ledger = ledger(tmp_path)
    for name in ORDER[:12]:
        complete_case(run_ledger, name, 1)
    complete_case(
        run_ledger, "A01", 1
    )  # seven unused normal calls do not become extras
    complete_case(run_ledger, "A02", 20)
    run_ledger.start_case("A03")
    for _ in range(12):
        n = run_ledger.reserve("A03", "b" * 64)
        run_ledger.complete_call(n, "c" * 64)
    with pytest.raises(ValueError, match="SHARED_EXTRA"):
        run_ledger.reserve("A03", "b" * 64)


@pytest.mark.parametrize("elapsed,reason", [(16200, "DEADLINE"), (-1, "BACKWARD")])
def test_deadline_and_clock_regression(tmp_path, elapsed, reason):
    now = [1000.0]
    run_ledger = ledger(tmp_path, now)
    now[0] += elapsed
    with pytest.raises(ValueError, match=reason):
        run_ledger.start_case("U01")


def test_five_hour_assessment_deadline_and_red_stop(tmp_path):
    now = [1000.0]
    run_ledger = ledger(tmp_path, now)
    run_ledger.start_case("U01")
    n = run_ledger.reserve("U01", "b" * 64)
    run_ledger.complete_call(n, "c" * 64)
    run_ledger.finish_case("U01", "d" * 64)
    now[0] += 18000
    with pytest.raises(ValueError, match="DEADLINE"):
        run_ledger.assess("U01", "e" * 64)
    # Independent ledger shows red halt survives reconstruction.
    other = tmp_path / "other"
    other.mkdir()
    run_ledger = ledger(other)
    complete_case(run_ledger, "U01", 1)
    run_ledger.stop("RED_EVENT")
    with pytest.raises(ValueError, match="STOPPED"):
        RunLedger(run_ledger.path, run_ledger.digest, now=lambda: 1001).start_case(
            "U02"
        )


@pytest.mark.parametrize(
    "name", [*(f"U{i:02}" for i in range(1, 9)), *(f"R{i:02}" for i in range(1, 5))]
)
def test_actual_review_entry_reproduces_frozen_wire(name):
    async def run():
        case = json.loads((BASE / "cases" / (name + ".json")).read_text())
        router, gen, reviews, _ = offline_router(valid_review(case["scope"]))
        result = await independent_review(case, router)
        expected = json.loads((BASE / "requests" / (name + ".json")).read_text())
        assert (
            not gen and len(reviews) == 1 and sha(reviews[0]) == expected["wire_sha256"]
        )
        assert (
            result["course_state"] is None
            and result["production_publish_performed"] is False
        )

    asyncio.run(run())


def test_transport_records_before_send_and_retains_timeout(tmp_path):
    async def run():
        run_ledger = ledger(tmp_path)
        run_ledger.start_case("U01")
        expected = json.loads((BASE / "requests/U01.json").read_text())
        wire = bytes.fromhex(expected["wire_hex"])
        context = dict(
            case="U01",
            ledger=run_ledger,
            directory=tmp_path,
            keys=("PLACEHOLDER_SECRET",),
            call_ids=[],
            completed=[],
            logical_input_sha256="a" * 64,
            business_schema={},
        )

        def timeout(request):
            assert len(run_ledger.snapshot()["calls"]) == 1
            assert (tmp_path / "01-request.json").is_file()
            raise httpx.ConnectTimeout("synthetic")

        t = AuditTransport(
            context,
            "https://www.cbbb.fun/v1",
            "gpt-6-luna",
            "high",
            ApprovedTarget(
                "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
            ),
            httpx.MockTransport(timeout),
        )
        request = httpx.Request(
            "POST",
            "https://8.8.8.8/v1/responses",
            content=wire,
            headers={"host": "www.cbbb.fun"},
            extensions={"sni_hostname": "www.cbbb.fun"},
        )
        with pytest.raises(httpx.ConnectTimeout):
            await t.handle_async_request(request)
        assert run_ledger.snapshot()["run"][3] == "SEND_OR_RECEIPT_UNCERTAIN"
        assert run_ledger.snapshot()["calls"][0][2] == "reserved"
        await t.aclose()

    asyncio.run(run())


def test_partial_response_is_saved_on_read_timeout(tmp_path):
    class Partial(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"partial":'
            raise httpx.ReadTimeout("synthetic midstream timeout")

    async def run():
        run_ledger = ledger(tmp_path)
        run_ledger.start_case("U01")
        wire = bytes.fromhex(
            json.loads((BASE / "requests/U01.json").read_text())["wire_hex"]
        )
        context = dict(
            case="U01",
            ledger=run_ledger,
            directory=tmp_path,
            keys=("OFFLINE_KEY",),
            call_ids=[],
            completed=[],
            logical_input_sha256="a" * 64,
            business_schema={},
        )
        transport = AuditTransport(
            context,
            "https://www.cbbb.fun/v1",
            "gpt-6-luna",
            "high",
            ApprovedTarget(
                "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
            ),
            httpx.MockTransport(lambda r: httpx.Response(200, stream=Partial())),
        )
        request = httpx.Request(
            "POST",
            "https://8.8.8.8/v1/responses",
            content=wire,
            headers={"host": "www.cbbb.fun"},
            extensions={"sni_hostname": "www.cbbb.fun"},
        )
        with pytest.raises(httpx.ReadTimeout):
            await transport.handle_async_request(request)
        assert (tmp_path / "01-partial-response.bin").read_bytes() == b'{"partial":'
        receipt = json.loads((tmp_path / "01-failure-receipt.json").read_text())
        assert receipt["http_status"] == 200 and receipt["raw_complete"] is False
        assert (
            receipt["usage"] is None
            and run_ledger.snapshot()["calls"][0][2] == "reserved"
        )
        await transport.aclose()

    asyncio.run(run())


def test_decoded_limit_and_compressed_secret_are_checked():
    import gzip

    raw = gzip.compress(b"SYNTHETIC_KEY")
    with pytest.raises(ValueError, match="SECRET_REFLECTED"):
        inspect_body(
            raw,
            httpx.Headers({"content-encoding": "gzip"}),
            ("SYNTHETIC_KEY",),
            complete=True,
        )
    bomb = gzip.compress(b"x" * (4 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="DECODED_RESPONSE_LIMIT"):
        inspect_body(
            bomb, httpx.Headers({"content-encoding": "gzip"}), (), complete=True
        )


def test_transport_rejects_wrong_route_before_count(tmp_path):
    async def run():
        run_ledger = ledger(tmp_path)
        run_ledger.start_case("U01")
        c = dict(
            case="U01",
            ledger=run_ledger,
            directory=tmp_path,
            keys=(),
            call_ids=[],
            completed=[],
        )
        t = AuditTransport(
            c,
            "https://www.cbbb.fun/v1",
            "gpt-6-luna",
            "high",
            ApprovedTarget(
                "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
            ),
            httpx.MockTransport(lambda r: pytest.fail("must not send")),
        )
        wire = bytes.fromhex(
            json.loads((BASE / "requests/U01.json").read_text())["wire_hex"]
        )
        req = httpx.Request(
            "POST",
            "https://8.8.8.8/v1/responses",
            content=wire,
            headers={"host": "evil.example"},
        )
        with pytest.raises(ValueError, match="TARGET_CHANGED"):
            await t.handle_async_request(req)
        assert not run_ledger.snapshot()["calls"]
        await t.aclose()

    asyncio.run(run())


def test_live_entry_mock_transport_records_all_evidence(tmp_path, monkeypatch):
    import run_five_hour_acceptance as runtime

    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    from app.core.provider_target import ProviderTargetGuard

    monkeypatch.setattr(
        ProviderTargetGuard,
        "approve_base",
        lambda self: ApprovedTarget(self.base_url, "www.cbbb.fun", 443, ("8.8.8.8",)),
    )

    def reply(request):
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(valid_review("unit")),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        )

    # Target approval is mocked, transport is MockTransport: no real DNS/HTTP.
    monkeypatch.setattr(
        httpx, "AsyncHTTPTransport", lambda **kw: httpx.MockTransport(reply)
    )
    run_ledger = ledger(tmp_path)
    run_ledger.start_case("U01")
    result = asyncio.run(
        execute_case(
            "U01", run_ledger, tmp_path, "NOT_USED", ("OFFLINE_GEN", "OFFLINE_REVIEW")
        )
    )
    assert result["state"] == "awaiting_gpt"
    assert run_ledger.snapshot()["calls"][0][2] == "complete"
    for suffix in ("request.json", "response.bin", "receipt.json", "parsed.json"):
        assert (tmp_path / ("01-" + suffix)).is_file()
    assert (
        json.loads((tmp_path / "01-parsed.json").read_text())["usage"]["output_tokens"]
        == 100
    )


def test_archived_key_selection_requires_exact_connection(tmp_path):
    path = tmp_path / ".env"
    path.write_text("""# EDUMIND_PROVIDER_BASE_URL=https://api.deepseek.com
# EDUMIND_PROVIDER_API_KEY=SYNTHETIC_DS
# EDUMIND_PROVIDER_MODEL=deepseek-flash
EDUMIND_PROVIDER_BASE_URL=https://www.cbbb.fun/v1
EDUMIND_PROVIDER_API_KEY=SYNTHETIC_LUNA
EDUMIND_PROVIDER_MODEL=gpt-6-luna
EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=responses_json_schema
""")
    path.chmod(0o600)
    assert load_keys(env_metadata(path), path) == ("SYNTHETIC_DS", "SYNTHETIC_LUNA")
    path.write_text(path.read_text().replace("deepseek-flash", "unapproved-model"))
    with pytest.raises(ValueError, match="EXACT_ARCHIVED"):
        load_keys(env_metadata(path), path)


def test_all_auxiliary_assertions_must_be_checked(tmp_path):
    record = {
        "result": {
            "findings": [],
            "coverage": {"unchecked": []},
            "unresolved": ["An auxiliary statement cannot disappear."],
        },
        "anchor_catalog": [],
    }
    (tmp_path / "review.json").write_text(json.dumps(record))
    result = {
        "case_id": "A01",
        "review_artifact_paths": ["review.json"],
        "resources": [],
    }
    assessment = {"claim_checks": [], "citation_checks": []}
    with pytest.raises(ValueError, match="ALL_REVIEW_ASSERTIONS"):
        check_audit_coverage(assessment, result, root=tmp_path)
    assessment["claim_checks"].append(
        {
            "review_artifact_path": "review.json",
            "json_pointer": "/result/unresolved/0",
            "quoted_text": record["result"]["unresolved"][0],
        }
    )
    check_audit_coverage(assessment, result, root=tmp_path)


def test_browser_server_blocks_generation_and_foreign_reads():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from serve_five_hour_results import readonly_app

    upstream = FastAPI()
    calls = []

    @upstream.get("/api/learning-units/{unit}")
    def read_unit(unit):
        calls.append(unit)
        return {"id": unit}

    result = {
        "operation_id": "op1",
        "learning_unit_id": "unit1",
        "course_state": "completed",
        "isolated_publication": {"version": 2},
    }
    client = TestClient(readonly_app(upstream, result, "SYNTHETIC_TOKEN"))
    assert (
        client.get("/api/learning-units/unit1?publication_version=2").status_code == 200
    )
    assert client.get("/api/learning-units/foreign").status_code == 403
    assert (
        client.post("/api/learning-sessions", json={"goal": "new"}).status_code == 403
    )
    assert client.post("/api/review-cases/a/decision").status_code == 403
    assert calls == ["unit1"]
    bootstrap = client.get("/api/__acceptance/bootstrap")
    assert "edumind:last-learning-operation" in bootstrap.text
    assert "SYNTHETIC_TOKEN" not in bootstrap.text
    assert "HttpOnly" in bootstrap.headers["set-cookie"]


def test_frozen_raw_goals_resolve_without_model_calls():
    from app.agents.goal_node_resolver import resolve_goal_node
    from app.services.knowledge_graph import default_knowledge_graph_repository

    class NoCalls:
        async def generate_structured(self, *args, **kwargs):
            pytest.fail("raw goal must not introduce hidden call")

    async def run():
        for n in range(1, 5):
            case = json.loads((BASE / "cases" / f"A{n:02}.json").read_text())
            resolved = await resolve_goal_node(
                case["original_request"],
                graph=default_knowledge_graph_repository(),
                gateway=NoCalls(),
            )
            if n in (2, 3):
                assert resolved.node is None and resolved.reason == "ambiguous_aliases"
                assert case["input_snapshot"]["metadata"]["node_id"] in {
                    c.id for c in resolved.candidates
                }
            else:
                assert resolved.node.id == case["input_snapshot"]["metadata"]["node_id"]

    asyncio.run(run())


@pytest.mark.parametrize("name", ["A01", "A02", "A03", "A04"])
def test_generated_service_entry_pg(name):
    """Opt-in real isolated PG, scripted gateway; not a candidate-quality result."""
    import os

    url = os.getenv("EDUMIND_FIVE_HOUR_TEST_URL")
    if not url:
        pytest.skip("requires prepared dedicated five-hour PG")
    sys.path.insert(0, str(ROOT / "backend/tests"))
    from test_hybrid_learning_publication import sequence
    from test_hybrid_resource_review import ReviewGateway

    async def run():
        # A01's first wire is tested separately; this exercises real persistence/gates.
        case = json.loads((BASE / "cases" / (name + ".json")).read_text())
        values = deepcopy(sequence())
        values[0]["reference_ids"] = list(case["input_snapshot"]["references"])
        result = await generated_course(case, ReviewGateway(values), url)
        assert result["course_state"] == "completed"
        assert result["operation_calls"] == 8
        assert len(result["reviews"]) == 4 and len(result["resources"]) == 3
        assert result["isolated_publication"]["approval_source"] == "auto"
        assert result["new_code_executed"] is False
        if name in ("A02", "A03"):
            assert result["raw_goal_selection"]["node_id"] is None
            assert (
                result["raw_goal_selection"]["manual_clarification"]["reviewer"]
                == "Lee"
            )

    previous = os.environ.get("EDUMIND_PRODUCT_MODE")
    os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
    try:
        asyncio.run(run())
    finally:
        if previous is None:
            os.environ.pop("EDUMIND_PRODUCT_MODE", None)
        else:
            os.environ["EDUMIND_PRODUCT_MODE"] = previous
