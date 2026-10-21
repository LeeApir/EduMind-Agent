"""Continuation gates and exact remaining wires; all HTTP is Mock, never real quality."""

# ruff: noqa: E402
import asyncio
import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "scripts/tests"),
]
import run_qwen_continuation as r
from acceptance_support.qwen_review_attempt import perform, AttemptFailure
from acceptance_support.qwen_compatibility_transport import QwenCompatibilityTransport
from app.services.qwen_schema import QWEN_SCHEMA_PROFILE, qwen_wire_schema
from test_evidence_v45 import answer


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def prepared(tmp_path, monkeypatch, approved=True):
    p = deepcopy(r.old.read(ROOT / r.BASE / "proposal.json"))
    p["execution_root"] = str(tmp_path.resolve())
    p["expiry_local"] = "2099-01-01T00:00:00+08:00"
    files = {
        n: h
        for n, h in p["budget_manifest"]["files"].items()
        if n
        in [
            "backend/app/services/openai_compatible.py",
            "docs/ADR/0015-approval-20261015.json",
            "docs/acceptance/phase-1-provider-connection-v1/results/final.json",
        ]
    }
    p["sources"] = files
    p["budget_manifest"]["files"] = files
    for name in [
        *files,
        r.BASE + "/requests.json",
        r.old.DESIGN + "/cases.json",
        p["imported_receipt_path"],
        p["imported_human_path"],
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    base = tmp_path / r.BASE
    write(base / "proposal.json", p)
    if approved:
        write(
            base / "run-approval.json",
            {
                "proposal_sha256": r.old.stable(p),
                "requests": 11,
                "cost_micro_cny": p["cost_micro_cny"],
                "reviewer": "Lee",
                "source_message_id": "SYNTHETIC_ONLY",
                "user_confirmation": "SYNTHETIC_ONLY",
            },
        )
        write(
            base / ("terms-" + time.strftime("%Y-%m-%d") + ".json"),
            {
                "proposal_sha256": r.old.stable(p),
                "checked_on": time.strftime("%Y-%m-%d"),
                "prices_and_limits_unchanged": True,
            },
        )
    monkeypatch.setattr(
        r.old, "credentials", lambda *_: ("https://synthetic.test/v1", "SYNTHETIC_KEY")
    )
    monkeypatch.setattr(r.old, "database_url", lambda: "SYNTHETIC_DB_NOT_USED")
    return p


def confirm(root, p, slot):
    receipt = r.old.read(root / r.PRIVATE / (slot + ".json"))
    write(
        root / r.PRIVATE / (slot + "-human.json"),
        {
            "proposal_sha256": r.old.stable(p),
            "receipt_sha256": r.old.stable(receipt),
            "reviewer": "Lee",
            "source_message_id": "SYNTHETIC_ONLY",
            "decision": "continue",
            "completeness_checked": True,
            "all_assertions_checked": True,
            "all_citations_checked": True,
            "issues": [],
        },
    )


def synthetic(calls, failed=False):
    async def attempt(case, wire, **kwargs):
        calls.append(wire)
        assert kwargs["schema_profile"] == QWEN_SCHEMA_PROFILE
        if failed:
            raise AttemptFailure(
                {
                    "normalized_error": "CAPABILITY_UNAVAILABLE",
                    "http_status": 400,
                    "sent": 1,
                    "input_tokens": None,
                    "output_tokens": None,
                    "provider_error": {"parse": "NON_JSON"},
                }
            )
        return {
            "sent": 1,
            "normal_finish": True,
            "schema_valid": True,
            "input_tokens": 100,
            "output_tokens": 100,
            "cleanup": {"done": True},
            "review_record": {
                "result": answer(case),
                "binding": case["material"]["binding"],
                "request_digest": r.sha(wire),
            },
        }

    return attempt


def test_exact_11_repaired_wires_and_budget():
    p = r.old.read(ROOT / r.BASE / "proposal.json")
    requests = r.old.read(ROOT / r.BASE / "requests.json")
    cases = r.old.read(ROOT / r.old.DESIGN / "cases.json")
    assert list(requests) == list(cases)[1:]
    assert [s["phase"] for s in p["slots"]] == ["screen"] * 3 + ["generalization"] * 8
    for name, item in requests.items():
        original = json.loads(bytes.fromhex(cases[name]["candidate_wire_hex"]))
        body = json.loads(bytes.fromhex(item["wire_hex"]))
        original["response_format"]["json_schema"]["schema"] = qwen_wire_schema(
            original["response_format"]["json_schema"]["schema"]
        )
        assert body == original
        assert item["request_sha256"] == r.sha(bytes.fromhex(item["wire_hex"]))
    assert p["cost_micro_cny"] == sum(
        12 * (1048576 + s["wire_bytes"]) + 36 * 8202 for s in p["slots"]
    )


def test_unapproved_no_private_state(tmp_path, monkeypatch):
    prepared(tmp_path, monkeypatch, False)
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(tmp_path))
    assert not (tmp_path / r.PRIVATE).exists()


