"""Isolated PG experiment: no real network except the dedicated database."""

# ruff: noqa: E402
import json
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate
from test_free_course_planning import candidate
from test_free_scene_generation import response
from test_p15_split_provider import course_slot, reply
from test_p15_split_provider import only_pg_network as only_pg_network

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from isolated_diagnostics import p15_exploration as x
from isolated_diagnostics import p15_split_provider as p

from app.core.provider_target import ApprovedTarget
from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
from app.services.free_course_scheduler import Scheduler
from app.services.free_course_snapshots import SnapshotError


def test_real_pg_pipeline_keeps_false_policy_and_original_production_refusal(tmp_path):
    batch = "p15-split-experiment-test-" + uuid4().hex
    grant = {
        "scope": "PHASE-1.5-T038",
        "package_sha256": "a" * 64,
        "batch_id": batch,
        "limits": asdict(x.ExplorationLimits()),
        "evidence_ref": "SYNTHETIC_TEST_NOT_APPROVAL",
        "fee_cap_waiver": True,
    }
    j = x.ExplorationJournal.create(tmp_path / "wire", batch, "a" * 64, grant)
    sent = []

    def handle(request):
        body = json.loads(request.content)
        sent.append(body)
        if request.headers["host"] == "api.deepseek.com":
            value = (
                candidate(2, "合成数组目标")
                if "needs_clarification" in body["text"]["format"]["schema"]["properties"]
                else response()
            )
            if "plan" in value:
                for scene in value["plan"]["scenes"]:
                    scene["forms"] = ["text", "code", "exercise", "visualization"]
        else:
            source = json.loads(body["input"][-1]["content"])
            value = {
                "source_sha256": source["source_sha256"],
                "scope_status": "complete",
                "uncertain_reason": None,
                "verdict": "pass",
                "issues": [],
            }
        return reply(request, value)

    adapter = x.ExplorationAdapter(
        j,
        {"generation": "TEST_ONLY_DEEPSEEK_KEY", "review": "TEST_ONLY_AIAPI_KEY"},
        lambda role: ApprovedTarget(
            "https://api.deepseek.com" if role == "generation" else "https://aiapi.world/v1",
            "api.deepseek.com" if role == "generation" else "aiapi.world",
            443,
            ("8.8.8.8",),
        ),
        lambda: httpx.MockTransport(handle),
    )

    async def run(sessions):
        result = await x.run_experimental_slot(course_slot("experiment", True), sessions, adapter)
        assert result["engineering_pass"] is True
        assert result["experimental_unbounded_admission"] is True
        assert result["production_bound_evidence"] is False
        identity = p.Identity(**result["scene_review_identity"])
        j.require_reviews_complete(identity)
        async with sessions() as db:
            attempts = (
                await db.scalars(
                    select(FreeCourseAttempt).where(
                        FreeCourseAttempt.course_id == UUID(identity.course_id)
                    )
                )
            ).all()
            assert len(attempts) == 3
            assert all(
                a.request_json["send_policy"]["bounded_output_verified"] is False for a in attempts
            )
            assert all(
                a.request_json["input_reservation_is_placeholder"] and a.input_tokens == 1
                for a in attempts
            )
            settlements = (
                await db.scalars(
                    select(FreeCourseSettlement).where(
                        FreeCourseSettlement.course_id == UUID(identity.course_id)
                    )
                )
            ).all()
            assert len(settlements) == 3 and all(s.input_tokens == 100 for s in settlements)
        # Original production scheduler still rejects the exact same unverified adapter.
        bound = adapter.bound(p.Identity("guard", "owner", "course"))
        try:
            await Scheduler(sessions).prepare(None, bound)
        except SnapshotError as exc:
            assert str(exc) == "EXECUTION_NOT_AUTHORIZED"
        else:
            raise AssertionError("Production gate must remain closed")

    try:
        dbwork(run)
        assert len(sent) == 5
        assert j.ledger.usage(batch)["fee_micros"] is None
    finally:
        j.ledger.close()
