"""Prepare exact historical diagnostic requests offline. No key or network access."""
# ruff: noqa: E402

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.phase1_budget import canonical, sha
from app.agents.learning_resource_schema import LearningResourceType
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.review_agent import ReviewAgent
from app.agents.review_context import ResourceReviewContext
from app.agents.review_schema import REVIEW_PROMPT_VERSION
from app.services.deepseek_responses import _request_body
from app.services.provider_gateway import StructuredResult

BASE = ROOT / "docs/acceptance/phase-1-t040-deepseek-v1"
HISTORY = ROOT / "docs/acceptance/phase-1-dynamic-v1/history.json"
GROUPS = ("error_detection", "classification", "correct_control", "long_review")
MAX_OUTPUT = 4096
OVERHEAD = 1024


class CaptureGateway:
    """Capture the actual ReviewAgent request without invoking a Provider."""

    def __init__(self):
        self.requests = []

    async def generate_structured(self, request, *, retry_safe=False):
        self.requests.append(request)
        return StructuredResult(
            value={"review_version": REVIEW_PROMPT_VERSION, "verdict": "pass", "issues": []},
            model_id="OFFLINE_CAPTURE_ONLY",
        )


async def capture_case(case):
    payload = case["payload"]
    assert sha(canonical(payload)) == case["payload_sha256"]
    resource = PendingLearningResource(
        resource_type=LearningResourceType(payload["resource_type"]),
        content=payload["content"],
        prompt_version="historical-diagnostic",
        model_id="historical-candidate",
        usage=None,
    )
    context = ResourceReviewContext(json.dumps(payload["reference_context"], ensure_ascii=False))
    capture = CaptureGateway()
    await ReviewAgent(capture)._review(resource, context)
    # A local rejection must never be presented as a real model observation.
    if len(capture.requests) != 1:
        raise ValueError("LOCAL_ONLY_CASE_REQUIRES_SEPARATE_PLAN")
    request = capture.requests[0]
    prompt = replace(request.prompt, max_output_tokens=MAX_OUTPUT, temperature=0)
    body = _request_body(prompt)
    body.update(model="deepseek-flash", text={"format": {
        "type": "json_schema", "name": "edumind_result", "schema": request.json_schema,
    }})
    return body


def reservation(body):
    """Peak uncached CNY list-price bound; no discounts or currency conversion."""
    input_bound = len(canonical(body)) + OVERHEAD
    return input_bound * 2 + MAX_OUTPUT * 8  # CNY micro per token: input 2, output 8.


