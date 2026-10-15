"""Freeze four new admission requests without reading a credential or granting approval."""

# ruff: noqa: E402
import argparse
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.om_diagnostic import (
    BASE,
    SLOTS,
    cases,
    dump,
    hash_bytes,
    price,
    stable,
)


def build(root=ROOT):
    # Metadata only: do not read/hash any credential bytes during zero-call preparation.
    env_path = root / ".env"
    st = env_path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.geteuid():
        raise ValueError("UNSAFE_CREDENTIAL_FILE")
    credential_metadata = {
        k: getattr(st, k)
        for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    }
    data = cases(root)
    labels = {
        "status": "PROPOSED_PENDING_USER_REVIEW_NOT_FORMAL_GROUND_TRUTH",
        "plan": "结构/跨字段/可信元数据绑定有效；实际教学内容仍需人工核对。",
        "correct-unit": "应自动pass；2+5+9=16，下标0..2，三题答案T/T/F；无害stddef.h不应被拒。",
        "reachable-safety": "必须具体检出a[4]超出a[3]的合法下标0..2；归类code_safety。函数被调用时无条件访问，不能泛泛reject代替检出。",
        "fact-contradiction": "必须具体检出解释写18与实际sum()返回16矛盾；归类fact。没有越界，不能归类内存安全。",
    }
    proof = {
        "checked_on": "2026-10-15",
        "model": "deepseek-flash",
        "documented_revision": "DeepSeek-V4.1-Flash",
        "immutable_weights_revision": "UNKNOWN",
        "currency": "CNY",
        "context_input_ceiling": 1048576,
        "input_bound": "1048576 + exact_wire_bytes (positive slack only; bytes are not Tokens)",
        "derivation": "Official 1M model window bounds all accepted text input including service formatting. Use max(1000000,2**20). Output reserve is separate, deliberately double conservative. No exact tokenizer or consumption prediction claimed.",
        "input_micro_cny_per_million": 2000000,
        "output_micro_cny_per_million": 8000000,
        "output_ceiling_per_request_including_reasoning": 2048,
        "discount_assumed": False,
        "expected_cost": None,
        "sources": [
            "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
            "https://api-docs.deepseek.com/quick_start/pricing/",
            "https://api-docs.deepseek.com/api/create-response/",
        ],
        "source_access": "2026-10-15 official English page and Responses direct open; Chinese official search excerpt (direct opens timed out). CNY prices not converted from USD.",
        "assumptions": [
            "Provider honors current window, prices and total-output cap.",
            "Only text JSON Responses; no tools, image, search or extra charges.",
            "Recheck official terms on execution day; changed or unverifiable terms stop.",
            "Application reservation is not a provider-account hard spend limit; a provider violation may exceed it and must halt.",
        ],
    }
    old = json.loads(
        (
            root / "docs/acceptance/phase-1-om-implementation/frozen-combination.json"
        ).read_text()
    )
    paths = [s["path"] for s in old["sources"]] + [
        "scripts/acceptance_support/phase1_budget.py",
        "scripts/run_deepseek_connection.py",
        "scripts/acceptance_support/connection_diagnostics.py",
        "scripts/run_phase1_provider_connection.py",
        "scripts/acceptance_support/om_diagnostic.py",
        "scripts/prepare_om_admission.py",
        "scripts/run_om_admission.py",
        "scripts/tests/test_om_admission.py",
        "docs/ADR/0011-dynamic-approval-20261008.json",
        "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json",
        "docs/acceptance/phase-1-om-implementation/frozen-combination.json",
    ]
    files = {p: hash_bytes((root / p).read_bytes()) for p in sorted(set(paths))}
    # Historical baseline remains frozen; this preparation cannot quietly rebaseline it.
    for s in old["sources"]:
        if files[s["path"]] != s["sha256"]:
            raise ValueError("IMPLEMENTATION_BASELINE_CHANGED")
    bound = sum(price(len(bytes.fromhex(c["wire_hex"]))) for c in data.values())
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
        "version": "om-admission-r01-v1",
        "execution_root": str(root.resolve()),
        "implementation_root": old["root_sha256"],
        "sources": files,
        "cases_sha256": stable(data),
        "labels_sha256": stable(labels),
        "proof_sha256": stable(proof),
        "target": {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash",
            "transport": "responses_json_schema",
            "reasoning": "none",
            "temperature": "0.0",
            "credential_reference": ".env:EDUMIND_PROVIDER_API_KEY",
        },
        "credential_file_metadata": credential_metadata,
        "slots": slots,
        "requests": 4,
        "cost_micro_cny": bound,
        "total_output_tokens_including_reasoning": 8192,
        "timeout_seconds": 60,
        "retries": 0,
        "fallback": False,
        "expiry_local": "2026-10-18T23:59:59+08:00",
        "status": "PREPARED_NOT_AUTHORIZED",
        "requests_authorized": 0,
        "fees_authorized": 0,
        "scope": "Four separate fixed-input admission probes, NOT eight-category diagnosis, generation publication or T040 formal acceptance.",
        "advance": "One request per invocation; prior exact receipt requires independent human continue. Never automatically escalates to eight-category or formal runs.",
        "stop": [
            "Any protocol, target, budget, auth, rate, timeout or uncertain usage failure.",
            "Concrete serious error missed; unsupported serious accusation; control not automatically pass.",
            "Human refuses continuation; replay/interrupted send not resumed or refunded.",
        ],
        "formal_envelope_separate": {
            "status": "NOT_EXECUTABLE_NOT_AUTHORIZED",
            "requests": 2360,
            "wire_byte_limit_per_call_proposed": 131072,
            "max_output_tokens_per_call": 4096,
            "cost_ceiling_micro_cny": 2360 * price(131072, 4096),
            "note": "Exact conservative contract envelope, not expected cost. 2360 includes prior eight-category diagnostic envelope; four admission requests are additional and never formal denominator. Must enforce this wire cap and freeze actual derived slots before formal execution.",
        },
        "remaining_formal_gates": [
            "all eight diagnosis categories with independent inputs and labels",
            "100/20/20/10 independent human scopes/ground truth",
            "trusted derived runner and exact graph/model/wire configuration",
            "new exact formal budget and explicit paid-run approval",
            "generation outputs independently fact-checked",
        ],
    }
    return {
        "proposal.json": proposal,
        "cases.json": data,
        "proposed-labels.json": labels,
        "token-cost-proof.json": proof,
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    values = build()
    base = ROOT / BASE
    if args.check:
        if any(json.loads((base / k).read_text()) != v for k, v in values.items()):
            raise SystemExit("FREEZE_CHANGED")
    else:
        base.mkdir(parents=True, exist_ok=True)
        if any((base / k).exists() for k in values):
            raise SystemExit("FREEZE_ALREADY_EXISTS")
        for k, v in values.items():
            dump(base / k, v)
    p = values["proposal.json"]
    print(
        json.dumps(
            {
                "root_sha256": stable(p),
                "requests_proposed": p["requests"],
                "cost_cap_micro_cny": p["cost_micro_cny"],
                "provider_requests": 0,
                "authorized_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
