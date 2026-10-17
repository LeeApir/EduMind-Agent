"""Real isolated PG/ConnectionOperation with MockHTTP; synthetic inputs, no cloud calls."""

# ruff: noqa: E402, F811
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "scripts/tests"),
]
import run_qwen_review as r
from acceptance_support.qwen_review_attempt import perform
from test_qwen_review_execution import prepared, execution  # noqa: F401 fixture reuse
from test_evidence_v45 import answer

DB_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="dedicated PostgreSQL URL required")


@pytest.mark.parametrize(
    "variant",
    [
        "ok8202",
        "alias",
        "schema",
        "length",
        "wrong_model",
        "key_echo",
        "http403",
        "overrun",
        "timeout",
    ],
)
def test_real_selected_dispatch_audit_cleanup_and_failure(
    execution, monkeypatch, variant
):
    root, p, data = execution
    case = next(iter(data.values()))
    calls = []
    key = "SYNTHETIC_QWEN_RUNTIME_KEY"
    monkeypatch.setattr(r, "credentials", lambda *_: ("https://chosen.test/v1", key))
    monkeypatch.setattr(r, "database_url", lambda: DB_URL)
    value = answer(case)
    if variant == "schema":
        value["unresolved"] = [{"unknown_unsafe_field": "DO_NOT_PERSIST_THIS_VALUE"}]
    if variant == "key_echo":
        value["findings"][0]["impact"] = key
    payload = {
        "model": "deepseek-flash"
        if variant == "wrong_model"
        else "qwen3.8-max-2026-09-02"
        if variant == "alias"
        else "qwen3.8-max-0902",
        "choices": [
            {
                "index": 0,
                "finish_reason": "length" if variant == "length" else "stop",
                "message": {"role": "assistant", "content": json.dumps(value)},
            }
        ],
        "usage": {
            "prompt_tokens": 14000,
            "completion_tokens": 8203 if variant == "overrun" else 8202,
        },
    }

    def send(request):
        calls.append(request.content)
        assert request.headers["Authorization"] == "Bearer " + key
        if variant == "timeout":
            raise httpx.ReadTimeout("DO_NOT_PERSIST_PROVIDER_EXCEPTION")
        return httpx.Response(
            403 if variant == "http403" else 200,
            stream=httpx.ByteStream(json.dumps(payload).encode()),
        )

    async def attempt(*args, **kwargs):
        return await perform(
            *args,
            **kwargs,
            transport=httpx.MockTransport(send),
            resolver=lambda *_: ["8.8.8.8"],
        )

    if variant in {"ok8202", "alias"}:
        result = asyncio.run(r.step(root, attempt=attempt))
        receipt = r.read(root / r.PRIVATE / (result["slot"] + ".json"))
        assert (
            all(receipt["completeness"].values()) and receipt["output_tokens"] == 8202
        )
        assert receipt["review_record"]["request_digest"] == r.sha(calls[0])
        assert not receipt["human_confirmed"] and not receipt["t040_passed"]
        assert receipt["review_record"]["provider_config_digest"]
    else:
        with pytest.raises(r.GateFailure, match="CANDIDATE_ELIMINATED"):
            asyncio.run(r.step(root, attempt=attempt))
        failure = r.read(root / r.PRIVATE / (next(iter(data)) + "-failure.json"))
        assert key not in json.dumps(
            failure
        ) and "DO_NOT_PERSIST_THIS_VALUE" not in json.dumps(failure)
        assert all(failure["observation"]["cleanup"].values())
        assert "DO_NOT_PERSIST_PROVIDER_EXCEPTION" not in json.dumps(failure)
        if variant == "overrun":
            assert failure["complete_review_record"]["result"] == value
        if variant == "schema":
            assert failure["observation"]["schema_location"]["status"] == "LOCATED"
        if variant == "length":
            assert failure["observation"]["finish_reason"] == "length"
        with pytest.raises(r.GateFailure, match="RUN_HALTED"):
            asyncio.run(r.step(root, attempt=attempt))
    assert len(calls) == 1 and calls[0] == bytes.fromhex(case["candidate_wire_hex"])


@pytest.mark.parametrize("slot", list(r.read(ROOT / r.DESIGN / "cases.json")))
def test_every_frozen_case_real_review_entry_exact_mock_wire(slot):
    case = r.read(ROOT / r.DESIGN / "cases.json")[slot]
    wire = bytes.fromhex(case["candidate_wire_hex"])
    value = answer(case)
    calls = []
    authorizations = []

    def send(request):
        calls.append(request.content)
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                json.dumps(
                    {
                        "model": "qwen3.8-max-0902",
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {
                                    "role": "assistant",
                                    "content": json.dumps(value),
                                },
                            }
                        ],
                        "usage": {"prompt_tokens": 14000, "completion_tokens": 8193},
                    }
                ).encode()
            ),
        )

    async def run():
        async def authorize(request):
            authorizations.append(request)
            assert request.purpose == "connection_test" and request.consent.accepted
            assert (
                request.route.model_id
                == request.capabilities.model_id
                == "qwen3.8-max-0902"
            )
            assert request.capabilities.thinking_enabled is False

        return await perform(
            case,
            wire,
            endpoint="https://chosen.test/v1",
            key="SYNTHETIC_QWEN_FIXTURE_KEY",
            database_url=DB_URL,
            authorize=authorize,
            transport=httpx.MockTransport(send),
            resolver=lambda *_: ["8.8.8.8"],
        )

    outcome = asyncio.run(run())
    assert calls == [wire] and len(authorizations) == 1
    assert all(outcome["cleanup"].values())
    assert outcome["review_record"]["binding"] == case["material"]["binding"]
    assert outcome["review_record"]["result"] == value
    assert outcome["review_record"]["request_digest"] == r.sha(wire)
