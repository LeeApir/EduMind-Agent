"""No credentials or network: safe failure records from the actual adapter path."""

import asyncio
import hashlib
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]

import run_review_config_observed as runner  # noqa: E402
from acceptance_support.failure_observation import observe_failure  # noqa: E402
from acceptance_support.om_diagnostic import stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from prepare_review_config_comparison import build, review_document  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.services.provider_gateway import (  # noqa: E402
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
    TokenUsage,
)

SECRET = "SYNTHETIC_PRIVATE_KEY"
BODY_SECRET = "SYNTHETIC_VENDOR_AND_LEARNER_TEXT"
SLOT = "trace-complete:candidate"


@pytest.fixture(scope="module")
def prepared():
    return build()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    values = deepcopy(prepared)
    p, data = values["proposal.json"], values["cases.json"]
    p["execution_root"] = str(tmp_path.resolve())
    p["expiry_local"] = "2099-01-01T00:00:00+08:00"
    values["token-cost-proof.json"]["checked_on"] = runner.time.strftime("%Y-%m-%d")
    p["proof_sha256"] = stable(values["token-cost-proof.json"])
    names = (
        "backend/app/services/deepseek_responses.py",
        "docs/ADR/0015-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    )
    p["sources"] = {n: stable(n) for n in names}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(runner.canonical(name))
    base = tmp_path / runner.BASE
    base.mkdir(parents=True)
    for name, value in values.items():
        (base / name).write_text(json.dumps(value))
    (base / "human-review.md").write_text(review_document(data))
    (base / "run-approval.json").write_text(
        json.dumps(
            {
                "version": "om-admission-human-approval-v1",
                "proposal_sha256": stable(p),
                "requests": 14,
                "cost_micro_cny": p["cost_micro_cny"],
                "labels_sha256": p["labels_sha256"],
                "confirmed_by": "Lee",
                "user_confirmation": "SYNTHETIC_ONLY",
                "source_message_id": "synthetic",
                "terms_verified_on": runner.time.strftime("%Y-%m-%d"),
            }
        )
    )
    (base / "labels-human.json").write_text(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "labels_sha256": p["labels_sha256"],
                "case_digests": {n: stable(c["material"]) for n, c in data.items()},
                "decision": "accept_calibration_labels",
                "reviewer": "Lee",
                "source_message_id": "synthetic",
            }
        )
    )
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda _: ProviderSettings(
            "https://api.deepseek.com", SECRET, "deepseek-flash"
        ),
    )
    return tmp_path, values


def body():
    return {
        "model": "deepseek-flash",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": json.dumps(valid_review("unit"))}
                ],
            }
        ],
        "usage": {"input_tokens": 90, "output_tokens": 30},
    }


def ledger(root):
    path = root / runner.PRIVATE / "budget.sqlite"
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return (
            db.execute("select halted from run").fetchone()[0],
            db.execute(
                "select state,input_tokens,output_tokens,error_code,cost_micro from attempts"
            ).fetchall(),
        )


