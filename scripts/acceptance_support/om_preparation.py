"""Offline OM acceptance roster/metrics. Never creates or sends a Provider request."""

import hashlib
import json
from pathlib import Path
from typing import Any

from acceptance_support.om_benchmarks import benchmark_materials

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/acceptance/phase-1-om-implementation"
METRIC_VERSION = "om-acceptance-metrics-v1"
DIAGNOSTICS = (
    "consistent_unit",
    "reachable_code_safety",
    "fact_contradiction",
    "cross_scene_conflict",
    "harmless_includes_control",
    "insufficient_premises",
    "corrections_exhausted",
    "long_complete",
)
ROUTE_SCENARIOS = (
    "clean_pass",
    "explicit_uncertainty",
    "unchecked_scope",
    "missing_required_check",
    "label_only_condition",
    "label_only_impact",
    "whitespace_condition",
    "unknown_anchor",
    "old_protocol",
    "pass_with_finding",
    "reject_without_finding",
    "human_without_unknown",
    "unit_revise",
    "unit_uncertainty",
    "unit_serious_reject",
    "local_eval",
    "local_file_io",
    "open_exercise",
    "stale_actions",
    "changed_content",
)


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preparation() -> dict[str, Any]:
    graph = json.loads((ROOT / "data/knowledge/phase-1.1.0.json").read_text())
    nodes = graph["nodes"]
    # New roster only: no old formal candidates, labels, ledger or score is imported.
    targets = [
        {
            "id": f"new-target-{i + 1:03}",
            "node_id": nodes[i % len(nodes)]["id"],
            "goal": f"用C学习{nodes[i % len(nodes)]['name']}："
            + (
                "解释基本表示并给出边界示例。",
                "对照代码追踪状态变化。",
                "通过客观题检查典型误解。",
                "结合失败前提说明算法行为。",
            )[i // len(nodes)],
            "status": "NOT_RUN",
            "label_status": "HUMAN_SCOPE_REVIEW_REQUIRED",
        }
        for i in range(100)
    ]
    materials, proposed_labels = benchmark_materials()
    benchmarks = {
        kind: [
            {
                "id": f"new-{kind}-{i + 1:02}",
                "status": "NOT_RUN",
                "material_status": "AUTHORED_PENDING_INDEPENDENT_HUMAN_LABELS",
                "material_digest": hashlib.sha256(
                    canonical(materials[kind][i]["unit"])
                ).hexdigest(),
            }
            for i in range(count)
        ]
        for kind, count in [("severe", 20), ("correct", 20), ("long", 10)]
    }
    paths = []
    for directory, suffixes in [
        ("backend/app", {".py", ".json"}),
        ("backend/alembic", {".py"}),
        ("web/src", {".ts", ".vue", ".css"}),
    ]:
        paths.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and p.suffix in suffixes and "__pycache__" not in p.parts
        )
    paths.extend(
        ROOT / p
        for p in [
            "backend/pyproject.toml",
            "backend/uv.lock",
            "web/package.json",
            "web/pnpm-lock.yaml",
            "data/knowledge/phase-1.1.0.json",
            "data/knowledge/phase-1.1.0.manifest.json",
            "data/knowledge/phase-1.1.0.sources.json",
            "data/knowledge_graph.yaml",
            "web/vite.config.ts",
            "web/index.html",
            "scripts/run_shared_learning_tests.py",
            "scripts/review_learning_cases.py",
            "docs/ADR/0015-shared-plan-and-hybrid-review.md",
            "docs/ADR/0015-approval-20261015.json",
            "docs/acceptance/phase-1-om-redesign/proposal-manifest.json",
            "docs/acceptance/phase-1-om-redesign/minimum-contract.schema.json",
            "docs/acceptance/phase-1-om-redesign/data-and-compatibility-contract.md",
            "docs/acceptance/phase-1-om-redesign/acceptance-plan.md",
            "docs/api/openapi.yaml",
            "docs/agents/shared-learning.md",
            "docs/agents/prompts/shared-learning-plan-v1.md",
            "docs/agents/prompts/evidence-resource-review-v4.md",
            "docs/acceptance/phase-1-t040-focus-r11/route-retired.json",
            "scripts/acceptance_support/om_preparation.py",
            "scripts/acceptance_support/om_benchmarks.py",
            "scripts/prepare_om_redesign_acceptance.py",
            "backend/tests/test_om_redesign_acceptance_preparation.py",
        ]
    )
    # Include regressions without reading environment files, private ledgers or generated media.
    paths.extend(p for p in (ROOT / "backend/tests").rglob("*.py") if "__pycache__" not in p.parts)
    paths.extend(
        p
        for p in (ROOT / "web/tests").rglob("*")
        if p.is_file() and p.suffix in {".ts", ".py"} and "__pycache__" not in p.parts
    )
    sources = [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sorted(set(paths))]
    diagnostics = [
        {"id": f"new-diagnostic-{i + 1:02}", "kind": kind, "max_requests": 20, "status": "NOT_RUN"}
        for i, kind in enumerate(DIAGNOSTICS)
    ]
    budget = {
        "currency": "CNY",
        "provider_requests_authorized": 0,
        "fee_authorized_micro_cny": 0,
        "diagnostic_request_ceiling": 8 * 20,
        "formal_generation_request_ceiling": 100 * 20,
        "audit_request_ceiling": (20 + 20 + 10) * 4,
        "total_request_ceiling": 2360,
        "max_total_output_tokens_per_request": 4096,
        "total_output_token_ceiling": 2360 * 4096,
        "input_token_proof": None,
        "verified_prices": None,
        "cost_ceiling_micro_cny": None,
        "per_operation_seconds": 180,
        "per_request_seconds": 60,
        "retries": 0,
        "fallbacks": 0,
        "note": (
            "Conservative envelope, not actual wire slots or expected spend; "
            "no money approval or account cap."
        ),
    }
    value = {
        "version": "om-acceptance-preparation-v1",
        "status": "OFFLINE_PREPARATION_NOT_EXECUTABLE",
        "configuration": {
            "generation_protocol": "shared-plan-v1",
            "graph_version": graph["graph_version"],
            "model_configuration_status": "EXACT_PROVIDER_MODEL_SAMPLING_REQUIRES_NEW_RUN_FREEZE",
            "production_mode": "catalog_only",
            "automatic_quality_gate": "T040 blocked",
            "optional_profile_and_preview_calls": 0,
            "operation_call_limit": 20,
        },
        "sources": sources,
        "targets": targets,
        "benchmarks": benchmarks,
        "diagnostics": diagnostics,
        "offline_route_scenarios": list(ROUTE_SCENARIOS),
        "budget": budget,
        "thresholds": {
            "first_schema": {"required": 98, "denominator": 100},
            "automatic_success": {"required": 95, "denominator": 100},
            "severe_recall": {"required": 18, "denominator": 20},
            "classification": {"required": 18, "denominator": 20},
            "correct_auto_pass": {"required": 19, "denominator": 20},
            "long_complete": {"required": 10, "denominator": 10},
        },
        "blocking_conditions": [
            "exact_model_and_parameters",
            "new_benchmark_materials",
            "independent_human_labels",
            "wire_and_derived_slot_freeze",
            "input_token_cost_proof",
            "precise_paid_run_approval",
            "separate_trusted_acceptance_runner",
        ],
        "historical_results": (
            "Original T033/r01-r11 decisions and stopped ledgers remain unchanged."
        ),
        "benchmark_materials_digest": hashlib.sha256(canonical(materials)).hexdigest(),
        "proposed_labels_digest": hashlib.sha256(canonical(proposed_labels)).hexdigest(),
        "label_status": "ALL_50_PROPOSED_LABELS_REQUIRE_INDEPENDENT_HUMAN_REVIEW",
        "human_approval_is_not_auto_pass": True,
    }
    value["root_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
    return value


def generation_metrics(rows: list[dict[str, Any]], slots: list[str]) -> dict[str, Any]:
    if len(slots) != 100 or len(set(slots)) != 100:
        raise ValueError("full target denominator required")
    records = {r["id"]: r for r in rows}
    if len(records) != len(rows) or not set(records) <= set(slots):
        raise ValueError("duplicate/foreign slot")
    counts = {
        key: 0
        for key in (
            "first_schema",
            "automatic_success",
            "human_pending",
            "human_approved",
            "human_rejected",
            "human_invalidated",
            "not_run",
            "mixed_publishable",
        )
    }
    for row in rows:
        for flag in ("first_schema", "independent_fact_pass"):
            if row.get(flag) is not None and type(row[flag]) is not bool:
                raise ValueError("Boolean evidence required")
        if row.get("provider_requests") is not None and (
            type(row["provider_requests"]) is not int or row["provider_requests"] < 0
        ):
            raise ValueError("Nonnegative request count required")
    for id in slots:
        r = records.get(id, {"status": "NOT_RUN"})
        if r.get("first_schema") is True:
            counts["first_schema"] += 1
        status = r["status"]
        if status not in (
            "NOT_RUN",
            "auto",
            "human_pending",
            "human_approved",
            "human_rejected",
            "human_invalidated",
            "failed",
        ):
            raise ValueError("unsupported result state")
        if status == "NOT_RUN":
            counts["not_run"] += 1
        if status.startswith("human_"):
            counts[status] += 1
        if status == "auto" and r.get("independent_fact_pass") is True:
            counts["automatic_success"] += 1
            counts["mixed_publishable"] += 1
        if status == "human_approved" and r.get("independent_fact_pass") is True:
            counts["mixed_publishable"] += 1
    return {
        "version": METRIC_VERSION,
        "denominator": 100,
        **counts,
        "automatic_gate_passed": counts["first_schema"] >= 98 and counts["automatic_success"] >= 95,
        "provider_requests_recorded": None
        if any(r.get("provider_requests") is None for r in rows)
        else sum(r["provider_requests"] for r in rows),
    }


def audit_metrics(kind: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = {"severe": 20, "correct": 20, "long": 10}[kind]
    expected = {f"new-{kind}-{i + 1:02}" for i in range(denominator)}
    if len({r["id"] for r in rows}) != len(rows) or not {r["id"] for r in rows} <= expected:
        raise ValueError("duplicate/foreign audit slot")
    result = {
        "denominator": denominator,
        "not_run": denominator - len(rows),
        "concrete_detected": 0,
        "classification_correct": 0,
        "correct_auto_pass": 0,
        "long_complete": 0,
        "unsupported_findings": sum(r.get("unsupported_findings", 0) for r in rows),
    }
    for r in rows:
        if r.get("concrete_detected") is True:
            result["concrete_detected"] += 1
            if r.get("classification_correct") is True:
                result["classification_correct"] += 1
        if r.get("automatic_verdict") == "pass" and r.get("independent_fact_pass") is True:
            result["correct_auto_pass"] += 1
        if r.get("completed") is True and r.get("schema_valid") is True:
            result["long_complete"] += 1
    return result
