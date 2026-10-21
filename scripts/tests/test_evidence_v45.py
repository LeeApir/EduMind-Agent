"""Frozen v4.5 scope, exact wires and all-assertion/citation human gates (mock only)."""

# ruff: noqa: E402
import asyncio
import json
import sys
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
import run_evidence_v45 as r
import test_review_suite as oldfixture
from prepare_evidence_v45 import build, review_document
from acceptance_support.phase1_budget import Approval, FrozenBudget, GateFailure
from acceptance_support.om_diagnostic import stable, valid_review
from app.agents.hybrid_resource_review import INSTRUCTION
from app.services.learning_policy import active_policy_digest


@pytest.fixture(scope="module")
def prepared():
    return build()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    monkeypatch.setattr(oldfixture, "r", r)
    monkeypatch.setattr(oldfixture, "review_document", review_document)
    root, values = oldfixture.execution.__wrapped__(tmp_path, monkeypatch, prepared)
    path = root / r.BASE / "run-approval.json"
    a = r.read(path)
    a["requests"] = 4
    path.write_text(json.dumps(a))
    return root, values


def answer(case):
    v = valid_review("unit")
    if case["comparison_kind"] != "positive":
        target = "/markdown" if case["comparison_kind"] == "fact" else "/source"
        anchor = next(
            a["anchor_id"] for a in case["anchors"] if a["json_pointer"] == target
        )
        v.update(
            verdict="reject",
            findings=[
                {
                    "category": "fact"
                    if case["comparison_kind"] == "fact"
                    else "code_safety",
                    "severity": "severe",
                    "anchors": [anchor],
                    "condition_or_counterexample": "Synthetic protocol example, not semantic proof",
                    "impact": "Synthetic protocol impact",
                }
            ],
            unresolved=["Synthetic teaching gap"]
            if case["comparison_kind"] == "mixed"
            else [],
        )
    return v


def transport(value, calls):
    def send(req):
        calls.append(req.content)
        payload = {
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
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(payload).encode())
        )

    return httpx.MockTransport(send)


def confirm(root, values, slot, **changes):
    receipt = r.read(root / r.PRIVATE / (slot + ".json"))
    record = {
        "proposal_sha256": stable(values["proposal.json"]),
        "receipt_sha256": stable(receipt),
        "decision": "continue",
        "reviewer": "Lee",
        "source_message_id": "SYNTHETIC_TEST_ONLY",
        "completeness_checked": True,
        "all_assertions_checked": True,
        "all_citations_checked": True,
        "issues": [],
    }
    record.update(changes)
    r.private_write(root / r.PRIVATE / (slot + "-human.json"), record)


def test_freeze_retains_student_content_schema_config_and_new_policy(prepared):
    old = r.read(ROOT / "docs/acceptance/phase-1-review-remaining-r01/cases.json")
    assert r.SLOT_IDS == tuple(
        n + ":candidate"
        for n in [
            "reachable-safety",
            "fact-contradiction",
            "gap-and-safety",
            "trace-complete",
        ]
    )
    for slot, c in prepared["cases.json"].items():
        p = old[slot]
        assert (
            c["input_snapshot"] == p["input_snapshot"]
            and c["material"]["plan"] == p["material"]["plan"]
        )
        assert [x["envelope"] for x in c["material"]["candidates"]] == [
            x["envelope"] for x in p["material"]["candidates"]
        ]
        body = json.loads(bytes.fromhex(c["wire_hex"]))
        prior = json.loads(bytes.fromhex(p["wire_hex"]))
        assert (
            body["input"][0]["content"] == INSTRUCTION
            and body["input"][0] != prior["input"][0]
        )
        assert (
            body["text"] == prior["text"]
            and body["reasoning"] == {"effort": "low"}
            and body["max_output_tokens"] == 8192
        )
        assert (
            c["material"]["binding"]["policy_digest"]
            == active_policy_digest()
            != p["material"]["binding"]["policy_digest"]
        )
    p = prepared["proposal.json"]
    assert p["requests"] == 4 and p["requests_authorized"] == p["fees_authorized"] == 0
    assert p["cost_micro_cny"] == sum(
        2 * (1048576 + s["wire_bytes"]) + 8 * 8192 for s in p["slots"]
    )
    assert build() == prepared


