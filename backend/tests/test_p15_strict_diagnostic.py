"""Actual PG scheduler under strict Responses wire Mock; complete local checks remain active."""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate  # noqa: F401
from test_free_course_planning import candidate, clarify
from test_free_scene_generation import response

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from acceptance_support.p15_diagnostic_execution import run_slot  # noqa: E402
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, digest  # noqa: E402
from acceptance_support.p15_strict_schema import validate_wire  # noqa: E402
from acceptance_support.p15_strict_transport import StrictDiagnosticAdapter  # noqa: E402

from app.core.config import ProviderSettings  # noqa: E402
from app.core.provider_target import ApprovedTarget  # noqa: E402


@pytest.mark.parametrize("mode", ["normal", "bad_schema_repaired", "bad_source_repaired"])
def test_strict_wire_original_local_contract_and_actual_scheduler(tmp_path, mode):
    ledger = Ledger(tmp_path / "TEST_ONLY.sqlite")
    batch = "TEST_ONLY_" + uuid4().hex
    limits = Limits(40, 800000, 200000, None, 600)
    approval = dict(
        scope="PHASE-1.5-T038",
        package_sha256="a" * 64,
        batch_id=batch,
        limits=asdict(limits),
        fee_cap_waiver=True,
        evidence_ref="synthetic_not_actual_approval",
    )
    ledger.start(batch, "a" * 64, limits, approval, pinned_approval_sha256=digest(approval))
    current, prompts = {}, []

    def handler(request):
        body = json.loads(request.content)
        assert body["text"]["format"]["strict"] is True
        validate_wire(body["text"]["format"]["schema"])
        if request.url.path.endswith("/input_tokens"):
            return httpx.Response(200, json=dict(object="response.input_tokens", input_tokens=100))
        prompts.append(body)
        props = body["text"]["format"]["schema"]["properties"]
        if "review_version" in props:
            value = dict(review_version="resource-review-v3", verdict="pass", issues=[])
        elif "needs_clarification" in props:
            value = (
                clarify("requirements_conflict", current["goal"])
                if current.get("negative")
                else candidate(1, current["goal"])
            )
            if value["plan"]:
                value["plan"]["scenes"][0]["forms"] = ["text", "code", "exercise", "visualization"]
            if len(prompts) == 1 and mode == "bad_schema_repaired":
                value["needs_clarification"] = True
            if len(prompts) == 1 and mode == "bad_source_repaired":
                value["plan"]["objectives"][0]["source_excerpt"] = (
                    "NOT_AN_EXCERPT_OF_THE_ACTUAL_GOAL"
                )
        else:
            value = response()
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
    adapter = StrictDiagnosticAdapter(
        ProviderSettings("https://www.cbbb.fun/v1", "TEST_ONLY_SECRET", "gpt-6-luna"),
        guard,
        ledger,
        batch,
        "a" * 64,
        tmp_path,
        lambda: httpx.MockTransport(handler),
    )

    async def execute(sessions):
        for known in [True, False] if mode == "normal" else [False]:
            current.update(goal="学习数组", negative=False)
            start = len(prompts)
            slot = dict(
                kind="course",
                slot_id="known" if known else "unknown",
                original_goal=current["goal"],
                scene_count_range=[1, 1],
                learner_evidence={"knowledge_base": {"self_report": "STRICT_TEST_ONLY_PROFILE"}}
                if known
                else {},
            )
            result = await run_slot(slot, sessions, adapter, ledger, batch, "a" * 64)
            assert result["engineering_pass"], result
            assert len(result["tables"]["free_course_plans"]) == 1
            assert len(result["tables"]["free_course_scene_generation_results"]) == 1
            assert (
                "STRICT_TEST_ONLY_PROFILE" in json.dumps(prompts[start])
                if known
                else "STRICT_TEST_ONLY_PROFILE" not in json.dumps(prompts[start])
            )
            scenes = result["tables"]["free_course_scene_generation_results"]
            assert {b["kind"] for b in scenes[0]["response_json"]["blocks"]} == {
                "text",
                "code",
                "exercise",
                "visualization",
            }
        if mode == "normal":
            current.update(goal="冲突要求", negative=True)
            result = await run_slot(
                dict(kind="negative", slot_id="N01", goal=current["goal"]),
                sessions,
                adapter,
                ledger,
                batch,
                "a" * 64,
            )
            assert (
                result["engineering_pass"] and result["operation_state"] == "awaiting_clarification"
            )
            result = await run_slot(
                dict(
                    kind="probe",
                    slot_id="R01",
                    content="栈后进先出",
                    proposed_label="NEVER_SEND_EXPECTED_LABEL",
                ),
                sessions,
                adapter,
                ledger,
                batch,
                "a" * 64,
            )
            assert result["engineering_pass"] and "NEVER_SEND_EXPECTED_LABEL" not in json.dumps(
                prompts
            )
            assert ledger.usage(batch)["requests"] == 12
        else:
            assert ledger.usage(batch)["requests"] == 6
            primary = [
                json.loads(r[0])
                for r in ledger.db.execute("SELECT body FROM receipts WHERE kind='primary_schema'")
            ]
            assert len(primary) == 2 and [r["valid"] for r in primary] == [False, True]
            assert len(result["tables"]["free_course_attempts"]) == 3
            assert len(result["tables"]["free_course_settlements"]) == 3
            assert (
                ledger.usage(batch)["input_tokens"] == ledger.usage(batch)["output_tokens"] == 300
            )

    try:
        dbwork(execute)
    finally:
        ledger.close()
