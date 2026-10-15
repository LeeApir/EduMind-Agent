"""Offline transport and role contract integration; no env keys, DNS or cloud traffic."""

import asyncio
import copy
import json
import socket
import sys
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from test_derived_diagnostic_budget import approval, bound_value, manifest, sample_value

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support import claim_review_prototype as p  # noqa: E402
from acceptance_support import derived_diagnostic_budget as d  # noqa: E402
from acceptance_support.derived_responses_sender import (  # noqa: E402
    CredentialLease,
    FrozenResponsesSender,
)
from acceptance_support.derived_review_contracts import contracts  # noqa: E402


@pytest.fixture
def rig(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Real socket/DNS access forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    m = manifest(tmp_path)
    target = {
        "version": "derived-deepseek-target-v1",
        "base_url": "https://api.deepseek.com",
        "model": m["target"]["model"],
        "transport": "responses_json_schema",
        "credential_ref": "synthetic-ref",
        "credential_version": 1,
        "consent_sha256": "c" * 64,
    }
    m["target"]["target_sha256"] = p.digest(target)
    for stage, contract in contracts().items():
        m["stages"][stage].update(contract)
    b = d.DerivedBudget(m, root=tmp_path, approval=approval(m))
    state = {
        "sends": [],
        "reads": 0,
        "dns": 0,
        "edit": None,
        "status": 200,
        "raw": None,
        "headers": {},
        "lease_edit": {},
    }

    def credentials():
        state["reads"] += 1
        lease = CredentialLease(
            "synthetic-secret-not-a-key",
            "synthetic-ref",
            1,
            "c" * 64,
            b.freeze,
            time.time() + 60,
        )
        return replace(lease, **state["lease_edit"])

    def resolve(host, port):
        state["dns"] += 1
        assert (host, port) == ("api.deepseek.com", 443)
        return state.get("addresses", ("8.8.8.8",))

    async def handle(request):
        state["sends"].append(request)
        if state.get("failure"):
            raise state["failure"]
        body = json.loads(request.content)
        req = {
            "slot": json.loads(body["input"][1]["content"])["request_binding"]["slot"],
            "wire": request.content,
        }
        value = bound_value(req, sample_value(b, req))
        payload = {
            "status": "completed",
            "model": target["model"],
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "output_tokens_details": {"reasoning_tokens": 150},
            },
        }
        if state["edit"]:
            state["edit"](payload)
        raw = state["raw"] if state["raw"] is not None else p.encoded(payload)
        if state.get("pause"):
            state["entered"].set()
            await state["pause"].wait()
        return httpx.Response(
            state["status"], headers=state["headers"], stream=httpx.ByteStream(raw)
        )

    sender = FrozenResponsesSender(
        b, target, credentials=credentials, resolver=resolve, transport=httpx.MockTransport(handle)
    )
    yield b, sender, state, target
    b.close()


def reserve(b):
    req = b.prepare()
    return req, b.reserve(req["slot"], req["wire"], req["parents"])


def snapshot(b):
    return b.snapshot()


def test_complete_chain_uses_frozen_bytes_and_server_supplied_ids(rig):
    b, sender, state, _ = rig

    async def run():
        for index in range(5):
            req, n = reserve(b)
            data = json.loads(json.loads(req["wire"])["input"][1]["content"])
            assert data["blocks"] and len(data["blocks"][0]["block_id"]) == 64
            if index >= 2:
                assert data["review_identity"]["inventory_sha256"]
            result = await sender.send(n)
            assert result["completed"] is True
            sent = state["sends"][-1]
            assert sent.content == req["wire"]
            assert str(sent.url) == "https://8.8.8.8/responses"
            assert sent.headers["host"] == "api.deepseek.com"
            assert sent.extensions["sni_hostname"] == "api.deepseek.com"
            assert sent.headers["accept-encoding"] == "identity"
            assert "synthetic-secret" not in json.dumps(b.snapshot())
        with pytest.raises(d.GateFailure, match="CASE_REVIEW_REQUIRED"):
            b.prepare()

    asyncio.run(run())
    rows = snapshot(b)["attempts"]
    assert len(rows) == state["reads"] == state["dns"] == len(state["sends"]) == 5
    assert all(r["reasoning_tokens"] == 150 and r["output_tokens"] == 200 for r in rows)


