"""Mock actual adapter failures; no key, DNS or real Provider request."""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "scripts/tests"),
]
import run_review_suite_observed as runner  # noqa: E402
import test_review_suite as suite  # noqa: E402
from prepare_review_suite import build  # noqa: E402
from acceptance_support.schema_failure_observation import schema_location  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from acceptance_support.om_diagnostic import valid_review  # noqa: E402
from app.services.provider_gateway import (  # noqa: E402
    ProviderError,
    ProviderErrorCode,
    OutputFailureReason,
)  # noqa: E402

SECRET = "SYNTHETIC_PRIVATE_KEY_AND_STUDENT_TEXT"


@pytest.fixture(scope="module")
def prepared():
    return build()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    monkeypatch.setattr(suite, "r", runner)
    return suite.execution.__wrapped__(tmp_path, monkeypatch, prepared)


def payload(value):
    return {
        "model": "deepseek-flash",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(value)}],
            }
        ],
        "usage": {"input_tokens": 90, "output_tokens": 6000},
    }


@pytest.mark.parametrize(
    "mode", ["root-extra", "nested-extra", "unknown-extra", "missing", "enum", "type"]
)
def test_actual_adapter_failure_safe_paths_and_persistent_halt(execution, mode):
    root, values = execution
    value = valid_review("unit")
    if mode == "root-extra":
        value["reason"] = SECRET
    if mode == "nested-extra":
        value["coverage"]["message"] = SECRET
    if mode == "unknown-extra":
        value[SECRET] = SECRET
    if mode == "missing":
        value.pop("verdict")
    if mode == "enum":
        value["verdict"] = SECRET
    if mode == "type":
        value["coverage"]["checked"] = SECRET
    calls = []

    def send(request):
        calls.append(request.content)
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(payload(value)).encode())
        )

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    p = root / runner.PRIVATE / (runner.SLOT_IDS[0] + "-failure-observation.json")
    raw = p.read_text()
    assert SECRET not in raw
    record = json.loads(raw)
    obs = record["observation"]
    loc = obs["schema_location"]
    assert obs["version"] == "safe-failure-observation-v2"
    assert loc["status"] == "LOCATED" and loc["first_violation_only"]
    assert (
        loc["request_wire_sha256"] == values["proposal.json"]["slots"][0]["wire_sha256"]
    )
    if mode in ["root-extra", "nested-extra", "unknown-extra"]:
        assert loc["keyword"] == "additionalProperties"
        assert loc["instance_path"]["segments"] == (
            ["coverage"] if mode == "nested-extra" else []
        )
        assert loc["unexpected"]["fields"][0]["name"] == (
            "reason"
            if mode == "root-extra"
            else "message"
            if mode == "nested-extra"
            else "<redacted>"
        )
    elif mode == "missing":
        assert loc["missing"]["fields"][0]["name"] == "verdict"
    elif mode == "enum":
        assert loc["instance_path"]["segments"] == ["verdict"]
    else:
        assert loc["instance_path"]["segments"] == ["coverage", "checked"]
    assert p.stat().st_mode & 0o077 == 0
    assert (
        obs["input_tokens"] == 90 and obs["output_tokens_including_reasoning"] == 6000
    )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
    assert len(calls) == 1
    db = sqlite3.connect(
        (root / runner.PRIVATE / "budget.sqlite").as_uri() + "?mode=ro", uri=True
    )
    assert db.execute("select count(*) from attempts").fetchone()[0] == 1
    assert db.execute("select halted from run").fetchone()[0] == "INVALID_OUTPUT"
    db.close()


def schema_error():
    return ProviderError(
        ProviderErrorCode.INVALID_OUTPUT,
        output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
    )


def test_absent_partial_or_unrelated_capture_is_not_reconstructed():
    assert schema_location(schema_error())["status"] == "INCOMPLETE_CAPTURE"
    audit = SimpleNamespace(
        capture_complete=False, decoded=lambda: pytest.fail("must not decode partial")
    )
    assert (
        schema_location(schema_error(), audit=audit)["status"] == "INCOMPLETE_CAPTURE"
    )
    assert (
        schema_location(Exception(SECRET), audit=audit)["status"]
        == "NOT_SCHEMA_FAILURE"
    )


def wire_schema():
    values = build()
    wire = bytes.fromhex(values["cases.json"][runner.SLOT_IDS[0]]["wire_hex"])
    return json.loads(wire)


def replay(value, body=None):
    envelope = payload(value)
    audit = SimpleNamespace(
        capture_complete=True, decoded=lambda: json.dumps(envelope).encode()
    )
    return schema_location(
        schema_error(),
        audit=audit,
        request_wire=json.dumps(body or wire_schema()).encode(),
    )


def test_bounds_many_extra_fields_and_secret_names():
    v = valid_review("unit")
    v.update({SECRET + str(i): SECRET for i in range(40)})
    result = replay(v)
    assert result["unexpected"]["count"] == 40 and result["unexpected"]["truncated"]
    assert len(result["unexpected"]["fields"]) == 16
    assert SECRET not in json.dumps(result)


def test_array_index_and_invalid_field_value_never_serialized():
    v = valid_review("unit")
    v["coverage"]["checked"][1] = SECRET
    loc = replay(v)
    assert loc["instance_path"]["segments"] == ["coverage", "checked", 1]
    assert SECRET not in json.dumps(loc)


def test_external_schema_ref_rejected_and_no_error_text_leaks():
    body = wire_schema()
    body["text"]["format"]["schema"] = {"$ref": "https://127.0.0.1/" + SECRET}
    loc = replay({}, body)
    assert loc["status"] == "REPLAY_UNAVAILABLE" and SECRET not in json.dumps(loc)


def test_replay_mismatch_not_faked_into_a_known_field():
    assert replay(valid_review("unit"))["status"] == "REPLAY_NO_SCHEMA_ERROR"
    audit = SimpleNamespace(
        capture_complete=True, decoded=lambda: (_ for _ in ()).throw(ValueError(SECRET))
    )
    loc = schema_location(
        schema_error(), audit=audit, request_wire=json.dumps(wire_schema()).encode()
    )
    assert loc["status"] == "REPLAY_UNAVAILABLE" and SECRET not in json.dumps(loc)


def test_future_executor_unapproved_before_key_dns_or_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "credentials", lambda _: pytest.fail("premature Key"))
    with pytest.raises(GateFailure):
        asyncio.run(
            runner.step(tmp_path, resolver=lambda *_: pytest.fail("premature DNS"))
        )
    assert not (tmp_path / runner.PRIVATE).exists()
    import run_review_suite as old

    assert old.BASE.endswith("r01") and runner.BASE.endswith("r02")


def test_diagnostic_disk_failure_cannot_release_halt(execution, monkeypatch):
    root, _ = execution
    write = runner.private_write

    def fail(path, value):
        if path.name.endswith("-failure-observation.json"):
            raise OSError(SECRET)
        return write(path, value)

    monkeypatch.setattr(runner, "private_write", fail)
    value = valid_review("unit")
    value["reason"] = SECRET
    with pytest.raises(OSError):
        asyncio.run(
            runner.step(
                root,
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200,
                        stream=httpx.ByteStream(json.dumps(payload(value)).encode()),
                    )
                ),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(runner.step(root))
