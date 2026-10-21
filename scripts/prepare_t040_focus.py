"""Prepare fixed four-focus r10 without a run approval, key access or Provider calls."""

import argparse
import hashlib
import json
from pathlib import Path

from acceptance_support import claim_review_prototype as p
from prepare_t040_derived_run import environment_version, EXPIRES_AT

ROOT = Path(__file__).resolve().parents[1]
BASE_REL = "docs/acceptance/phase-1-t040-focus-r10"
SOURCE_REL = "docs/acceptance/phase-1-t040-span-review-offline"


def build(root=ROOT):
    source = root / SOURCE_REL
    worksheet = json.loads((source / "worksheet.json").read_text())
    scope = json.loads((source / "scope-confirmation.json").read_text())

    def sha(f):
        return hashlib.sha256((root / f).read_bytes()).hexdigest()

    def require(ok):
        if not ok:
            raise ValueError("SCOPE_CHANGED")

    require(scope["worksheet_sha256"] == sha(SOURCE_REL + "/worksheet.json"))
    require(scope["confirmed_by"] == "Lee" and scope["user_confirmation"] == "确认")
    require(scope["claim_ids"] == [i["claim"]["claim_id"] for i in worksheet["items"]])
    previews = json.loads((source / "focus-previews.json").read_text())
    requests = {
        r["probe_id"]: {
            "model": "deepseek-flash",
            "input": [
                {"role": "system", "content": r["system"]},
                {"role": "user", "content": p.encoded(r["payload"]).decode()},
            ],
            "reasoning": {"effort": "none"},
            "temperature": 0,
            "max_output_tokens": 2048,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "focus",
                    "schema": r["schema"],
                }
            },
        }
        for r in previews
    }
    history = json.loads(
        (root / "docs/acceptance/phase-1-dynamic-v1/history.json").read_text()
    )
    by_id = {i["id"]: i["payload"] for i in history["cases"]}
    items = [
        {**i, "payload": by_id[i["historical_case_id"]]} for i in worksheet["items"]
    ]
    binding = {"path": ".env", "metadata": environment_version(root / ".env")}
    consent = {
        "purpose": "span-selection-redesign-v1 fixed focus round 1",
        "credential_binding": binding,
        "model": "deepseek-flash",
        "endpoint": "https://api.deepseek.com",
        "scope_sha256": sha(SOURCE_REL + "/scope-confirmation.json"),
        "request_sha256": {k: p.digest(v) for k, v in requests.items()},
        "fallback": False,
    }
    target = {
        "version": "derived-deepseek-target-v1",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "transport": "responses_json_schema",
        "credential_ref": "server-env:" + p.digest(binding),
        "credential_version": 1,
        "consent_sha256": p.digest(consent),
    }
    caps = {
        k: (len(p.encoded(v)) + 1048576) * 2 + 2048 * 8 for k, v in requests.items()
    }
    plan = {
        "version": "fixed-focus-plan-v1",
        "execution_root": str(root.resolve()),
        "round": 1,
        "strategy_id": "span-selection-redesign-v1",
        "expires_at": EXPIRES_AT,
        "overall_seconds": 3600,
        "target": target,
        "consent": consent,
        "credential_binding": binding,
        "scope_sha256": consent["scope_sha256"],
        "focus_items": items,
        "expected_by_probe": {
            i["probe_id"]: i["expected"]
            for i in json.loads(
                (source / "expectations-not-for-model.json").read_text()
            )
        },
        "cost_cap_micro_cny": sum(caps.values()),
        "slot_cost_micro_cny": caps,
        "reasoning": "none",
        "max_output_tokens": 2048,
        "timeout_seconds": 60,
        "corrections": 0,
        "retries": 0,
        "fallbacks": 0,
        "exit_limits": {
            "max_rounds": 2,
            "max_total_attempts": 8,
            "max_attempts_per_round": 4,
        },
        "expected_consumption_estimate": None,
        "cost_bound": "Provider 1M window interpreted as 1048576 covers all model input; positive wire bytes add conservative slack; not a bytes-to-token conversion or account hard cap. Peak CNY2/8 per million; output includes reasoning.",
        "prior_evidence": "r09 failure remains independent; no reuse of remaining 37 slots",
        "provider_requests_authorized": 0,
        "provider_cost_authorized": 0,
    }
    config = {
        "provider_type": "openai-compatible",
        "model_id": "deepseek-flash",
        "adapter_sha256": sha("scripts/acceptance_support/derived_responses_sender.py"),
        "capability_sha256": p.digest(target),
        "model_revision": "DeepSeek-V4.1-Flash",
        "currency": "CNY",
        "input_price_micro_per_million": 2000000,
        "output_price_micro_per_million": 8000000,
        "input_overhead_tokens": 1048576,
        "max_wire_bytes": max(len(p.encoded(v)) for v in requests.values()),
        "max_total_output_tokens": 2048,
        "total_output_limit_verified": True,
        "token_byte_bound_verified": True,
        "output_limit_path": ["max_output_tokens"],
    }
    old = json.loads(
        (
            root / "docs/acceptance/phase-1-t040-derived-calibration-r09/run-r09.json"
        ).read_text()
    )
    files = {k: sha(k) for k in old["files"]}
    extra = [
        "scripts/prepare_t040_focus.py",
        "scripts/run_t040_focus.py",
        "scripts/acceptance_support/fixed_focus_gate.py",
        "scripts/acceptance_support/span_review_offline.py",
        "backend/tests/test_fixed_focus.py",
        BASE_REL + "/token-cost-proof.json",
        SOURCE_REL + "/worksheet.json",
        SOURCE_REL + "/scope-confirmation.json",
        SOURCE_REL + "/focus-previews.json",
        SOURCE_REL + "/expectations-not-for-model.json",
        SOURCE_REL + "/exit-policy-proposal.json",
    ]
    files.update({k: sha(k) for k in extra})
    files.update(
        {
            BASE_REL + "/requests.json": p.digest(requests),
            BASE_REL + "/plan.json": p.digest(plan),
        }
    )
    connection = "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json"
    adr = "docs/ADR/0014-derived-budget-approval-20261015.json"
    run = {
        "version": "phase1-run-v1",
        "run_id": "span-focus-r10",
        "phase": "diagnostic",
        "state": "FROZEN_RUN_READY",
        "files": files,
        "targets": {p.digest(target): config},
        "slots": [
            {
                "id": k,
                "input_sha256": p.digest(v),
                "attempts": 1,
                "stages": ["review"],
                "targets": [p.digest(target)],
                "resources": ["explanation"],
            }
            for k, v in requests.items()
        ],
        "bounds": {
            "requests": 4,
            "cost_micro": sum(caps.values()),
            "max_active_attempts": 1,
            "timeout_seconds": 60,
            "corrections_per_resource": 2,
        },
        "required_evidence": ["adr", "connection"],
        "evidence": {"adr": sha(adr), "connection": sha(connection)},
    }
    # Legacy correction ceiling is fixed at 2 by schema; no correction stage/slot exists here.
    return {"requests.json": requests, "plan.json": plan, "run.json": run}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    for name, value in data.items():
        path = ROOT / BASE_REL / name
        raw = p.encoded(value)
        if args.check:
            if path.read_bytes() != raw:
                raise ValueError("FREEZE_CHANGED")
        else:
            if path.exists() and path.read_bytes() != raw:
                raise ValueError("UNAPPROVED_PROPOSAL_CHANGED")
            path.write_bytes(raw)
    print(
        json.dumps(
            {
                "root_sha256": p.digest(data["run.json"]),
                "potential_requests": 4,
                "cost_micro_cny": data["plan.json"]["cost_cap_micro_cny"],
                "real_requests_authorized": 0,
                "state": "AWAITING_EXACT_RUN_APPROVAL",
            }
        )
    )


if __name__ == "__main__":
    main()