async def prepare():
    history = json.loads(HISTORY.read_text())
    requests = {}
    groups = []
    for group in GROUPS:
        kind = "error_detection" if group == "classification" else group
        cases = [case for case in history["cases"] if case["kind"] == kind]
        rows = []
        for index, case in enumerate(cases, 1):
            slot = f"{group}:{index:02}"
            body = await capture_case(case)
            requests[slot] = body
            rows.append({
                "slot": slot, "historical_case_id": case["id"],
                "payload_sha256": case["payload_sha256"],
                "request_sha256": sha(canonical(body)),
                "request_bytes": len(canonical(body)),
                "input_token_upper_bound": len(canonical(body)) + OVERHEAD,
                "output_token_upper_bound": MAX_OUTPUT,
                "reservation_micro_cny": reservation(body),
            })
        conservative = sum(row["reservation_micro_cny"] for row in rows)
        # Round up to whole cents. Approval must bind this exact individual group cap.
        groups.append({
            "id": group, "state": "PENDING_BUDGET_APPROVAL",
            "requests": len(rows), "cost_cap_micro_cny": ((conservative + 9999) // 10000) * 10000,
            "computed_reservation_micro_cny": conservative,
            "timeout_seconds_per_request": 60, "retries": 0, "fallbacks": 0,
            "corrections": 0, "max_active_requests": 1,
            "advance_requires": "Previous group complete and human-confirmed pass; explicit group budget approval.",
            "slots": rows,
        })
    assert [group["requests"] for group in groups] == [5, 5, 1, 2]
    return requests, {
        "version": "t040-deepseek-diagnostic-proposal-v1",
        "state": "PENDING_BUDGET_APPROVAL", "real_requests_sent": 0,
        "provider_requests_authorized": 0, "provider_cost_micro_authorized": 0,
        "model_id": "deepseek-flash", "model_revision": "DeepSeek-V4.1-Flash",
        "base_url": "https://api.deepseek.com", "transport": "responses_json_schema",
        "adapter": "DeepSeekResponsesAdapter", "reasoning_effort": "none", "temperature": 0,
        "max_output_tokens_including_reasoning": MAX_OUTPUT,
        "request_input_bound": "Full UTF-8 serialized body bytes plus 1024 template tokens; includes schema.",
        "input_peak_uncached_cny_per_million": 2, "output_peak_cny_per_million": 8,
        "pricing_evidence": "docs/acceptance/phase-1-deepseek-connection-v1/pricing.json",
        "billing_claim": "Conservative reservation only; actual bill unknown.",
        "groups": groups,
        "requested_total_calls": sum(group["requests"] for group in groups),
        "requested_total_cost_micro_cny": sum(group["cost_cap_micro_cny"] for group in groups),
        "production_mode": "catalog_only", "formal_quality_authorized": False,
        "dsl_quality_authorized": False, "t041_authorized": False,
        "human_gate": "Bind reviewer, input/request/response hashes, concrete defect and location, classification or correct pass. No inferred human signoff.",
        "stop_conditions": [
            "Provider/schema/completion/model/usage/budget failure stops group immediately.",
            "Concrete missed defect, wrong classification, false rejection or incomplete long review blocks advance.",
            "No automatic move to another group or formal set; missing slots retained.",
        ],
    }


def write_proposal():
    if (BASE / "proposal.json").exists():
        raise ValueError("PROPOSAL_ALREADY_EXISTS_USE_NEW_VERSION")
    requests, proposal = asyncio.run(prepare())
    BASE.mkdir(parents=True, exist_ok=True)
    path = BASE / "requests.json"
    path.write_text(json.dumps(requests, ensure_ascii=False, indent=2) + "\n")
    paths = sorted((ROOT / "backend/app").rglob("*.py")) + [
        Path(__file__).resolve(),
        ROOT / "backend/tests/test_t040_diagnostic_preparation.py",
        ROOT / "scripts/acceptance_support/phase1_budget.py",
        ROOT / "scripts/verify_phase1_dynamic_approval.py",
        ROOT / "scripts/verify_phase1_dynamic_freeze.py",
        ROOT / "backend/uv.lock", ROOT / "backend/pyproject.toml", HISTORY, path,
        ROOT / "docs/ADR/0011-dynamic-approval-20261008.json",
        ROOT / "docs/acceptance/phase-1-deepseek-connection-v1/pricing.json",
        ROOT / "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
    ]
    proposal["files"] = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}
    (BASE / "proposal.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"requests": 13, "cost_cap_micro_cny": proposal["requested_total_cost_micro_cny"],
                      "authorized": False, "network_calls": 0}))


def check_proposal():
    """Reject any source, request, sample or budget drift before requesting approval."""
    requests, expected = asyncio.run(prepare())
    proposal = json.loads((BASE / "proposal.json").read_text())
    files = proposal.pop("files")
    assert proposal == expected, "PROPOSAL_CHANGED"
    assert json.loads((BASE / "requests.json").read_text()) == requests, "REQUESTS_CHANGED"
    for relative, digest in files.items():
        path = ROOT / relative
        assert not path.is_symlink() and path.resolve().is_relative_to(ROOT)
        assert sha(path.read_bytes()) == digest, relative
    print("PASS: exact diagnostic requests, group budgets and source hashes; real calls=0")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write-proposal", action="store_true")
    group.add_argument("--check-proposal", action="store_true")
    args = parser.parse_args()
    write_proposal() if args.write_proposal else check_proposal()