def test_same_attempt_concurrent_send_only_one_reads_key_or_opens_network(rig):
    b, sender, state, _ = rig
    _, n = reserve(b)

    async def run():
        state["entered"], state["pause"] = asyncio.Event(), asyncio.Event()
        first = asyncio.create_task(sender.send(n))
        await state["entered"].wait()
        with pytest.raises(d.GateFailure, match="SEND_ALREADY_CONSUMED"):
            await sender.send(n)
        state["pause"].set()
        await first
        with pytest.raises(d.GateFailure, match="SEND_ALREADY_CONSUMED"):
            await sender.send(n)

    asyncio.run(run())
    assert len(state["sends"]) == state["reads"] == state["dns"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("reference", "other"),
        ("consent_sha256", "d" * 64),
        ("root_sha256", "a" * 64),
        ("expires_at", 0),
        ("key", "bad\r\nheader"),
    ],
)
def test_stale_credential_or_consent_never_sends(rig, field, value):
    b, sender, state, _ = rig
    state["lease_edit"] = {field: value}
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match="SAFETY_FAILURE"):
        asyncio.run(sender.send(n))
    assert not state["sends"]
    assert snapshot(b)["run"]["halted"] == "SAFETY_FAILURE"


@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("8.8.8.8", "169.254.169.254")])
def test_dns_private_or_mixed_public_private_before_credentials(rig, addresses):
    b, sender, state, _ = rig
    state["addresses"] = addresses
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match="TARGET_CHANGED"):
        asyncio.run(sender.send(n))
    assert not state["sends"] and not state["reads"]
    assert snapshot(b)["run"]["halted"] == "TARGET_CHANGED"


@pytest.mark.parametrize(
    "status,code",
    [
        (302, "TARGET_CHANGED"),
        (401, "AUTHENTICATION_FAILED"),
        (429, "RATE_LIMITED"),
        (500, "TEMPORARILY_UNAVAILABLE"),
    ],
)
def test_http_errors_stop_once_without_redirect_or_retry(rig, status, code):
    b, sender, state, _ = rig
    state.update(
        status=status,
        headers={"Location": "http://127.0.0.1/private"},
        raw=b"vendor error with synthetic-secret-not-a-key",
    )
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match=code):
        asyncio.run(sender.send(n))
    assert len(state["sends"]) == 1
    assert snapshot(b)["run"]["halted"] == code
    assert "vendor" not in json.dumps(snapshot(b))


@pytest.mark.parametrize(
    "raw,code",
    [
        (b'{"status":"completed","status":"incomplete"}', "INVALID_OUTPUT"),
        (b"NaN", "INVALID_OUTPUT"),
        (b"[]", "INVALID_OUTPUT"),
        (b"synthetic-secret-not-a-key", "SAFETY_FAILURE"),
        (b"sk-123456789012345678901234", "SAFETY_FAILURE"),
        (b"x" * (2 * 1024 * 1024 + 1), "INVALID_OUTPUT"),
    ],
)
def test_malicious_or_oversized_observation_never_becomes_parent(rig, raw, code):
    b, sender, state, _ = rig
    state["raw"] = raw
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match=code):
        asyncio.run(sender.send(n))
    row = snapshot(b)["attempts"][0]
    assert row["state"] == "failed" and row["value_hash"] is None


@pytest.mark.parametrize(
    "change",
    [
        "incomplete",
        "wrong_model",
        "missing_usage",
        "tools",
        "two_messages",
        "two_parts",
        "reasoning_exceeds_total",
    ],
)
def test_protocol_identity_and_usage_faults_halt(rig, change):
    b, sender, state, _ = rig

    def edit(v):
        if change == "incomplete":
            v["status"] = "incomplete"
        elif change == "wrong_model":
            v["model"] = "other"
        elif change == "missing_usage":
            v.pop("usage")
        elif change == "tools":
            v["output"].append({"type": "function_call", "name": "exec"})
        elif change == "two_messages":
            v["output"] *= 2
        elif change == "two_parts":
            v["output"][0]["content"] *= 2
        else:
            v["usage"]["output_tokens_details"]["reasoning_tokens"] = 201

    state["edit"] = edit
    _, n = reserve(b)
    with pytest.raises(d.GateFailure):
        asyncio.run(sender.send(n))
    assert snapshot(b)["run"]["halted"] is not None
    assert len(state["sends"]) == 1


