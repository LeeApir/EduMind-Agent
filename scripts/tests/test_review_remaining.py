"""Five-class scope/order, contract consistency and semantic stopping gates."""

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
import run_review_remaining as r
import test_review_suite as oldfixture
from prepare_review_remaining import build, review_document
from acceptance_support.phase1_budget import GateFailure
from acceptance_support.om_diagnostic import stable, valid_review


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
    a["requests"] = 5
    path.write_text(json.dumps(a))
    return root, values


def answer(case):
    kind = case["comparison_kind"]
    v = valid_review("unit")
    if kind == "pure_gap":
        v.update(
            verdict="needs_human",
            unresolved=[
                "States and exit already taught; questions only test arithmetic/index/return, not the process."
            ],
        )
    elif kind != "positive":
        v.update(
            verdict="reject",
            findings=[
                {
                    "category": "fact" if kind == "fact" else "code_safety",
                    "severity": "severe",
                    "anchors": [case["anchors"][0]["anchor_id"]],
                    "condition_or_counterexample": "Synthetic protocol test only",
                    "impact": "Synthetic impact only",
                }
            ],
            unresolved=["Synthetic teaching gap"] if kind == "mixed" else [],
        )
    return v


def transport(v, calls):
    def send(req):
        calls.append(req.content)
        body = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(v)}],
                }
            ],
            "usage": {"input_tokens": 90, "output_tokens": 6000},
        }
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(body).encode()))

    return httpx.MockTransport(send)


def confirm(root, values, slot):
    rec = r.read(root / r.PRIVATE / (slot + ".json"))
    r.private_write(
        root / r.PRIVATE / (slot + "-human.json"),
        {
            "proposal_sha256": stable(values["proposal.json"]),
            "receipt_sha256": stable(rec),
            "decision": "continue",
            "reviewer": "Lee",
            "source_message_id": "SYNTHETIC_TEST_ONLY",
        },
    )


def test_five_exact_cases_wires_order_and_budget(prepared):
    assert r.SLOT_IDS == tuple(
        n + ":candidate"
        for n in [
            "assessment-gap",
            "fact-contradiction",
            "reachable-safety",
            "gap-and-safety",
            "trace-complete",
        ]
    )
    old = r.read(ROOT / "docs/acceptance/phase-1-review-suite-r01/cases.json")
    assert tuple(prepared["cases.json"]) == r.SLOT_IDS
    for slot, c in prepared["cases.json"].items():
        assert c == old[slot]
        body = json.loads(bytes.fromhex(c["wire_hex"]))
        assert (
            body["reasoning"] == {"effort": "low"} and body["max_output_tokens"] == 8192
        )
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert (
            body["text"]["format"]["schema"]["properties"]["unresolved"]["items"][
                "type"
            ]
            == "string"
        )
    p = prepared["proposal.json"]
    assert p["requests"] == 5 and p["cost_micro_cny"] == 11235560
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert build() == prepared
    m = r.manifest(p, ROOT)
    assert m["bounds"]["timeout_seconds"] == 60 and m["bounds"]["requests"] == 5
    assert next(iter(m["targets"].values()))["max_total_output_tokens"] == 8192


def test_five_mock_steps_exact_wires_human_gate_and_final_exhaustion(execution):
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
        assert result["slot"] == slot
        assert calls[-1] == bytes.fromhex(case["wire_hex"])
        receipt = r.read(root / r.PRIVATE / (slot + ".json"))
        assert all(receipt["completeness"].values())
        assert not receipt["human_confirmed"]
        if slot != r.SLOT_IDS[-1]:
            with pytest.raises(GateFailure):
                asyncio.run(
                    r.step(
                        root,
                        resolver=lambda *_: pytest.fail("DNS before human evidence"),
                    )
                )
        confirm(root, values, slot)
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 5


@pytest.mark.parametrize("mode", ["schema", "wrong_route", "invented_fact"])
def test_first_failure_stops_with_no_retry_or_next_slot(execution, mode):
    root, values = execution
    calls = []
    case = values["cases.json"][r.SLOT_IDS[0]]
    v = answer(case)
    if mode == "schema":
        v["reason"] = "SYNTHETIC_PRIVATE_TEXT"
    elif mode == "wrong_route":
        v = valid_review("unit")
    else:
        v["findings"] = answer(values["cases.json"][r.SLOT_IDS[1]])["findings"]
        v["findings"][0]["anchors"] = [case["anchors"][0]["anchor_id"]]
        v["findings"][0]["condition_or_counterexample"] = "Invented missing callsite"
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            r.step(root, transport=transport(v, calls), resolver=lambda *_: ["8.8.8.8"])
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 1
    if mode == "schema":
        raw = (
            root / r.PRIVATE / (r.SLOT_IDS[0] + "-failure-observation.json")
        ).read_text()
        loc = json.loads(raw)["observation"]["schema_location"]
        assert (
            loc["unexpected"]["fields"][0]["name"] == "reason"
            and "SYNTHETIC_PRIVATE_TEXT" not in raw
        )


@pytest.mark.parametrize("slot", r.SLOT_IDS[1:4])
def test_serious_errors_cannot_all_become_human(prepared, slot):
    case = prepared["cases.json"][slot]
    v = answer(case)
    assert asyncio.run(r.assess(case, v, slot))["route"]["verdict"] == "reject"
    v["verdict"] = "needs_human"
    v["unresolved"] = ["Teaching gap exists"]
    with pytest.raises(GateFailure, match="CANDIDATE_CRITERION_FAILED"):
        asyncio.run(r.assess(case, v, slot))


@pytest.mark.parametrize("change", ["approval", "count", "slot"])
def test_missing_or_wider_scope_denied_before_key_dns(execution, monkeypatch, change):
    root, values = execution
    b = root / r.BASE
    if change == "approval":
        (b / "run-approval.json").unlink()
    else:
        p = deepcopy(values["proposal.json"])
        a = r.read(b / "run-approval.json")
        labels = r.read(b / "labels-human.json")
        if change == "count":
            p["requests"] = a["requests"] = 7
        else:
            p["slots"][0]["id"] = "plan-only-gap:candidate"
        a["proposal_sha256"] = labels["proposal_sha256"] = stable(p)
        for n, v in [
            ("proposal.json", p),
            ("run-approval.json", a),
            ("labels-human.json", labels),
        ]:
            (b / n).write_text(json.dumps(v))
    monkeypatch.setattr(r, "credentials", lambda _: pytest.fail("Key before gate"))
    with pytest.raises(GateFailure):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("DNS before gate")))
    assert not (root / r.PRIVATE).exists()
