"""Build non-executable synthetic role request drafts without credentials or HTTP.

These development fixtures are not a frozen execution package. The trusted
sender and deadline gate are still unresolved and no provider may be called.
"""

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as contract
from scripts.isolated_diagnostics import p15_minimal_probe_contract as probe
from scripts.isolated_diagnostics import p15_controlled_mock_v2 as mock_validation
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as review
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/acceptance/phase-1.5-isolated-blockers-t102/offline-evidence.json.gz"
OUTPUT = ROOT / "docs/acceptance/phase-1.5-manual-bc-preparation-t102/role-draft"
REQUEST_BYTES_LIMIT = 262_144


def build() -> tuple[dict[str, bytes], dict[str, Any]]:
    """Return seven synthetic echo bodies and their development-only index."""
    archive = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
    contract.require(archive["real_provider_calls"] == 0, "SYNTHETIC_ARCHIVE")
    archive_catalog = contract.make_catalog(archive["package"]["slots"][0]["spec"])
    context = json.loads((contract.DESIGN / "context-example.json").read_text())
    catalog = contract.make_catalog(context["spec"])
    originals = probe.bodies()
    first = json.loads(json.loads(originals["S1"])["input"][1]["content"])[
        "expected_output"
    ]
    result: dict[str, bytes] = {}
    entries = []
    for name in probe.ORDER:
        stage = probe.STAGES[name]
        body = json.loads(originals[name])
        payload = json.loads(body["input"][1]["content"])
        instruction, instruction_version = budget.instruction(stage)
        payload["candidate_role_instruction_data"] = instruction
        if stage == "C_content":
            payload["role_input"]["plan"] = deepcopy(first)
        elif stage == "C_repair":
            payload["role_input"]["original_input"]["plan"] = deepcopy(first)
        if stage.startswith("review_"):
            arm = stage[-1]
            row = next(item for item in archive["attempts"] if item["stage"] == stage)
            original_body = json.loads(row["request"])
            sent_view = json.loads(original_body["input"][1]["content"])
            candidate = archive["results"][arm]["versions"][0]
            expected_view, binding = review.build(candidate, archive_catalog)
            contract.require(sent_view == expected_view, "DRAFT_VIEW_BINDING")
            envelope = json.loads(row["raw_response"])
            expected_output = json.loads(envelope["output"][0]["content"][0]["text"])
            review.validate_review(
                expected_output, canonical(sent_view), candidate, archive_catalog, binding
            )
            contract.require(bool(expected_output["issues"]), "DRAFT_REVIEW_ISSUE")
            payload["role_input"] = sent_view
            payload["expected_output"] = expected_output
        else:
            contract.validate(
                stage,
                payload["expected_output"],
                catalog=catalog if stage.startswith("C_") else None,
            )
        body["input"][1]["content"] = canonical(payload).decode("utf-8")
        contract.require(body["text"]["format"]["schema"] == contract.schema_for(stage), "DRAFT_SCHEMA")
        raw = canonical(body)
        contract.require(len(raw) <= REQUEST_BYTES_LIMIT, "DRAFT_REQUEST_SIZE")
        result[name] = raw
        entries.append(
            {
                "slot": name,
                "stage": stage,
                "role": probe.ROLES[name],
                "model": body["model"],
                "reasoning": body["reasoning"]["effort"],
                "system_instruction_role": "system_echo_instruction",
                "system_instruction_sha256": hashlib.sha256(
                    body["input"][0]["content"].encode("utf-8")
                ).hexdigest(),
                "role_instruction_location": "user_payload_data_not_system_instruction",
                "role_instruction_data_version": instruction_version,
                "role_instruction_data_sha256": hashlib.sha256(
                    instruction.encode("utf-8")
                ).hexdigest(),
                "request_bytes": len(raw),
                "request_sha256": hashlib.sha256(raw).hexdigest(),
                "local_input_reservation": len(raw) + 8192,
                "output_cap": body["max_output_tokens"],
            }
        )
    return result, {
        "status": "development_only_not_execution_package",
        "real_provider_calls": 0,
        "archive_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "requests": entries,
        "local_input_total": sum(item["local_input_reservation"] for item in entries),
        "output_cap_total": sum(item["output_cap"] for item in entries),
    }


