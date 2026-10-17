"""No cloud: immutable approval, budget overrun, human/phase gates and stop recovery."""

# ruff: noqa: E402
import asyncio
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "scripts/tests"),
]
import run_qwen_review as r
from test_evidence_v45 import answer
from prepare_qwen_review_execution import build


@pytest.fixture(scope="module")
def prepared():
    return build()


@pytest.fixture
def execution(tmp_path, monkeypatch, prepared):
    p = deepcopy(prepared)
    p["execution_root"] = str(tmp_path.resolve())
    p["expiry_local"] = "2099-01-01T00:00:00+08:00"
    p["sources"] = {}
    for name in [
        "backend/app/services/openai_compatible.py",
        "docs/ADR/0015-approval-20261015.json",
        "docs/acceptance/phase-1-provider-connection-v1/results/final.json",
    ]:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / name).read_bytes())
        p["sources"][name] = r.sha(dest.read_bytes())
    design = tmp_path / r.DESIGN
    design.mkdir(parents=True)
    for name in ["cases.json", "proposed-labels.json"]:
        (design / name).write_bytes((ROOT / r.DESIGN / name).read_bytes())
    base = tmp_path / r.BASE
    base.mkdir(parents=True)
    (base / "proposal.json").write_text(json.dumps(p))
    a = {
        "version": "qwen-review-real-approval-v1",
        "proposal_sha256": r.stable(p),
        "requests": 12,
        "cost_micro_cny": p["cost_micro_cny"],
        "reviewer": "Lee",
        "user_confirmation": "SYNTHETIC_TEST_ONLY",
        "source_message_id": "SYNTHETIC_TEST_ONLY",
    }
    (base / "run-approval.json").write_text(json.dumps(a))
    data = r.read(design / "cases.json")
    labels = {
        "proposal_sha256": r.stable(p),
        "labels_sha256": p["labels_sha256"],
        "case_digests": {s: r.stable(c["material"]) for s, c in data.items()},
        "reviewer": "Lee",
        "decision": "accept_calibration_labels",
        "source_message_id": "SYNTHETIC_TEST_ONLY",
    }
    (base / "labels-human.json").write_text(json.dumps(labels))
    terms = {
        "proposal_sha256": r.stable(p),
        "checked_on": r.time.strftime("%Y-%m-%d"),
        "official_terms_sha256": p["official_terms_sha256"],
        "unchanged_model_prices_and_limits": True,
        "verified_by": "assistant",
        "source_urls": p["official_sources"],
    }
    (base / ("terms-" + terms["checked_on"] + ".json")).write_text(json.dumps(terms))
    monkeypatch.setattr(
        r, "credentials", lambda *_: ("https://chosen.test/v1", "SYNTHETIC_KEY_ONLY")
    )
    monkeypatch.setattr(r, "database_url", lambda: "SYNTHETIC_DB_NOT_USED")
    return tmp_path, p, data


def synthetic_outcome(case, wire, *, output=8202):
    return {
        "review_record": {
            "binding": case["material"]["binding"],
            "request_digest": r.sha(wire),
            "prompt_version": "evidence-resource-review-v4.5",
            "result": answer(case),
        },
        "input_tokens": 90,
        "output_tokens": output,
        "model_id": "qwen3.8-max-0902",
        "normal_finish": True,
        "schema_valid": True,
        "sent": 1,
        "cleanup": {
            "connection_disabled": True,
            "persistent_secret_absent": True,
            "config_version_invalidated": True,
        },
        "raw_response_sha256": "1" * 64,
    }


def fake_attempt(calls, output=8202):
    async def attempt(case, wire, **kwargs):
        calls.append(wire)
        await kwargs["authorize"](
            SimpleNamespace(
                route=SimpleNamespace(
                    model_id="qwen3.8-max-0902", data_categories=frozenset({"probe"})
                ),
                purpose="connection_test",
            )
        )
        return synthetic_outcome(case, wire, output=output)

    return attempt