def test_all_four_mock_steps_exact_requests_three_checks_before_next(execution):
    root, values = execution
    calls = []
    for slot, case in values["cases.json"].items():
        result = asyncio.run(
            r.step(
                root,
                transport=transport(answer(case), calls),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
        assert result["slot"] == slot and calls[-1] == bytes.fromhex(case["wire_hex"])
        if slot != r.SLOT_IDS[-1]:
            with pytest.raises(GateFailure):
                asyncio.run(
                    r.step(
                        root, resolver=lambda *_: pytest.fail("DNS before human review")
                    )
                )
        confirm(root, values, slot)
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 4


@pytest.mark.parametrize(
    "change",
    [
        "completeness_checked",
        "all_assertions_checked",
        "all_citations_checked",
        "issues",
    ],
)
def test_any_failed_human_check_blocks_next_before_dns(execution, change):
    root, values = execution
    calls = []
    slot = r.SLOT_IDS[0]
    asyncio.run(
        r.step(
            root,
            transport=transport(answer(values["cases.json"][slot]), calls),
            resolver=lambda *_: ["8.8.8.8"],
        )
    )
    confirm(
        root,
        values,
        slot,
        **{change: ["Unresolved citation problem"] if change == "issues" else False},
    )
    with pytest.raises(GateFailure, match="HUMAN_CHECK_REQUIRED"):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert len(calls) == 1


def test_core_detection_never_automatically_confirms_accompanying_claims(execution):
    root, values = execution
    calls = []
    slot = r.SLOT_IDS[0]
    v = answer(values["cases.json"][slot])
    v["findings"].append(
        {
            **v["findings"][0],
            "category": "fact",
            "condition_or_counterexample": "Synthetic unsupported guaranteed unequal numeric result",
        }
    )
    asyncio.run(
        r.step(root, transport=transport(v, calls), resolver=lambda *_: ["8.8.8.8"])
    )
    receipt = r.read(root / r.PRIVATE / (slot + ".json"))
    assert (
        receipt["value"] == v
        and not receipt["local_assessment"]["semantic_detection_confirmed"]
    )
    with pytest.raises(GateFailure):
        asyncio.run(r.step(root))
    p = values["proposal.json"]
    a = r.read(root / r.BASE / "run-approval.json")
    m = r.manifest(p, root)
    gate = FrozenBudget(
        m,
        root / r.PRIVATE / "budget.sqlite",
        root=root,
        approval=Approval(
            stable(m), "diagnostic", 4, p["cost_micro_cny"], stable(a), True
        ),
    )
    gate.halt("ADMISSION_FAILED")
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 1 and r.read(root / r.PRIVATE / (slot + ".json"))["value"] == v


@pytest.mark.parametrize("change", ["approval", "count", "slot"])
def test_missing_approval_or_wider_scope_cannot_send(execution, monkeypatch, change):
    root, values = execution
    b = root / r.BASE
    if change == "approval":
        (b / "run-approval.json").unlink()
    else:
        p = deepcopy(values["proposal.json"])
        a = r.read(b / "run-approval.json")
        labels = r.read(b / "labels-human.json")
        if change == "count":
            p["requests"] = a["requests"] = 5
        else:
            p["slots"][0]["id"] = "assessment-gap:candidate"
        a["proposal_sha256"] = labels["proposal_sha256"] = stable(p)
        for n, v in [
            ("proposal.json", p),
            ("run-approval.json", a),
            ("labels-human.json", labels),
        ]:
            (b / n).write_text(json.dumps(v))
    monkeypatch.setattr(r, "credentials", lambda _: pytest.fail("premature Key"))
    with pytest.raises(GateFailure):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / r.PRIVATE).exists()


@pytest.mark.parametrize("mode", ["schema", "cutoff"])
def test_transport_failures_preserve_diagnostic_and_cannot_retry(execution, mode):
    root, values = execution
    calls = []
    slot = r.SLOT_IDS[0]
    v = answer(values["cases.json"][slot])
    if mode == "schema":
        v["reason"] = "SYNTHETIC_PRIVATE_TEXT"

    def send(req):
        calls.append(req.content)
        body = {
            "model": "deepseek-flash",
            "status": "completed" if mode == "schema" else "incomplete",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": json.dumps(v)}],
                }
            ],
            "usage": {
                "input_tokens": 90,
                "output_tokens": 6000 if mode == "schema" else 8192,
            },
        }
        if mode == "cutoff":
            body["incomplete_details"] = {"reason": "max_output_tokens"}
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body).encode()))

    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            r.step(
                root,
                transport=httpx.MockTransport(send),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root))
    raw = (root / r.PRIVATE / (slot + "-failure-observation.json")).read_text()
    o = json.loads(raw)["observation"]
    assert o["output_failure_reason"] == (
        "STRUCTURED_SCHEMA_MISMATCH" if mode == "schema" else "OUTPUT_TOKEN_LIMIT"
    )
    if mode == "schema":
        assert o["schema_location"]["unexpected"]["fields"][0]["name"] == "reason"
    assert "SYNTHETIC_PRIVATE_TEXT" not in raw and len(calls) == 1