def observation(root):
    path = root / runner.PRIVATE / (SLOT + "-failure-observation.json")
    assert path.stat().st_mode & 0o077 == 0
    raw = path.read_text()
    assert SECRET not in raw and BODY_SECRET not in raw
    return json.loads(raw)["observation"]


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("cutoff", "OUTPUT_TOKEN_LIMIT"),
        ("structured_json", "STRUCTURED_JSON_INVALID"),
        ("schema", "STRUCTURED_SCHEMA_MISMATCH"),
        ("response_json", "RESPONSE_JSON_INVALID"),
    ],
)
def test_actual_adapter_errors_keep_reason_usage_hash_and_halt(execution, mode, reason):
    root, _ = execution
    value = body()
    value["vendor_message"] = BODY_SECRET
    if mode == "cutoff":
        value.update(
            status="incomplete", incomplete_details={"reason": "max_output_tokens"}
        )
        value["usage"]["output_tokens"] = 2048
    elif mode == "structured_json":
        value["output"][0]["content"][0]["text"] = '{"unterminated":"' + BODY_SECRET
    elif mode == "schema":
        value["output"][0]["content"][0]["text"] = json.dumps(
            {"unexpected": BODY_SECRET}
        )
    raw = (
        json.dumps(value).encode()
        if mode != "response_json"
        else (BODY_SECRET + "{").encode()
    )
    calls = []

    def send(request):
        calls.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    obs = observation(root)
    assert obs["output_failure_reason"] == reason
    assert obs["stage"] == "provider"
    assert obs["transport_dispatch_count"] == 1 and obs["http_status"] == 200
    assert obs["response_capture_complete"] is True
    assert obs["decoded_response_sha256"] == hashlib.sha256(raw).hexdigest()
    expected_in = None if mode == "response_json" else 90
    expected_out = None if mode == "response_json" else 2048 if mode == "cutoff" else 30
    assert (obs["input_tokens"], obs["output_tokens_including_reasoning"]) == (
        expected_in,
        expected_out,
    )
    halt, rows = ledger(root)
    assert halt == "INVALID_OUTPUT" and rows[0][:4] == (
        "failed",
        expected_in,
        expected_out,
        "INVALID_OUTPUT",
    )
    assert rows[0][4] > 0  # Reservation is never refunded.
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "mode", ["rate_limit", "network", "missing_usage", "privacy", "invalid_envelope"]
)
def test_safe_failure_metadata_without_vendor_text_or_fake_zero(execution, mode):
    root, _ = execution
    value = body()
    if mode == "missing_usage":
        value.pop("usage")
    if mode == "invalid_envelope":
        value["status"] = {"untrusted": BODY_SECRET}
        value["usage"] = {"input_tokens": True, "output_tokens": BODY_SECRET}
    if mode == "privacy":
        reflected = valid_review("unit")
        reflected.update(verdict="needs_human", unresolved=[SECRET])
        value["output"][0]["content"][0]["text"] = json.dumps(reflected)
    calls = []

    def send(request):
        calls.append(request)
        if mode == "network":
            raise httpx.ConnectError(BODY_SECRET)
        if mode == "rate_limit":
            return httpx.Response(429, json={"error": {"message": BODY_SECRET}})
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(value).encode()))

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    obs = observation(root)
    assert obs["transport_dispatch_count"] == 1
    assert obs["dispatch_is_server_receipt_proof"] is False
    if mode == "rate_limit":
        assert obs["http_status"] == 429 and not obs["response_capture_complete"]
    if mode == "network":
        assert obs["http_status"] is None and not obs["response_capture_complete"]
    if mode == "privacy":
        assert obs["normalized_error"] == "SAFETY_FAILURE"
        assert obs["stage"] == "response_checks"
    if mode in {"rate_limit", "network", "missing_usage", "invalid_envelope"}:
        assert (
            obs["input_tokens"] is None
            and obs["output_tokens_including_reasoning"] is None
        )
    assert len(calls) == 1 and ledger(root)[1][0][0] == "failed"


def test_before_dispatch_failure_is_zero_dispatch_but_unknown_usage(
    execution, monkeypatch
):
    root, _ = execution
    monkeypatch.setattr(
        runner,
        "credentials",
        lambda _: (_ for _ in ()).throw(GateFailure("SAFETY_FAILURE")),
    )
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(root, resolver=lambda *_: pytest.fail("unexpected DNS"))
        )
    obs = observation(root)
    assert obs["stage"] == "credentials" and obs["transport_dispatch_count"] == 0
    assert obs["http_status"] is None and obs["input_tokens"] is None


def test_diagnostic_write_failure_cannot_release_reservation_or_retry(
    execution, monkeypatch
):
    root, _ = execution
    original = runner.private_write

    def fail_write(path, value):
        if path.name.endswith("-failure-observation.json"):
            raise PermissionError(BODY_SECRET)
        original(path, value)

    monkeypatch.setattr(runner, "private_write", fail_write)
    value = body()
    value.update(
        status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    with pytest.raises(PermissionError):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200, stream=httpx.ByteStream(json.dumps(value).encode())
                    )
                ),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    assert ledger(root)[0] == "INVALID_OUTPUT"
    assert len(ledger(root)[1]) == 1
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))


def test_partial_capture_is_not_hashed_as_a_complete_response(execution):
    root, _ = execution

    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield (BODY_SECRET + "partial").encode()
            raise httpx.ReadError(BODY_SECRET)

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, stream=Broken())
                ),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    obs = observation(root)
    assert obs["response_capture_complete"] is False
    assert obs["captured_wire_sha256"] is not None
    assert obs["decoded_response_sha256"] is None
    assert obs["input_tokens"] is None


