"""Proposed wire/ledger/authorization tests; no credentials, DNS or real network."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest
from scripts.isolated_diagnostics import p15_agent_pilot as c
from scripts.isolated_diagnostics import p15_pilot_baseline as b
from scripts.isolated_diagnostics import p15_pilot_execution as e
from scripts.isolated_diagnostics import p15_pilot_wire as w
from scripts import check_p15_pilot_execution as check
from scripts import run_p15_agent_pilot as run
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest
from scripts.isolated_diagnostics.p15_pilot_batch import BatchError
from scripts.tests.test_p15_agent_pilot import SPEC, content, opinion
from scripts.tests.test_p15_pilot_baseline import full_payload


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Real DNS/network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def request(role="generation"):
    schema = c.obj(dict(ok=dict(const="OK")))
    return StructuredRequest(
        TextRequest(
            (ChatMessage("system", "json only"), ChatMessage("user", "OK")),
            max_output_tokens=8000,
            temperature=0.2,
        ),
        schema,
        stage="pilot_review" if role == "review" else "pilot_content",
    )


def response(body, value=None):
    return dict(
        status="completed",
        model=body["model"],
        error=None,
        incomplete_details=None,
        store=False,
        tools=[],
        instructions=body["input"][0]["content"],
        reasoning=body["reasoning"],
        usage=dict(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            output_tokens_details=dict(reasoning_tokens=0),
        ),
        output=[
            dict(
                type="message",
                role="assistant",
                status="completed",
                content=[
                    dict(
                        type="output_text",
                        text=json.dumps(value or {"ok": "OK"}),
                        annotations=[],
                    )
                ],
            )
        ],
    )


def test_full_schema_and_no_tools_unchanged():
    req = request()
    body = w.request_body(req, "generation")
    assert body["text"]["format"]["schema"] == dict(req.json_schema)
    assert body["text"]["format"]["strict"] is True
    assert "tools" not in body and "previous_response_id" not in body
    result, observation = w.validate(
        body, json.dumps(response(body)).encode(), "generation"
    )
    assert result.value == {"ok": "OK"} and not observation["upstream_context_verified"]


@pytest.mark.parametrize(
    "fault",
    [
        "model",
        "status",
        "store",
        "tools",
        "usage",
        "negative",
        "over_output",
        "instructions",
        "reasoning",
        "function",
        "text_count",
        "content",
        "schema",
        "duplicate",
        "nan",
        "reasoning_on_generator",
    ],
)
def test_wire_protocol_fail_closed(fault):
    body = w.request_body(request(), "generation")
    value = response(body)
    if fault == "model":
        value["model"] = "other"
    elif fault == "status":
        value["status"] = "incomplete"
    elif fault == "store":
        value["store"] = True
    elif fault == "tools":
        value["tools"] = [{"type": "function"}]
    elif fault == "usage":
        value["usage"]["total_tokens"] = 99
    elif fault == "negative":
        value["usage"]["input_tokens"] = -1
    elif fault == "over_output":
        value["usage"].update(output_tokens=8001, total_tokens=8011)
    elif fault == "instructions":
        value["instructions"] += "unknown injection"
    elif fault == "reasoning":
        value["reasoning"] = {"effort": "high"}
    elif fault == "function":
        value["output"][0]["type"] = "function_call"
    elif fault == "text_count":
        value["output"] *= 2
    elif fault == "content":
        value["output"][0]["content"][0]["annotations"] = [{"url": "x"}]
    elif fault == "schema":
        value["output"][0]["content"][0]["text"] = "{}"
    elif fault == "duplicate":
        value["output"][0]["content"][0]["text"] = '{"ok":"OK","ok":"OK"}'
    elif fault == "nan":
        value["output"][0]["content"][0]["text"] = '{"ok": NaN}'
    else:
        value["output"].insert(0, dict(type="reasoning", summary=[]))
    with pytest.raises(ValueError):
        w.validate(body, json.dumps(value).encode(), "generation")


def test_review_opaque_known_differences_are_observations_not_identity():
    body = w.request_body(request("review"), "review")
    value = response(body)
    value["instructions"] += w.SUFFIX
    turn = {"turn_id": "00000000-0000-0000-0000-000000000001"}
    value["output"].insert(
        0,
        dict(
            type="reasoning",
            summary=[dict(type="summary_text", text="opaque")],
            metadata=turn,
            internal_chat_message_metadata_passthrough=turn,
        ),
    )
    original = deepcopy(value)
    result, obs = w.validate(body, json.dumps(value).encode(), "review")
    assert value == original and result.value == {"ok": "OK"}
    assert obs["known_suffix_observed"] and obs["opaque_turn_metadata_quarantined"]
    assert (
        not obs["opaque_identity_verified"] and not obs["instruction_delivery_verified"]
    )
    value["instructions"] = None
    assert (
        w.validate(body, json.dumps(value).encode(), "review")[1]["instruction_echo"]
        == "unavailable"
    )


@pytest.mark.parametrize(
    "fault", ["one_map", "extra", "unequal", "uuid", "summary", "plain", "encrypted"]
)
def test_reasoning_metadata_boundary_not_expanded(fault):
    body = w.request_body(request("review"), "review")
    value = response(body)
    turn = {"turn_id": "00000000-0000-0000-0000-000000000001"}
    item = dict(
        type="reasoning",
        summary=[],
        metadata=turn,
        internal_chat_message_metadata_passthrough=deepcopy(turn),
    )
    if fault == "one_map":
        del item["metadata"]
    elif fault == "extra":
        item["metadata"]["user"] = "owner"
    elif fault == "unequal":
        item["metadata"] = {"turn_id": "00000000-0000-0000-0000-000000000002"}
    elif fault == "uuid":
        item["metadata"]["turn_id"] = "notuuid"
    elif fault == "summary":
        item["summary"] = [dict(type="summary_text", text="x" * 4097)]
    elif fault == "plain":
        item["content"] = ["reasoning"]
    else:
        item["encrypted_content"] = "opaque ciphertext"
    value["output"].insert(0, item)
    with pytest.raises(ValueError):
        w.validate(body, json.dumps(value).encode(), "review")


@pytest.fixture
def journal(tmp_path):
    inputs = dict(
        version="pilot-inputs-v1",
        slots=[
            dict(slot_id="slot", kind="supported", spec=deepcopy(SPEC), question=None)
        ],
    )
    grant = dict(window_started_epoch=0, deadline_epoch=1000)
    j = e.Journal.start(tmp_path / "run", "a" * 64, grant, inputs, clock=lambda: 100)
    yield j, inputs
    j.db.close()


def mocked_transport(mutate=None):
    def handle(req):
        assert req.url.host == "8.8.8.8" and req.extensions["sni_hostname"] in (
            "api.deepseek.com",
            "aiapi.world",
        )
        body = json.loads(req.content)
        payload = json.loads(body["input"][1]["content"])
        schema = body["text"]["format"]["schema"]
        if schema == b.SCHEMA:
            value = full_payload() if "original" not in payload else payload["original"]
        elif schema == c.PLAN_SCHEMA:
            value = dict(
                objectives=list(c.GOALS),
                spec=payload["allowed_spec"],
                coverage=[
                    dict(objective=k, observation_key=v) for k, v in c.GOALS.items()
                ],
            )
        elif schema == c.CONTENT_SCHEMA:
            value = (
                content(payload["example"])
                if "example" in payload
                else payload["original"]
            )
        else:
            value = opinion(payload["source"])
        raw = response(body, value)
        if mutate:
            mutate(body, raw)
        return httpx.Response(200, json=raw)

    return lambda: httpx.MockTransport(handle)


def fake_step(j, inputs, mutate=None):
    return asyncio.run(
        run.step(
            j,
            inputs,
            dict(generation="SYNTHETIC_GEN_KEY", review="SYNTHETIC_REV_KEY"),
            transport_factory=mocked_transport(mutate),
            resolver=lambda *args: ("8.8.8.8",),
        )
    )


def report(j, result, decision="accept"):
    pending = j.batch()["pending"]
    checks = dict.fromkeys(["facts", "answers", "code", "actions", "teaching"], True)
    return dict(
        version="pilot-slot-review-v1",
        reviewer="pilot_independent_evaluator",
        reviewer_type="assistant",
        package_sha256="a" * 64,
        slot_id=pending["slot_id"],
        arm=pending["arm"],
        result_sha256=pending["result_sha256"],
        decision=decision,
        checks=checks,
        issues=[],
        version_reviews=[
            dict(revision=i, checks=checks, issues=[])
            for i in range(len(result["versions"]))
        ],
        evidence_ref="SYNTHETIC_TEST_NOT_AUTHORITY",
    )


def test_b_and_c_pause_for_independent_review_and_readonly_evidence(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    assert r["calls"] == 2 and j.batch()["status"] == "awaiting_assistant"
    with pytest.raises(c.PilotError, match="BATCH_NOT_ACTIVE"):
        fake_step(j, inputs)
    j.accept_report(report(j, r))
    r = fake_step(j, inputs)
    assert r["calls"] == 3 and j.batch()["status"] == "awaiting_assistant"
    j.accept_report(report(j, r))
    assert j.batch()["status"] == "collected"
    before = {p.name: p.read_bytes() for p in j.output.iterdir() if p.is_file()}
    result = check.verify(j.output, "a" * 64)
    assert result["evidence_verified"] and result["requests_reserved"] == 5
    assert result["transport_kinds"] == {"mock": 5}
    assert not result["production_admission"] and not result["T070_completed"]
    after = {p.name: p.read_bytes() for p in j.output.iterdir() if p.is_file()}
    assert before == after


def test_reservation_order_counts_and_no_unknown_reuse(journal):
    j, _ = journal
    with pytest.raises(c.PilotError, match="SLOT_ORDER"):
        j.reserve("wrong", "B", "pilot_baseline", {})
    with pytest.raises(c.PilotError, match="REQUEST_OR_STAGE_LIMIT"):
        j.reserve("slot", "B", "pilot_review", {})
    ticket = j.reserve("slot", "B", "pilot_baseline", {})
    j.sent(ticket)
    with pytest.raises(c.PilotError, match="DUPLICATE_SEND"):
        j.sent(ticket)
    with pytest.raises(c.PilotError, match="PENDING_OR_UNKNOWN"):
        j.reserve("slot", "B", "pilot_review", {})
    j.stop("test")
    assert j.db.execute("SELECT state FROM calls").fetchone()[0] == "unknown"
    with pytest.raises(c.PilotError, match="BATCH_NOT_ACTIVE"):
        j.guard()


def test_protocol_failure_preserves_raw_unknown_and_stops(journal):
    j, inputs = journal

    def mutate(body, raw):
        raw["model"] = "drift"

    r = fake_step(j, inputs, mutate)
    assert r["state"] == "stopped" and j.batch()["status"] == "stopped"
    assert j.db.execute("SELECT state FROM calls").fetchone()[0] == "unknown"
    assert (j.output / "call-000-response.json").exists()
    assert check.verify(j.output, "a" * 64)["unknown"] == 1


def test_assistant_report_cannot_inflate_authority_or_change_source(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    for key, value in [
        ("reviewer_type", "human"),
        ("result_sha256", "b" * 64),
        ("reviewer", "developer"),
    ]:
        wrong = report(j, r)
        wrong[key] = value
        with pytest.raises(c.PilotError):
            j.accept_report(wrong)
    wrong = report(j, r)
    wrong["version_reviews"] = []
    with pytest.raises(c.PilotError, match="ALL_VERSIONS"):
        j.accept_report(wrong)
    wrong = report(j, r)
    wrong["checks"]["facts"] = False
    with pytest.raises(c.PilotError, match="ASSISTANT_FALSE_ACCEPT"):
        j.accept_report(wrong)
    assert j.batch()["position"] == 0


def test_unapproved_gate_precedes_keys_dns_output(monkeypatch, tmp_path):
    policy = dict(limits={"requests": 90})
    path = tmp_path / "execution-approval.json"
    path.write_text('{"accepted":false}')
    monkeypatch.setattr(run, "BASE", tmp_path)
    monkeypatch.setattr(run, "load_keys", lambda: pytest.fail("Key loader reached"))
    with pytest.raises(c.PilotError, match="EXACT_NEW_EXECUTION_APPROVAL_REQUIRED"):
        run.grant_before_keys("a" * 64, policy, {"status": "pending"})
    assert list(tmp_path.iterdir()) == [path]


def test_unknown_raw_tampering_rejected(journal):
    j, inputs = journal

    def mutate(body, raw):
        raw["status"] = "incomplete"

    fake_step(j, inputs, mutate)
    (j.output / "call-000-response.json").write_text("{}")
    with pytest.raises(c.PilotError, match="OBSERVED_WIRE_DIGEST"):
        check.verify(j.output, "a" * 64)


def test_local_refusal_never_resolves_target_or_loads_keys(tmp_path):
    inputs = dict(
        version="pilot-inputs-v1",
        slots=[
            dict(
                slot_id="reject",
                kind="refusal",
                spec={**SPEC, "variant": "unknown"},
                question=None,
            )
        ],
    )
    j = e.Journal.start(
        tmp_path / "refusal",
        "a" * 64,
        dict(window_started_epoch=0, deadline_epoch=1000),
        inputs,
        clock=lambda: 100,
    )
    try:
        result = asyncio.run(
            run.step(j, inputs, {}, resolver=lambda *a: pytest.fail("DNS reached"))
        )
        assert result["state"] == "refused" and result["calls"] == 0
        assert j.batch()["position"] == 1
    finally:
        j.db.close()


def test_report_time_does_not_extend_window(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    j.clock = lambda: 1001
    with pytest.raises(c.PilotError, match="ASSISTANT_CHECKPOINT_STATE_OR_TIME"):
        j.accept_report(report(j, r))
    assert j.batch()["status"] == "awaiting_assistant"


def test_first_revision_failed_facts_cannot_be_hidden_by_empty_issues(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    # Construct a repaired second version for the validator, without changing recorded evidence.
    repaired = deepcopy(r)
    repaired["versions"].append(deepcopy(r["versions"][0]))
    proposed = report(j, repaired)
    proposed["version_reviews"][0]["checks"] = {**proposed["checks"], "facts": False}
    with pytest.raises(c.PilotError, match="FAILED_CHECK_WITHOUT_EVIDENCE"):
        e.validate_assistant_report(proposed, "a" * 64, j.batch()["pending"], repaired)


def test_first_revision_severe_error_cannot_be_repaired_away(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    repaired = deepcopy(r)
    repaired["versions"].append(deepcopy(r["versions"][0]))
    proposed = report(j, repaired)
    proposed["version_reviews"][0]["issues"] = [
        dict(
            severity="severe",
            area="fact",
            source_pointer="/versions/0/payload/blocks/0/markdown",
            evidence_value=r["versions"][0]["payload"]["blocks"][0]["markdown"],
            reason="Synthetic severe finding",
        )
    ]
    with pytest.raises(
        c.PilotError, match="INITIAL_SEVERE_ERROR_CANNOT_BE_REPAIRED_AWAY"
    ):
        e.validate_assistant_report(proposed, "a" * 64, j.batch()["pending"], repaired)


def test_checker_revalidates_report_even_if_receipt_chain_is_rehashed(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    j.accept_report(report(j, r))
    stored = json.loads((j.output / "assistant-00.json").read_text())
    stored["reviewer_type"] = "human"
    (j.output / "assistant-00.json").write_text(json.dumps(stored))
    row = j.db.execute(
        "SELECT seq FROM events WHERE kind='assistant_review'"
    ).fetchone()
    j.db.execute(
        "UPDATE events SET payload=? WHERE seq=?", (json.dumps(stored), row[0])
    )
    parent = None
    for row in j.db.execute("SELECT * FROM events ORDER BY seq").fetchall():
        sha = digest(
            dict(
                seq=row["seq"],
                kind=row["kind"],
                payload=json.loads(row["payload"]),
                previous=parent,
                epoch=row["epoch"],
            )
        )
        j.db.execute(
            "UPDATE events SET previous=?,digest=? WHERE seq=?",
            (parent, sha, row["seq"]),
        )
        parent = sha
    with pytest.raises(BatchError, match="BATCH_ASSISTANT_BINDING"):
        check.verify(j.output, "a" * 64)


def test_external_input_pin_and_workflow_spec_binding(journal):
    j, inputs = journal
    fake_step(j, inputs)
    with pytest.raises(c.PilotError, match="EXTERNAL_INPUT_PIN"):
        check.verify(j.output, "a" * 64, expected_inputs_sha256="0" * 64)
    modified = deepcopy(inputs)
    modified["slots"][0]["spec"]["insert_values"][0] = 8
    (j.output / "inputs.json").write_text(json.dumps(modified))
    with pytest.raises(c.PilotError, match="WORKFLOW_INPUT_SPEC"):
        check.verify(j.output, "a" * 64)


def test_missing_ratifier_metadata_rejected_without_reading_truth(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run, "BASE", tmp_path)
    summary = {"status": "assistant_reference_ratified_not_execution_authority"}
    path = tmp_path / "independent-e03-summary.json"
    path.write_text(json.dumps(summary))
    (tmp_path / "candidate-manifest.json").write_text('{"files":[]}')
    materials = dict(
        status="independent_e03_ratified", summary_sha256=run.file_sha(path)
    )
    with pytest.raises(c.PilotError, match="INDEPENDENT_RATIFICATION"):
        run.validate_materials(materials)


def test_expired_new_authorization_does_not_touch_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "BASE", tmp_path)
    policy = dict(limits=run.LIMITS)
    grant = dict(
        accepted=True,
        package_sha256="a" * 64,
        scope="PHASE-1.5-T069",
        human_message="SYNTHETIC_NOT_AUTHORITY",
        evidence_ref="synthetic",
        reviewer_type="assistant_independent",
        limits=run.LIMITS,
        compatibility_scope_accepted=True,
        synthetic_transfer_accepted=True,
        new_window_accepted=True,
        unbounded_tokens_accepted=True,
        unbounded_money_and_unverified_invoice_accepted=True,
        relay_context_risk_accepted=True,
        window_started_epoch=0,
        deadline_epoch=10800,
    )
    (tmp_path / "execution-approval.json").write_text(json.dumps(grant))
    with pytest.raises(c.PilotError, match="NEW_WINDOW_INVALID_OR_EXPIRED"):
        run.grant_before_keys("a" * 64, policy, dict(status="independent_e03_ratified"))


def test_executor_lock_prevents_second_process_scope(journal):
    j, _ = journal
    other = e.Journal(j.output, clock=lambda: 100)
    try:
        with j.lock():
            with pytest.raises(c.PilotError, match="CONCURRENT_EXECUTOR"):
                with other.lock():
                    pytest.fail("Second executor entered")
    finally:
        other.db.close()


def test_late_reply_preserves_unknown_no_advance(journal):
    j, inputs = journal

    def mutate(body, raw):
        j.clock = lambda: 1001

    r = fake_step(j, inputs, mutate)
    assert r["state"] == "stopped" and j.batch()["status"] == "stopped"
    assert j.db.execute("SELECT state FROM calls").fetchone()[0] == "unknown"
    assert j.batch()["position"] == 0


def independent_materials(tmp_path, monkeypatch):
    import hashlib
    from datetime import datetime, timezone

    private = tmp_path / "independent"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(run, "INDEPENDENT_DIRECTORY", private)
    package = tmp_path / "package"
    package.mkdir()
    monkeypatch.setattr(run, "BASE", package)
    slots = []
    for variant in (
        "normal",
        "reversed_assignment",
        "discard_return",
        "uninitialized_next",
    ):
        for n in range(2):
            slots.append(
                dict(
                    slot_id=variant + str(n),
                    kind="supported",
                    question=None,
                    spec={**deepcopy(SPEC), "variant": variant},
                )
            )
    for n in range(2):
        slots.append(
            dict(
                slot_id="allocation" + str(n),
                kind="supported",
                question=None,
                spec={**deepcopy(SPEC), "allocation_success": [True, False]},
            )
        )
    slots += [
        dict(
            slot_id="unknown",
            kind="refusal",
            question=None,
            spec={**SPEC, "variant": "unknown"},
        ),
        dict(
            slot_id="code",
            kind="refusal",
            question=None,
            spec={**SPEC, "code": "not executed"},
        ),
        dict(
            slot_id="long",
            kind="refusal",
            question=None,
            spec={**SPEC, "insert_values": [1] * 5, "allocation_success": [True] * 5},
        ),
        dict(
            slot_id="exact",
            kind="refusal",
            question="exact_traversal",
            spec={**SPEC, "variant": "uninitialized_next"},
        ),
    ]
    values = {
        "inputs.json": dict(version="pilot-inputs-v1", slots=slots),
        "truth.json": {"synthetic_not_truth": True},
        "ratification.json": {"synthetic": True},
        "hand-derivation.md": "SYNTHETIC_TEST_NOT_AUTHORITY",
    }
    for name, value in values.items():
        (private / name).write_text(json.dumps(value))
        (private / name).chmod(0o600)
    candidate = dict(frozen_at="2026-10-28T01:00:00+08:00", files=[])
    (package / "candidate-manifest.json").write_text(json.dumps(candidate))
    summary = dict(
        schema_version="p15-independent-reference-summary-v1",
        status="assistant_reference_ratified_not_execution_authority",
        evaluator=dict(
            identity="pilot_independent_evaluator", type="assistant", human=False
        ),
        human_signoff=False,
        candidate_manifest_sha256=run.file_sha(package / "candidate-manifest.json"),
        supported_slots=10,
        local_refusal_slots=4,
        provider_requests=0,
        network_requests=0,
        c_execution=0,
        ratified_at=datetime.now(timezone.utc).isoformat(),
    )
    for key, name in dict(
        inputs="inputs.json",
        truth="truth.json",
        ratification="ratification.json",
        derivation="hand-derivation.md",
    ).items():
        summary[key + "_path"] = str(private / name)
        summary[key + "_sha256"] = hashlib.sha256(
            (private / name).read_bytes()
        ).hexdigest()
    (package / "independent-e03-summary.json").write_text(json.dumps(summary))
    materials = {
        k: summary[k]
        for k in (
            "candidate_manifest_sha256",
            "inputs_path",
            "inputs_sha256",
            "truth_sha256",
            "ratification_sha256",
            "derivation_sha256",
        )
    }
    materials.update(
        status="independent_e03_ratified",
        summary_sha256=run.file_sha(package / "independent-e03-summary.json"),
    )
    return private, package, summary, materials


def test_exact_materials_and_denominators_without_truth_content_read(
    tmp_path, monkeypatch
):
    private, package, summary, materials = independent_materials(tmp_path, monkeypatch)
    original = Path.read_bytes

    def guarded(path):
        assert path.name not in (
            "truth.json",
            "ratification.json",
            "hand-derivation.md",
        )
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    assert run.validate_materials(materials)["evaluator"]["human"] is False
    assert len(run.read_inputs(materials)["slots"]) == 14


@pytest.mark.parametrize(
    "fault", ["reviewer", "time", "candidate", "inputs", "count", "permission"]
)
def test_ratification_identity_time_candidate_and_digest_are_required(
    tmp_path, monkeypatch, fault
):
    private, package, summary, materials = independent_materials(tmp_path, monkeypatch)
    if fault == "reviewer":
        summary["evaluator"]["identity"] = "developer"
    elif fault == "time":
        summary["ratified_at"] = "2020-01-01T00:00:00+08:00"
    elif fault == "candidate":
        summary["candidate_manifest_sha256"] = "0" * 64
    elif fault == "inputs":
        materials["inputs_sha256"] = "0" * 64
    elif fault == "count":
        summary["supported_slots"] = 9
    else:
        (private / "truth.json").chmod(0o644)
    (package / "independent-e03-summary.json").write_text(json.dumps(summary))
    materials["summary_sha256"] = run.file_sha(package / "independent-e03-summary.json")
    with pytest.raises(c.PilotError):
        run.validate_materials(materials)


def test_no_refund_or_new_request_after_timeout(tmp_path):
    inputs = dict(
        version="pilot-inputs-v1",
        slots=[
            dict(slot_id="slot", kind="supported", spec=deepcopy(SPEC), question=None)
        ],
    )
    j = e.Journal.start(
        tmp_path / "short_window",
        "a" * 64,
        dict(window_started_epoch=0, deadline_epoch=100.01),
        inputs,
        clock=lambda: 100,
    )

    async def slow(req):
        await asyncio.sleep(1)

    r = asyncio.run(
        run.step(
            j,
            inputs,
            dict(generation="SYNTHETIC_GEN_KEY", review="SYNTHETIC_REV_KEY"),
            transport_factory=lambda: httpx.MockTransport(slow),
            resolver=lambda *a: ("8.8.8.8",),
        )
    )
    assert r["state"] == "stopped"
    assert j.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1
    assert j.db.execute("SELECT state FROM calls").fetchone()[0] == "unknown"
    with pytest.raises(c.PilotError, match="BATCH_NOT_ACTIVE"):
        fake_step(j, inputs)


def test_degraded_candidate_is_not_first_structure_success(journal, monkeypatch):
    j, inputs = journal
    r = fake_step(j, inputs)
    j.accept_report(report(j, r))
    monkeypatch.setattr(c, "build_actions", lambda *a: [])
    r = fake_step(j, inputs)
    assert r["state"] == "stopped" and r["versions"][0]["payload"]["degraded"]
    result = check.verify(j.output, "a" * 64)
    assert result["initial_structure"]["numerators"] == {"B": 1, "C": 0}


def test_both_review_arms_have_exact_original_goal_and_constraints(journal):
    j, inputs = journal
    r = fake_step(j, inputs)
    b_review = next(
        event["payload"]["payload"]
        for event in r["events"]
        if event["kind"] == "dispatch" and event["payload"]["role"] == "review"
    )
    j.accept_report(report(j, r))
    r = fake_step(j, inputs)
    c_review = next(
        event["payload"]["payload"]
        for event in r["events"]
        if event["kind"] == "dispatch" and event["payload"]["role"] == "review"
    )
    assert b_review["review_context"] == c_review["review_context"]
    assert b_review["review_context"]["plan_constraints"] == SPEC
    assert b_review["review_context"]["original_goal"]


def resync_forged_transcript(
    j,
    result=None,
    request_ticket=None,
    body=None,
    response_ticket=None,
    raw=None,
    result_index=0,
):
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

    if request_ticket:
        (j.output / (request_ticket + "-request.json")).write_bytes(canonical(body))
        j.db.execute(
            "UPDATE calls SET request_sha=? WHERE ticket=?",
            (digest(body), request_ticket),
        )
    if response_ticket:
        content_bytes = canonical(raw)
        (j.output / (response_ticket + "-response.json")).write_bytes(content_bytes)
        import hashlib

        response_sha = hashlib.sha256(content_bytes).hexdigest()
        j.db.execute(
            "UPDATE calls SET response_sha=? WHERE ticket=?",
            (response_sha, response_ticket),
        )
    new_result_sha = None
    if result:
        previous = None
        for event in result["events"]:
            event.pop("event_digest", None)
            event["previous_digest"] = previous
            event["event_digest"] = digest(event)
            previous = digest(event)
        rootrow = j.db.execute(
            "SELECT payload FROM events WHERE kind='slot_result' ORDER BY seq LIMIT 1 OFFSET ?",
            (result_index,),
        ).fetchone()
        descriptor = json.loads(rootrow[0])
        data = canonical(result)
        (j.output / descriptor["name"]).write_bytes(data)
        import hashlib

        new_result_sha = hashlib.sha256(data).hexdigest()
        current = j.batch()
        if current["pending"] and current["pending"]["name"] == descriptor["name"]:
            current["pending"]["result_sha256"] = new_result_sha
            j.update(pending=current["pending"])
        report_path = j.output / f"assistant-{result_index:02d}.json"
        if report_path.exists():
            proposed = json.loads(report_path.read_text())
            proposed["result_sha256"] = new_result_sha
            report_path.write_bytes(canonical(proposed))
    parent = None
    for event in j.db.execute("SELECT * FROM events ORDER BY seq").fetchall():
        payload = json.loads(event["payload"])
        if (
            request_ticket
            and payload.get("ticket") == request_ticket
            and event["kind"] == "reserved"
        ):
            payload["request_sha256"] = digest(body)
        if response_ticket and payload.get("ticket") == response_ticket:
            if event["kind"] in ("wire_observed", "settled"):
                payload["response_sha256"] = response_sha
        if (
            new_result_sha
            and event["kind"] in ("slot_result", "assistant_review")
            and payload["slot_id"] == descriptor["slot_id"]
            and payload["arm"] == descriptor["arm"]
        ):
            payload["result_sha256"] = new_result_sha
        sha = digest(
            dict(
                seq=event["seq"],
                kind=event["kind"],
                payload=payload,
                previous=parent,
                epoch=event["epoch"],
            )
        )
        j.db.execute(
            "UPDATE events SET payload=?,previous=?,digest=? WHERE seq=?",
            (canonical(payload).decode(), parent, sha, event["seq"]),
        )
        parent = sha


@pytest.mark.parametrize(
    "fault",
    [
        "temperature",
        "tools",
        "previous_response_id",
        "extra_message",
        "baseline_extra_context",
    ],
)
def test_complete_request_replay_refuses_rehashed_outbound_context(journal, fault):
    j, inputs = journal
    r = fake_step(j, inputs)
    body = json.loads((j.output / "call-000-request.json").read_text())
    if fault == "temperature":
        body["temperature"] = 0.9
    elif fault == "tools":
        body["tools"] = [{"type": "function", "name": "other"}]
    elif fault == "previous_response_id":
        body["previous_response_id"] = "hidden"
    elif fault == "extra_message":
        body["input"].append(dict(role="system", content="hidden context"))
    else:
        payload = json.loads(body["input"][1]["content"])
        payload["reference"] = {"extra": "hidden"}
        from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

        body["input"][1]["content"] = canonical(payload).decode()
        next(e["payload"] for e in r["events"] if e["kind"] == "dispatch")[
            "payload"
        ] = payload
    resync_forged_transcript(j, r, request_ticket="call-000", body=body)
    with pytest.raises(c.PilotError, match="COMPLETE_REQUEST_REPLAY_MISMATCH"):
        check.verify(j.output, "a" * 64)


@pytest.mark.parametrize("fault", ["question_keys", "extra_reference"])
def test_content_full_payload_is_bound_even_after_rehash(journal, fault):
    j, inputs = journal
    r = fake_step(j, inputs)
    j.accept_report(report(j, r))
    r = fake_step(j, inputs)
    # Preserve the first result; mutate only the C slot's request to exercise complete replay.
    body = json.loads((j.output / "call-003-request.json").read_text())
    payload = json.loads(body["input"][1]["content"])
    if fault == "question_keys":
        payload["question_keys"] = ["wrong"]
    else:
        payload["unexpected_context"] = {"private": "extra"}
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

    body["input"][1]["content"] = canonical(payload).decode()
    next(
        event["payload"]
        for event in r["events"]
        if event["kind"] == "dispatch" and event["payload"]["role"] == "content"
    )["payload"] = payload
    resync_forged_transcript(j, r, request_ticket="call-003", body=body, result_index=1)
    with pytest.raises(c.PilotError, match="COMPLETE_REQUEST_REPLAY_MISMATCH"):
        check.verify(j.output, "a" * 64)


@pytest.mark.parametrize("verdict", ["unknown", "fact"])
def test_model_unknown_or_fact_stop_cannot_be_forged_as_success(journal, verdict):
    j, inputs = journal
    r = fake_step(j, inputs)
    j.accept_report(report(j, r))
    raw = json.loads((j.output / "call-001-response.json").read_text())
    source = r["versions"][0]["payload"]
    new_opinion = (
        opinion(source, "unknown")
        if verdict == "unknown"
        else opinion(source, "revise", "fact", "severe")
    )
    raw["output"][0]["content"][0]["text"] = json.dumps(new_opinion)
    for event in r["events"]:
        if event["kind"] == "response" and event["payload"]["role"] == "review":
            event["payload"]["value"] = deepcopy(new_opinion)
        if event["kind"] == "review":
            event["payload"] = deepcopy(new_opinion)
    resync_forged_transcript(j, r, response_ticket="call-001", raw=raw)
    with pytest.raises(c.PilotError, match="WORKFLOW_STATE_REPLAY_MISMATCH"):
        check.verify(j.output, "a" * 64)


def test_exact_local_refusal_reason_is_recomputed(tmp_path):
    inputs = dict(
        version="pilot-inputs-v1",
        slots=[
            dict(
                slot_id="bad",
                kind="refusal",
                spec={**SPEC, "variant": "unknown"},
                question=None,
            )
        ],
    )
    j = e.Journal.start(
        tmp_path / "refusal_proof",
        "a" * 64,
        dict(window_started_epoch=0, deadline_epoch=1000),
        inputs,
        clock=lambda: 100,
    )
    try:
        r = asyncio.run(run.step(j, inputs, {}))
        r["reason"] = "unsupported_question"
        resync_forged_transcript(j, r)
        with pytest.raises(c.PilotError, match="EXACT_REFUSAL_REASON"):
            check.verify(j.output, "a" * 64)
    finally:
        j.db.close()


def repaired_baseline(j, inputs):
    counter = [0]

    def mutate(body, raw):
        if body["text"]["format"]["schema"] == c.REVIEW_SCHEMA:
            counter[0] += 1
            if counter[0] == 1:
                payload = json.loads(body["input"][1]["content"])
                raw["output"][0]["content"][0]["text"] = json.dumps(
                    opinion(payload["source"], "revise")
                )

    result = fake_step(j, inputs, mutate)
    assert result["calls"] == 4 and len(result["versions"]) == 2
    return result


def test_baseline_repair_goals_are_part_of_complete_request(journal):
    j, inputs = journal
    r = repaired_baseline(j, inputs)
    body = json.loads((j.output / "call-002-request.json").read_text())
    payload = json.loads(body["input"][1]["content"])
    payload["goals"] = ["other learning objective"]
    from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

    body["input"][1]["content"] = canonical(payload).decode()
    next(
        event["payload"]
        for event in r["events"]
        if event["kind"] == "dispatch" and event["payload"]["role"] == "baseline_repair"
    )["payload"] = payload
    resync_forged_transcript(j, r, request_ticket="call-002", body=body)
    with pytest.raises(c.PilotError, match="COMPLETE_REQUEST_REPLAY_MISMATCH"):
        check.verify(j.output, "a" * 64)


def test_second_review_revise_cannot_be_forged_as_repaired_success(journal):
    j, inputs = journal
    r = repaired_baseline(j, inputs)
    raw = json.loads((j.output / "call-003-response.json").read_text())
    new_opinion = opinion(r["versions"][-1]["payload"], "revise")
    raw["output"][0]["content"][0]["text"] = json.dumps(new_opinion)
    response_events = [
        event
        for event in r["events"]
        if event["kind"] == "response" and event["payload"]["role"] == "review"
    ]
    response_events[-1]["payload"]["value"] = deepcopy(new_opinion)
    [event for event in r["events"] if event["kind"] == "review"][-1]["payload"] = (
        deepcopy(new_opinion)
    )
    resync_forged_transcript(j, r, response_ticket="call-003", raw=raw)
    with pytest.raises(c.PilotError, match="WORKFLOW_STATE_REPLAY_MISMATCH"):
        check.verify(j.output, "a" * 64)


def test_deadline_is_rechecked_at_dispatch_not_only_at_reservation(journal):
    j, _ = journal
    ticket = j.reserve("slot", "B", "pilot_baseline", {})
    j.clock = lambda: 1001
    with pytest.raises(c.PilotError, match="DISPATCH_WINDOW_OR_STATE"):
        j.sent(ticket)
    assert not j.db.execute("SELECT 1 FROM events WHERE kind='sent'").fetchone()
    assert j.db.execute("SELECT state FROM calls").fetchone()[0] == "reserved"
