"""Offline controller end-to-end tests; all HTTP is a controlled MockTransport."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import threading

import httpx
import pytest

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as controller
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_pilot_wire_execution import response
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC


def grant(arm, path):
    return dict(
        batch="dev",
        ledger_path=str(path.absolute()),
        slot="slot",
        arm=arm,
        spec=SPEC,
        calls=4 if arm == "B" else 5,
        input=8_000_000,
        output=40_000,
        request_bytes=8_000_000,
        deadline=4_000_000_000,
    )


def package_grant(path, *, calls=9, output=72_000):
    return dict(
        batch="dev",
        ledger_path=str(path.absolute()),
        slots=[dict(slot="slot", arm=arm, spec=SPEC) for arm in ("B", "C")],
        calls=calls,
        input=16_000_000,
        output=output,
        request_bytes=8_000_000,
        deadline=4_000_000_000,
    )


def handler_for(arm, seen, *, fault=None):
    reviews = 0

    def handler(request):
        nonlocal reviews
        body = json.loads(request.content)
        payload = json.loads(body["input"][1]["content"])
        role = "review" if "cells" in payload else "generation"
        assert str(request.url) == controller.wire.ROUTES[role]["url"]
        assert request.headers["content-type"] == "application/json"
        assert request.headers["accept-encoding"] == "identity"
        assert "authorization" not in request.headers
        seen.append((body, payload))
        if "cells" in payload:
            reviews += 1
            paragraph = next(
                cell for cell in payload["cells"] if cell["kind"] == "paragraph"
            )
            value = dict(
                candidate_id=payload["candidate_id"],
                verdict="revise" if reviews == 1 else "pass",
                uncertainty="",
                issues=[],
            )
            if reviews == 1:
                value["issues"] = [
                    dict(
                        severity="minor",
                        area="difficulty",
                        target_id=paragraph["id"],
                        evidence_quote=paragraph["text"][:4],
                        reason="需要补充解释。",
                    )
                ]
        elif "original" in payload:
            value = deepcopy(payload["original"])
            value["paragraphs"][0]["text"] += " 补充解释。"
        elif body["text"]["format"]["schema"] == c.schema_for("C_plan"):
            value = dict(spec_id=payload["spec_id"], objective_ids=list(c.GOALS))
        else:
            value = content() if arm == "C" else b_fixture(SPEC)
        raw = response(body, value)
        if fault == "unknown_usage":
            del raw["usage"]
        elif fault == "over_usage":
            raw["usage"]["input_tokens"] = 8_000_001
            raw["usage"]["total_tokens"] = 8_000_021
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(raw, ensure_ascii=False).encode())
        )

    return handler


def attest(candidate, opinion, receipt):
    # Test-only independent fixture; this is not a semantic assessment.
    assert opinion["issues"][0]["reason"] == "需要补充解释。"
    return dict(
        candidate_digest=candidate["artifact_digest"],
        review_receipt_digest=receipt["receipt_digest"],
        issues_digest=digest(opinion["issues"]),
        reviewer="offline-fixture-reviewer",
        approved=True,
    )


@pytest.mark.parametrize("arm", ["B", "C"])
def test_full_generation_review_repair_rereview_uses_actual_mock_responses(
    tmp_path, arm
):
    seen = []
    instance = controller.Controller(
        tmp_path / "ledger.db",
        grant(arm, tmp_path / "ledger.db"),
        httpx.MockTransport(handler_for(arm, seen)),
    )
    result = asyncio.run(instance.run(attest))
    assert (
        result["status"] == "mock_advisory_pass" and result["real_provider_calls"] == 0
    )
    assert len(result["versions"]) == len(result["opinions"]) == 2
    assert (
        result["opinions"][0]["issues"] and result["opinions"][1]["verdict"] == "pass"
    )
    assert (
        result["versions"][1]["identity"]["parent_digest"]
        == result["versions"][0]["artifact_digest"]
    )
    assert len(seen) == (4 if arm == "B" else 5)
    for body, payload in seen:
        if "cells" in payload:
            system = body["input"][0]["content"]
            assert "target_catalog" not in system
            assert "id field of an actually supplied cells item" in system
            assert "same item's text field" in system
    rows = list(instance.db.execute("SELECT * FROM attempts ORDER BY ordinal"))
    assert all(
        row["state"] == "responded"
        and row["input_used"] == 10
        and row["output_used"] == 20
        for row in rows
    )
    assert rows[-1]["previous_receipt"]
    assert instance.status() == "complete"
    replay = asyncio.run(instance.run(attest))
    assert (
        replay == result
        and instance.status() == "complete"
        and len(seen) == (4 if arm == "B" else 5)
    )
    instance.close()
    reopened = controller.Controller(
        tmp_path / "ledger.db",
        grant(arm, tmp_path / "ledger.db"),
        httpx.MockTransport(handler_for(arm, seen)),
    )
    replay = asyncio.run(reopened.run(attest))
    assert (
        replay == result
        and reopened.status() == "complete"
        and len(seen) == (4 if arm == "B" else 5)
    )
    reopened.close()


@pytest.mark.parametrize("fault", ["unknown_usage", "over_usage"])
def test_unknown_or_over_reserved_usage_stops_and_preserves_raw(tmp_path, fault):
    seen = []
    instance = controller.Controller(
        tmp_path / "ledger.db",
        grant("B", tmp_path / "ledger.db"),
        httpx.MockTransport(handler_for("B", seen, fault=fault)),
    )
    with pytest.raises((c.ContractError, ValueError)):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT * FROM attempts").fetchone()
    assert instance.status() == "stopped" and row["response"] and len(seen) == 1
    assert row["input_reserved"] > 0 and row["output_reserved"] == 8000
    instance.close()


def test_stop_while_http_in_flight_keeps_late_response_without_advancing(tmp_path):
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        seen = []
        sync_handler = handler_for("B", seen)

        async def handler(request):
            started.set()
            await release.wait()
            return sync_handler(request)

        instance = controller.Controller(
            tmp_path / "ledger.db",
            grant("B", tmp_path / "ledger.db"),
            httpx.MockTransport(handler),
        )
        task = asyncio.create_task(instance.run(attest))
        await started.wait()
        await instance.stop()
        release.set()
        with pytest.raises(c.ContractError, match="MOCK_LATE_RESPONSE"):
            await task
        row = instance.db.execute("SELECT * FROM attempts").fetchone()
        assert instance.status() == "stopped" and row["state"] == "late"
        assert row["response"] and row["input_used"] == 10 and len(seen) == 1
        instance.close()

    asyncio.run(exercise())


def test_grant_is_readonly_copy_and_wrong_grant_does_not_leak_lock(tmp_path):
    path = tmp_path / "ledger.db"
    seen = []
    transport = httpx.MockTransport(handler_for("B", seen))
    instance = controller.Controller(
        path, grant("B", tmp_path / "ledger.db"), transport
    )
    altered = instance.grant
    altered["calls"] = 99
    assert instance.grant["calls"] == 4
    instance.close()
    wrong = grant("B", tmp_path / "ledger.db")
    wrong["input"] -= 1
    with pytest.raises(c.ContractError, match="MOCK_GRANT_BINDING"):
        controller.Controller(path, wrong, transport)
    correct = controller.Controller(path, grant("B", tmp_path / "ledger.db"), transport)
    correct.close()


def test_expired_window_never_sends(tmp_path):
    seen = []
    expired = grant("B", tmp_path / "ledger.db")
    expired["deadline"] = 1
    instance = controller.Controller(
        tmp_path / "ledger.db", expired, httpx.MockTransport(handler_for("B", seen))
    )
    with pytest.raises(c.ContractError, match="MOCK_STOPPED_OR_EXPIRED"):
        asyncio.run(instance.run(attest))
    assert not seen and instance.status() == "stopped"
    instance.close()


def test_stale_b_feedback_does_not_send_repair(tmp_path):
    seen = []
    instance = controller.Controller(
        tmp_path / "ledger.db",
        grant("B", tmp_path / "ledger.db"),
        httpx.MockTransport(handler_for("B", seen)),
    )

    def stale(candidate, opinion, receipt):
        record = attest(candidate, opinion, receipt)
        record["review_receipt_digest"] = "0" * 64
        return record

    with pytest.raises(c.ContractError, match="MOCK_B_FEEDBACK_ATTESTATION"):
        asyncio.run(instance.run(stale))
    assert len(seen) == 2 and instance.status() == "stopped"
    instance.close()


def test_schema_echo_and_reasoning_quarantine_preserve_raw():
    payload = {"cells": []}
    raw_body, _ = budget.build(
        "review_B", payload, budget.DevelopmentPolicy(100_000, 200_000, 8000)
    )
    body = json.loads(raw_body)
    reply = response(
        body, {"candidate_id": "x", "verdict": "pass", "uncertainty": "", "issues": []}
    )
    reply["text"] = {"format": deepcopy(body["text"]["format"])}
    reply["output"].insert(
        0, {"type": "reasoning", "summary": [], "encrypted_content": "opaque"}
    )
    original = json.dumps(reply).encode()
    private, echo = controller.response_for_validation(raw_body, original, "review")
    assert (
        echo == "matched"
        and json.loads(private)["output"][0]["encrypted_content"] is None
    )
    assert json.loads(original)["output"][0]["encrypted_content"] == "opaque"
    assert (
        controller.wire.validate(body, private, "review")[0].value["verdict"] == "pass"
    )
    del reply["text"]["format"]["schema"]
    assert (
        controller.response_for_validation(
            raw_body, json.dumps(reply).encode(), "review"
        )[1]
        == "unknown"
    )
    reply["text"]["format"]["schema"] = {"type": "string"}
    with pytest.raises(c.ContractError, match="MOCK_SCHEMA_ECHO"):
        controller.response_for_validation(
            raw_body, json.dumps(reply).encode(), "review"
        )
    del reply["text"]
    reply["output"][0]["encrypted_content"] = "x" * 8193
    with pytest.raises(c.ContractError, match="MOCK_REASONING_BOUND"):
        controller.response_for_validation(
            raw_body, json.dumps(reply).encode(), "review"
        )


def test_stop_during_expansion_prevents_review_dispatch(tmp_path, monkeypatch):
    async def exercise():
        entered, release = threading.Event(), threading.Event()
        real = controller.worker.expand

        def wait_expand(*args):
            entered.set()
            release.wait(5)
            return real(*args)

        monkeypatch.setattr(controller.worker, "expand", wait_expand)
        seen = []
        instance = controller.Controller(
            tmp_path / "ledger.db",
            grant("B", tmp_path / "ledger.db"),
            httpx.MockTransport(handler_for("B", seen)),
        )
        task = asyncio.create_task(instance.run(attest))
        assert await asyncio.to_thread(entered.wait, 2)
        await instance.stop()
        release.set()
        with pytest.raises(c.ContractError, match="MOCK_STOPPED"):
            await task
        assert len(seen) == 1 and instance.status() == "stopped"
        instance.close()

    asyncio.run(exercise())


def test_recovery_with_sent_attempt_stops_and_forbids_retry(tmp_path):
    path = tmp_path / "ledger.db"
    seen = []
    instance = controller.Controller(
        path,
        grant("B", tmp_path / "ledger.db"),
        httpx.MockTransport(handler_for("B", seen)),
    )
    instance.db.execute(
        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES ('slot','B',0,'B_generate',x'7b7d','hash',NULL,100,8000,'sent')"
    )
    instance._seal()  # Simulate a crash after durable sent state.
    instance.close()
    recovered = controller.Controller(
        path,
        grant("B", tmp_path / "ledger.db"),
        httpx.MockTransport(handler_for("B", seen)),
    )
    assert recovered.status() == "stopped"
    assert recovered.db.execute("SELECT state FROM attempts").fetchone()[0] == "unknown"
    with pytest.raises(c.ContractError):
        asyncio.run(recovered.run(attest))
    assert not seen
    recovered.close()


def test_recovery_after_persisted_response_replays_without_resending(tmp_path):
    path = tmp_path / "ledger.db"
    seen = []
    transport = httpx.MockTransport(handler_for("B", seen))
    first = controller.Controller(path, grant("B", tmp_path / "ledger.db"), transport)
    asyncio.run(first._exchange("B_generate", old.baseline_input(SPEC)))
    assert len(seen) == 1
    first.close()
    recovered = controller.Controller(
        path, grant("B", tmp_path / "ledger.db"), transport
    )
    result = asyncio.run(recovered.run(attest))
    assert result["status"] == "mock_advisory_pass"
    assert len(seen) == 4
    recovered.close()


def test_mismatched_replay_request_stops_before_any_new_http(tmp_path):
    path = tmp_path / "ledger.db"
    seen = []
    transport = httpx.MockTransport(handler_for("B", seen))
    first = controller.Controller(path, grant("B", tmp_path / "ledger.db"), transport)
    asyncio.run(first._exchange("B_generate", old.baseline_input(SPEC)))
    first.db.execute("UPDATE attempts SET previous_receipt='forged' WHERE ordinal=0")
    first._seal()  # Exercise replay checks even with a matching local seal.
    first.close()
    recovered = controller.Controller(
        path, grant("B", tmp_path / "ledger.db"), transport
    )
    with pytest.raises(c.ContractError, match="MOCK_REPLAY_BINDING"):
        asyncio.run(recovered.run(attest))
    assert recovered.status() == "stopped" and len(seen) == 1
    recovered.close()


def test_simultaneous_run_cannot_dispatch_twice(tmp_path):
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        seen = []
        handler = handler_for("B", seen)

        async def delayed(request):
            started.set()
            await release.wait()
            return handler(request)

        instance = controller.Controller(
            tmp_path / "ledger.db",
            grant("B", tmp_path / "ledger.db"),
            httpx.MockTransport(delayed),
        )
        first = asyncio.create_task(instance.run(attest))
        await started.wait()
        with pytest.raises(c.ContractError):
            await instance.run(attest)
        release.set()
        with pytest.raises(c.ContractError):
            await first
        assert len(seen) == 1 and instance.status() == "stopped"
        instance.close()

    asyncio.run(exercise())


def test_valid_large_output_is_not_rejected_by_old_64k_phase_gate():
    value = b_fixture(SPEC)
    value["paragraphs"] = [dict(key=f"p{i}", text="字" * 3990) for i in range(8)]
    for question in value["questions"].values():
        question["stem"] = "题" * 3990
        question["explanation"] = "解" * 3990
    # This boundary fixture must also satisfy the 128,000-byte raw payload cap.
    for row in value["paragraphs"]:
        row["text"] = "x" * 3990
    for question in value["questions"].values():
        question["stem"] = "x" * 3990
        question["explanation"] = "x" * 3990
    c.validate("B_generate", value)
    body_raw, _ = budget.build(
        "B_generate",
        old.baseline_input(SPEC),
        budget.DevelopmentPolicy(200_000, 210_000, 8000),
    )
    body = json.loads(body_raw)
    reply = response(body, value)
    reply["output"][0]["phase"] = "final_answer"
    raw = json.dumps(reply, ensure_ascii=False).encode()
    assert 65536 < len(raw) < controller.MAX_RESPONSE
    checked, _ = controller.response_for_validation(body_raw, raw, "generation")
    assert controller.wire.validate(body, checked, "generation")[0].value == value


def test_expired_during_review_validation_never_completes(tmp_path, monkeypatch):
    clock = [50.0]
    monkeypatch.setattr(controller.time, "time", lambda: clock[0])
    real = controller.worker.validate_review
    checks = []

    def validate(*args):
        real(*args)
        checks.append(1)
        if len(checks) == 2:
            clock[0] = 101.0

    monkeypatch.setattr(controller.worker, "validate_review", validate)
    limits = grant("B", tmp_path / "ledger.db")
    limits["deadline"] = 100
    seen = []
    instance = controller.Controller(
        tmp_path / "ledger.db", limits, httpx.MockTransport(handler_for("B", seen))
    )
    with pytest.raises(c.ContractError, match="MOCK_STOPPED_OR_EXPIRED"):
        asyncio.run(instance.run(attest))
    assert len(seen) == 4 and instance.status() == "stopped"
    instance.close()


def test_stop_during_feedback_review_never_sends_repair(tmp_path):
    async def exercise():
        entered, release = threading.Event(), threading.Event()
        seen = []
        instance = controller.Controller(
            tmp_path / "ledger.db",
            grant("B", tmp_path / "ledger.db"),
            httpx.MockTransport(handler_for("B", seen)),
        )

        def delayed_attestation(*args):
            entered.set()
            release.wait(5)
            return attest(*args)

        task = asyncio.create_task(instance.run(delayed_attestation))
        assert await asyncio.to_thread(entered.wait, 3)
        await instance.stop()
        release.set()
        with pytest.raises(c.ContractError, match="MOCK_STOPPED"):
            await task
        assert len(seen) == 2 and instance.status() == "stopped"
        instance.close()

    asyncio.run(exercise())


def test_streamed_oversize_stops_at_limit_and_preserves_prefix(tmp_path):
    seen = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * (1024 * 1024)
            yield b"y" * (1024 * 1024 + 1)
            seen.append("unexpected third read")
            yield b"z"

    async def handler(request):
        return httpx.Response(200, stream=Stream())

    instance = controller.Controller(
        tmp_path / "ledger.db",
        grant("B", tmp_path / "ledger.db"),
        httpx.MockTransport(handler),
    )
    with pytest.raises(c.ContractError, match="MOCK_RESPONSE_SIZE"):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT * FROM attempts").fetchone()
    assert row["state"] == "unknown" and len(row["response"]) == controller.MAX_RESPONSE
    assert instance.status() == "stopped" and not seen
    instance.close()


def test_shared_batch_accounts_both_arms_and_replays_after_reopen(tmp_path):
    path = tmp_path / "package.db"
    package = package_grant(path)
    seen_b, seen_c = [], []
    first = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen_b)),
        selected=("slot", "B"),
    )
    b_result = asyncio.run(first.run(attest))
    assert first.status() == "complete" and first.batch_status() == "active"
    assert len(seen_b) == 4
    frozen_package = first.package
    first.close()
    second = controller.Controller(
        path,
        frozen_package,
        httpx.MockTransport(handler_for("C", seen_c)),
        selected=("slot", "C"),
    )
    c_result = asyncio.run(second.run(attest))
    assert second.batch_status() == "complete" and len(seen_c) == 5
    rows = list(
        second.db.execute(
            "SELECT slot,arm,input_reserved,output_reserved FROM attempts"
        )
    )
    assert len(rows) == 9 and sum(row["output_reserved"] for row in rows) == 72_000
    assert sum(row["input_reserved"] for row in rows) <= package["input"]
    assert {row["arm"] for row in rows} == {"B", "C"}
    second.transport = httpx.MockTransport(handler_for("B", seen_b))
    second.select_slot("slot", "B")
    assert asyncio.run(second.run(attest)) == b_result and len(seen_b) == 4
    second.transport = httpx.MockTransport(handler_for("C", seen_c))
    second.select_slot("slot", "C")
    assert asyncio.run(second.run(attest)) == c_result and len(seen_c) == 5
    second.close()


def test_shared_batch_budget_exhaustion_stops_all_slots(tmp_path):
    path = tmp_path / "package.db"
    package = package_grant(path, calls=8)
    seen_b, seen_c = [], []
    instance = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen_b)),
        selected=("slot", "B"),
    )
    asyncio.run(instance.run(attest))
    instance.select_slot("slot", "C")
    instance.transport = httpx.MockTransport(handler_for("C", seen_c))
    with pytest.raises(c.ContractError, match="MOCK_BUDGET"):
        asyncio.run(instance.run(attest))
    assert instance.batch_status() == "stopped"
    assert len(seen_b) == len(seen_c) == 4
    assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 8
    with pytest.raises(c.ContractError, match="MOCK_SLOT_SWITCH"):
        instance.select_slot("slot", "B")
    instance.close()


@pytest.mark.parametrize("kind", ["input", "output"])
def test_shared_batch_token_reservations_cannot_reset_between_arms(tmp_path, kind):
    path = tmp_path / "package.db"
    package = package_grant(path)
    package[kind] = 400_000 if kind == "input" else 48_000
    seen_b, seen_c = [], []
    instance = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen_b)),
        selected=("slot", "B"),
    )
    asyncio.run(instance.run(attest))
    instance.select_slot("slot", "C")
    instance.transport = httpx.MockTransport(handler_for("C", seen_c))
    with pytest.raises(c.ContractError, match="MOCK_BUDGET"):
        asyncio.run(instance.run(attest))
    rows = list(instance.db.execute("SELECT * FROM attempts"))
    assert instance.batch_status() == "stopped" and len(seen_b) == 4
    assert len(seen_c) < 5
    assert sum(row["input_reserved"] for row in rows) <= package["input"]
    assert sum(row["output_reserved"] for row in rows) <= package["output"]
    instance.close()


def test_shared_stop_during_one_arm_blocks_every_other_arm(tmp_path):
    async def exercise():
        path = tmp_path / "package.db"
        started, release = asyncio.Event(), asyncio.Event()
        seen = []
        handler = handler_for("B", seen)

        async def waiting(request):
            started.set()
            await release.wait()
            return handler(request)

        package = package_grant(path)
        instance = controller.Controller(
            path, package, httpx.MockTransport(waiting), selected=("slot", "B")
        )
        task = asyncio.create_task(instance.run(attest))
        await started.wait()
        with pytest.raises(c.ContractError, match="MOCK_SLOT_SWITCH"):
            instance.select_slot("slot", "C")
        await instance.stop()
        release.set()
        with pytest.raises(c.ContractError, match="MOCK_LATE_RESPONSE"):
            await task
        assert instance.batch_status() == "stopped"
        assert instance.db.execute("SELECT state FROM attempts").fetchone()[0] == "late"
        with pytest.raises(c.ContractError, match="MOCK_SLOT_SWITCH"):
            instance.select_slot("slot", "C")
        instance.close()
        recovered = controller.Controller(
            path,
            package,
            httpx.MockTransport(handler_for("C", seen)),
            selected=("slot", "C"),
        )
        with pytest.raises(c.ContractError, match="MOCK_NOT_ACTIVE"):
            await recovered.run(attest)
        assert recovered.batch_status() == "stopped" and len(seen) == 1
        recovered.close()

    asyncio.run(exercise())


def test_package_cannot_be_reused_at_a_different_ledger_path(tmp_path):
    path = tmp_path / "package.db"
    package = package_grant(path)
    with pytest.raises(c.ContractError, match="MOCK_GRANT"):
        controller.Controller(
            tmp_path / "other.db",
            package,
            httpx.MockTransport(handler_for("B", [])),
            selected=("slot", "B"),
        )


def test_single_slot_grant_cannot_be_reused_at_another_ledger_path(tmp_path):
    path = tmp_path / "ledger.db"
    frozen = grant("B", path)
    with pytest.raises(c.ContractError, match="MOCK_GRANT"):
        controller.Controller(
            tmp_path / "other.db", frozen, httpx.MockTransport(handler_for("B", []))
        )


@pytest.mark.parametrize("mismatch", ["spec", "kind", "question"])
def test_paired_slots_must_have_exactly_matching_inputs(tmp_path, mismatch):
    path = tmp_path / "package.db"
    package = package_grant(path)
    if mismatch == "spec":
        package["slots"][1] = dict(
            package["slots"][1], spec=dict(SPEC, initial_values=[9])
        )
    else:
        package["slots"][1] = dict(
            package["slots"][1],
            kind="refusal",
            question="unsupported" if mismatch == "question" else None,
        )
    with pytest.raises(c.ContractError, match="MOCK_PAIRED_SLOT"):
        controller.Controller(
            path,
            package,
            httpx.MockTransport(handler_for("B", [])),
            selected=("slot", "B"),
        )


def test_crash_after_response_cannot_skip_failed_slot(tmp_path):
    path = tmp_path / "package.db"
    package = package_grant(path)
    seen = []
    first = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen)),
        selected=("slot", "B"),
    )
    asyncio.run(first._exchange("B_generate", old.baseline_input(SPEC)))
    first.db.execute(
        "UPDATE attempts SET http_status=500 WHERE slot='slot' AND arm='B' AND ordinal=0"
    )
    first._seal()  # Simulate a durable HTTP failure before semantic reduction.
    first.close()
    with pytest.raises(c.ContractError, match="MOCK_SLOT_ORDER"):
        controller.Controller(
            path,
            package,
            httpx.MockTransport(handler_for("C", seen)),
            selected=("slot", "C"),
        )
    recovered = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen)),
        selected=("slot", "B"),
    )
    with pytest.raises(c.ContractError, match="MOCK_USAGE_OR_HTTP"):
        asyncio.run(recovered.run(attest))
    assert recovered.batch_status() == "stopped" and len(seen) == 1
    recovered.close()


def test_recovery_with_preexisting_unknown_stops_shared_batch(tmp_path):
    path = tmp_path / "package.db"
    package = package_grant(path)
    seen = []
    first = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen)),
        selected=("slot", "B"),
    )
    first.db.execute(
        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES ('slot','B',0,'B_generate',x'7b7d','hash',NULL,100,8000,'unknown')"
    )
    first._seal()  # Simulate a durable unknown before the batch-stop projection.
    first.close()
    recovered = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("C", seen)),
        selected=("slot", "C"),
    )
    assert recovered.batch_status() == "stopped"
    with pytest.raises(c.ContractError):
        asyncio.run(recovered.run(attest))
    assert not seen
    recovered.close()


@pytest.mark.parametrize("state", ["missing", "empty_sqlite", "missing_anchor"])
def test_lost_ledger_or_anchor_cannot_reset_grant(tmp_path, state):
    path = tmp_path / "ledger.db"
    frozen = grant("B", path)
    transport = httpx.MockTransport(handler_for("B", []))
    instance = controller.Controller(path, frozen, transport)
    instance.close()
    if state == "missing_anchor":
        Path(str(path) + ".anchor").unlink()
    else:
        path.unlink()
        if state == "empty_sqlite":
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE unrelated (id INTEGER)")
            db.close()
    with pytest.raises(c.ContractError, match="MOCK_LEDGER_(LOST|UNANCHORED|CORRUPT)"):
        controller.Controller(path, frozen, transport)
    if state == "missing":
        assert not path.exists()


def test_completed_prefix_is_replayed_before_new_arm_after_restart(tmp_path):
    path = tmp_path / "package.db"
    package = package_grant(path)
    seen_b, seen_c = [], []
    first = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("B", seen_b)),
        selected=("slot", "B"),
    )
    asyncio.run(first.run(attest))
    first.db.execute(
        "UPDATE attempts SET response_sha=? WHERE slot='slot' AND arm='B' AND ordinal=0",
        ("0" * 64,),
    )
    first._seal()  # Exercise prefix replay independently of the snapshot seal.
    first.close()
    recovered = controller.Controller(
        path,
        package,
        httpx.MockTransport(handler_for("C", seen_c)),
        selected=("slot", "C"),
    )
    with pytest.raises(c.ContractError, match="MOCK_RECEIPT_DIGEST"):
        asyncio.run(recovered.run(attest))
    assert recovered.batch_status() == "stopped" and not seen_c
    recovered.close()


def test_older_ledger_snapshot_cannot_reuse_newer_anchor_budget(tmp_path):
    path = tmp_path / "ledger.db"
    snapshot = tmp_path / "older.db"
    frozen = grant("B", path)
    seen = []
    transport = httpx.MockTransport(handler_for("B", seen))
    first = controller.Controller(path, frozen, transport)
    asyncio.run(first._exchange("B_generate", old.baseline_input(SPEC)))
    first.close()
    shutil.copyfile(path, snapshot)
    resumed = controller.Controller(path, frozen, transport)
    asyncio.run(resumed.run(attest))
    assert len(seen) == 4
    resumed.close()
    shutil.copyfile(snapshot, path)
    with pytest.raises(c.ContractError, match="MOCK_LEDGER_ROLLBACK"):
        controller.Controller(path, frozen, transport)
    assert len(seen) == 4


def test_stop_during_request_serialization_prevents_dispatch(tmp_path, monkeypatch):
    async def exercise():
        entered, release = threading.Event(), threading.Event()
        real = controller.budget.build

        def waiting(*args):
            entered.set()
            release.wait(5)
            return real(*args)

        monkeypatch.setattr(controller.budget, "build", waiting)
        path = tmp_path / "ledger.db"
        seen = []
        instance = controller.Controller(
            path, grant("B", path), httpx.MockTransport(handler_for("B", seen))
        )
        task = asyncio.create_task(instance.run(attest))
        assert await asyncio.to_thread(entered.wait, 3)
        await instance.stop()
        release.set()
        with pytest.raises(c.ContractError, match="MOCK_STOPPED"):
            await task
        assert instance.batch_status() == "stopped" and not seen
        assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        instance.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("arm", ["B", "C"])
@pytest.mark.parametrize(
    "case", ["unknown_variant", "too_many", "arbitrary_code", "exact_unknown"]
)
def test_refusal_slots_are_local_and_make_no_http(tmp_path, arm, case):
    path = tmp_path / "refusal.db"
    spec = deepcopy(SPEC)
    question = None
    if case == "unknown_variant":
        spec["variant"] = "unsupported"
    elif case == "too_many":
        spec["insert_values"] = [1, 2, 3, 4, 5]
        spec["allocation_success"] = [True] * 5
    elif case == "arbitrary_code":
        spec["arbitrary_code"] = "int unsafe(void) { return 1; }"
    else:
        spec["variant"] = "uninitialized_next"
        question = "exact_unknown_traversal"
    package = dict(
        batch="dev",
        ledger_path=str(path.absolute()),
        slots=[
            dict(slot="slot", arm=arm, spec=spec, kind="refusal", question=question)
        ],
        calls=0,
        input=1,
        output=1,
        request_bytes=1,
        deadline=4_000_000_000,
    )
    seen = []
    instance = controller.Controller(
        path, package, httpx.MockTransport(handler_for(arm, seen))
    )
    result = asyncio.run(instance.run(attest))
    assert result["status"] == "local_refused" and result["real_provider_calls"] == 0
    assert instance.status() == instance.batch_status() == "complete"
    assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    assert (
        instance.db.execute("SELECT reason FROM local_refusals").fetchone()[0]
        == result["reason"]
    )
    assert asyncio.run(instance.run(attest)) == result and not seen
    instance.close()


def test_falsely_labelled_refusal_stops_without_http(tmp_path):
    path = tmp_path / "refusal.db"
    package = dict(
        batch="dev",
        ledger_path=str(path.absolute()),
        slots=[dict(slot="slot", arm="B", spec=SPEC, kind="refusal", question=None)],
        calls=0,
        input=1,
        output=1,
        request_bytes=1,
        deadline=4_000_000_000,
    )
    seen = []
    instance = controller.Controller(
        path, package, httpx.MockTransport(handler_for("B", seen))
    )
    with pytest.raises(c.ContractError, match="MOCK_EXPECTED_REFUSAL_NOT_REJECTED"):
        asyncio.run(instance.run(attest))
    assert instance.batch_status() == "stopped" and not seen
    instance.close()
