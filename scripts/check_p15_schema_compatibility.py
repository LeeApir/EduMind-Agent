"""Audit the frozen p01 failure and propose enum typing offline. No live mode or credentials."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics.p15_schema_audit import (  # noqa: E402
    VERSION, audit_schema, explicit_string_enum_proposal,
)

ORIGINAL = Path("/private/tmp/edumind-p15-agent-pilot-p01")
PINS = {
    "call-000-request.json": "abd06d9b3a7043bef7825f1915120ad92f73bc154f744d34bb1388e27977c69b",
    "call-000-response.json": "662956d5b2a2a0c4c259bda9f3f263789ff2fd6d195446c2de15f2d8c83723cd",
    "call-000-status.json": "99a5642d715711b7096d3777e06393b44c8cde2aedeacc717ec8948d9dd46648",
}
PACKAGE = "295bc335af529b6906a51a61c5e22586b414d4e6c9986068534703b7b0aebe0d"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def verified_originals(directory: Path = ORIGINAL) -> dict[str, Any]:
    originals = {}
    for name, expected in PINS.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
            raise ValueError("ORIGINAL_PATH_OR_SIZE")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("ORIGINAL_DRIFT")
        originals[name] = json.loads(raw)
    return originals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = ROOT / "docs/acceptance/phase-1.5-agent-pilot/execution-p01/manifest.json"
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PACKAGE:
        raise ValueError("OLD_PACKAGE_DRIFT")
    for row in json.loads(raw)["files"]:
        path = ROOT / row["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("OLD_FROZEN_FILE_DRIFT")
    originals = verified_originals()
    body = originals["call-000-request.json"]
    # These imports only read the already frozen local prompt/spec files.
    from scripts.isolated_diagnostics import p15_agent_pilot as c
    from scripts.isolated_diagnostics import p15_pilot_baseline as b

    schema = body["text"]["format"]["schema"]
    if schema != b.SCHEMA:
        raise ValueError("BASELINE_SCHEMA_SOURCE_MISMATCH")
    proposal, changes = explicit_string_enum_proposal(schema)
    report = dict(
        version=VERSION,
        old_package_sha256=PACKAGE,
        originals_sha256=PINS,
        request_parameters={k: body[k] for k in (
            "model", "reasoning", "max_output_tokens", "temperature", "stream", "store"
        )},
        http_status=originals["call-000-status.json"]["http_status"],
        error_code=originals["call-000-response.json"]["error"]["code"],
        baseline=audit_schema(schema, "/text/format/schema"),
        roles={name: dict(
            provider_url=url, model=model, **audit_schema(s)
        ) for name, s, url, model in (
            ("C_plan", c.PLAN_SCHEMA, "https://api.deepseek.com/responses", "deepseek-flash"),
            ("C_content", c.CONTENT_SCHEMA, "https://api.deepseek.com/responses", "deepseek-flash"),
            ("B_C_review", c.REVIEW_SCHEMA, "https://aiapi.world/v1/responses", "gpt-6.1-sol"),
        )},
        enum_typing_proposal=dict(
            changed_pointers=changes,
            original_schema_sha256=hashlib.sha256(canonical(schema)).hexdigest(),
            proposed_schema_sha256=hashlib.sha256(canonical(proposal)).hexdigest(),
            semantic_argument="A string-only enum entails type:string; all other keywords unchanged.",
            provider_acceptance_verified=False,
            runtime_applied=False,
        ),
        live_requests=0,
        credentials_loaded=False,
        private_reference_read=False,
        course_feasibility_gate="blocked_until_relevant_role_wire_schemas_verified",
    )
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, value in (("audit.json", report), ("enum-typing-proposal.json", proposal)):
        (args.output / name).write_bytes(canonical(value) + b"\n")
    print(json.dumps(dict(output=str(args.output), changed_enum_types=len(changes),
                          live_requests=0, source_and_originals_verified=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
