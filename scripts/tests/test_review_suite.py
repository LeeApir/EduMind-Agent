"""Offline ordered-suite scope, taxonomy, first dispatch and human gates."""

import asyncio
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_review_suite as r  # noqa: E402
from prepare_review_suite import build, review_document  # noqa: E402
from acceptance_support.om_diagnostic import stable, valid_review  # noqa: E402
from acceptance_support.phase1_budget import GateFailure  # noqa: E402
from app.core.config import ProviderSettings  # noqa: E402


@pytest.fixture(scope="module")
def prepared():
    return build()


def test_freeze_original_cases_only_changes_output_limit(prepared):
    old = r.read(ROOT / "docs/acceptance/phase-1-review-config-r01/cases.json")
    data = prepared["cases.json"]
    assert tuple(data) == r.SLOT_IDS and len(data) == 7
    for slot, case in data.items():
        left, right = deepcopy(case), deepcopy(old[slot])
        wire = json.loads(bytes.fromhex(left.pop("wire_hex")))
        oldwire = json.loads(bytes.fromhex(right.pop("wire_hex")))
        assert left == right
        assert wire.pop("max_output_tokens") == 8192
        assert oldwire.pop("max_output_tokens") == 2048
        assert wire == oldwire
    p = prepared["proposal.json"]
    assert p["requests"] == 7 and p["requests_authorized"] == p["fees_authorized"] == 0
    assert p["cost_micro_cny"] == sum(
        2 * (1048576 + s["wire_bytes"]) + 8 * 8192 for s in p["slots"]
    )
    assert build() == prepared
    m = r.manifest(p, ROOT)
    assert m["bounds"]["timeout_seconds"] == 60
    assert next(iter(m["targets"].values()))["max_total_output_tokens"] == 8192
    import run_distributed_budget as oldrunner

    assert oldrunner.REQUESTS == 1


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    values = deepcopy(prepared)
    p = values["proposal.json"]
    p["execution_root"] = str(tmp_path.resolve())
    p["expiry_local"] = "2099-01-01T00:00:00+08:00"
    values["token-cost-proof.json"]["checked_on"] = r.time.strftime("%Y-%m-%d")
    p["proof_sha256"] = stable(values["token-cost-proof.json"])
    names = [
        "backend/app/services/deepseek_responses.py",
        "docs/ADR/0015-approval-20261015.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    ]
    p["sources"] = {name: stable(name) for name in names}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.canonical(name))
    base = tmp_path / r.BASE
    base.mkdir(parents=True)
    for name, value in values.items():
        (base / name).write_text(json.dumps(value))
    (base / "human-review.md").write_text(review_document(values["cases.json"]))
    approval = {
        "version": "om-admission-human-approval-v1",
        "proposal_sha256": stable(p),
        "requests": 7,
        "cost_micro_cny": p["cost_micro_cny"],
        "labels_sha256": p["labels_sha256"],
        "confirmed_by": "Lee",
        "user_confirmation": "SYNTHETIC_ONLY",
        "source_message_id": "synthetic",
        "terms_verified_on": r.time.strftime("%Y-%m-%d"),
    }
    labels = {
        "proposal_sha256": stable(p),
        "labels_sha256": p["labels_sha256"],
        "case_digests": {
            n: stable(c["material"]) for n, c in values["cases.json"].items()
        },
        "decision": "accept_calibration_labels",
        "reviewer": "Lee",
        "source_message_id": "synthetic",
    }
    for name, value in [("run-approval.json", approval), ("labels-human.json", labels)]:
        (base / name).write_text(json.dumps(value))
    monkeypatch.setattr(
        r,
        "credentials",
        lambda _: ProviderSettings(
            "https://api.deepseek.com", "SYNTHETIC_PRIVATE_KEY", "deepseek-flash"
        ),
    )
    return tmp_path, values


def gap_review():
    value = valid_review("unit")
    value.update(
        verdict="needs_human",
        unresolved=[
            "Student-visible loop states and exit are missing; plan trajectory is not delivered."
        ],
    )
    return value


def transport_for(value, calls):
    def send(request):
        calls.append(request.content)
        payload = {
            "model": "deepseek-flash",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": json.dumps(value)}],
                }
            ],
            "usage": {"input_tokens": 90, "output_tokens": 6000},
        }
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps(payload).encode())
        )

    return httpx.MockTransport(send)


