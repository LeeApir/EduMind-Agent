"""Freeze the user's five remaining diagnostics with byte-identical existing wires."""

# ruff: noqa: E402
import argparse
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.om_diagnostic import stable
from acceptance_support.phase1_budget import sha
from app.agents.hybrid_resource_review import INSTRUCTION, review_output_schema
from run_review_remaining import BASE, SLOT_IDS, REQUESTS, OUTPUT_LIMIT

PRIOR = "docs/acceptance/phase-1-review-suite-r01"
PRIOR_ROOT = "d932bb269cd4a9aaa6038d2c50cc6f4b9fa395516784d08bb46f9862921958f3"
CRITERIA = {
    "assessment-gap:candidate": "needs_human; explicitly distinguish already taught states/exit from missing process assessment; no findings or invented facts.",
    "fact-contradiction:candidate": "reject; major/severe fact concretely identifies explanation return18 versus actual loop sum16.",
    "reachable-safety:candidate": "reject; major/severe code_safety concretely identifies reachable return a[4] from length3 array (legal0..2).",
    "gap-and-safety:candidate": "reject; retain major/severe a[4] code_safety even with real teaching/measurement gap, never downgrade all to human.",
    "trace-complete:candidate": "pass with five required checks and no findings/unchecked/unresolved or attached false positives.",
}


def read(p):
    return json.loads(p.read_text())


def review_document(data):
    lines = [
        "# 其余五类：实际材料与冻结判据",
        "",
        "零调用提案，未绑定真实预算/标签批准，不预签模型结果。",
    ]
    for slot, c in data.items():
        lines += [
            "",
            "## " + slot,
            CRITERIA[slot],
            "原始目标：" + c["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(c["material"]),
            "wire摘要：" + sha(bytes.fromhex(c["wire_hex"])),
            "```json",
            json.dumps(c["material"], ensure_ascii=False, indent=2),
            "```",
        ]
    return "\n".join(lines) + "\n"


def build(root=ROOT):
    original = read(root / PRIOR / "proposal.json")
    old = read(root / PRIOR / "cases.json")
    if stable(original) != PRIOR_ROOT or stable(old) != original["cases_sha256"]:
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    sources = deepcopy(original["sources"])
    for name, h in sources.items():
        if sha((root / name).read_bytes()) != h:
            raise ValueError("V44_SOURCE_BASELINE_CHANGED")
    data = {}
    slots = []
    rows = []
    for slot in SLOT_IDS:
        case = deepcopy(old[slot])
        wire = bytes.fromhex(case["wire_hex"])
        body = json.loads(wire)
        prior = next(s for s in original["slots"] if s["id"] == slot)
        if (
            sha(wire) != prior["wire_sha256"]
            or body["max_output_tokens"] != OUTPUT_LIMIT
            or body["reasoning"] != {"effort": "low"}
            or body["model"] != "deepseek-flash"
        ):
            raise ValueError("ORIGINAL_REQUEST_CHANGED")
        schema = body["text"]["format"]["schema"]
        if body["input"][0] != {
            "role": "system",
            "content": INSTRUCTION,
        } or schema != review_output_schema(
            "unit", anchor_ids=[a["anchor_id"] for a in case["anchors"]]
        ):
            raise ValueError("CONTRACT_CHANGED")
        if (
            schema["additionalProperties"] is not False
            or schema["properties"]["unresolved"]["items"]["type"] != "string"
        ):
            raise ValueError("CONTRACT_CHANGED")
        cost = 2 * (1048576 + len(wire)) + 8 * OUTPUT_LIMIT
        if prior["cost_micro_cny"] != cost:
            raise ValueError("BUDGET_CHANGED")
        data[slot] = case
        slots.append(deepcopy(prior))
        rows.append(
            {
                "id": slot,
                "kind": case["comparison_kind"],
                "expected_route": "pass"
                if case["comparison_kind"] == "positive"
                else "needs_human"
                if case["comparison_kind"] == "pure_gap"
                else "reject",
                "material_sha256": stable(case["material"]),
                "specific_evidence": CRITERIA[slot],
                "human_specific_evidence_required": True,
            }
        )
    labels = {
        "status": "PROPOSED_NOT_HUMAN_SIGNED",
        "rows": rows,
        "basis": "Same five authored materials and criteria. No plan-gap/distributed rerun; historical positive references not new result signoff.",
    }
    proof = read(root / BASE / "official-terms.json")
    if (
        proof["model"],
        proof["currency"],
        proof["context_input_ceiling"],
        proof["input_micro_cny_per_million"],
        proof["output_micro_cny_per_million"],
        proof["output_ceiling_per_request_including_reasoning"],
    ) != ("deepseek-flash", "CNY", 1048576, 2000000, 8000000, 8192):
        raise ValueError("TERMS_CHANGED_REDESIGN_REQUIRED")
    extra = [
        "scripts/run_review_remaining.py",
        "scripts/prepare_review_remaining.py",
        "scripts/tests/test_review_remaining.py",
        "scripts/acceptance_support/schema_failure_observation.py",
        "scripts/tests/test_schema_failure_observation.py",
        "docs/acceptance/phase-1-plan-gap-contract-audit/audit.json",
        "docs/acceptance/phase-1-plan-gap-location-r01/results/plan-only-gap-01.json",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
    ]
    sources.update({n: sha((root / n).read_bytes()) for n in extra})
    meta = (root / ".env").lstat()
    if (
        not stat.S_ISREG(meta.st_mode)
        or meta.st_mode & 0o077
        or meta.st_uid != os.geteuid()
    ):
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    p = {
        "version": "review-remaining-r01",
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
            k: getattr(meta, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "historical_source": {"package": PRIOR, "proposal_sha256": PRIOR_ROOT},
        "unchanged": [
            "entire selected five cases and exact HTTP wires",
            "Prompt/Schema/input/student materials/anchors",
            "model/low/8192/temperature0/60s/criteria",
            "production defaults and all old stopped runs",
        ],
        "changes": [
            "independent5-slot approval/ledger/executor",
            "safe schema-location diagnosis",
        ],
        "semantic_checks": CRITERIA,
        "stop_rule": "One send per step; concrete semantic evidence plus receipt-bound real human continue before next. Technical/structural/semantic mismatch stops. No retry/correction/fallback/extra probe. Stop after fifth, no formal T040 pass.",
    }
    return {
        "proposal.json": p,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values = build()
    if args.write:
        rendered = {
            k: json.dumps(v, ensure_ascii=False, indent=2) + "\n"
            for k, v in values.items()
        }
        rendered["human-review.md"] = review_document(values["cases.json"])
        for n, s in rendered.items():
            path = ROOT / BASE / n
            if path.exists() and path.read_text() != s:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        for n, s in rendered.items():
            (ROOT / BASE / n).write_text(s)
    p = values["proposal.json"]
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "requests": REQUESTS,
                "cost_micro_cny": p["cost_micro_cny"],
                "slots": p["slots"],
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
