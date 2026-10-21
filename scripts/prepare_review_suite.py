"""Freeze ordered unchanged v4.4 cases at low8192 without Provider access."""

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
import httpx
from acceptance_support.om_diagnostic import stable
from acceptance_support.phase1_budget import sha
from run_review_suite import BASE, OUTPUT_LIMIT, REQUESTS, SLOT_IDS

PRIOR = "docs/acceptance/phase-1-review-config-r01"
PRIOR_ROOT = "939497f3bc0b997254f0dd64e37342ce3780703db58a8649e55aa713c9edf819"
CRITERIA = {
    "plan-only-gap:candidate": "needs_human; concretely identify missing student-visible loop states and exit support (internal plan does not count); no findings, including invented callsite fact.",
    "assessment-gap:candidate": "needs_human; teaching states/exit exist, but questions test arithmetic/index/return rather than execution process; concrete measurement gap, no findings.",
    "fact-contradiction:candidate": "reject; major/severe fact anchored to claim sum returns18 versus actual16; not merely a generic label.",
    "reachable-safety:candidate": "reject; major/severe code_safety anchored to reachable return a[4] with a[3] length, legal indices0..2; do not execute unsafe code.",
    "gap-and-safety:candidate": "reject retaining major/severe code_safety for a[4] despite real teaching/measurement gaps; acknowledge gaps in semantic review without downgrading severe issue.",
    "trace-complete:candidate": "pass, five checks covered and no findings/unchecked/unresolved; no invented callsite or animation requirements.",
    "trace-distributed:candidate": "pass, five checks covered and no findings/unchecked/unresolved; student-visible code key_steps and process questions satisfy distributed coverage.",
}


def read(path):
    return json.loads(path.read_text())


def review_document(data):
    lines = [
        "# 有序小型审核：原材料与预登记判据",
        "",
        "零调用提案；尚未绑定本包预算/标签批准，非正式验收。",
    ]
    for slot, case in data.items():
        lines += [
            "",
            "## " + slot,
            CRITERIA[slot],
            "原始目标：" + case["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(case["material"]),
            "```json",
            json.dumps(case["material"], ensure_ascii=False, indent=2),
            "```",
        ]
    return "\n".join(lines) + "\n"


def build(root=ROOT):
    original = read(root / PRIOR / "proposal.json")
    old = read(root / PRIOR / "cases.json")
    if stable(original) != PRIOR_ROOT or stable(old) != original["cases_sha256"]:
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    sources = deepcopy(original["sources"])
    for name, expected in sources.items():
        if sha((root / name).read_bytes()) != expected:
            raise ValueError("V44_SOURCE_BASELINE_CHANGED")
    data, slots, rows = {}, [], []
    for slot in SLOT_IDS:
        case = deepcopy(old[slot])
        wire = bytes.fromhex(case["wire_hex"])
        prior_slot = next(s for s in original["slots"] if s["id"] == slot)
        if sha(wire) != prior_slot["wire_sha256"]:
            raise ValueError("HISTORICAL_WIRE_CHANGED")
        body = json.loads(wire)
        if (
            body["model"] != "deepseek-flash"
            or body["reasoning"] != {"effort": "low"}
            or body["max_output_tokens"] != 2048
        ):
            raise ValueError("ORIGINAL_CONFIGURATION_CHANGED")
        body["max_output_tokens"] = OUTPUT_LIMIT
        actual = httpx.Request(
            "POST", "https://api.deepseek.com/responses", json=body
        ).content
        body["max_output_tokens"] = 2048
        if (
            httpx.Request(
                "POST", "https://api.deepseek.com/responses", json=body
            ).content
            != wire
        ):
            raise ValueError("REQUEST_CHANGED_BEYOND_OUTPUT_LIMIT")
        case["wire_hex"] = actual.hex()
        data[slot] = case
        cost = 2 * (1048576 + len(actual)) + 8 * OUTPUT_LIMIT
        slots.append(
            {
                "id": slot,
                "wire_sha256": sha(actual),
                "wire_bytes": len(actual),
                "cost_micro_cny": cost,
            }
        )
        kind = case["comparison_kind"]
        rows.append(
            {
                "id": slot,
                "kind": kind,
                "expected_route": "pass"
                if kind == "positive"
                else "needs_human"
                if kind == "pure_gap"
                else "reject",
                "material_sha256": stable(case["material"]),
                "specific_evidence": CRITERIA[slot],
                "human_specific_evidence_required": True,
            }
        )
    labels = {
        "status": "PROPOSED_NOT_HUMAN_SIGNED",
        "rows": rows,
        "basis": "Original seven authored materials and criteria unchanged; low arm only, output limit8192. Not independent holdouts.",
    }
    proof = read(root / BASE / "official-terms.json")
    if (
        proof["model"],
        proof["currency"],
        proof["context_input_ceiling"],
        proof["input_micro_cny_per_million"],
        proof["output_micro_cny_per_million"],
        proof["output_ceiling_per_request_including_reasoning"],
    ) != ("deepseek-flash", "CNY", 1048576, 2000000, 8000000, OUTPUT_LIMIT):
        raise ValueError("TERMS_CHANGED_REDESIGN_REQUIRED")
    extra = [
        "scripts/run_review_suite.py",
        "scripts/prepare_review_suite.py",
        "scripts/tests/test_review_suite.py",
        "scripts/acceptance_support/failure_observation.py",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        "docs/acceptance/phase-1-distributed-budget-r01/results/distributed-low8192-01.json",
    ]
    sources.update({name: sha((root / name).read_bytes()) for name in extra})
    metadata = (root / ".env").lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.geteuid()
    ):
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    proposal = {
        "version": "ordered-review-suite-r01",
        "execution_root": str(root.resolve()),
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "requests": REQUESTS,
        "output_token_limit": OUTPUT_LIMIT,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "sources": sources,
        "slots": slots,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "credential_file_metadata": {
            k: getattr(metadata, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "historical_source": {"package": PRIOR, "proposal_sha256": PRIOR_ROOT},
        "unchanged": [
            "case material/anchors/input snapshot",
            "HTTP body except max_output_tokens2048->8192",
            "v4.4 input/Prompt/Schema/low/rubric/60s",
            "production defaults and all old runs",
        ],
        "stop_rule": "One send per step; inspect completeness and concrete semantics. Prior receipt-bound real human continue required before next slot. Any technical/structural/semantic failure stops; no retry/fallback/correction. After seventh stop; no formal T040 pass.",
        "semantic_checks": CRITERIA,
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
                "requests": REQUESTS,
                "cost_micro_cny": p["cost_micro_cny"],
                "authorized": False,
                "slots": p["slots"],
            }
        )
    )


if __name__ == "__main__":
    main()
