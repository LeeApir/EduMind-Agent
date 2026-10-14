"""Execute approved historical diagnostics one request at a time; no formal samples."""
# ruff: noqa: E402

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from unittest.mock import patch

from run_deepseek_connection import Audit, MODEL, observe
from run_phase1_provider_connection import configured
from prepare_t040_diagnostics import BASE, GROUPS, ROOT, check_proposal
from acceptance_support.phase1_budget import (
    Approval,
    FrozenBudget,
    GateFailure,
    canonical,
    sha,
)
from acceptance_support.connection_diagnostics import ProbeFailure, classify_failure
from app.agents.review_schema import validate_review
from app.core.config import ProviderSettings
from app.core.provider_factory import configured_provider_adapter
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.provider_gateway import ChatMessage, StructuredRequest, TextRequest

RAW = ROOT / "local-materials/phase-1-t040-deepseek-v1"
ROUND = "r01"


def read(path):
    return json.loads(path.read_text())


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(value))


def approval_record():
    plan = read(BASE / "proposal.json")
    approval = read(BASE / "diagnostic-approval.json")
    if (
        approval.get("approved") is not True
        or approval.get("proposal_sha256") != sha((BASE / "proposal.json").read_bytes())
        or approval.get("groups")
        != {
            g["id"]: {"requests": g["requests"], "cost_micro": g["cost_cap_micro_cny"]}
            for g in plan["groups"]
        }
    ):
        raise GateFailure("NOT_AUTHORIZED")
    return plan, approval


def freeze():
    check_proposal()
    plan, _ = approval_record()
    old = read(ROOT / "docs/acceptance/phase-1-deepseek-connection-v1/run-r01.json")
    connection_path = (
        ROOT / "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json"
    )
    connection = read(connection_path)
    if len(connection["observations"]) != 4 or not all(
        row["passed"] is True for row in connection["observations"]
    ):
        raise GateFailure("PREREQUISITE_MISSING")
    files = {
        **plan["files"],
        **{
            str(p.relative_to(ROOT)): sha(p.read_bytes())
            for p in [
                Path(__file__).resolve(),
                ROOT / "scripts/run_deepseek_connection.py",
                ROOT / "scripts/run_phase1_provider_connection.py",
                ROOT / "scripts/acceptance_support/connection_diagnostics.py",
                ROOT / "backend/tests/test_t040_diagnostic_runner.py",
                BASE / "proposal.json",
                BASE / "diagnostic-approval.json",
            ]
        },
    }
    for group in plan["groups"]:
        path = BASE / f"run-{group['id']}-{ROUND}.json"
        if path.exists():
            raise GateFailure("FREEZE_CHANGED")
        target = dict(next(iter(old["targets"].values())))
        target.update(
            max_wire_bytes=max(r["request_bytes"] for r in group["slots"]),
            max_total_output_tokens=plan["max_output_tokens_including_reasoning"],
            adapter_sha256=sha(
                (ROOT / "backend/app/services/deepseek_responses.py").read_bytes()
            ),
            capability_sha256=sha(
                canonical(
                    {
                        "model": MODEL,
                        "transport": plan["transport"],
                        "reasoning_effort": plan["reasoning_effort"],
                        "max_output_tokens": plan[
                            "max_output_tokens_including_reasoning"
                        ],
                    }
                )
            ),
        )
        target_id = sha(
            canonical(
                {"model": MODEL, "target": target, "transport": plan["transport"]}
            )
        )
        manifest = {
            "version": "phase1-run-v1",
            "run_id": f"t040-{group['id']}-{ROUND}",
            "state": "FROZEN_RUN_READY",
            "phase": "diagnostic",
            "files": files,
            "targets": {target_id: target},
            "slots": [
                {
                    "id": r["slot"],
                    "input_sha256": r["request_sha256"],
                    "attempts": 1,
                    "stages": ["review"],
                    "targets": [target_id],
                    "resources": ["unit"],
                }
                for r in group["slots"]
            ],
            "bounds": {
                "requests": group["requests"],
                "cost_micro": group["cost_cap_micro_cny"],
                "timeout_seconds": group["timeout_seconds_per_request"],
                "max_active_attempts": 1,
                "corrections_per_resource": 2,
            },
            "required_evidence": ["adr", "connection"],
            "evidence": {
                "adr": files["docs/ADR/0011-dynamic-approval-20261008.json"],
                "connection": sha(connection_path.read_bytes()),
            },
        }
        private_write(path, manifest)
        budget(group["id"])._authorize()
    print("Four independent approved diagnostic runs frozen; model calls=0")


