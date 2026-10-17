"""Freeze remaining 11 repaired requests after actual first-result human confirmation."""

# ruff: noqa: E402
import argparse
import json
import stat
import sys
from copy import deepcopy
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_qwen_review as old
from app.services.qwen_schema import qwen_wire_schema, QWEN_SCHEMA_PROFILE
from acceptance_support.qwen_review_budget import sha
from run_qwen_continuation import BASE, PRIVATE, human_valid


def rendered(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def build(root=ROOT):
    previous = old.read(
        root / "docs/acceptance/phase-1-qwen-compatibility-r01/proposal.json"
    )
    sources = dict(previous["sources"])
    for name, digest in sources.items():
        assert sha((root / name).read_bytes()) == digest
    receipt_path = (
        "docs/acceptance/phase-1-qwen-compatibility-r01/results/compatibility-01.json"
    )
    human_path = "docs/acceptance/phase-1-qwen-compatibility-r01/results/compatibility-01-human.json"
    receipt = old.read(root / receipt_path)
    human = old.read(root / human_path)
    human_valid(human, old.stable(receipt), receipt["proposal_sha256"])
    cases = old.read(root / old.DESIGN / "cases.json")
    requests = {}
    slots = []
    for index, (name, case) in enumerate(list(cases.items())[1:]):
        original = json.loads(bytes.fromhex(case["candidate_wire_hex"]))
        body = deepcopy(original)
        full = body["response_format"]["json_schema"]["schema"]
        body["response_format"]["json_schema"]["schema"] = qwen_wire_schema(full)
        wire = httpx.Request(
            "POST", "https://example.com/chat/completions", json=body
        ).content
        requests[name] = {
            "wire_hex": wire.hex(),
            "request_sha256": sha(wire),
            "wire_bytes": len(wire),
            "full_schema_sha256": old.stable(full),
            "wire_schema_sha256": old.stable(
                body["response_format"]["json_schema"]["schema"]
            ),
            "material_sha256": old.stable(case["material"]),
        }
        slots.append(
            {
                "id": name,
                "phase": "screen" if index < 3 else "generalization",
                "wire_sha256": sha(wire),
                "wire_bytes": len(wire),
                "cost_micro_cny": 12 * (1048576 + len(wire)) + 36 * 8202,
            }
        )
    sources.update(
        {
            n: sha((root / n).read_bytes())
            for n in [
                receipt_path,
                human_path,
                "scripts/run_qwen_continuation.py",
                "scripts/prepare_qwen_continuation.py",
                "scripts/tests/test_qwen_continuation.py",
                BASE + "/README.md",
            ]
        }
    )
    sources[BASE + "/requests.json"] = sha(rendered(requests))
    p = deepcopy(previous)
    p.pop("budget_manifest")
    p.update(
        version="qwen-continuation-r01",
        execution_root=str(root.resolve()),
        sources=sources,
        slots=slots,
        requests=11,
        cost_micro_cny=sum(s["cost_micro_cny"] for s in slots),
        schema_profile=QWEN_SCHEMA_PROFILE,
        imported_receipt_path=receipt_path,
        imported_human_path=human_path,
        imported_receipt_sha256=old.stable(receipt),
        human_interpretation=human["interpretation"],
        imported_first_case_is_new_call=False,
    )
    for stale in ["request_sha256", "business_schema_sha256", "wire_schema_sha256"]:
        p.pop(stale, None)
    meta = (root / ".env").lstat()
    assert stat.S_ISREG(meta.st_mode) and not meta.st_mode & 0o077
    p["credential_file_metadata"] = {
        k: getattr(meta, k) for k in previous["credential_file_metadata"]
    }
    manifest = old.manifest(p, root)
    manifest["run_id"] = "qwen-continuation-r01"
    manifest["bounds"]["requests"] = 11
    target = next(iter(manifest["targets"].values()))
    target["capability_sha256"] = sources[
        "docs/acceptance/phase-1-qwen-compatibility-r01/official-schema.json"
    ]
    tid = old.stable(target)
    manifest["targets"] = {tid: target}
    for slot in manifest["slots"]:
        slot["targets"] = [tid]
    p["budget_manifest"] = manifest
    return p, requests


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    p, requests = build()
    if args.write:
        assert (
            not (ROOT / BASE / "run-approval.json").exists()
            and not (ROOT / PRIVATE).exists()
        ), "APPROVED_OR_ENROLLED_FREEZE_IMMUTABLE"
        for name, value in [("proposal.json", p), ("requests.json", requests)]:
            (ROOT / BASE / name).write_bytes(rendered(value))
    print(
        json.dumps(
            {
                "requests": 11,
                "cost_micro_cny": p["cost_micro_cny"],
                "screen_requests": 3,
                "screen_cost_micro_cny": sum(
                    s["cost_micro_cny"] for s in p["slots"][:3]
                ),
                "generalization_requests": 8,
                "generalization_cost_micro_cny": sum(
                    s["cost_micro_cny"] for s in p["slots"][3:]
                ),
                "sources": len(p["sources"]),
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