def confirm(root, p, slot, **changes):
    rec = r.read(root / r.PRIVATE / (slot + ".json"))
    human = {
        "proposal_sha256": r.stable(p),
        "receipt_sha256": r.stable(rec),
        "reviewer": "Lee",
        "source_message_id": "SYNTHETIC_TEST_ONLY",
        "decision": "continue",
        "completeness_checked": True,
        "all_assertions_checked": True,
        "all_citations_checked": True,
        "issues": [],
    }
    human.update(changes)
    r.private_write(root / r.PRIVATE / (slot + "-human.json"), human)


def screen_pass(root, p):
    record = {
        "proposal_sha256": r.stable(p),
        "receipt_digests": {
            s["id"]: r.stable(r.read(root / r.PRIVATE / (s["id"] + ".json")))
            for s in p["slots"][:4]
        },
        "reviewer": "Lee",
        "source_message_id": "SYNTHETIC_TEST_ONLY",
        "decision": "admit_generalization",
    }
    r.private_write(root / r.PRIVATE / "screen-pass.json", record)


def test_budget_fork_only_changes_documented_output_ceiling(prepared):
    old = (ROOT / "scripts/acceptance_support/phase1_budget.py").read_text()
    actual = (ROOT / "scripts/acceptance_support/qwen_review_budget.py").read_text()
    expected = old.replace(
        '"""Durable acceptance reservation; no Provider settings, secrets or network entry point."""',
        '"""Qwen diagnostic budget fork: only ceiling8202 differs from the frozen8192 kernel."""',
        1,
    ).replace(
        '_integer(target["max_total_output_tokens"], 1, 8192)',
        '_integer(target["max_total_output_tokens"], 1, 8202)',
        1,
    )
    assert actual == expected
    assert (
        prepared["cost_micro_cny"] == 161071260 and prepared["requests_authorized"] == 0
    )


def test_missing_approval_terms_labels_fail_before_key_db_or_private(
    execution, monkeypatch
):
    root, p, _ = execution
    for name in [
        "run-approval.json",
        "labels-human.json",
        "terms-" + r.time.strftime("%Y-%m-%d") + ".json",
    ]:
        path = root / r.BASE / name
        data = path.read_bytes()
        path.unlink()
        monkeypatch.setattr(
            r, "credentials", lambda *_: pytest.fail("Key before approvals")
        )
        monkeypatch.setattr(
            r, "database_url", lambda: pytest.fail("DB before approvals")
        )
        with pytest.raises(r.GateFailure):
            asyncio.run(r.step(root))
        assert not (root / r.PRIVATE).exists()
        path.write_bytes(data)


def test_all12_mock_steps_human_phase_and_final_signoff(execution):
    root, p, data = execution
    calls = []
    for index, (slot, c) in enumerate(data.items()):
        if index == 4:
            with pytest.raises(r.GateFailure):
                asyncio.run(r.step(root, attempt=fake_attempt(calls)))
            assert len(calls) == 4
            screen_pass(root, p)
        result = asyncio.run(r.step(root, attempt=fake_attempt(calls)))
        assert result["slot"] == slot and calls[-1] == bytes.fromhex(
            c["candidate_wire_hex"]
        )
        with pytest.raises(r.GateFailure):
            asyncio.run(r.step(root, attempt=fake_attempt(calls)))
        assert len(calls) == index + 1
        confirm(root, p, slot)
    assert (
        asyncio.run(r.step(root, check_complete=True))["status"]
        == "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION"
    )
    with pytest.raises(r.GateFailure, match="BUDGET_EXHAUSTED"):
        asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    assert len(calls) == 12