def test_first_gap_one_send_then_real_receipt_human_gate(execution):
    root, values = execution
    calls = []
    asyncio.run(
        r.step(
            root,
            transport=transport_for(gap_review(), calls),
            resolver=lambda *_: ["8.8.8.8"],
        )
    )
    assert calls == [bytes.fromhex(values["cases.json"][r.SLOT_IDS[0]]["wire_hex"])]
    receipt = r.read(root / r.PRIVATE / (r.SLOT_IDS[0] + ".json"))
    assert all(receipt["completeness"].values())
    assert receipt["local_assessment"]["route"]["verdict"] == "needs_human"
    assert not receipt["human_confirmed"]
    with pytest.raises(GateFailure):
        asyncio.run(
            r.step(
                root,
                transport=transport_for(gap_review(), calls),
                resolver=lambda *_: pytest.fail("premature DNS"),
            )
        )
    assert len(calls) == 1
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
    result = asyncio.run(
        r.step(
            root,
            transport=transport_for(gap_review(), calls),
            resolver=lambda *_: ["8.8.8.8"],
        )
    )
    assert result["slot"] == r.SLOT_IDS[1] and len(calls) == 2
    assert calls[1] == bytes.fromhex(values["cases.json"][r.SLOT_IDS[1]]["wire_hex"])


def test_semantic_route_failure_halts_no_second_send(execution):
    root, _ = execution
    calls = []
    with pytest.raises(GateFailure, match="ADMISSION_STOPPED"):
        asyncio.run(
            r.step(
                root,
                transport=transport_for(valid_review("unit"), calls),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
    with pytest.raises(GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 1
    path = root / r.PRIVATE / (r.SLOT_IDS[0] + "-failed.json")
    assert r.read(path)["value"]["verdict"] == "pass"
    db = sqlite3.connect(
        (root / r.PRIVATE / "budget.sqlite").as_uri() + "?mode=ro", uri=True
    )
    assert db.execute("select count(*) from attempts").fetchone()[0] == 1
    db.close()


@pytest.mark.parametrize("name", ["run-approval.json", "labels-human.json"])
def test_unapproved_no_key_dns_or_real_directory(execution, monkeypatch, name):
    root, _ = execution
    (root / r.BASE / name).unlink()
    monkeypatch.setattr(r, "credentials", lambda _: pytest.fail("key before gate"))
    with pytest.raises(GateFailure):
        asyncio.run(r.step(root, resolver=lambda *_: pytest.fail("DNS before gate")))
    assert not (root / r.PRIVATE).exists()


@pytest.mark.parametrize("slot", r.SLOT_IDS)
def test_expected_routes_and_no_gap_downgrade(prepared, slot):
    case = prepared["cases.json"][slot]
    if case["comparison_kind"] == "pure_gap":
        result = asyncio.run(r.assess(case, gap_review(), slot))
        assert result["route"]["verdict"] == "needs_human"
    elif case["comparison_kind"] == "positive":
        assert asyncio.run(r.assess(case, valid_review("unit"), slot))[
            "criterion_signal"
        ]
    else:
        with pytest.raises(GateFailure, match="CANDIDATE_CRITERION_FAILED"):
            asyncio.run(r.assess(case, gap_review(), slot))


def severe_review(case):
    value = valid_review("unit")
    value.update(
        verdict="reject",
        findings=[
            {
                "category": "fact"
                if case["comparison_kind"] == "fact"
                else "code_safety",
                "severity": "severe",
                "anchors": [case["anchors"][0]["anchor_id"]],
                "condition_or_counterexample": "Synthetic counterexample for protocol test only",
                "impact": "Synthetic impact for protocol test only",
            }
        ],
        unresolved=["Synthetic teaching gap"]
        if case["comparison_kind"] == "mixed"
        else [],
    )
    return value


def test_all_seven_mock_steps_exact_wires_and_final_exhaustion(execution):
    root, values = execution
    calls = []
    for slot, case in values["cases.json"].items():
        value = (
            gap_review()
            if case["comparison_kind"] == "pure_gap"
            else valid_review("unit")
            if case["comparison_kind"] == "positive"
            else severe_review(case)
        )
        result = asyncio.run(
            r.step(
                root,
                transport=transport_for(value, calls),
                resolver=lambda *_: ["8.8.8.8"],
            )
        )
        assert result["slot"] == slot
        assert calls[-1] == bytes.fromhex(case["wire_hex"])
        receipt = r.read(root / r.PRIVATE / (slot + ".json"))
        assert receipt["local_assessment"]["criterion_signal"]
        if case["comparison_kind"] == "mixed":
            assert receipt["local_assessment"]["route"]["verdict"] == "reject"
        r.private_write(
            root / r.PRIVATE / (slot + "-human.json"),
            {
                "proposal_sha256": stable(values["proposal.json"]),
                "receipt_sha256": stable(receipt),
                "decision": "continue",
                "reviewer": "Lee",
                "source_message_id": "synthetic",
            },
        )
    with pytest.raises(GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(r.step(root))
    assert len(calls) == 7


def test_pure_gap_with_invented_fact_is_rejected(prepared):
    case = prepared["cases.json"][r.SLOT_IDS[0]]
    value = gap_review()
    value["findings"] = severe_review(case)["findings"]
    value["findings"][0]["category"] = "fact"
    value["findings"][0]["condition_or_counterexample"] = "Invented missing callsite"
    with pytest.raises(GateFailure, match="CANDIDATE_CRITERION_FAILED"):
        asyncio.run(r.assess(case, value, r.SLOT_IDS[0]))