def test_compression_rejected_without_decoding(rig):
    b, sender, state, _ = rig
    state.update(headers={"Content-Encoding": "gzip"}, raw=b"not gzip")
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match="INVALID_OUTPUT"):
        asyncio.run(sender.send(n))
    assert snapshot(b)["attempts"][0]["value_hash"] is None


@pytest.mark.parametrize(
    "error,code",
    [
        (httpx.ReadTimeout("private vendor text"), "TIMEOUT"),
        (httpx.ConnectError("secret"), "TEMPORARILY_UNAVAILABLE"),
    ],
)
def test_network_failure_no_retry_or_vendor_error_in_ledger(rig, error, code):
    b, sender, state, _ = rig
    state["failure"] = error
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match=code):
        asyncio.run(sender.send(n))
    assert len(state["sends"]) == 1
    assert "private vendor" not in json.dumps(snapshot(b))


def test_cancellation_durable_stop(rig):
    b, sender, state, _ = rig
    _, n = reserve(b)

    async def run():
        state["entered"], state["pause"] = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(sender.send(n))
        await state["entered"].wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert snapshot(b)["run"]["halted"] == "SAFETY_FAILURE"
    assert len(state["sends"]) == 1


def test_consumed_stale_target_bytes_block_send(rig):
    b, sender, state, _ = rig
    _, n = reserve(b)
    target = json.loads(sender.target_bytes)
    target["base_url"] = "http://127.0.0.1"
    sender.target_bytes = p.encoded(target)
    with pytest.raises(d.GateFailure, match="TARGET_CHANGED"):
        asyncio.run(sender.send(n))
    assert not state["reads"] and not state["dns"] and not state["sends"]


def test_payload_contains_only_copyable_hashes_not_hashing_instructions(rig):
    b, _, _, _ = rig
    while True:
        try:
            request, n = reserve(b)
        except d.GateFailure as exc:
            assert exc.code == "CASE_REVIEW_REQUIRED"
            break
        body = json.loads(request["wire"])
        data = json.loads(body["input"][1]["content"])
        assert data["blocks"][0]["text"] == data["candidate"]["content"]["markdown"]
        inner = sample_value(b, request)
        if "identity" in inner:
            assert inner["identity"] == data["review_identity"]
        value = bound_value(request, inner)
        assert Draft202012Validator(body["text"]["format"]["schema"]).is_valid(value)
        b.consume(n)
        b.finish(
            n,
            value=value,
            model=b.manifest["target"]["model"],
            status="completed",
            input_tokens=1,
            output_tokens=1,
            response_sha256="e" * 64,
        )


def test_contract_schema_rejects_unbounded_arrays_and_extra_keys():
    cs = contracts()
    for contract in cs.values():
        Draft202012Validator.check_schema(contract["schema"])
    original = copy.deepcopy(cs)
    cs["claim"]["schema"]["properties"]["result"]["properties"]["findings"]["maxItems"] = 999
    assert original == contracts()
    assert not Draft202012Validator(contracts()["correction"]["schema"]).is_valid(
        {
            "request_binding": {"root_sha256": "a" * 64, "parents_sha256": "b" * 64, "slot": "x"},
            "result": {},
        }
    )


def test_escaped_secret_reflection_rejected_after_strict_json_decode(rig):
    b, sender, state, _ = rig
    state["raw"] = b'{"leak":"\\u0073ynthetic-secret-not-a-key"}'
    _, n = reserve(b)
    with pytest.raises(d.GateFailure, match="SAFETY_FAILURE"):
        asyncio.run(sender.send(n))
    assert snapshot(b)["attempts"][0]["value_hash"] is None