def budget(group):
    plan, _ = approval_record()
    manifest = read(BASE / f"run-{group}-{ROUND}.json")
    expected = next(g for g in plan["groups"] if g["id"] == group)
    return FrozenBudget(
        manifest,
        RAW / group / "budget.sqlite",
        root=ROOT,
        approval=Approval(
            sha(canonical(manifest)),
            "diagnostic",
            expected["requests"],
            expected["cost_cap_micro_cny"],
            sha((BASE / "diagnostic-approval.json").read_bytes()),
            True,
        ),
    )


def require_prior_group(group):
    """A later group needs actual human evidence over all previous response hashes."""
    for previous in GROUPS[: GROUPS.index(group)]:
        gate = budget(previous)
        snapshot = gate.snapshot()
        path = BASE / f"human-{previous}-{ROUND}.json"
        if snapshot["halted"] or snapshot["unattempted_slots"] or not path.exists():
            raise GateFailure("PREREQUISITE_MISSING")
        signoff = read(path)
        responses = {
            slot["id"]: read(RAW / previous / (slot["id"].replace(":", "-") + ".json"))[
                "response_sha256"
            ]
            for slot in gate.manifest["slots"]
        }
        if (
            signoff.get("human_confirmed") is not True
            or signoff.get("passed") is not True
            or signoff.get("freeze") != gate.freeze
            or signoff.get("response_hashes") != responses
            or not signoff.get("reviewer")
            or not signoff.get("user_confirmation_evidence")
        ):
            raise GateFailure("PREREQUISITE_MISSING")


def coarse_quality_failure(group, review, expected_area):
    """Only certain failures; a rejection alone is never proof of concrete detection."""
    if group in {"error_detection", "classification"}:
        if review["verdict"] == "pass":
            return "CONCRETE_DEFECT_MISSED"
        if group == "classification" and not any(
            issue["area"] == expected_area for issue in review["issues"]
        ):
            return "ADMISSION_FAILED"
    if group == "correct_control" and review["verdict"] != "pass":
        return "CONTROL_REJECTED"
    return None


