"""Zero-call v4.5 rebuild: same student material, new prompt/policy binding."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import httpx
from acceptance_support.om_diagnostic import stable
from acceptance_support.phase1_budget import sha
from prepare_review_config_comparison import rebuild
from app.agents.hybrid_resource_review import INSTRUCTION, REVIEW_V4_PROMPT
from app.services.learning_policy import active_policy_digest
from run_evidence_v45 import BASE, REQUESTS, OUTPUT_LIMIT, SLOT_IDS

PRIOR = "docs/acceptance/phase-1-review-remaining-r01"
EXPECTED_CHANGES = {
    "backend/app/agents/hybrid_resource_review.py",
    "backend/app/services/learning_policy.py",
    "backend/tests/test_hybrid_review_scope.py",
    "backend/tests/test_learning_review_cases.py",
}
CRITERIA = {
    "reachable-safety:candidate": "reject severe/major code_safety for length3 a4; all additional claims must be supported, no deterministic UB return/outcome; every anchor must support its corresponding argument.",
    "fact-contradiction:candidate": "reject major/severe fact for return18 versus actual16; every main/secondary anchor must support the argument, no borrowing adjacent fields or accepting a15/F as numeric evidence.",
    "gap-and-safety:candidate": "retain serious code_safety reject despite teaching gap; every other claim/citation accurate, no UB numerical inference.",
    "trace-complete:candidate": "pass with all five checks and empty findings/unchecked/unresolved, no false positives.",
}


def read(p):
    return json.loads(p.read_text())


def review_document(data):
    lines = [
        "# v4.5四例：冻结学生材料与三项人工判据",
        "",
        "尚未绑定真实预算/标签批准；完整性、全部断言、全部引用任一失败即停。",
    ]
    for slot, c in data.items():
        lines += [
            "",
            "## " + slot,
            CRITERIA[slot],
            "原始目标：" + c["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(c["material"]),
            "```json",
            json.dumps(c["material"], ensure_ascii=False, indent=2),
            "```",
        ]
    return "\n".join(lines) + "\n"


async def materials(old):
    data = {}
    for slot in SLOT_IDS:
        previous = old[slot]
        name = slot.split(":")[0]
        c = await rebuild(name, previous, deepcopy(previous["input_snapshot"]))
        assert c["input_snapshot"] == previous["input_snapshot"]
        assert c["material"]["plan"] == previous["material"]["plan"]
        assert [x["envelope"] for x in c["material"]["candidates"]] == [
            x["envelope"] for x in previous["material"]["candidates"]
        ]
        assert [x["content_digest"] for x in c["material"]["candidates"]] == [
            x["content_digest"] for x in previous["material"]["candidates"]
        ]
        body = json.loads(bytes.fromhex(c["wire_hex"]))
        body["reasoning"] = {"effort": "low"}
        body["max_output_tokens"] = OUTPUT_LIMIT
        old_body = json.loads(bytes.fromhex(previous["wire_hex"]))
        assert body["text"] == old_body["text"] and body["model"] == old_body["model"]
        assert body["input"][0]["content"] == INSTRUCTION
        assert (
            body["temperature"] == old_body["temperature"] == 0.0
            and body["stream"] == old_body["stream"] is False
        )
        c.update(
            wire_hex=httpx.Request(
                "POST", "https://api.deepseek.com/responses", json=body
            ).content.hex(),
            arm="candidate",
            comparison_kind=previous["comparison_kind"],
            material_id=name,
        )
        data[slot] = c
    return data


def build(root=ROOT):
    prior = read(root / PRIOR / "proposal.json")
    old = read(root / PRIOR / "cases.json")
    if (
        stable(prior)
        != "7b7d495f9fd7d64ad0db40e5b03cc55c01ce804de61f82a99348691186b90d8f"
        or stable(old) != prior["cases_sha256"]
    ):
        raise ValueError("HISTORICAL_PACKAGE_CHANGED")
    sources = {n: sha((root / n).read_bytes()) for n in prior["sources"]}
    changed = {
        n: {"before": h, "after": sources[n]}
        for n, h in prior["sources"].items()
        if h != sources[n]
    }
    if set(changed) != EXPECTED_CHANGES:
        raise ValueError("UNEXPECTED_IMPLEMENTATION_CHANGE")
    data = asyncio.run(materials(old))
    slots = []
    rows = []
    for slot, c in data.items():
        raw = bytes.fromhex(c["wire_hex"])
        cost = 2 * (1048576 + len(raw)) + 8 * OUTPUT_LIMIT
        slots.append(
            {
                "id": slot,
                "wire_sha256": sha(raw),
                "wire_bytes": len(raw),
                "cost_micro_cny": cost,
            }
        )
        rows.append(
            {
                "id": slot,
                "expected_route": "pass"
                if c["comparison_kind"] == "positive"
                else "reject",
                "kind": c["comparison_kind"],
                "material_sha256": stable(c["material"]),
                "concrete_criterion": CRITERIA[slot],
                "human_all_assertions_and_citations_required": True,
            }
        )
    labels = {
        "status": "PROPOSED_NOT_HUMAN_SIGNED",
        "rows": rows,
        "basis": "Same authored student envelopes/goal/plan and original criteria, plus no tolerance for unsupported accompanying assertions/citations. New policy bindings not new ground truth.",
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
        "backend/app/agents/review_evidence.py",
        "backend/tests/test_review_evidence_v45.py",
        "docs/agents/review-evidence-v4.5.md",
        "docs/agents/prompts/evidence-resource-review-v4.5.txt",
        "docs/acceptance/phase-1-review-evidence-v45/validation.json",
        "scripts/run_evidence_v45.py",
        "scripts/prepare_evidence_v45.py",
        "scripts/tests/test_evidence_v45.py",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        PRIOR + "/proposal.json",
        PRIOR + "/cases.json",
        PRIOR + "/results/reachable-safety-03.json",
        PRIOR + "/results/fact-contradiction-02.json",
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
        "version": "evidence-v45-r01",
        "implementation_baseline": "fdce381",
        "execution_root": str(root.resolve()),
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "requests": REQUESTS,
        "output_token_limit": OUTPUT_LIMIT,
        "review_prompt_version": REVIEW_V4_PROMPT,
        "policy_digest": active_policy_digest(),
        "requests_authorized": 0,
        "fees_authorized": 0,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "sources": sources,
        "implementation_changes": changed,
        "slots": slots,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "credential_file_metadata": {
            k: getattr(meta, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "unchanged": [
            "student envelopes and content digests",
            "original goals and shared plans",
            "output schema/model/low/8192/temperature0/60s",
            "old evidence and halted ledgers",
        ],
        "changed": [
            "v4.5 generic prompt rules, shared policy digest and required identity/dependency bindings",
            "new independent4-slot approval/ledger/three-part human confirmation gate",
        ],
        "semantic_checks": CRITERIA,
        "stop_rule": "Any completeness/assertion/citation failure stops persistently, even with core defect detected. One send per step, prior receipt-bound real human three-part check before next, no retry/correction/fallback. Final four signoffs before T040 formal admission review; no formal requests authorized here.",
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
