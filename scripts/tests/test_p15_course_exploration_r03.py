"""Real experiment adapter exercised only with isolated durable ledger and HTTPX Mock."""

# ruff: noqa: E402
import asyncio
import json
import socket
import sys
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from isolated_diagnostics import p15_course_exploration_r03 as x
from isolated_diagnostics import p15_split_provider as p
from isolated_diagnostics.p15_course_sol_bridge import PROMPT
from app.core.provider_target import ApprovedTarget
from app.services.provider_gateway import TextRequest, ChatMessage, StructuredRequest
from test_p15_split_provider import scene_target, clean_opinion


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("No real networking")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def test_actual_adapter_scene_low_and_source_checkpoint(tmp_path):
    j, identity, adapter, calls = setup(tmp_path)
    try:
        state = asyncio.run(x.review_pending(adapter, identity, verify_current=current))
        assert state == "live_reviews_complete"
        assert len(calls) == 1 and calls[0]["reasoning"] == {"effort": "low"}
        assert j.events("scene_review_finished")[0]["opinion"]["verdict"] == "pass"
        assert j.ledger.usage(j.batch)["output_tokens"] == 100
        asyncio.run(x.review_pending(adapter, identity, verify_current=current))
        assert len(calls) == 1
    finally:
        j.ledger.close()


async def current(target):
    return True


def setup(tmp_path, fault=None):
    grant = dict(
        scope="PHASE-1.5-T038",
        package_sha256="a" * 64,
        batch_id="p15-split-experiment-r03-mock",
        limits=asdict(x.ExplorationLimits()),
        evidence_ref="OFFLINE_SYNTHETIC_NOT_AUTHORITY",
        fee_cap_waiver=True,
    )
    j = x.ExplorationJournal.create(
        tmp_path / "wire", grant["batch_id"], "a" * 64, grant
    )
    identity = p.Identity("D01-known", "test-owner", "test-course")
    j.bind(identity)
    target = scene_target(identity)
    j.freeze(identity, [target])
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        opinion = clean_opinion(target["payload"])
        if fault == "path":
            opinion.update(
                verdict="revise",
                issues=[
                    dict(
                        area="fact",
                        severity="minor",
                        source_pointer="/source/scene/text",
                        evidence_quote="栈",
                        message="synthetic",
                    )
                ],
            )
        response = dict(
            object="response",
            model=body["model"],
            status="completed",
            store=False,
            tools=[],
            instructions=PROMPT + x.compat.SUFFIX,
            reasoning={"effort": "low"},
            usage=dict(
                input_tokens=100,
                output_tokens=100,
                total_tokens=200,
                output_tokens_details={"reasoning_tokens": 11},
            ),
            output=[
                dict(
                    type="reasoning",
                    summary=[],
                    content=[],
                    encrypted_content="MOCK_OPAQUE",
                ),
                dict(
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[dict(type="output_text", text=json.dumps(opinion))],
                ),
            ],
        )
        if fault == "suffix":
            response["instructions"] += " "
        if fault == "usage":
            response["usage"]["total_tokens"] += 1
        return httpx.Response(200, json=response)

    adapter = x.ExplorationAdapter(
        j,
        {"generation": "SYNTHETIC_GEN_KEY", "review": "SYNTHETIC_REVIEW_KEY"},
        lambda role: ApprovedTarget(
            "https://aiapi.world/v1", "aiapi.world", 443, ("8.8.8.8",)
        ),
        lambda: httpx.MockTransport(handler),
    )
    return j, identity, adapter, calls


@pytest.mark.parametrize("fault", ["path", "suffix", "usage"])
def test_wire_failures_stop_preserve_unknown_and_never_replay(tmp_path, fault):
    j, identity, adapter, calls = setup(tmp_path, fault)
    try:
        with pytest.raises((ValueError, x.Refused)):
            asyncio.run(x.review_pending(adapter, identity, verify_current=current))
        assert len(calls) == 1 and not j.events("scene_review_finished")
        row = j.ledger.db.execute("SELECT state FROM attempts").fetchone()
        assert row["state"] == "unknown"
        with pytest.raises(x.Refused):
            asyncio.run(x.review_pending(adapter, identity, verify_current=current))
        assert len(calls) == 1
    finally:
        j.ledger.close()


def test_probe_route_not_admitted_and_schema_cannot_drift(tmp_path):
    j, identity, adapter, calls = setup(tmp_path)
    try:
        request = StructuredRequest(
            TextRequest((ChatMessage("system", PROMPT),), max_output_tokens=100),
            x.compat.schema(),
            "development_review_probe",
        )
        with pytest.raises(x.Refused, match="STAGE_OR_SCHEMA_NOT_FROZEN"):
            asyncio.run(adapter.send(identity, request, retry_safe=False))
        assert calls == []
    finally:
        j.ledger.close()


def test_new_absolute_window_stops_without_any_dispatch(tmp_path):
    tick = [100.0, 100.0]
    grant = dict(
        scope="PHASE-1.5-T038",
        package_sha256="a" * 64,
        batch_id="p15-split-experiment-window-mock",
        limits=asdict(x.ExplorationLimits()),
        evidence_ref="SYNTHETIC_NOT_AUTHORITY",
        fee_cap_waiver=True,
        window_deadline_epoch=105.0,
    )
    j = x.ExplorationJournal.create(
        tmp_path / "window",
        grant["batch_id"],
        "a" * 64,
        grant,
        clock=lambda: tuple(tick),
    )
    try:
        tick[:] = [106.0, 106.0]
        with pytest.raises(x.Refused, match="EXPLICIT_WINDOW_EXPIRED"):
            j.guard()
        assert j.ledger.usage(j.batch)["requests"] == 0
        assert (
            j.ledger.db.execute("SELECT state FROM batches").fetchone()["state"]
            == "stopped"
        )
    finally:
        j.ledger.close()


def test_fourteen_request_ceiling_does_not_reuse_old_243_remainder(tmp_path):
    j, _, _, calls = setup(tmp_path)
    try:
        for n in range(14):
            j.ledger.reserve(
                j.batch, j.package, str(n), input_max=0, output_max=0, fee_max=0
            )
        with pytest.raises(x.Refused, match="BUDGET_EXHAUSTED"):
            j.ledger.reserve(
                j.batch, j.package, "overflow", input_max=0, output_max=0, fee_max=0
            )
        assert j.ledger.usage(j.batch)["requests"] == 14 and calls == []
    finally:
        j.ledger.close()
