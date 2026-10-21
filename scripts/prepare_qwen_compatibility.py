"""Zero-call complete request/source/budget freeze. Does not read credential contents."""

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
from app.services.learning_policy import active_policy_digest
from app.services.qwen_schema import QWEN_SCHEMA_PROFILE, qwen_wire_schema
from acceptance_support.qwen_review_budget import sha

BASE = "docs/acceptance/phase-1-qwen-compatibility-r01"


def build(root=ROOT):
    previous = old.read(root / old.BASE / "proposal.json")
    sources = {name: sha((root / name).read_bytes()) for name in previous["sources"]}
    changed = [
        name for name, digest in previous["sources"].items() if sources[name] != digest
    ]
    expected = {
        "backend/app/services/openai_compatible.py",
        "backend/app/services/provider_connection_dispatch.py",
        "scripts/acceptance_support/qwen_review_attempt.py",
    }
    assert set(changed) == expected
    case = old.read(root / old.DESIGN / "cases.json")["reachable-safety:candidate"]
    original = json.loads(bytes.fromhex(case["candidate_wire_hex"]))
    body = deepcopy(original)
    full = body["response_format"]["json_schema"]["schema"]
    body["response_format"]["json_schema"]["schema"] = qwen_wire_schema(full)
    wire = httpx.Request(
        "POST", "https://example.com/chat/completions", json=body
    ).content
    cost = 12 * (1048576 + len(wire)) + 36 * 8202
    request = {
        "wire_hex": wire.hex(),
        "request_sha256": sha(wire),
        "wire_bytes": len(wire),
        "business_schema_sha256": old.stable(full),
        "wire_schema_sha256": old.stable(
            body["response_format"]["json_schema"]["schema"]
        ),
        "schema_profile": QWEN_SCHEMA_PROFILE,
        "only_request_difference": "response_format.json_schema.schema; messages/Prompt/model/other parameters unchanged",
    }
    names = [
        "backend/app/services/qwen_schema.py",
        "scripts/acceptance_support/provider_error_decode.py",
        "scripts/acceptance_support/qwen_compatibility_transport.py",
        "scripts/tests/test_qwen_compatibility_repair.py",
        "scripts/tests/test_qwen_compatibility_runner.py",
        "scripts/run_qwen_compatibility.py",
        "scripts/prepare_qwen_compatibility.py",
        BASE + "/README.md",
        BASE + "/official-schema.json",
        BASE + "/request.json",
    ]
    for name in names:
        sources[name] = (
            sha((root / name).read_bytes())
            if not name.endswith("/request.json")
            else sha(
                (json.dumps(request, ensure_ascii=False, indent=2) + "\n").encode()
            )
        )
    p = deepcopy(previous)
    p.update(
        version="qwen-compatibility-r01",
        execution_root=str(root.resolve()),
        sources=sources,
        policy_digest=active_policy_digest(),
        cost_micro_cny=cost,
        requests=1,
        schema_profile=QWEN_SCHEMA_PROFILE,
        request_sha256=sha(wire),
        business_schema_sha256=request["business_schema_sha256"],
        wire_schema_sha256=request["wire_schema_sha256"],
        prior_run="qwen-review-execution-r01 remains stopped; no balance reused",
    )
    meta = (root / ".env").lstat()
    assert stat.S_ISREG(meta.st_mode) and not meta.st_mode & 0o077
    p["credential_file_metadata"] = {
        key: getattr(meta, key) for key in previous["credential_file_metadata"]
    }
    p["slots"] = [
        {
            "id": "compatibility",
            "phase": "diagnostic",
            "wire_sha256": sha(wire),
            "wire_bytes": len(wire),
            "cost_micro_cny": cost,
        }
    ]
    manifest = old.manifest(p, root)
    manifest["run_id"] = "qwen-compatibility-r01"
    manifest["bounds"]["requests"] = 1
    manifest["slots"][0]["input_sha256"] = sha(wire)
    target = next(iter(manifest["targets"].values()))
    target["max_wire_bytes"] = len(wire)
    target["capability_sha256"] = sources[BASE + "/official-schema.json"]
    tid = old.stable(target)
    manifest["targets"] = {tid: target}
    manifest["slots"][0]["targets"] = [tid]
    p["budget_manifest"] = manifest
    return p, request


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    p, request = build()
    if args.write:
        assert not (ROOT / BASE / "run-approval.json").exists(), (
            "APPROVED_FREEZE_IMMUTABLE"
        )
        assert not (ROOT / "local-materials/phase-1-qwen-compatibility-r01").exists(), (
            "ENROLLED_FREEZE_IMMUTABLE"
        )
        for name, value in [("proposal.json", p), ("request.json", request)]:
            (ROOT / BASE / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n"
            )
    print(
        json.dumps(
            {
                "requests": 1,
                "cost_micro_cny": p["cost_micro_cny"],
                "request_sha256": p["request_sha256"],
                "sources": len(p["sources"]),
                "provider_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
