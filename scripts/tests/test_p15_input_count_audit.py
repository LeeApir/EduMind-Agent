"""Offline forensic comparison and original transport replay, never a real probe."""

import asyncio
import json
import socket
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from acceptance_support.p15_diagnostic_transport import CountedTransport  # noqa: E402
from audit_p15_input_count import OUTPUT, build, findings  # noqa: E402


@pytest.fixture(autouse=True)
def forbid_network_and_env(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network or credentials allowed")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name != ".env" and not path.name.startswith(".env.")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)


def evidence():
    result = json.loads((ROOT / "docs/acceptance/phase-1.5-development-diagnostic-results-r03/results.json").read_text())
    paths = {i["role"]: Path(i["path"]) for i in result["raw_evidence"]}
    return [paths[k].read_bytes() for k in ("request_body", "count_response", "model_response")]


def test_actual_comparison_and_frozen_evidence():
    assert build() == json.loads((ROOT / OUTPUT).read_text())


@pytest.mark.parametrize("mode", ["actual", "count_equal_but_transformed", "clean_control"])
def test_original_transport_exact_body_replay(tmp_path, mode):
    body, raw_count, raw_response = evidence()
    response = json.loads(raw_response)
    if mode != "actual":
        raw_count = json.dumps({"object": "response.input_tokens", "input_tokens": 6507}).encode()
    if mode == "clean_control":
        request = json.loads(body)
        response["instructions"] = "\n\n".join(m["content"] for m in request["input"] if m["role"] == "system")
        response["max_output_tokens"] = request["max_output_tokens"]
    seen = []

    def handler(request):
        seen.append((request.url.path, request.content, dict(request.headers), dict(request.extensions)))
        return httpx.Response(200, content=raw_count if request.url.path.endswith("input_tokens") else json.dumps(response).encode())

    ledger = Ledger(tmp_path / "TEST_ONLY.sqlite")
    limits = Limits(2, 32000, 8000, None, 600)
    approval = dict(scope="PHASE-1.5-T038", batch_id="TEST_ONLY", package_sha256="a" * 64,
                    limits=asdict(limits), fee_cap_waiver=True, evidence_ref="synthetic_offline_only")
    ledger.start("TEST_ONLY", "a" * 64, limits, approval, pinned_approval_sha256=digest(approval))
    transport = CountedTransport(httpx.MockTransport(handler), ledger, "TEST_ONLY", "a" * 64, tmp_path, "TEST_ONLY")
    request = httpx.Request("POST", "https://www.cbbb.fun/v1/responses", content=body,
                            headers={"Host": "www.cbbb.fun", "Content-Type": "application/json"},
                            extensions={"sni_hostname": "www.cbbb.fun"})
    try:
        if mode == "actual":
            with pytest.raises(Refused, match="USAGE_BOUND_MISMATCH"):
                asyncio.run(transport.handle_async_request(request))
            assert ledger.usage("TEST_ONLY")["input_tokens"] == 32000
            assert ledger.usage("TEST_ONLY")["output_tokens"] == 8000
            assert ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"
        else:
            asyncio.run(transport.handle_async_request(request))
            assert transport.usage == (6507, 480)
            # Equality alone passes even with the actual appended instructions and null cap.
            assert bool(findings(json.loads(body), json.loads(raw_count), response)) is (mode != "clean_control")
        assert [s[0] for s in seen] == ["/v1/responses/input_tokens", "/v1/responses"]
        assert seen[0][1:] == seen[1][1:]
        assert seen[0][1] == body
    finally:
        ledger.close()


@pytest.mark.parametrize("case,expected", [
    ("clean", []),
    ("count", ["INPUT_COUNT_MISMATCH"]),
    ("instructions", ["INSTRUCTIONS_ECHO_DIFFERENT_OR_UNVERIFIED"]),
    ("cap", ["OUTPUT_LIMIT_ECHO_DIFFERENT_OR_UNVERIFIED"]),
    ("schema", ["SCHEMA_ECHO_DIFFERENT_OR_UNVERIFIED"]),
])
def test_proposed_checks_are_independent(case, expected):
    body, _, raw = evidence()
    request = json.loads(body)
    response = deepcopy(json.loads(raw))
    response["instructions"] = "\n\n".join(m["content"] for m in request["input"] if m["role"] == "system")
    response["max_output_tokens"] = request["max_output_tokens"]
    count = {"input_tokens": response["usage"]["input_tokens"]}
    if case == "count":
        count["input_tokens"] -= 1
    if case == "instructions":
        response["instructions"] += "\nUNAPPROVED"
    if case == "cap":
        response["max_output_tokens"] = None
    if case == "schema":
        response["text"]["format"]["schema"] = {}
    assert findings(request, count, response) == expected
