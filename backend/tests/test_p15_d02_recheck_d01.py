"""Isolated PG experiment: no real network except the dedicated database."""

# ruff: noqa: E402
import json
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate
from test_free_course_planning import candidate
from test_free_scene_generation import response
from test_p15_split_provider import only_pg_network as only_pg_network
from test_p15_split_provider import reply

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from isolated_diagnostics import p15_d02_recheck_d01 as x
from isolated_diagnostics import p15_split_provider as p
from isolated_diagnostics.p15_d02_review_d01 import verify_consistency

from app.core.provider_target import ApprovedTarget
from app.models.free_course_scheduler import FreeCourseAttempt, FreeCourseSettlement
from app.services.free_course_scheduler import Scheduler
from app.services.free_course_snapshots import SnapshotError


def test_full_pg_two_scene_pipeline_low_metadata_and_production_refusal(tmp_path):
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
                candidate(2, "学习单链表头插，用C代码和练习组织2个场景。")
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
        res = reply(request, value)
        if request.headers["host"] == "aiapi.world":
            data = json.loads(res.content)
            data["reasoning"] = {"effort": "low"}
            data.pop("instructions")
            data["usage"]["output_tokens_details"] = {"reasoning_tokens": 11}
            data["output"].insert(
                0,
                {
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "MOCK_SUMMARY_NOT_FORWARDED"}],
                    "content": [],
                },
            )
            assert body["reasoning"] == {"effort": "low"}
            return httpx.Response(200, json=data)
        assert body["reasoning"] == {"effort": "none"}
        if "plan" in body["input"][-1]["content"]:
            candidate_payload = json.loads(body["input"][-1]["content"])
            if "response_contract" in candidate_payload:
                assert candidate_payload["prompt_version"] == "free-scene-generation-v4"
                assert candidate_payload["response_contract"]["exercise_answers"]
                assert (
                    candidate_payload["response_contract"]["semantic_contract"]["version"]
                    == "free-course-c-semantics-v1"
                )
        return res

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
        result = await x.run_experimental_slot(
            json.loads((ROOT / "docs/acceptance/phase-1.5-d02-recheck-d01/slots.json").read_text())[
                0
            ],
            sessions,
            adapter,
        )
        assert result["engineering_pass"] is True
        assert result["experimental_unbounded_admission"] is True
        assert result["production_bound_evidence"] is False
        identity = p.Identity(**result["scene_review_identity"])
        j.require_reviews_complete(identity)
        audits = j.events("consistency_observation")
        assert len(audits) == 2 and all(
            a["report"]["coverage"]["complete"] is False for a in audits
        )
        assert all("consistency_observation" not in json.dumps(b) for b in sent)
        verify_consistency([result], audits)
        changed = deepcopy(audits)
        changed[0]["report"]["semantic_correctness_verified"] = True
        with pytest.raises(p.Refused, match="CONSISTENCY_OBSERVATION_CHANGED"):
            verify_consistency([result], changed)
        observed = j.events("review_protocol_observation")
        assert len(observed) == 2
        assert all(v["instruction_echo_status"] == "echo_unavailable" for v in observed)
        assert all(v["instruction_delivery_verified"] is False for v in observed)
        assert all(v["summary_interpreted_or_forwarded"] is False for v in observed)
        assert "MOCK_SUMMARY_NOT_FORWARDED" not in json.dumps(observed)
        assert all("MOCK_SUMMARY_NOT_FORWARDED" not in json.dumps(b) for b in sent)
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
        assert j.ledger.usage(batch)["workflow_requests"] == 30
    finally:
        j.ledger.close()