@pytest.mark.parametrize("output", [8192, 8193, 8202])
def test_8192_request_reserves_and_accepts_8202_total(execution, output):
    root, p, data = execution
    calls = []
    result = asyncio.run(r.step(root, attempt=fake_attempt(calls, output)))
    assert json.loads(calls[0])["max_completion_tokens"] == 8192
    with sqlite3.connect(
        (root / r.PRIVATE / "budget.sqlite").resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        row = db.execute(
            "SELECT cost_micro,output_bound,output_tokens,state FROM attempts"
        ).fetchone()
    assert row == (p["slots"][0]["cost_micro_cny"], 8202, output, "complete")
    assert result["requests_sent"] == 1


@pytest.mark.parametrize("output", [8203, None])
def test_output_overrun_or_unknown_usage_stops_no_next(execution, output):
    root, p, _ = execution
    calls = []
    with pytest.raises(r.GateFailure, match="CANDIDATE_ELIMINATED"):
        asyncio.run(r.step(root, attempt=fake_attempt(calls, output)))
    with pytest.raises(r.GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "field", ["completeness_checked", "all_assertions_checked", "all_citations_checked"]
)
def test_any_false_check_blocks_next_before_key(execution, field, monkeypatch):
    root, p, data = execution
    calls = []
    slot = next(iter(data))
    asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    confirm(root, p, slot, **{field: False})
    monkeypatch.setattr(r, "credentials", lambda *_: pytest.fail("Key before check"))
    with pytest.raises(r.GateFailure, match="HUMAN_CHECK_REQUIRED"):
        asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    assert len(calls) == 1


def test_negative_review_persists_halt_and_keeps_original(execution):
    root, p, data = execution
    calls = []
    slot = next(iter(data))
    asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    path = root / r.PRIVATE / (slot + ".json")
    before = path.read_bytes()
    confirm(
        root,
        p,
        slot,
        decision="eliminate",
        issues=["SYNTHETIC unsupported auxiliary assertion"],
    )
    with pytest.raises(r.GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    assert path.read_bytes() == before
    with pytest.raises(r.GateFailure, match="RUN_HALTED"):
        asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    assert len(calls) == 1


def test_semantic_eliminate_is_persistent_and_receipt_immutable(execution):
    root, p, data = execution
    calls = []
    slot = next(iter(data))
    asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    path = root / r.PRIVATE / (slot + ".json")
    before = path.read_bytes()
    # A crossed-day/expired terms attestation can block sending but must not block stopping.
    (root / r.BASE / ("terms-" + r.time.strftime("%Y-%m-%d") + ".json")).unlink()
    r.eliminate(root, slot, ["SYNTHETIC citation fails its claim"])
    with pytest.raises(r.GateFailure):
        asyncio.run(r.step(root, attempt=fake_attempt(calls)))
    assert (
        r._gate(p, r.read(root / r.BASE / "run-approval.json"), root).snapshot()[
            "halted"
        ]
        == "ADMISSION_FAILED"
    )
    assert path.read_bytes() == before and len(calls) == 1


def test_inactive_qwen_key_is_selected_without_changing_active_provider(
    tmp_path, monkeypatch
):
    from acceptance_support.qwen_review_budget import sha

    content = "EDUMIND_PROVIDER_BASE_URL=https://api.deepseek.com\nEDUMIND_PROVIDER_API_KEY=ACTIVE_SYNTHETIC\nEDUMIND_PROVIDER_MODEL=deepseek-flash\n\n# EDUMIND_PROVIDER_BASE_URL=https://chosen.test/v1\n# EDUMIND_PROVIDER_API_KEY=QWEN_SYNTHETIC\n# EDUMIND_PROVIDER_MODEL=qwen3.8-max-0902\n"
    path = tmp_path / ".env"
    path.write_text(content)
    path.chmod(0o600)
    meta = path.stat()
    p = {
        "endpoint_sha256": sha(b"https://chosen.test/v1"),
        "credential_file_metadata": {
            k: getattr(meta, k)
            for k in ["st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"]
        },
    }
    # Fixture above patched the runner; restore original function for this independent test.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_qwen_credential_test", ROOT / "scripts/run_qwen_review.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.credentials(tmp_path, p) == (
        "https://chosen.test/v1",
        "QWEN_SYNTHETIC",
    )
    assert path.read_text() == content
    p["endpoint_sha256"] = "0" * 64
    with pytest.raises(r.GateFailure):
        module.credentials(tmp_path, p)


def test_private_parent_cannot_redirect_ledger_outside_execution_root(
    execution, tmp_path, monkeypatch
):
    root, _, _ = execution
    outside = root.parent / (root.name + "-outside")
    outside.mkdir()
    (root / "local-materials").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        r, "credentials", lambda *_: pytest.fail("Key on redirected private path")
    )
    with pytest.raises(r.GateFailure, match="SAFETY_FAILURE"):
        asyncio.run(r.step(root))
    assert list(outside.iterdir()) == []
