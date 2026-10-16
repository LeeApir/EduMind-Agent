"""Freeze one byte-identical historical low request, without reading any key."""

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
from run_distributed_diagnostic import BASE, SLOT

PRIOR = "docs/acceptance/phase-1-review-config-r01"
PRIOR_ROOT = "939497f3bc0b997254f0dd64e37342ce3780703db58a8649e55aa713c9edf819"


def read(path):
    return json.loads(path.read_text())


def review_document(data):
    case = data[SLOT]
    return "\n".join(
        [
            "# 单例诊断：分散覆盖low原请求",
            "",
            "预算/标签尚未绑定批准。最多一次，成功或失败后都停止，不测试其他样本。",
            "判据保持：pass且无finding/unchecked/unresolved，无附带误报；具体语义需实际人工核对。",
            "目标：" + case["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(case["material"]),
            "原wire摘要：" + sha(bytes.fromhex(case["wire_hex"])),
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
    data = {SLOT: case}  # No restaging, input projection or request regeneration.
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
        or proof["output_ceiling_per_request_including_reasoning"] != 2048
    ):
        raise ValueError("TERMS_CHANGED_REDESIGN_REQUIRED")
    extra = [
        "scripts/run_review_config_observed.py",
        "scripts/acceptance_support/failure_observation.py",
        "scripts/run_distributed_diagnostic.py",
        "scripts/prepare_distributed_diagnostic.py",
        "scripts/tests/test_failure_observation.py",
        "scripts/tests/test_distributed_diagnostic.py",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        PRIOR + "/results/trace-distributed-candidate-03-failure.json",
    ]
    sources.update({name: sha((root / name).read_bytes()) for name in extra})
    metadata = (root / ".env").lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.geteuid()
    ):
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    cost = 2 * (1048576 + len(wire)) + 8 * 2048
    proposal = {
        "version": "distributed-single-diagnostic-r01",
        "execution_root": str(root.resolve()),
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "requests": 1,
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
            "wire_sha256": sha(wire),
            "material_sha256": stable(case["material"]),
        },
        "unchanged": [
            "full case",
            "wire bytes",
            "v4.4 input",
            "Prompt",
            "JSON Schema",
            "low",
            "2048 total output",
            "pass/no false findings criterion",
        ],
        "changes": [
            "independent one-slot run identity/ledger/approval",
            "safe failure observation executor",
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
                "cost_micro_cny": p["cost_micro_cny"],
                "wire_sha256": p["slots"][0]["wire_sha256"],
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
