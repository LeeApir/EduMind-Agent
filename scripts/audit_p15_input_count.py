"""Read-only r03 comparison. No credentials, network, tokenizer or execution entry point."""

import argparse
import hashlib
import json
from pathlib import Path

from check_p15_r03_diagnostic_results import check as check_stopped

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("docs/acceptance/phase-1.5-input-count-audit-t051/comparison.json")


def fingerprint(value):
    raw = value.encode() if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def findings(request, count, response):
    """Offline proposed checks only; never grants admission or settles a ledger."""
    expected = "\n\n".join(
        item["content"] for item in request["input"] if item["role"] == "system"
    )
    actual = response.get("instructions")
    issues = []
    if count["input_tokens"] != response["usage"]["input_tokens"]:
        issues.append("INPUT_COUNT_MISMATCH")
    if actual != expected:
        issues.append("INSTRUCTIONS_ECHO_DIFFERENT_OR_UNVERIFIED")
    if response.get("max_output_tokens") != request["max_output_tokens"]:
        issues.append("OUTPUT_LIMIT_ECHO_DIFFERENT_OR_UNVERIFIED")
    if response.get("text", {}).get("format", {}).get("schema") != request["text"]["format"]["schema"]:
        issues.append("SCHEMA_ECHO_DIFFERENT_OR_UNVERIFIED")
    return issues


def build(root=ROOT):
    # Verify frozen source, approvals, all raw hashes, stopped state and full holds first.
    check_stopped(root)
    result = json.loads((root / "docs/acceptance/phase-1.5-development-diagnostic-results-r03/results.json").read_text())
    paths = {i["role"]: Path(i["path"]) for i in result["raw_evidence"]}
    request, count, response = [json.loads(paths[k].read_bytes()) for k in (
        "request_body", "count_response", "model_response"
    )]
    expected = "\n\n".join(m["content"] for m in request["input"] if m["role"] == "system")
    actual = response["instructions"]
    assert actual.startswith(expected)
    suffix = actual[len(expected):]
    usage = response["usage"]
    attribution = usage["attribution"]
    fields = {k: v["input_tokens"] for k, v in attribution["request_fields"].items()}
    items = [v["input_tokens"] for v in attribution["items"].values()]
    return {
        "task_id": "PHASE-1.5-T051", "new_provider_http_requests": 0,
        "raw_evidence": result["raw_evidence"],
        "request_comparison": {
            "count_endpoint": "POST /v1/responses/input_tokens",
            "generation_endpoint": "POST /v1/responses",
            "body_sha256_both_reconstructed_from_frozen_transport": hashlib.sha256(paths["request_body"].read_bytes()).hexdigest(),
            "body_bytes": paths["request_body"].stat().st_size,
            "body_equality_evidence": "Single saved body + frozen content=request.content path; independently replayed with explicit MockTransport. No separate historical count-body capture or packet trace.",
            "headers_equality_evidence": "Frozen code forwards headers/extensions unchanged. Historical header/IP/TLS captures were not saved; no credentials read or exported.",
            "messages": [{"role": m["role"], "characters": len(m["content"]), **fingerprint(m["content"])} for m in request["input"]],
            "request_has_top_level_instructions": "instructions" in request,
            "request_has_previous_response_or_conversation": any(k in request for k in ("previous_response_id", "conversation")),
            "request_max_output_tokens": request["max_output_tokens"],
            "response_max_output_tokens": response["max_output_tokens"],
            "request_schema_equals_response_schema": request["text"]["format"]["schema"] == response["text"]["format"]["schema"],
            "request_strict": request["text"]["format"]["strict"],
            "response_strict": response["text"]["format"]["strict"],
            "response_format_extra_keys": sorted(set(response["text"]["format"]) - set(request["text"]["format"])),
        },
        "instructions_echo": {
            "expected_joined_system": {"characters": len(expected), **fingerprint(expected)},
            "response": {"characters": len(actual), **fingerprint(actual)},
            "expected_is_exact_prefix": True,
            "unrequested_suffix": {"characters": len(suffix), **fingerprint(suffix)},
            "suffix_classification": "Coding-agent identity, workspace collaboration and commentary instructions, not course-planning input; response-claimed text only, not independently verified model context.",
        },
        "reported_accounting": {
            "preflight_input_tokens": count["input_tokens"],
            "generation_input_tokens": usage["input_tokens"],
            "input_delta": usage["input_tokens"] - count["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "reasoning_tokens": usage["output_tokens_details"]["reasoning_tokens"],
            "cached_tokens": usage["input_tokens_details"]["cached_tokens"],
            "request_field_attribution": fields, "item_attribution": items,
            "attribution_sum": sum(fields.values()) + sum(items),
            "attribution_is_provider_report_only": True,
            "delta_exactly_attributable_to_suffix": False,
            "verified_model_settlement": None, "actual_relay_fee": None,
        },
        "proposed_offline_findings": findings(request, count, response),
        "gate_judgment": {
            "r03_stop_was_required": True,
            "equality_is_universal_budget_bound_proof": False,
            "equality_is_sufficient_context_integrity_proof": False,
            "relaxation_justified_by_available_evidence": False,
            "production_gate_changed": False, "real_probe_required_for_this_audit": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    assert build() == json.loads((ROOT / OUTPUT).read_text()), "Comparison drift"
    print("T051 offline comparison verified; zero new Provider calls; T038 remains blocked")


if __name__ == "__main__":
    main()
