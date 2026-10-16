"""Single slot limits and exact contract/request preservation, zero cloud calls."""

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
import run_plan_gap_location as r
import test_distributed_budget as oldfixture
from prepare_plan_gap_location import build, review_document
from audit_plan_gap_contract import audit
from acceptance_support.phase1_budget import GateFailure
from acceptance_support.om_diagnostic import stable, valid_review


@pytest.fixture(scope="module")
def prepared():
    return build()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    for key, val in [
        ("runner_module", r),
        ("BASE", r.BASE),
        ("PRIVATE", r.PRIVATE),
        ("SLOT", r.SLOT_IDS[0]),
        ("review_document", review_document),
    ]:
        monkeypatch.setattr(oldfixture, key, val)
    return oldfixture.execution.__wrapped__(tmp_path, monkeypatch, prepared)


def test_actual_contract_audit_has_no_conflict_and_no_sent_output_example():
    v = audit()
    assert not v["clear_contract_conflict_found"]
    assert v["actual_request_output_examples"]["count"] == 0
    assert set(v["negative_schema_checks"]) == {
        "unresolved_object",
        "unresolved_string",
        "extra_top_explanation",
        "extra_coverage_field",
    }
    assert all(v["negative_schema_checks"].values())
    assert v["provider_configuration"]["strict_present"] is False


def test_exact_original_case_wire_and_single_budget(prepared):
    old = r.read(ROOT / "docs/acceptance/phase-1-review-suite-r01/cases.json")
    assert list(prepared["cases.json"]) == list(r.SLOT_IDS)
    assert prepared["cases.json"][r.SLOT_IDS[0]] == old[r.SLOT_IDS[0]]
    p = prepared["proposal.json"]
    assert p["requests"] == 1 and p["cost_micro_cny"] == 2245566
    assert p["requests_authorized"] == p["fees_authorized"] == 0
    assert build() == prepared
    m = r.manifest(p, ROOT)
    assert m["bounds"]["requests"] == 1 and m["bounds"]["timeout_seconds"] == 60
    assert next(iter(m["targets"].values()))["max_total_output_tokens"] == 8192


def response(value):
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


@pytest.mark.parametrize("mode", ["success", "schema", "wrong_verdict"])
def test_single_send_success_exhausts_failure_halts_and_records_location(
    execution, mode
):
    r, root, values = execution
    calls = []
    v = valid_review("unit")
    v.update(
        verdict="needs_human",
        unresolved=["Student-visible loop states and exit boundary missing."],
    )
    if mode == "schema":
        v["reason"] = "SYNTHETIC_PRIVATE_RESPONSE_TEXT"
    if mode == "wrong_verdict":
        v = valid_review("unit")

    def send(req):
        calls.append(req.content)
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(response(v)).encode())
        )

    kwargs = {
        "transport": httpx.MockTransport(send),
        "resolver": lambda *_: ["8.8.8.8"],
    }
    if mode == "success":
        result = asyncio.run(r.step(root, **kwargs))
        assert result["slot"] == r.SLOT_IDS[0]
        receipt = r.read(root / r.PRIVATE / (r.SLOT_IDS[0] + ".json"))
        r.private_write(
            root / r.PRIVATE / (r.SLOT_IDS[0] + "-human.json"),
            {
                "proposal_sha256": stable(values["proposal.json"]),
                "receipt_sha256": stable(receipt),
                "decision": "continue",
                "reviewer": "Lee",
                "source_message_id": "synthetic",
            },
        )
    else:
        with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
            asyncio.run(r.step(root, **kwargs))
        if mode == "schema":
            raw = (
                root / r.PRIVATE / (r.SLOT_IDS[0] + "-failure-observation.json")
            ).read_text()
            obs = json.loads(raw)["observation"]
            assert obs["schema_location"]["unexpected"]["fields"][0]["name"] == "reason"
            assert obs["schema_location"]["instance_path"]["segments"] == []
            assert "SYNTHETIC_PRIVATE_RESPONSE_TEXT" not in raw
    with pytest.raises(
        GateFailure, match="BUDGET_EXHAUSTED" if mode == "success" else "RUN_HALTED"
    ):
        asyncio.run(r.step(root))
    assert calls == [bytes.fromhex(values["cases.json"][r.SLOT_IDS[0]]["wire_hex"])]


@pytest.mark.parametrize("change", ["approval", "count", "slot"])
def test_missing_or_expanded_approval_rejected_before_key_dns(
    execution, monkeypatch, change
):
    r, root, values = execution
    base = root / r.BASE
    if change == "approval":
        (base / "run-approval.json").unlink()
    else:
        p = deepcopy(values["proposal.json"])
        a = r.read(base / "run-approval.json")
        labels = r.read(base / "labels-human.json")
        if change == "count":
            p["requests"] = a["requests"] = 7
        else:
            p["slots"][0]["id"] = "assessment-gap:candidate"
        a["proposal_sha256"] = labels["proposal_sha256"] = stable(p)
        for name, value in [
            ("proposal.json", p),
            ("run-approval.json", a),
            ("labels-human.json", labels),
        ]:
            (base / name).write_text(json.dumps(value))
    monkeypatch.setattr(r, "credentials", lambda _: pytest.fail("premature Key"))
    with pytest.raises(GateFailure):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("premature DNS")))
    assert not (root / r.PRIVATE).exists()
