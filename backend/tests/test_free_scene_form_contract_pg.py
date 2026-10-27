"""Real isolated PG: explicit form contract drives bounded structural repair."""

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
from app.models.free_course import FreeCourse
from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement


def test_no_visualization_plan_and_repair_keep_original_rejected_candidate(tmp_path):
    batch = "p15-split-experiment-test-forms-" + uuid4().hex
    grant = {
        "scope": "PHASE-1.5-T038",
        "package_sha256": "a" * 64,
        "batch_id": batch,
        "limits": asdict(x.ExplorationLimits()),
        "evidence_ref": "SYNTHETIC_TEST_NOT_APPROVAL",
        "fee_cap_waiver": True,
    }
    j = x.ExplorationJournal.create(tmp_path / "wire", batch, "a" * 64, grant)
    scene_calls = []

    def handle(request):
        body = json.loads(request.content)
        if request.headers["host"] == "api.deepseek.com":
            if "needs_clarification" in body["text"]["format"]["schema"]["properties"]:
                value = candidate(2, "合成数组目标")
                for s in value["plan"]["scenes"]:
                    s["forms"] = ["text", "code", "exercise"]
            else:
                payload = json.loads(body["input"][1]["content"])
                contract = payload["response_contract"]
                assert payload["prompt_version"] == "free-scene-generation-v3"
                assert contract["allowed_block_kinds"] == ["code", "exercise", "text"]
                assert contract["forbidden_block_kinds"] == ["visualization"]
                scene_calls.append(body)
                # Deliberately violate the first call; only repair may become ready.
                value = (
                    response()
                    if len(scene_calls) == 1
                    else response(contract["allowed_block_kinds"])
                )
                if len(scene_calls) == 2:
                    assert "Repair only structural" in body["input"][-1]["content"]
                    assert contract["format_repair"]["unexpected_block_kind"]
        else:
            source = json.loads(body["input"][-1]["content"])
            assert all(
                b["kind"] != "visualization" for b in source["source"]["scene"]["content"]["blocks"]
            )
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
        result = await x.run_experimental_slot(course_slot("forms", True), sessions, adapter)
        assert result["engineering_pass"] is True
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
            settlements = (
                await db.scalars(
                    select(FreeCourseSettlement).where(
                        FreeCourseSettlement.course_id == UUID(identity.course_id)
                    )
                )
            ).all()
            assert len(attempts) == len(settlements) == 4
            outcomes = {s.attempt_id: s.outcome_json["value"] for s in settlements}
            repairs = [a for a in attempts if a.purpose == "format_repair"]
            assert len(repairs) == 1
            repair = outcomes[repairs[0].id]
            assert not any(b["kind"] == "visualization" for b in repair["blocks"])
            original = [
                outcomes[a.id]
                for a in attempts
                if a.purpose == "primary"
                and a.request_json["request"]["stage"] == "free_scene_generation"
            ]
            assert any(any(b["kind"] == "visualization" for b in v["blocks"]) for v in original)
            assert (await db.get(FreeCourse, UUID(identity.course_id))).endorsement == "unendorsed"

    try:
        dbwork(run)
        assert len(scene_calls) == 3
    finally:
        j.ledger.close()