async def run_one(group):
    require_prior_group(group)
    gate = budget(group)
    gate._authorize()
    if any(
        configured(name) != value
        for name, value in {
            "EDUMIND_PROVIDER_BASE_URL": "https://api.deepseek.com",
            "EDUMIND_PROVIDER_MODEL": MODEL,
            "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT": "responses_json_schema",
        }.items()
    ):
        raise GateFailure("TARGET_CHANGED")
    snapshot = gate.snapshot()
    if snapshot["halted"]:
        raise GateFailure("RUN_HALTED")
    if not snapshot["unattempted_slots"]:
        raise GateFailure("BUDGET_EXHAUSTED")
    slot = snapshot["unattempted_slots"][0]
    body = read(BASE / "requests.json")[slot]
    frozen = next(r for r in gate.manifest["slots"] if r["id"] == slot)
    if sha(canonical(body)) != frozen["input_sha256"]:
        raise GateFailure("FREEZE_CHANGED")
    number = gate.reserve(
        slot,
        "review",
        next(iter(gate.manifest["targets"])),
        canonical(body),
        resource="unit",
    )
    audit = Audit(body)
    review = None
    error = category = quality_failure = None
    decoded = b""
    started = time.monotonic()
    try:
        async with asyncio.timeout(gate.manifest["bounds"]["timeout_seconds"]):
            settings = ProviderSettings(
                "https://api.deepseek.com",
                configured("EDUMIND_PROVIDER_API_KEY"),
                MODEL,
            )
            with patch.dict(
                os.environ,
                {"EDUMIND_PROVIDER_STRUCTURED_TRANSPORT": "responses_json_schema"},
            ):
                adapter = configured_provider_adapter(
                    settings,
                    ProviderTargetGuard(settings.base_url, TargetPolicy()),
                    reasoning_effort=body["reasoning"]["effort"],
                )
            adapter._transport = audit
            answer = await adapter.generate_structured(
                StructuredRequest(
                    TextRequest(
                        tuple(
                            ChatMessage(m["role"], m["content"]) for m in body["input"]
                        ),
                        max_output_tokens=body["max_output_tokens"],
                        temperature=0,
                    ),
                    body["text"]["format"]["schema"],
                )
            )
            review = validate_review(answer.value)
            fields = audit.observation()
            if (
                answer.model_id != MODEL
                or not fields["completed"]
                or not fields["model_matches"]
            ):
                raise ProbeFailure("completion_or_identity")
            plan, _ = approval_record()
            planned_slot = next(
                r for g in plan["groups"] for r in g["slots"] if r["slot"] == slot
            )
            cases = read(ROOT / "docs/acceptance/phase-1-dynamic-v1/history.json")[
                "cases"
            ]
            expected_case = next(
                c for c in cases if c["id"] == planned_slot["historical_case_id"]
            )
            quality_group = (
                "classification" if group == "classification" else expected_case["kind"]
            )
            quality_failure = coarse_quality_failure(
                quality_group, review, expected_case["expected_area"]
            )
    except Exception as exc:
        error, category = classify_failure(exc)
    try:
        fields = audit.observation()
        decoded = audit.decoded()
    except Exception:
        fields = observe(None)
    fields["reasoning_tokens"] = reasoning_count(decoded, fields["output_tokens"])
    # Private raw evidence includes text for human checking, never request headers or credentials.
    # Reflected secrets are discarded entirely rather than copied into evidence or exceptions.
    secret = configured("EDUMIND_PROVIDER_API_KEY").encode()
    if (secret and secret in decoded) or re.search(rb"sk-[A-Za-z0-9_-]{16,}", decoded):
        decoded = b""
        review = None
        error, category = "SAFETY_FAILURE", "secret_reflection"
    gate.finish(
        number,
        error_code=error,
        input_tokens=fields["input_tokens"],
        output_tokens=fields["output_tokens"],
    )
    if quality_failure:
        gate.halt(quality_failure)
    row = {
        "slot": slot,
        "freeze": gate.freeze,
        "request_sha256": sha(canonical(body)),
        "response_sha256": sha(decoded),
        "wire_response_sha256": sha(bytes(audit.payload)),
        "http_status": audit.status,
        "outbound_sends": audit.sent,
        "protocol_passed": error is None,
        "error_code": error,
        "error_category": category,
        "quality_failure": quality_failure,
        "response": fields,
        "review": review,
        "duration_seconds": round(time.monotonic() - started, 6),
        "human_confirmed": False,
        "real_cloud": True,
        "mock": False,
    }
    private_write(RAW / group / (slot.replace(":", "-") + ".json"), row)
    retained = retain_generated_response(decoded)
    if retained is not None:
        private_write(
            RAW / group / (slot.replace(":", "-") + "-response.json"), retained
        )
    print(json.dumps({key: value for key, value in row.items() if key != "review"}))
    print(
        json.dumps(
            {
                "halted": gate.snapshot()["halted"],
                "remaining": gate.snapshot()["unattempted_slots"],
            }
        )
    )


def retain_generated_response(decoded):
    """Preserve completed model outputs for human review, never raw vendor errors."""
    try:
        raw = json.loads(decoded)
    except (ValueError, UnicodeError):
        return None
    if (
        not isinstance(raw, dict)
        or raw.get("status") != "completed"
        or raw.get("error")
    ):
        return None
    retained = {key: raw.get(key) for key in ("status", "model", "usage")}
    output = raw.get("output")
    retained["output"] = (
        [
            item
            for item in output
            if isinstance(item, dict) and item.get("type") == "message"
        ]
        if isinstance(output, list)
        else []
    )
    return retained


def reasoning_count(decoded, output_tokens):
    """Numeric provider usage only; absent details remain unknown, never fabricated zero."""
    try:
        value = json.loads(decoded)["usage"]["output_tokens_details"][
            "reasoning_tokens"
        ]
    except (ValueError, UnicodeError, KeyError, TypeError):
        return None
    if (
        type(value) is int
        and type(output_tokens) is int
        and 0 <= value <= output_tokens
    ):
        return value
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze", action="store_true")
    action.add_argument("--run-one", choices=GROUPS)
    args = parser.parse_args()
    try:
        freeze() if args.freeze else asyncio.run(run_one(args.run_one))
    except Exception as exc:
        print(
            "Stopped: "
            + (exc.code if isinstance(exc, GateFailure) else type(exc).__name__)
        )
        raise SystemExit(1) from None
