"""Freeze last diagnostic proposal; metadata only, no Key, approval or network."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from acceptance_support import claim_review_prototype as p
from acceptance_support.final_focus_contract import VERSION, fixture
from prepare_t040_derived_run import EXPIRES_AT, environment_version

ROOT = Path(__file__).resolve().parents[1]
BASE_REL = "docs/acceptance/phase-1-t040-focus-r11"
PRIOR_REL = "docs/acceptance/phase-1-t040-focus-r10"


def build(root=ROOT):
    def read(name):
        return json.loads((root / name).read_bytes())

    def sha(name):
        return hashlib.sha256((root / name).read_bytes()).hexdigest()

    prior = read(PRIOR_REL + "/run.json")
    for name, expected in prior["files"].items():
        if sha(name) != expected:
            raise ValueError("PRIOR_FREEZE_CHANGED")
    prior_result = read(PRIOR_REL + "/results/r10-focus-02.json")
    if (
        prior_result["root_sha256"] != p.digest(prior)
        or prior_result["state"] != "HALTED_ADMISSION_FAILED"
    ):
        raise ValueError("PRIOR_RESULT_MISMATCH")
    samples = read(BASE_REL + "/samples.json")
    if len(samples["items"]) != 4 or [x["expected"] for x in samples["items"]] != [
        "fact",
        "code_safety",
        "pass",
        "pass",
    ]:
        raise ValueError("INVALID_SAMPLE_SCOPE")
    items, requests = [], {}
    for sample in samples["items"]:
        item, req = fixture(sample)
        items.append(item)
        requests[sample["probe_id"]] = {
            "model": "deepseek-flash",
            "input": [
                {"role": "system", "content": req["system"]},
                {"role": "user", "content": p.encoded(req["payload"]).decode()},
            ],
            "reasoning": {"effort": "none"},
            "temperature": 0,
            "max_output_tokens": 2048,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "focus",
                    "schema": req["schema"],
                }
            },
        }
    binding = {"path": ".env", "metadata": environment_version(root / ".env")}
    consent = {
        "purpose": "span-selection-redesign-v1 final round 2; four new diagnostic fixtures",
        "credential_binding": binding,
        "model": "deepseek-flash",
        "endpoint": "https://api.deepseek.com",
        "scope_sha256": sha(BASE_REL + "/scope.json"),
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
        "version": "fixed-final-focus-plan-v1",
        "execution_root": str(root.resolve()),
        "round": 2,
        "strategy_id": "span-selection-redesign-v1",
        "prompt_version": VERSION,
        "prior_root_sha256": p.digest(prior),
        "last_round": True,
        "expires_at": EXPIRES_AT,
        "overall_seconds": 3600,
        "target": target,
        "consent": consent,
        "credential_binding": binding,
        "scope_sha256": consent["scope_sha256"],
        "focus_items": items,
        "expected_by_probe": {x["probe_id"]: x["expected"] for x in samples["items"]},
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
        "failure_action": "Stop the current automatic generation/review troubleshooting route; retain catalog_only and T040 blocked. No third round or resetting strategy/track counters.",
        "success_action": "Only this diagnostic passes; formal T040 remains independently unverified and unauthorized.",
        "scope_is_diagnostic_only": True,
        "expected_consumption_estimate": None,
        "provider_requests_authorized": 0,
        "provider_cost_authorized": 0,
    }
    config = copy.deepcopy(next(iter(prior["targets"].values())))
    config.update(
        capability_sha256=p.digest(target),
        max_wire_bytes=max(len(p.encoded(v)) for v in requests.values()),
    )
    files = dict(prior["files"])
    names = [
        "scripts/prepare_t040_final_focus.py",
        "scripts/run_t040_final_focus.py",
        "scripts/acceptance_support/final_focus_contract.py",
        "backend/tests/test_final_focus.py",
        BASE_REL + "/samples.json",
        BASE_REL + "/scope.json",
        BASE_REL + "/token-cost-proof.json",
        PRIOR_REL + "/run.json",
        PRIOR_REL + "/run-approval.json",
        PRIOR_REL + "/results/r10-focus-02.json",
        PRIOR_REL + "/delegated-stop-focus-02.json",
    ]
    files.update({k: sha(k) for k in names})
    files.update(
        {
            BASE_REL + "/plan.json": p.digest(plan),
            BASE_REL + "/requests.json": p.digest(requests),
        }
    )
    run = {
        **copy.deepcopy(prior),
        "run_id": "span-focus-r11",
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
        "bounds": {**prior["bounds"], "cost_micro": sum(caps.values())},
    }
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
                "state": "AWAITING_EXACT_FINAL_RUN_APPROVAL",
                "root_sha256": p.digest(data["run.json"]),
                "requests": 4,
                "cost_micro_cny": data["plan.json"]["cost_cap_micro_cny"],
                "real_requests_authorized": 0,
                "last_round": True,
            }
        )
    )


if __name__ == "__main__":
    main()
