"""Freeze a new v4.4 four-control run; read metadata only, never credentials or network."""

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
from acceptance_support.coverage_v44 import PRIOR, PRIOR_SHA, SLOTS, cases, original
from acceptance_support.om_diagnostic import dump, hash_bytes, price, stable
from prepare_coverage_admission import review_document as old_document
from run_coverage_v44 import BASE

ALLOWED_CHANGES = {
    "backend/app/agents/hybrid_resource_review.py",
    "backend/app/agents/planned_scene_generation.py",
    "backend/app/agents/unit_consistency_review.py",
    "backend/app/services/learning_policy.py",
    "backend/app/services/planned_learning_flow.py",
    "backend/tests/om_fixtures.py",
    "backend/tests/test_hybrid_learning_publication.py",
    "backend/tests/test_hybrid_resource_review.py",
    "backend/tests/test_hybrid_review_scope.py",
    "backend/tests/test_learning_review_cases.py",
    "backend/tests/test_planned_scene_generation.py",
    "backend/tests/test_review_delivery.py",
    "backend/tests/test_unit_consistency_review.py",
    "scripts/tests/test_coverage_review.py",
    "scripts/tests/test_om_admission_r02.py",
    "scripts/tests/test_om_admission_r03.py",
    "scripts/tests/test_coverage_admission.py",
}
EXTRA = (
    "backend/app/agents/review_input.py",
    "backend/tests/test_review_input.py",
    "docs/agents/review-input-v4.4.md",
    "scripts/acceptance_support/coverage_v44.py",
    "scripts/prepare_coverage_v44.py",
    "scripts/run_coverage_v44.py",
    "scripts/tests/test_coverage_v44.py",
    BASE + "/official-terms.json",
)


