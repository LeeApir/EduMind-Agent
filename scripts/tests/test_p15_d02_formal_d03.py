"""No-network regression tests for the narrow D02 execution boundary."""

# ruff: noqa: E402
import asyncio
import socket
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.p15_diagnostic_ledger import Refused, digest
from isolated_diagnostics import p15_d02_formal_d03 as x
from isolated_diagnostics.p15_d02_review_d02 import SplitExecution, assess


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("No real network")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


@pytest.fixture
def journal(tmp_path):
    grant = dict(
        scope="PHASE-1.5-T038",
        package_sha256="a" * 64,
        batch_id="p15-split-experiment-d02-mock",
        limits=asdict(x.ExplorationLimits()),
        evidence_ref="SYNTHETIC_NOT_AUTHORITY",
        fee_cap_waiver=True,
        window_deadline_epoch=1900,
    )
    j = x.ExplorationJournal.create(
        tmp_path / "wire", grant["batch_id"], "a" * 64, grant, clock=lambda: (100, 100)
    )
    yield j
    j.ledger.close()


def test_five_reservations_preserve_prior_30_and_never_inherit_250(journal):
    for n in range(5):
        journal.ledger.reserve(
            journal.batch, journal.package, str(n), input_max=0, output_max=0, fee_max=0
        )
    assert journal.ledger.usage(journal.batch)["workflow_requests"] == 35
    with pytest.raises(Refused, match="BUDGET_EXHAUSTED"):
        journal.ledger.reserve(
            journal.batch,
            journal.package,
            "extra",
            input_max=0,
            output_max=0,
            fee_max=0,
        )


@pytest.mark.parametrize(
    "role,slot,stage,limit",
    [
        ("generation", "D02-known", "free_scene_generation", 3),
        ("review", "D02-known:scene-review", "development_scene_review", 2),
    ],
)
def test_role_caps_before_dispatch_receipt(journal, role, slot, stage, limit):
    row = dict(provider=role, identity=dict(slot_id=slot), stage=stage)
    for n in range(limit):
        journal.record("live_dispatch_reserved", {**row, "ticket": str(n)})
    with pytest.raises(Refused, match="D02_ROLE_SCOPE_OR_LIMIT"):
        journal.record("live_dispatch_reserved", row)
    assert len(journal.events("live_dispatch_reserved")) == limit


@pytest.mark.parametrize(
    "slot,stage",
    [("D01-known", "free_scene_generation"), ("R01", "development_review_probe")],
)
def test_foreign_slot_and_probe_dispatch_refused(journal, slot, stage):
    with pytest.raises(Refused, match="D02_ROLE_SCOPE_OR_LIMIT"):
        journal.record(
            "live_dispatch_reserved",
            dict(provider="generation", identity=dict(slot_id=slot), stage=stage),
        )
    assert not journal.events("live_dispatch_reserved")


def test_old_window_still_expires(journal):
    journal.ledger.clock = lambda: (1901, 1901)
    with pytest.raises(Refused, match="EXPLICIT_WINDOW_EXPIRED"):
        journal.guard()


def test_foreign_slot_cannot_create_database_course(journal):
    with pytest.raises(Refused, match="D02_KNOWN_ONLY"):
        asyncio.run(
            x.run_experimental_slot(
                dict(slot_id="D01-known", kind="course"),
                None,
                type("A", (), {"journal": journal})(),
            )
        )


def test_missing_consistency_review_cannot_be_imported(journal):
    execution = SplitExecution(journal, [dict(slot_id="D02-known", kind="course")])
    with pytest.raises(Refused, match="ALL_TWO_CONSISTENCY_REPORTS_REQUIRED"):
        execution.review({})


@pytest.mark.parametrize("fault", ["hash", "coverage", "missing", "hidden"])
def test_consistency_source_and_actual_findings_cannot_be_silenced(journal, fault):
    finding = dict(code="SYNTHETIC", source_pointer="/candidate/text")
    reports = [
        dict(version="v1", source_digest=str(n), findings=[finding]) for n in (1, 2)
    ]
    rows = []
    for r in reports:
        journal.record(
            "consistency_observation", dict(report_sha256=digest(r), report=r)
        )
        rows.append(
            dict(
                report_sha256=digest(r),
                incomplete_coverage_acknowledged=True,
                findings=[
                    dict(
                        finding_sha256=digest(finding),
                        decision="confirmed",
                        reason="Synthetic",
                    )
                ],
            )
        )
    if fault == "hash":
        rows[0]["report_sha256"] = "x" * 64
    if fault == "coverage":
        rows[0]["incomplete_coverage_acknowledged"] = False
    if fault == "missing":
        rows[0]["findings"] = []
    with pytest.raises(Refused):
        SplitExecution(journal, []).review(
            dict(consistency_checks=rows, items=[dict(area="facts", verdict="pass")])
        )


def test_small_pass_never_becomes_t038_or_pair_pass():
    r = assess(
        [{}],
        [dict(engineering_pass=True, scene_source_hashes=["a", "b"])],
        [
            dict(
                items=[dict(verdict="pass")],
                natural_severe_errors=0,
                atomic_facts=[{}],
                answer_checks=[{}],
                consistency_checks=[{}, {}],
            )
        ],
        [dict(valid=True)] * 3,
    )
    assert (
        r["local_recheck_pass"]
        and not r["T038_completed"]
        and not r["production_admitted"]
    )
    assert r["personalized_pair_comparison"].startswith("not_assessed")
    assert not assess([{}], [], [], [])["local_recheck_pass"]