def test_incomplete_keeps_observed_safe_usage_and_reserved_cost(rig):
    b, sender, state, _ = rig
    state["edit"] = lambda v: v.update(status="incomplete")
    _, n = reserve(b)
    before = snapshot(b)["attempts"][0]["cost"]
    with pytest.raises(d.GateFailure, match="INVALID_OUTPUT"):
        asyncio.run(sender.send(n))
    row = snapshot(b)["attempts"][0]
    assert (row["input_tokens"], row["output_tokens"], row["reasoning_tokens"]) == (100, 200, 150)
    assert row["cost"] == before and row["state"] == "failed"


def test_changed_frozen_source_prevents_dns_and_key_read(rig):
    b, sender, state, _ = rig
    _, n = reserve(b)
    (b.root / "proof.txt").write_text("changed")
    with pytest.raises(d.GateFailure, match="FREEZE_CHANGED"):
        asyncio.run(sender.send(n))
    assert not state["reads"] and not state["dns"] and not state["sends"]


def test_client_disables_environment_proxy_redirects_and_retries(rig, monkeypatch):
    b, sender, _, _ = rig
    real_client = httpx.AsyncClient
    calls = []

    def client(**kwargs):
        calls.append(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:12345")
    _, n = reserve(b)
    asyncio.run(sender.send(n))
    assert len(calls) == 1
    assert calls[0]["trust_env"] is False and calls[0]["follow_redirects"] is False
    # MockTransport is explicitly supplied only by this synthetic fixture. The default
    # branch separately constructs AsyncHTTPTransport(retries=0), never an SDK.


def test_abort_unknown_and_hostile_usage_stays_unknown(rig):
    b, _, _, _ = rig
    _, n = reserve(b)
    b.consume(n)
    with pytest.raises(d.GateFailure, match="INVALID_OUTPUT"):
        b.abort(
            n,
            error_code="INVALID_OUTPUT",
            input_tokens=True,
            output_tokens=2**90,
            reasoning_tokens=1,
        )
    row = snapshot(b)["attempts"][0]
    assert row["input_tokens"] is row["output_tokens"] is row["reasoning_tokens"] is None


def test_default_transport_explicitly_disables_retries(rig, monkeypatch):
    b, sender, _, _ = rig
    mock = sender.transport
    sender.transport = None
    arguments = []

    def transport(**kwargs):
        arguments.append(kwargs)
        return mock

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    _, n = reserve(b)
    asyncio.run(sender.send(n))
    assert arguments == [{"retries": 0}]


def test_role_schema_all_strings_arrays_and_objects_have_finite_bounds():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "string":
                assert "maxLength" in node or "enum" in node or "const" in node
            if node.get("type") == "array":
                assert type(node["maxItems"]) is int
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for contract in contracts().values():
        walk(contract["schema"])


def test_draft_is_not_an_execution_manifest_or_fee_approval():
    from prepare_t040_derived_calibration import CASE_IDS, MAX_WIRE, build, wire_bound

    draft = build()
    assert draft["state"] == "DRAFT_NOT_EXECUTABLE"
    assert draft["potential_request_upper_bound"] == 2 * (16 + 3) == 38
    assert draft["cost_cap_micro_cny"] is None
    assert draft["token_bound_proof"]["status"] == "MISSING"
    assert draft["provider_requests_authorized"] == draft["provider_cost_micro_authorized"] == 0
    assert tuple(c["historical_case_id"] for c in draft["cases"]) == CASE_IDS
    assert draft["corrections"] == 0
    for case in draft["cases"]:
        for stage, bound in case["wire_byte_upper_bounds"].items():
            assert bound == wire_bound(case["payload"], stage, contracts()[stage]) <= MAX_WIRE
        # Byte-bound proof covers a double JSON serialization, even controls/escapes/Unicode.
        adversarial = {"text": '\u0000\\\\"🙂中文' * 100}
        assert (
            len(p.encoded(p.encoded(adversarial).decode())) <= 2 * len(p.encoded(adversarial)) + 2
        )