def build(root=ROOT):
    prior, _ = original(root)
    sources = {
        name: hash_bytes((root / name).read_bytes()) for name in prior["sources"]
    }
    changed = {
        name: {"before": sha, "after": sources[name]}
        for name, sha in prior["sources"].items()
        if sha != sources[name]
    }
    if set(changed) != ALLOWED_CHANGES:
        raise ValueError("UNEXPECTED_IMPLEMENTATION_CHANGE")
    extra = set(EXTRA)
    extra |= {
        str(p.relative_to(root)) for p in (root / PRIOR).rglob("*") if p.is_file()
    }
    extra |= {
        str(p.relative_to(root))
        for p in (root / "docs/acceptance/phase-1-review-input-v1").iterdir()
        if p.is_file()
    }
    sources.update(
        {name: hash_bytes((root / name).read_bytes()) for name in sorted(extra)}
    )
    data = cases(root)
    labels = deepcopy(json.loads((root / PRIOR / "proposed-labels.json").read_text()))
    labels["case_digests"] = {name: stable(data[name]["material"]) for name in SLOTS}
    labels["status"] = "SAME_CRITERIA_USER_RECONFIRMED_PENDING_NEW_RUN_BINDING"
    labels["basis"] = (
        "Current user explicitly retains pass/pass/needs_human/needs_human, "
    )
    labels["basis"] += (
        "r04 student envelopes are exactly equal; this is not new formal ground truth."
    )
    proof = json.loads((root / BASE / "official-terms.json").read_text())
    if (
        proof["currency"] != "CNY"
        or proof["model"] != "deepseek-flash"
        or proof["input_micro_cny_per_million"] != 2000000
        or proof["output_micro_cny_per_million"] != 8000000
        or proof["context_input_ceiling"] != 1048576
        or proof["output_ceiling_per_request_including_reasoning"] != 2048
    ):
        raise ValueError("TERMS_CHANGED_REDESIGN_REQUIRED")
    st = (root / ".env").lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    slots = [
        {
            "id": name,
            "wire_sha256": hash_bytes(bytes.fromhex(data[name]["wire_hex"])),
            "wire_bytes": len(bytes.fromhex(data[name]["wire_hex"])),
            "cost_micro_cny": price(len(bytes.fromhex(data[name]["wire_hex"]))),
        }
        for name in SLOTS
    ]
    proposal = {
        "version": "coverage-v44-r05-v1",
        "implementation_baseline": "4d66a7d",
        "execution_root": str(root.resolve()),
        "prior_proposal_sha256": PRIOR_SHA,
        "sources": sources,
        "implementation_changes": changed,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "input_snapshot_adapter": (
            "r04-flat-to-bound-metadata-v1; verbatim original request goal, not plan"
        ),
        "credential_file_metadata": {
            k: getattr(st, k)
            for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        },
        "target": {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash",
            "transport": "responses_json_schema",
            "reasoning": "none",
            "temperature": 0,
            "credential_reference": ".env:EDUMIND_PROVIDER_API_KEY",
        },
        "slots": slots,
        "requests": 4,
        "cost_micro_cny": sum(s["cost_micro_cny"] for s in slots),
        "total_output_tokens_including_reasoning": 8192,
        "timeout_seconds": 60,
        "retries": 0,
        "fallback": False,
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "status": "PREPARED_NOT_AUTHORIZED",
        "requests_authorized": 0,
        "fees_authorized": 0,
        "advance": (
            "One exact request, first trace-complete; "
            "independent actual receipt review before next."
        ),
        "stop": (
            "Any route/protocol/target/usage failure stops "
            "permanently; no retry or refund reuse."
        ),
        "semantic_gate": (
            "Specific correct gap and location require human "
            "verification; generic needs_human is not detection."
        ),
        "following_gates": [
            "all four actual results independently confirmed",
            "separate fact/safety and other diagnosis, separately frozen and approved",
            "formal quality admission only after diagnosis; separate full budget/ground truth",
        ],
        "formal_t040": (
            "blocked; four authored controls are not general "
            "efficacy, recall or formal success"
        ),
        "prior_run": (
            "r04 remains stopped after one failure; no "
            "approval, unused slots or ledger inherited"
        ),
    }
    return {
        "proposal.json": proposal,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def review_document(values):
    p, data = values["proposal.json"], values["cases.json"]
    text = old_document(values)
    text = text[text.index("## trace-complete") :].replace(
        "用户目标：", "计划goal（保持原文）："
    )
    header = [
        "# v4.4 / r05 四对照与准确预算",
        "",
        f"执行根：`{stable(p)}`。",
        "",
        f"最多4次，整窗保守上限{p['cost_micro_cny'] / 1000000:.6f}元；总输出8192tokens。",
        "无重试/回退，首败停止。每条真实结果需独立核对后才继续，不能只看路由相同。",
        "四组学生envelope、内容digest及完整计划与r04完全相同；只换输入契约和必要版本/身份绑定。",
        "原始目标从旧冻结input_snapshot.goal原文包装到metadata.goal，不从计划推测。",
        "",
    ]
    for name, c in data.items():
        header += [
            f"- {name} 原始请求：{c['input_snapshot']['metadata']['goal']}",
            f"  原快照摘要：`{c['original_input_digest']}`；"
            f"新绑定：`{c['material']['binding']['input_digest']}`。",
        ]
    header += [
        "",
        "判据保持pass/pass/needs_human/needs_human，后两例必须具体说明真实缺口及位置，不虚构事实错误。",
        "本包只含四覆盖对照；四例通过且人工核对后，另做事实/安全等诊断，再进入正式验收。",
        "",
        text,
    ]
    return "\n".join(header)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values, base = build(), ROOT / BASE
    if args.write:
        if (base / "proposal.json").exists():
            raise SystemExit("Refuse overwriting a frozen proposal.")
        for name, value in values.items():
            dump(base / name, value)
        (base / "human-review.md").write_text(review_document(values))
    else:
        for name, value in values.items():
            if json.loads((base / name).read_text()) != value:
                raise SystemExit("FREEZE_CHANGED: " + name)
        if (base / "human-review.md").read_text() != review_document(values):
            raise SystemExit("HUMAN_REVIEW_CHANGED")
    print("v4.4 r05 root=" + stable(values["proposal.json"]))


if __name__ == "__main__":
    main()
