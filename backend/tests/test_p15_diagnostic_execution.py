"""Actual isolated PG/scheduler, explicit HTTPX wire mock; no live model calls."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_planning import candidate, clarify
from test_free_scene_generation import response

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support.p15_diagnostic_execution import run_slot  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from acceptance_support.p15_diagnostic_transport import DiagnosticAdapter  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402


def test_actual_scheduler_profile_unknown_negative_and_probe_with_counted_wire(tmp_path):
    ledger = Ledger(tmp_path / "TEST_ONLY.sqlite")
    limits = Limits(50, 1000000, 300000, None, 600)
    approval = dict(
        package_sha256="a" * 64,
        batch_id="TEST_ONLY_PG",
        limits=limits.__dict__,
        scope="PHASE-1.5-T038",
        evidence_ref="synthetic",
        fee_cap_waiver=True,
    )
    ledger.start(
        "TEST_ONLY_PG", "a" * 64, limits, approval, pinned_approval_sha256=digest(approval)
    )
    prompts = []
    current = {}

    def wire(request):
        if request.url.path.endswith("input_tokens"):
            return httpx.Response(
                200, json={"object": "response.input_tokens", "input_tokens": 100}
            )
        body = json.loads(request.content)
        prompts.append(body)
        schema = body["text"]["format"]["schema"]
        if "review_version" in schema["properties"]:
            value = dict(review_version="resource-review-v3", verdict="pass", issues=[])
        elif "needs_clarification" in schema["properties"]:
            value = (
                clarify("requirements_conflict", current["goal"])
                if current["negative"]
                else candidate(1, current["goal"])
            )
        else:
            value = response(["text"])
        if current.get("bad_primary") and len(body["input"]) == 2:
            value = {}
        return httpx.Response(
            200,
            json=dict(
                model="gpt-6-luna",
                status="completed",
                output=[
                    dict(
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[dict(type="output_text", text=json.dumps(value))],
                    )
                ],
                usage=dict(input_tokens=100, output_tokens=100),
            ),
        )

    guard = SimpleNamespace(
        approve_base=lambda: ApprovedTarget(
            "https://www.cbbb.fun/v1", "www.cbbb.fun", 443, ("8.8.8.8",)
        )
    )
    adapter = DiagnosticAdapter(
        ProviderSettings("https://www.cbbb.fun/v1", "TEST_ONLY_SECRET", "gpt-6-luna"),
        guard,
        ledger,
        "TEST_ONLY_PG",
        "a" * 64,
        tmp_path,
        lambda: httpx.MockTransport(wire),
    )

    async def execute(sessions):
        for known in [True, False]:
            current.update(goal="学习数组", negative=False)
            slot = dict(
                kind="course",
                slot_id="known" if known else "unknown",
                original_goal=current["goal"],
                scene_count_range=[1, 1],
                learner_evidence={"knowledge_base": {"self_report": "TEST_ONLY_LEARNER"}}
                if known
                else {},
            )
            result = await run_slot(slot, sessions, adapter, ledger, "TEST_ONLY_PG", "a" * 64)
            assert result["engineering_pass"], result
            assert result["planned_scene_denominator"] == 1
            payload = json.loads(prompts[-2]["input"][1]["content"])
            assert ("TEST_ONLY_LEARNER" in json.dumps(payload)) is known
            assert "free_course_attempts" in result["tables"]
        current.update(goal="冲突要求", negative=True)
        result = await run_slot(
            dict(kind="negative", slot_id="N01", goal=current["goal"]),
            sessions,
            adapter,
            ledger,
            "TEST_ONLY_PG",
            "a" * 64,
        )
        assert (
            result["engineering_pass"] and result["operation_state"] == "awaiting_clarification"
        ), result
        result = await run_slot(
            dict(
                kind="probe",
                slot_id="R01",
                content="栈后进先出",
                proposed_label="NEVER_SEND_THIS_LABEL",
            ),
            sessions,
            adapter,
            ledger,
            "TEST_ONLY_PG",
            "a" * 64,
        )
        assert result["engineering_pass"]
        assert "NEVER_SEND_THIS_LABEL" not in json.dumps(prompts)
        assert ledger.usage("TEST_ONLY_PG")["requests"] == 12
        assert (
            ledger.db.execute(
                "SELECT count(*) FROM receipts WHERE kind='primary_schema'"
            ).fetchone()[0]
            == 4
        )
        current.update(goal="学习数组", negative=False, bad_primary=True)
        with pytest.raises(Refused, match="FIRST_SCHEMA_THRESHOLD_UNREACHABLE"):
            await run_slot(
                dict(
                    kind="course",
                    slot_id="bad-primary",
                    original_goal="学习数组",
                    scene_count_range=[1, 1],
                ),
                sessions,
                adapter,
                ledger,
                "TEST_ONLY_PG",
                "a" * 64,
            )
        assert ledger.usage("TEST_ONLY_PG")["requests"] == 18
        assert ledger.db.execute("SELECT state FROM batches").fetchone()[0] == "stopped"

    try:
        dbwork(execute)
    finally:
        ledger.close()
