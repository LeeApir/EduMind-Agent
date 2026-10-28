"""Exact-package T069 execution gate. --check and --assessment never load keys or send."""

import argparse
import asyncio
import hashlib
import json
import os
import re
from collections import Counter
import sqlite3
from pathlib import Path
import sys
import time
import stat
from datetime import datetime
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_agent_pilot as c  # noqa: E402
from scripts.isolated_diagnostics import p15_pilot_execution as execution  # noqa: E402
from scripts.isolated_diagnostics import p15_pilot_wire as wire  # noqa: E402
from scripts.isolated_diagnostics.p15_head_insertion_engine import (  # noqa: E402
    SpecError,
    VARIANTS,
    answer,
    build_example,
    digest,
)

BASE = ROOT / "docs/acceptance/phase-1.5-agent-pilot/execution-p01"
OUTPUT = Path("/private/tmp/edumind-p15-agent-pilot-p01")
INDEPENDENT_DIRECTORY = Path("/private/tmp/edumind-p15-pilot-independent-e03")
LIMITS = dict(
    requests=90,
    input_tokens=None,
    output_tokens=None,
    fee_cap=None,
    wall_seconds=10800,
    per_request_seconds=120,
    requested_max_output_tokens=8000,
    request_bytes=131072,
    response_bytes=2097152,
)


