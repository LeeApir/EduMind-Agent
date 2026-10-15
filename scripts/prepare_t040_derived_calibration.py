"""Build/check an explicitly non-executable two-history calibration draft. No env/network."""

import argparse
import hashlib
import json
from pathlib import Path

from acceptance_support.claim_review_prototype import digest, encoded, freeze
from acceptance_support.derived_review_contracts import contracts

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = (
    ROOT / "docs/acceptance/phase-1-t040-derived-calibration-draft/proposal.json"
)
CASE_IDS = ("queue:explanation:1", "correct-list-concept")
MAX_RESULT = 65536
MAX_WIRE = 1048576


def wire_bound(case, stage, contract):
    """Upper bound on complete wire, for these fixed roots and accepted bounded parents.

    Canonical JSON bytes already escape controls. Putting that JSON into a JSON string
    adds at most one byte per original byte (quote/backslash), so factor two suffices.
    The final inventory contains up to two accepted inner objects (inventory/coverage),
    plus 16 added server claim IDs and fixed frozen-version/object punctuation. A claim
    request may repeat the entire largest claim as focus: bound it by whole inventory.
    """
    snap = freeze(case["resource_type"], case["content"], case["reference_context"])
    base = {
        "candidate": snap.data,
        "blocks": snap.blocks,
        "identity": {k: "f" * 64 for k in snap.identity},
        "request_binding": {
            "root_sha256": "f" * 64,
            "slot": "s" * 160,
            "parents_sha256": "f" * 64,
        },
    }
    # Extra 4096 includes frozen version, object/list punctuation and 16 claim IDs.
    inv_bound = 2 * MAX_RESULT + 4096
    payload = len(encoded(base))
    if stage != "inventory":
        payload += (
            len(encoded("inventory"))
            + 2
            + (MAX_RESULT if stage == "coverage" else inv_bound)
        )
    if stage == "claim":
        payload += len(encoded("focus")) + 2 + inv_bound
    if stage in ("claim", "overall"):
        identity = {
            k: "f" * 64 for k in (*snap.identity, "inventory_sha256", "claim_id")
        }
        payload += len(encoded("review_identity")) + 2 + len(encoded(identity))
    envelope = {
        "model": "deepseek-flash",
        "input": [
            {"role": "system", "content": contract["system"]},
            {"role": "user", "content": ""},
        ],
        "reasoning": {"effort": "low"},
        "temperature": 0,
        "max_output_tokens": 8192,
        "text": {
            "format": {
                "type": "json_schema",
                "name": stage,
                "schema": contract["schema"],
            }
        },
    }
    return len(encoded(envelope)) + 2 * payload


def build(root=ROOT):
    history_path = root / "docs/acceptance/phase-1-dynamic-v1/history.json"
    history = json.loads(history_path.read_text())
    cases = []
    cs = contracts()
    for case_id in CASE_IDS:
        original = next(c for c in history["cases"] if c["id"] == case_id)
        payload = original["payload"]
        assert digest(payload) == original["payload_sha256"]
        bounds = {
            s: wire_bound(payload, s, cs[s])
            for s in ("inventory", "coverage", "claim", "overall")
        }
        assert max(bounds.values()) <= MAX_WIRE
        cases.append(
            {
                "historical_case_id": case_id,
                "payload": payload,
                "payload_sha256": digest(payload),
                "original_label_sha256": digest(original),
                "wire_byte_upper_bounds": bounds,
                "potential_requests": 19,
            }
        )
    files = [
        "scripts/prepare_t040_derived_calibration.py",
        "scripts/acceptance_support/derived_review_contracts.py",
        "scripts/acceptance_support/derived_responses_sender.py",
        "scripts/acceptance_support/derived_diagnostic_budget.py",
        "scripts/acceptance_support/claim_review_prototype.py",
        "scripts/acceptance_support/phase1_budget.py",
        "backend/app/core/provider_target.py",
        "backend/app/services/deepseek_responses.py",
        "backend/app/services/provider_protocol.py",
        "backend/app/services/provider_gateway.py",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "docs/acceptance/phase-1-dynamic-v1/history.json",
    ]
    return {
        "version": "derived-calibration-draft-v1",
        "state": "DRAFT_NOT_EXECUTABLE",
        "scope": "Two historical calibration resources only; no full diagnostic/formal/DSL/T041",
        "provider_requests_authorized": 0,
        "provider_cost_micro_authorized": 0,
        "model": "deepseek-flash",
        "documented_revision": "DeepSeek-V4.1-Flash",
        "runtime_weights_revision": "unknown",
        "base_url": "https://api.deepseek.com",
        "reasoning": "low",
        "temperature": 0,
        "temperature_effect": "ignored in thinking mode",
        "max_claims": 16,
        "corrections": 0,
        "potential_request_upper_bound": 38,
        "max_output_tokens_including_reasoning": 8192,
        "max_result_bytes": MAX_RESULT,
        "max_wire_bytes": MAX_WIRE,
        "timeout_seconds_per_attempt": 120,
        "max_active_requests": 1,
        "retries": 0,
        "fallbacks": 0,
        "stage_contracts": cs,
        "cases": cases,
        "pricing_observation": {
            "checked_on": "2026-10-15",
            "currency": "CNY",
            "peak_uncached_input_per_million": 2,
            "peak_output_per_million": 8,
            "source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
            "is_billing_or_future_price_guarantee": False,
        },
        "token_bound_proof": {
            "status": "MISSING",
            "source": "https://api-docs.deepseek.com/zh-cn/quick_start/token_usage/",
            "reason": "Official ratios and offline demo do not establish a bound for this Responses serialization and current model.",
        },
        "cost_cap_micro_cny": None,
        "execution_prerequisites_missing": [
            "Proven input-token bound including server formatting for this transport/model.",
            "Cost upper bound and frozen expiry computed from that proof; human exact run approval.",
            "Trusted real run-approval parser and current server credential/consent version lease.",
            "Independent concrete defect/category and correct-control assessment plus human gate.",
        ],
        "facts_to_check": "Original queue label requires both defects and categories; correct control must not be falsely rejected. Labels are not sent to model.",
        "failure_policy": "Protocol/coverage/usage/budget/safety failure stops immediately; semantic miss stops after factual assessment; no auto next case/group.",
        "production_mode": "catalog_only",
        "real_requests_sent": 0,
        "files": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in files
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    proposal = build()
    if args.check:
        assert json.loads(DESTINATION.read_text()) == proposal, "Draft/source changed"
        print(
            "PASS: draft bytes/bounds/sources match; NOT EXECUTABLE; real authorization=0"
        )
    else:
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION.write_text(
            json.dumps(proposal, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            "Wrote non-executable draft; 38 potential requests, token/cost proof still missing."
        )


if __name__ == "__main__":
    main()