def test_wrong_imported_result_confirmation_blocks(tmp_path, monkeypatch):
    p = prepared(tmp_path, monkeypatch)
    human = r.old.read(tmp_path / p["imported_human_path"])
    human["receipt_sha256"] = "0" * 64
    write(tmp_path / p["imported_human_path"], human)
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(tmp_path))
    assert not (tmp_path / r.PRIVATE).exists()


def test_all11_require_human_and_4receipt_screen_gate(tmp_path, monkeypatch):
    p = prepared(tmp_path, monkeypatch)
    calls = []
    attempt = synthetic(calls)
    for index, s in enumerate(p["slots"]):
        response = asyncio.run(r.step(tmp_path, attempt))
        assert response["status"] == "HUMAN_CHECK_REQUIRED"
        with pytest.raises(r.GateFailure):
            asyncio.run(r.step(tmp_path, attempt, check_complete=index == 10))
        assert len(calls) == index + 1
        confirm(tmp_path, p, s["id"])
        if index == 2:
            with pytest.raises(r.GateFailure):
                asyncio.run(r.step(tmp_path, attempt))
            digests = {"reachable-safety:candidate": p["imported_receipt_sha256"]}
            digests.update(
                {
                    x["id"]: r.old.stable(
                        r.old.read(tmp_path / r.PRIVATE / (x["id"] + ".json"))
                    )
                    for x in p["slots"][:3]
                }
            )
            write(
                tmp_path / r.PRIVATE / "screen-pass.json",
                {
                    "proposal_sha256": r.old.stable(p),
                    "receipt_digests": digests,
                    "reviewer": "Lee",
                    "decision": "admit_generalization",
                    "source_message_id": "SYNTHETIC_ONLY",
                },
            )
    assert (
        asyncio.run(r.step(tmp_path, attempt, check_complete=True))["status"]
        == "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION"
    )
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(tmp_path, attempt))
    assert len(calls) == 11