def test_missing_approval_stops_before_key_dns_or_directory(execution, monkeypatch):
    root, _ = execution
    (root / runner.BASE / "run-approval.json").unlink()
    monkeypatch.setattr(runner, "credentials", lambda _: pytest.fail("premature key"))
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED"):
        asyncio.run(runner.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / runner.PRIVATE).exists()


def test_unknown_exception_and_untrusted_fields_never_serialize_text():
    audit = SimpleNamespace(payload=b"", capture_complete=False, sent=0, status=None)
    result = observe_failure(
        RuntimeError(BODY_SECRET + SECRET), audit=audit, stage=BODY_SECRET
    )
    assert BODY_SECRET not in json.dumps(result) and SECRET not in json.dumps(result)
    assert result["output_failure_reason"] is None and result["stage"] is None
    assert result["input_tokens"] is None


def test_error_usage_outside_bound_is_recorded_and_halts(execution, monkeypatch):
    root, _ = execution

    class Over:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_structured(self, request):
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.OUTPUT_TOKEN_LIMIT,
                usage=TokenUsage(90, 2049),
            )

    monkeypatch.setattr(runner, "DeepSeekResponsesAdapter", Over)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(runner.step(root, resolver=lambda *_: ["8.8.8.8"]))
    assert observation(root)["output_tokens_including_reasoning"] == 2049
    assert ledger(root)[0] == "USAGE_BOUND_EXCEEDED"


def test_success_still_sends_one_exact_request_and_waits_for_receipt(execution):
    root, values = execution
    calls = []

    def send(request):
        calls.append(request)
        assert request.content == bytes.fromhex(values["cases.json"][SLOT]["wire_hex"])
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body()).encode()))

    result = asyncio.run(
        runner.step(
            root, transport=httpx.MockTransport(send), resolver=lambda *_: ["8.8.8.8"]
        )
    )
    assert result["status"] == "HUMAN_CHECK_REQUIRED"
    assert not list((root / runner.PRIVATE).glob("*-failure-observation.json"))
    with pytest.raises(GateFailure, match="NOT_AUTHORIZED|HUMAN_CHECK_REQUIRED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1 and ledger(root)[1][0][:3] == ("complete", 90, 30)


@pytest.mark.parametrize(
    "cause,normalized,category",
    [
        (TimeoutError(BODY_SECRET), "TIMEOUT", "deadline"),
        (asyncio.CancelledError(BODY_SECRET), "SAFETY_FAILURE", "cancellation"),
    ],
)
def test_timeout_and_cancellation_keep_stop_evidence(
    execution, cause, normalized, category
):
    root, _ = execution

    def send(request):
        raise cause

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    obs = observation(root)
    assert obs["normalized_error"] == normalized and obs["error_category"] == category
    assert obs["transport_dispatch_count"] == 1 and obs["http_status"] is None
    assert obs["input_tokens"] is None and ledger(root)[0] is not None


def test_dns_failure_records_no_dispatch(execution):
    root, _ = execution

    def fail(*args):
        raise OSError(BODY_SECRET)

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(runner.step(root, resolver=fail))
    obs = observation(root)
    assert obs["stage"] == "target_resolution"
    assert obs["transport_dispatch_count"] == 0 and obs["http_status"] is None


def test_valid_envelope_can_recover_usage_when_shape_error_has_no_attached_usage(
    execution,
):
    root, _ = execution
    value = body()
    value["output"] = []
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200, stream=httpx.ByteStream(json.dumps(value).encode())
                    )
                ),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    obs = observation(root)
    assert obs["output_failure_reason"] is None
    assert obs["usage_sources"] == {
        "input_tokens": "decoded_envelope",
        "output_tokens": "decoded_envelope",
    }
    assert ledger(root)[1][0][1:3] == (90, 30)


def test_complete_gzip_capture_has_distinct_wire_and_decoded_digests(execution):
    import gzip

    root, _ = execution
    value = body()
    value["output"] = []
    raw = json.dumps(value).encode()
    packed = gzip.compress(raw)
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200,
                        headers={"Content-Encoding": "gzip"},
                        stream=httpx.ByteStream(packed),
                    )
                ),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    obs = observation(root)
    assert obs["captured_wire_sha256"] == hashlib.sha256(packed).hexdigest()
    assert obs["decoded_response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert obs["response_capture_complete"] is True
