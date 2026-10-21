"""Freeze one8192 experiment; request differs only in max_output_tokens."""

# ruff: noqa: E402
import argparse
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.om_diagnostic import stable
from acceptance_support.phase1_budget import sha
from run_distributed_budget import BASE, OUTPUT_LIMIT, SLOT_IDS

SLOT = SLOT_IDS[0]

PRIOR = "docs/acceptance/phase-1-distributed-diagnostic-r01"
PRIOR_ROOT = "ca6e41a624172ed6fc14b022ea72a862118977061c7a816a2a98aaea784c1012"


def read(path):
    return json.loads(path.read_text())


def review_document(data):
    case = data[SLOT]
    return "\n".join(
        [
            "# 单例预算验证：分散覆盖low，只调总输出上限至8192",
            "",
            "预算/标签尚未绑定批准。最多一次，成功或失败后都停止，不测试其他样本。",
            "判据保持：pass且无finding/unchecked/unresolved，无附带误报；具体语义需实际人工核对。",
            "目标：" + case["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(case["material"]),
            "本次wire摘要：" + sha(bytes.fromhex(case["wire_hex"])),
            "```json",
            json.dumps(case["material"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )


def build(root=ROOT):
    original = read(root / PRIOR / "proposal.json")
    cases = read(root / PRIOR / "cases.json")
    if stable(original) != PRIOR_ROOT or stable(cases) != original["cases_sha256"]:
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    sources = deepcopy(original["sources"])
    for name, expected in sources.items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError("V44_SOURCE_BASELINE_CHANGED")
    case = deepcopy(cases[SLOT])
    wire = bytes.fromhex(case["wire_hex"])
    old_slot = next(s for s in original["slots"] if s["id"] == SLOT)
    if sha(wire) != old_slot["wire_sha256"]:
        raise ValueError("HISTORICAL_WIRE_CHANGED")
    body = json.loads(wire)
    if (
        body["model"] != "deepseek-flash"
        or body["reasoning"] != {"effort": "low"}
        or body["max_output_tokens"] != 2048
    ):
        raise ValueError("ORIGINAL_CONFIGURATION_CHANGED")
    # Preserve the complete original case; only replace the outer output limit.
    old_wire = wire
    body["max_output_tokens"] = OUTPUT_LIMIT
    import httpx

    wire = httpx.Request(
        "POST", "https://api.deepseek.com/responses", json=body
    ).content
    restored = dict(body)
    restored["max_output_tokens"] = 2048
    if (
        httpx.Request(
            "POST", "https://api.deepseek.com/responses", json=restored
        ).content
        != old_wire
    ):
        raise ValueError("REQUEST_CHANGED_BEYOND_OUTPUT_LIMIT")
    case["wire_hex"] = wire.hex()
    data = {SLOT: case}
    labels = {
        "status": "ORIGINAL_DISTRIBUTED_PASS_CRITERION_PENDING_NEW_BINDING",
        "rows": [
            {
                "id": SLOT,
                "expected_route": "pass",
                "findings": [],
                "unchecked": [],
                "unresolved": [],
                "material_sha256": stable(case["material"]),
                "human_specific_evidence_required": True,
            }
        ],
        "scope": "Original authored distributed-coverage calibration only; not formal acceptance or old failure cause recovery.",
    }
    proof = read(root / BASE / "official-terms.json")
    if (
        proof["model"] != "deepseek-flash"
        or proof["currency"] != "CNY"
        or proof["context_input_ceiling"] != 1048576
        or proof["input_micro_cny_per_million"] != 2000000
        or proof["output_micro_cny_per_million"] != 8000000
        or proof["output_ceiling_per_request_including_reasoning"] != OUTPUT_LIMIT
        or proof.get("provider_documented_max_output") != "384K"
        or proof.get("experiment_limit_within_documented_support") is not True
    ):
        raise ValueError("TERMS_CHANGED_REDESIGN_REQUIRED")
    extra = [
        "scripts/run_distributed_budget.py",
        "scripts/acceptance_support/failure_observation.py",
        "scripts/prepare_distributed_budget.py",
        "scripts/tests/test_failure_observation.py",
        "scripts/tests/test_distributed_budget.py",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        PRIOR + "/results/distributed-low-01.json",
    ]
    sources.update({name: sha((root / name).read_bytes()) for name in extra})
    metadata = (root / ".env").lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.geteuid()
    ):
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    cost = 2 * (1048576 + len(wire)) + 8 * OUTPUT_LIMIT
    proposal = {
        "version": "distributed-output-budget-r01",
        "execution_root": str(root.resolve()),
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "requests": 1,
        "output_token_limit": OUTPUT_LIMIT,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "cost_micro_cny": cost,
        "sources": sources,
        "slots": [
            {
                "id": SLOT,
                "wire_sha256": sha(wire),
                "wire_bytes": len(wire),
                "cost_micro_cny": cost,
            }
        ],
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "credential_file_metadata": {
            k: getattr(metadata, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "historical_source": {
            "package": PRIOR,
            "proposal_sha256": PRIOR_ROOT,
            "slot": SLOT,
            "wire_sha256": sha(old_wire),
            "material_sha256": stable(case["material"]),
        },
        "unchanged": [
            "case except wire output limit",
            "request body except max_output_tokens",
            "v4.4 input",
            "Prompt",
            "JSON Schema",
            "low",
            "60-second timeout",
            "pass/no false findings criterion",
        ],
        "changes": [
            "max_output_tokens2048->8192 (including reasoning)",
            "independent run/approval/ledger with synchronized request/manifest/usage8192 bound",
            "separate completeness evidence and semantic review without changing verdict criterion",
        ],
        "completeness_checks": [
            "completed/no error/no incomplete details",
            "one assistant message/one text block",
            "strict JSON and unchanged schema",
            "model and exact wire binding",
            "usage within8192 total",
        ],
        "semantic_checks": [
            "local goal only; do not add other graph objectives",
            "visible code steps total2/7/16 and i3 exit plus process questions support the short explanation",
            "do not invent callsite fact, missing optional animation or other false findings",
            "expected pass with five check IDs and empty findings/unchecked/unresolved",
            "actual content/response independent human review; JSON completeness alone is not semantic pass",
        ],
        "stop_rule": "One reservation only; success exhausts budget, any failure persists halt. No retry/fallback/continuation or refund.",
    }
    return {
        "proposal.json": proposal,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = build()
    if args.write:
        rendered = {
            name: json.dumps(value, ensure_ascii=False, indent=2) + "\n"
            for name, value in result.items()
        }
        rendered["human-review.md"] = review_document(result["cases.json"])
        for name, content in rendered.items():
            path = ROOT / BASE / name
            if path.exists() and path.read_text() != content:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        for name, content in rendered.items():
            (ROOT / BASE / name).write_text(content)
    p = result["proposal.json"]
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "requests": 1,
                "output_token_limit": OUTPUT_LIMIT,
                "cost_micro_cny": p["cost_micro_cny"],
                "wire_sha256": p["slots"][0]["wire_sha256"],
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