@pytest.mark.parametrize("failure", ["http", "semantic", "criterion", "negative-human"])
def test_failures_halt_no_retry_and_preserve_evidence(tmp_path, monkeypatch, failure):
    p = prepared(tmp_path, monkeypatch)
    calls = []
    attempt = synthetic(calls, failure == "http")
    slot = p["slots"][0]["id"]
    if failure == "criterion":
        original = attempt

        async def wrong(*args, **kwargs):
            out = await original(*args, **kwargs)
            out["review_record"]["result"]["verdict"] = "pass"
            out["review_record"]["result"]["findings"] = []
            return out

        attempt = wrong
    response = asyncio.run(r.step(tmp_path, attempt))
    if failure == "semantic":
        # Stop action remains possible without a fresh daily terms record.
        (tmp_path / r.BASE / ("terms-" + time.strftime("%Y-%m-%d") + ".json")).unlink()
        r.eliminate(tmp_path, slot, ["SYNTHETIC unsupported assertion"])
        assert (tmp_path / r.PRIVATE / (slot + "-semantic-stop.json")).exists()
    elif failure == "negative-human":
        write(
            tmp_path / r.PRIVATE / (slot + "-human.json"),
            {
                "proposal_sha256": r.old.stable(p),
                "receipt_sha256": r.old.stable(
                    r.old.read(tmp_path / r.PRIVATE / (slot + ".json"))
                ),
                "reviewer": "Lee",
                "source_message_id": "SYNTHETIC_ONLY",
                "decision": "eliminate",
                "issues": ["SYNTHETIC defect"],
            },
        )
    else:
        assert response["status"] == "CANDIDATE_ELIMINATED"
        saved = r.old.read(tmp_path / r.PRIVATE / (slot + "-failure.json"))
        if failure == "criterion":
            assert (
                saved["complete_review_receipt"]["outcome"]["review_record"]["result"][
                    "verdict"
                ]
                == "pass"
            )
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(tmp_path, attempt))
    assert len(calls) == 1


@pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="dedicated PostgreSQL required"
)
@pytest.mark.parametrize(
    "slot",
    list(
        json.loads(
            (
                ROOT / "docs/acceptance/phase-1-review-model-candidate-r01/cases.json"
            ).read_text()
        )
    )[1:],
)
def test_remaining11_actual_review_once_wires_profile_and_cleanup(slot):
    case = r.old.read(ROOT / r.old.DESIGN / "cases.json")[slot]
    wire = bytes.fromhex(r.old.read(ROOT / r.BASE / "requests.json")[slot]["wire_hex"])
    value = answer(case)
    seen = []

    def handler(request):
        seen.append(request.content)
        assert request.content == wire
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
                        "usage": {"prompt_tokens": 12000, "completion_tokens": 500},
                    }
                ).encode()
            ),
        )

    async def authorize(request):
        assert (
            request.capabilities.schema_profile == QWEN_SCHEMA_PROFILE
            and request.purpose == "connection_test"
        )

    async def run():
        outcome = await perform(
            case,
            wire,
            endpoint="https://chosen.test/v1",
            key="SYNTHETIC_CONTINUATION_KEY",
            database_url=os.environ["EDUMIND_TEST_DATABASE_URL"],
            authorize=authorize,
            transport=httpx.MockTransport(handler),
            resolver=lambda *_: ["8.8.8.8"],
            schema_profile=QWEN_SCHEMA_PROFILE,
            audit_factory=QwenCompatibilityTransport,
        )
        assert outcome["review_record"]["result"] == value
        assert outcome["review_record"]["request_digest"] == r.sha(wire)
        assert all(outcome["cleanup"].values())

    asyncio.run(run())
    assert seen == [wire]


def test_missing_ledger_cannot_reset_authorized_call_count(tmp_path, monkeypatch):
    prepared(tmp_path, monkeypatch)
    calls = []
    attempt = synthetic(calls)
    asyncio.run(r.step(tmp_path, attempt))
    (tmp_path / r.PRIVATE / "budget.sqlite").unlink()
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(tmp_path, attempt))
    assert len(calls) == 1


def test_unbound_negative_confirmation_does_not_count_as_human_verdict(
    tmp_path, monkeypatch
):
    p = prepared(tmp_path, monkeypatch)
    calls = []
    attempt = synthetic(calls)
    asyncio.run(r.step(tmp_path, attempt))
    slot = p["slots"][0]["id"]
    write(
        tmp_path / r.PRIVATE / (slot + "-human.json"),
        {"decision": "eliminate", "issues": ["UNBOUND_RECORD"]},
    )
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(tmp_path, attempt))
    _, a = r.load(tmp_path)
    assert r.gate_for(p, a, tmp_path).snapshot()["halted"] is None
    assert len(calls) == 1