def observe_synthetic_echo(name: str, request: bytes, raw: bytes) -> dict[str, Any]:
    """Validate a synthetic echo response; this does not send or save a response.

    S6/S7 require the new visible-view binding. The legacy seven-role observer
    expects the previous artifact/target_catalog format and is not suitable.
    """
    bodies, _ = build()
    contract.require(name in bodies and request == bodies[name], "DRAFT_REQUEST_BINDING")
    stage, role = probe.STAGES[name], probe.ROLES[name]
    body = wire.strict_json(request)
    payload = wire.strict_json(body["input"][1]["content"])
    private_view, schema_echo = mock_validation.response_for_validation(request, raw, role)
    contract.require(schema_echo == "matched", "DRAFT_SCHEMA_ECHO_UNKNOWN")
    result, observed = wire.validate(body, private_view, role)
    original = wire.strict_json(raw)
    echo_format = original.get("text", {}).get("format", {})
    format_fields = {
        key: "recognized" if key in echo_format else "unavailable"
        for key in ("type", "name", "strict")
    }
    contract.require(
        observed["reported_input_tokens"] <= len(request) + 8192
        and observed["reported_total_output_tokens"] <= body["max_output_tokens"],
        "DRAFT_USAGE_LIMIT",
    )
    if stage.startswith("review_"):
        archive = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
        catalog = contract.make_catalog(archive["package"]["slots"][0]["spec"])
        candidate = archive["results"][stage[-1]]["versions"][0]
        sent_view = payload["role_input"]
        expected_view, binding = review.build(candidate, catalog)
        contract.require(sent_view == expected_view, "DRAFT_VIEW_BINDING")
        review.validate_review(dict(result.value), canonical(sent_view), candidate, catalog, binding)
    else:
        context = json.loads((contract.DESIGN / "context-example.json").read_text())
        catalog = contract.make_catalog(context["spec"])
        contract.validate(
            stage,
            dict(result.value),
            catalog=catalog if stage.startswith("C_") else None,
        )
    contract.require(
        canonical(result.value) == canonical(payload["expected_output"]), "DRAFT_ECHO_MISMATCH"
    )
    return {
        "slot": name,
        "role": role,
        "stage": stage,
        "schema_payload_echo": schema_echo,
        "format_field_echo": format_fields,
        "reported_input_tokens": observed["reported_input_tokens"],
        "reported_total_output_tokens": observed["reported_total_output_tokens"],
        "instruction_echo": observed["instruction_echo"],
        "reasoning_echo": "recognized" if original.get("reasoning") is not None else "unavailable",
        "admission_decision": "not_evaluated",
        "provider_identity_verified": False,
        "teaching_evaluated": False,
    }


def main() -> None:
    if sys.argv[1:] not in (["--write-new"], ["--check"]):
        raise SystemExit("Use --write-new once or --check; this script cannot send requests.")
    bodies, index = build()
    files = {f"{name}.json": raw for name, raw in bodies.items()}
    files["DRAFT-INDEX.json"] = canonical(index)
    if sys.argv[1] == "--write-new":
        OUTPUT.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            (OUTPUT / name).write_bytes(raw)
    else:
        for name, raw in files.items():
            contract.require((OUTPUT / name).read_bytes() == raw, "DRAFT_BYTES_MISMATCH")
        contract.require({path.name for path in OUTPUT.iterdir()} == set(files), "DRAFT_EXTRA_FILE")
    print("7 synthetic development requests verified; no credentials or Provider; not a frozen package")


if __name__ == "__main__":
    main()