def file_sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4000000:
        raise c.PilotError("PACKAGE_FILE")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_package() -> tuple[str, dict[str, Any], dict[str, Any]]:
    manifest = wire.strict_json((BASE / "manifest.json").read_bytes())
    for row in manifest["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise c.PilotError("MANIFEST_PATH")
        path = ROOT / relative
        if any(
            p.is_symlink() for p in (path, *path.parents)
        ) or not path.is_relative_to(ROOT):
            raise c.PilotError("MANIFEST_PATH")
        if file_sha(path) != row["sha256"]:
            raise c.PilotError("PACKAGE_DRIFT")
    package = file_sha(BASE / "manifest.json")
    policy = wire.strict_json((BASE / "policy.json").read_bytes())
    materials = wire.strict_json((BASE / "materials.json").read_bytes())
    if policy["limits"] != LIMITS or policy["providers"] != wire.ROUTES:
        raise c.PilotError("POLICY_IMPLEMENTATION_MISMATCH")
    return package, policy, materials


def validate_materials(materials: dict[str, Any]) -> dict[str, Any]:
    if materials.get("status") != "independent_e03_ratified":
        raise c.PilotError("INDEPENDENT_E03_REQUIRED")
    summary_path = BASE / "independent-e03-summary.json"
    if file_sha(summary_path) != materials.get("summary_sha256"):
        raise c.PilotError("INDEPENDENT_SUMMARY_DRIFT")
    summary = wire.strict_json(summary_path.read_bytes())
    candidate = wire.strict_json((BASE / "candidate-manifest.json").read_bytes())
    candidate_sha = file_sha(BASE / "candidate-manifest.json")
    if (
        summary.get("schema_version") != "p15-independent-reference-summary-v1"
        or summary.get("status")
        != "assistant_reference_ratified_not_execution_authority"
        or summary.get("evaluator")
        != dict(identity="pilot_independent_evaluator", type="assistant", human=False)
        or summary.get("human_signoff") is not False
        or summary.get("candidate_manifest_sha256") != candidate_sha
        or materials.get("candidate_manifest_sha256") != candidate_sha
        or summary.get("supported_slots") != 10
        or summary.get("local_refusal_slots") != 4
        or summary.get("provider_requests") != 0
        or summary.get("network_requests") != 0
        or summary.get("c_execution") != 0
    ):
        raise c.PilotError("INDEPENDENT_RATIFICATION")
    for row in candidate["files"]:
        relative = Path(row["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or file_sha(ROOT / relative) != row["sha256"]
        ):
            raise c.PilotError("CANDIDATE_DRIFT_AFTER_SELECTION")
    try:
        selected_at = datetime.fromisoformat(summary["ratified_at"])
        frozen_at = datetime.fromisoformat(candidate["frozen_at"])
        if (
            selected_at.tzinfo is None
            or frozen_at.tzinfo is None
            or selected_at < frozen_at
        ):
            raise ValueError("selection precedes freeze")
    except (TypeError, KeyError, ValueError) as exc:
        raise c.PilotError("INDEPENDENT_SELECTION_TIME") from exc
    expected_names = dict(
        inputs="inputs.json",
        truth="truth.json",
        ratification="ratification.json",
        derivation="hand-derivation.md",
    )
    if (
        not INDEPENDENT_DIRECTORY.is_dir()
        or stat.S_IMODE(INDEPENDENT_DIRECTORY.stat().st_mode) != 0o700
    ):
        raise c.PilotError("INDEPENDENT_DIRECTORY_PERMISSIONS")
    for key, name in expected_names.items():
        path = INDEPENDENT_DIRECTORY / name
        if (
            summary.get(key + "_path") != str(path)
            or re.fullmatch(r"[0-9a-f]{64}", summary.get(key + "_sha256", "")) is None
            or not path.is_file()
            or any(p.is_symlink() for p in (path, *path.parents))
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise c.PilotError("INDEPENDENT_MATERIAL_BINDING")
    if any(
        materials.get(k) != summary[k]
        for k in (
            "inputs_path",
            "inputs_sha256",
            "truth_sha256",
            "ratification_sha256",
            "derivation_sha256",
        )
    ):
        raise c.PilotError("INDEPENDENT_MATERIAL_DIGESTS")
    # No truth/derivation/ratification contents are read by the developer or runtime.
    return cast(dict[str, Any], summary)


def read_inputs(materials: dict[str, Any]) -> dict[str, Any]:
    if materials["status"] != "independent_e03_ratified":
        raise c.PilotError("INDEPENDENT_E03_REQUIRED")
    validate_materials(materials)
    path = Path(materials["inputs_path"])
    if path != INDEPENDENT_DIRECTORY / "inputs.json" or any(
        p.is_symlink() for p in (path, *path.parents)
    ):
        raise c.PilotError("INDEPENDENT_INPUT_PATH")
    if file_sha(path) != materials["inputs_sha256"]:
        raise c.PilotError("INPUTS_DRIFT")
    value = wire.strict_json(path.read_bytes())
    if set(value) != {"version", "slots"} or value["version"] != "pilot-inputs-v1":
        raise c.PilotError("INPUTS_FORMAT")
    slots = value["slots"]
    if (
        len(slots) != 14
        or len({s["slot_id"] for s in slots}) != 14
        or sum(s["kind"] == "supported" for s in slots) != 10
        or sum(s["kind"] == "refusal" for s in slots) != 4
    ):
        raise c.PilotError("INPUT_DENOMINATORS")
    categories: Counter[str] = Counter()
    refusals: Counter[str] = Counter()
    for slot in slots:
        if (
            set(slot) != {"slot_id", "kind", "spec", "question"}
            or type(slot["slot_id"]) is not str
            or re.fullmatch(r"[A-Za-z0-9_-]{1,48}", slot["slot_id"]) is None
            or len(slot["slot_id"]) > 48
            or slot["kind"] not in ("supported", "refusal")
            or slot["question"] not in (None, "exact_traversal")
        ):
            raise c.PilotError("INPUT_SLOT")
        try:
            example = build_example(slot["spec"])
            if slot["question"] is not None:
                answer(example, slot["question"])
            supported = True
        except SpecError:
            supported = False
        if supported != (slot["kind"] == "supported"):
            raise c.PilotError("INPUT_KIND_CONFLICT")
        spec = slot["spec"]
        if supported:
            category = (
                "allocation_failure"
                if not all(spec["allocation_success"])
                else spec["variant"]
            )
            categories[category] += 1
        elif slot["question"] == "exact_traversal":
            if spec.get("variant") != "uninitialized_next" or not any(
                spec["allocation_success"]
            ):
                raise c.PilotError("REFUSAL_QUESTION_SCOPE")
            refusals["unknown_exact_traversal"] += 1
        elif "code" in spec:
            refusals["arbitrary_code"] += 1
        elif spec.get("variant") not in VARIANTS:
            refusals["unknown_variant"] += 1
        elif type(spec.get("insert_values")) is list and len(spec["insert_values"]) > 4:
            refusals["overlong_sequence"] += 1
        else:
            raise c.PilotError("REFUSAL_CATEGORY")
    if categories != Counter(
        {k: 2 for k in (*VARIANTS, "allocation_failure")}
    ) or refusals != Counter(
        {
            k: 1
            for k in (
                "unknown_exact_traversal",
                "arbitrary_code",
                "unknown_variant",
                "overlong_sequence",
            )
        }
    ):
        raise c.PilotError("INPUT_CATEGORY_DENOMINATORS")
    return cast(dict[str, Any], value)


def grant_before_keys(
    package: str, policy: dict[str, Any], materials: dict[str, Any]
) -> dict[str, Any]:
    grant = wire.strict_json((BASE / "execution-approval.json").read_bytes())
    if (
        grant.get("accepted") is not True
        or grant.get("package_sha256") != package
        or grant.get("scope") != "PHASE-1.5-T069"
        or not grant.get("human_message")
        or not grant.get("evidence_ref")
        or grant.get("reviewer_type") != "assistant_independent"
        or grant.get("limits") != policy["limits"]
        or any(
            grant.get(key) is not True
            for key in (
                "compatibility_scope_accepted",
                "synthetic_transfer_accepted",
                "new_window_accepted",
                "unbounded_tokens_accepted",
                "unbounded_money_and_unverified_invoice_accepted",
                "relay_context_risk_accepted",
            )
        )
    ):
        raise c.PilotError("EXACT_NEW_EXECUTION_APPROVAL_REQUIRED")
    if materials["status"] != "independent_e03_ratified":
        raise c.PilotError("INDEPENDENT_E03_REQUIRED")
    now = time.time()
    start, end = grant.get("window_started_epoch"), grant.get("deadline_epoch")
    if (
        type(start) not in (int, float)
        or type(end) not in (int, float)
        or not start <= now < end
        or end - start != 10800
    ):
        raise c.PilotError("NEW_WINDOW_INVALID_OR_EXPIRED")
    return cast(dict[str, Any], grant)


def load_keys() -> dict[str, str]:
    from dotenv import dotenv_values

    values = dotenv_values(ROOT / ".env", interpolate=False)

    def value(name: str) -> str | None:
        return os.getenv(name) or values.get(name)

    generation = value("EDUMIND_DEEPSEEK_COMPAT_API_KEY")
    review = value("EDUMIND_AIAPI_REVIEW_API_KEY")
    if not review and value("EDUMIND_PROVIDER_BASE_URL") in (
        "https://aiapi.world/v1",
        "https://aiapi.world/v1/",
    ):
        review = value("EDUMIND_PROVIDER_API_KEY")
    if not generation or not review:
        raise c.PilotError("EXACT_PROVIDER_CREDENTIALS_MISSING")
    return dict(generation=generation, review=review)


async def step(
    journal: execution.Journal,
    inputs: dict[str, Any],
    keys: dict[str, str],
    *,
    transport_factory: Any = None,
    resolver: Any = None,
) -> dict[str, Any]:
    from app.core.provider_target import resolve_addresses
    import httpx

    row = journal.guard()
    item = row["order"][row["position"]]
    slot = next(s for s in inputs["slots"] if s["slot_id"] == item["slot_id"])
    if slot["kind"] == "refusal":
        # No real gateway, target resolution or provider call is needed for a local refusal.
        try:
            example = build_example(slot["spec"])
            if slot["question"] is not None:
                answer(example, slot["question"])
        except SpecError as exc:
            result = dict(
                state="refused", reason=str(exc), calls=0, versions=[], events=[]
            )
            journal.finish(result)
            return result
        raise c.PilotError("REFUSAL_NOT_REFUSED")
    factory = transport_factory or (
        lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    )
    gateways = {
        role: execution.ExecutionGateway(
            execution.RecordedAdapter(
                journal,
                role=role,
                slot=slot["slot_id"],
                arm=item["arm"],
                keys=keys,
                transport_factory=factory,
                resolver=resolver or resolve_addresses,
            )
        )
        for role in wire.ROUTES
    }
    workflow = (execution.ExecutionB if item["arm"] == "B" else execution.ExecutionC)(
        gateways["generation"], gateways["review"], journal
    )
    result = await workflow.run(
        run_id="p15_agent_pilot_p01",
        slot_id=slot["slot_id"],
        spec=slot["spec"],
        question=slot["question"],
    )
    journal.finish(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--start", action="store_true")
    group.add_argument("--step", action="store_true")
    group.add_argument("--accept-report", type=Path)
    group.add_argument("--assessment", action="store_true")
    args = parser.parse_args()
    journal = None
    try:
        package, policy, materials = check_package()
        if args.check:
            if materials["status"] == "independent_e03_ratified":
                read_inputs(materials)
            print(
                json.dumps(
                    dict(
                        package_sha256=package,
                        materials=materials["status"],
                        check_is_not_execution_authority=True,
                        real_requests=0,
                    )
                )
            )
            return 0
        if args.assessment:
            from scripts.check_p15_pilot_execution import verify

            print(
                json.dumps(
                    verify(
                        OUTPUT,
                        package,
                        expected_inputs_sha256=materials["inputs_sha256"],
                        expected_grant_digest=digest(
                            wire.strict_json(
                                (BASE / "execution-approval.json").read_bytes()
                            )
                        ),
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        grant = grant_before_keys(package, policy, materials)
        inputs = read_inputs(materials)
        if args.start:
            journal = execution.Journal.start(OUTPUT, package, grant, inputs)
            print("New exact batch registered; requests: 0.")
            return 0
        journal = execution.Journal(OUTPUT)
        with journal.lock():
            row = journal.batch()
            if row["package_sha256"] != package or row["grant_sha256"] != digest(grant):
                raise c.PilotError("PACKAGE_OR_GRANT_CHANGED")
            if args.accept_report:
                report_path = args.accept_report.absolute()
                if (
                    not report_path.is_relative_to(OUTPUT)
                    or ".." in report_path.parts
                    or any(p.is_symlink() for p in (report_path, *report_path.parents))
                ):
                    raise c.PilotError("ASSISTANT_REPORT_PATH")
                file_sha(report_path)
                report = wire.strict_json(report_path.read_bytes())
                journal.accept_report(report)
                print("Independent assistant report recorded; requests: 0.")
                return 0
            journal.guard(
                package=package, grant=grant
            )  # Before .env, keys, DNS or real transport.
            keys = (
                {}
                if row["order"][row["position"]]["kind"] == "refusal"
                else load_keys()
            )
            result = asyncio.run(step(journal, inputs, keys))
            print(
                json.dumps(
                    dict(
                        state=result["state"],
                        calls=result["calls"],
                        batch_state=journal.batch()["status"],
                    )
                )
            )
            return (
                0
                if result["state"] in ("refused", "model_advisory_pending_assistant")
                else 2
            )
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        if journal is not None and journal.batch()["status"] == "active":
            journal.stop("LOCAL_OR_PROVIDER_STOP")
        print(
            str(error)
            if isinstance(error, c.PilotError)
            else "Execution refused; state preserved."
        )
        return 2
    finally:
        if journal is not None:
            journal.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
