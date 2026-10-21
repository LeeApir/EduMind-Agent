"""Prepare executable r04 calibration; no key reads, human approvals or Provider sends."""

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
from acceptance_support.om_diagnostic import dump, hash_bytes, price, stable
from run_coverage_review import BASE, SLOTS

PLAN = "docs/acceptance/phase-1-coverage-r04"
PLAN_SHA = "1e2ae4e392c2e151f6ab9555206a2f9d11e4436db2d910e8d862b868ce3832ca"
EXTRA = (
    "scripts/run_coverage_review.py",
    "scripts/prepare_coverage_admission.py",
    "scripts/tests/test_coverage_admission.py",
    "docs/acceptance/phase-1-coverage-r04-admission/official-terms.json",
)


def build(root=ROOT):
    planbase = root / PLAN
    plan = json.loads((planbase / "proposal.json").read_text())
    if stable(plan) != PLAN_SHA:
        raise ValueError("HISTORICAL_PLAN_CHANGED")
    for name, sha in plan["artifacts"].items():
        if stable(json.loads((planbase / name).read_text())) != sha:
            raise ValueError("HISTORICAL_PLAN_CHANGED")
    sources = {name: hash_bytes((root / name).read_bytes()) for name in plan["sources"]}
    if sources != plan["sources"]:
        raise ValueError("IMPLEMENTATION_BASELINE_CHANGED")
    extra = set(EXTRA) | {
        str(p.relative_to(root)) for p in planbase.iterdir() if p.is_file()
    }
    sources.update(
        {name: hash_bytes((root / name).read_bytes()) for name in sorted(extra)}
    )
    data = json.loads((planbase / "cases.json").read_text())
    if tuple(data) != SLOTS:
        raise ValueError("SLOT_CHANGED")
    labels = deepcopy(json.loads((planbase / "proposed-labels.json").read_text()))
    labels["scope"] = (
        "Exact authored four-case calibration, not independent holdout or formal truth."
    )
    labels["case_digests"] = {name: stable(data[name]["material"]) for name in SLOTS}
    labels["human_signoff"] = "REQUIRED_SEPARATE_LABELS_HUMAN_RECORD"
    proof = json.loads((root / BASE / "official-terms.json").read_text())
    if (
        proof["model"] != "deepseek-flash"
        or proof["currency"] != "CNY"
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
        "version": "coverage-r04-admission-v1",
        "execution_root": str(root.resolve()),
        "prior_plan_sha256": PLAN_SHA,
        "sources": sources,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
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
            "One invocation sends at most one request. "
            "Exact human receipt continue before next."
        ),
        "stop": (
            "Any route/protocol/target/usage failure halts permanently; "
            "semantic uncertainty waits for human."
        ),
        "formal_t040": (
            "blocked; these four authored probes do not establish "
            "general quality or recall"
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
    lines = [
        "# r04 准入人工核对材料",
        "",
        "四例是按用户标准预制的小诊断；请核对实际正文与预期，不能把助手标签当人工签核。",
        "实际审核结果返回后仍须逐条核对，不自动继续。",
        "",
        f"执行根：`{stable(p)}`；最多4次，整窗保守上限8.768806元，输出总上限8192tokens。",
        "无重试/回退；首次失败停止；原r03余额/halt不继承。",
        "",
    ]
    for name, case in data.items():
        m = case["material"]
        expected = "pass" if name in SLOTS[:2] else "needs_human"
        lines += [
            f"## {name} → {expected}",
            "",
            f"材料摘要：`{stable(m)}`",
            "",
            "用户目标：" + m["plan"]["goal"],
            "",
            "计划目标：" + "；".join(o["text"] for o in m["plan"]["objectives"]),
            "",
        ]
        for c in m["candidates"]:
            v = c["envelope"]["content"]
            lines += ["### " + c["role"], ""]
            if c["role"] == "explanation":
                lines += [v["markdown"], ""]
            elif c["role"] == "code":
                lines += ["```c", v["source"], "```", "", v["expected_output"], ""]
                lines += ["- " + s for s in v["key_steps"]] + [""]
            else:
                for q in v["items"]:
                    lines += [
                        f"- {q['id']}：{q['question']}",
                        f"  答案：{q['answer']}；提交后解析：{q['explanation']}",
                        "",
                    ]
        lines += [
            "内部计划（不计交付）：",
            "```json",
            json.dumps(m["plan"]["shared_example"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values, base = build(), ROOT / BASE
    if args.write:
        if (base / "proposal.json").exists():
            raise SystemExit("Refuse overwriting a frozen execution proposal.")
        for name, value in values.items():
            dump(base / name, value)
        (base / "human-review.md").write_text(review_document(values))
    else:
        for name, value in values.items():
            if json.loads((base / name).read_text()) != value:
                raise SystemExit("FREEZE_CHANGED: " + name)
        if (base / "human-review.md").read_text() != review_document(values):
            raise SystemExit("HUMAN_REVIEW_CHANGED")
    print("coverage admission root=" + stable(values["proposal.json"]))


if __name__ == "__main__":
    main()
