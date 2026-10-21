"""Persist server-bound plan evidence. No model execution, repair or publication."""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningOperation
from app.models.learning_plan import LearningPlanVersion
from app.models.plan_check import PlanCheck, PlanCheckResolution, PlanRebuildEvent
from app.services import plan_verifiers
from app.services.learning_contract import LearningContractError, canonical, digest, validate_plan
from app.services.learning_owner_lock import lock_learning_owner

SCHEMA = json.loads(Path(__file__).with_suffix(".schema.json").read_text())


def validate_evidence(value: object, kind: str = "record") -> dict[str, Any]:
    try:
        schema = {"$ref": "#/$defs/" + kind, "$defs": SCHEMA["$defs"]}
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
        if len(canonical(value)) > 131072:
            raise ValueError("PLAN_EVIDENCE_TOO_LARGE")
        result = deepcopy(cast(dict[str, Any], value))
        if kind == "record":
            _validate_record(result)
        return result
    except Exception:
        raise LearningContractError("PLAN_EVIDENCE_INVALID") from None


def _validate_record(value: dict[str, Any]) -> None:
    """Validate evidence consistency only; never execute a route."""
    schema = SCHEMA
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    model = value["model_result"]
    decision = value["server_assessment"]
    binding = value["binding"]
    anchors = {a["anchor_id"]: a for a in value["anchor_catalog"]}
    if len(anchors) != len(value["anchor_catalog"]) or any(
        a["end_utf8"] <= a["start_utf8"] for a in anchors.values()
    ):
        raise ValueError("ANCHOR_SET_INVALID")
    source_bindings = {
        "user_request": "input_digest",
        "plan": "plan_digest",
        "reference": "reference_digest",
        "reference_context": "input_digest",
    }
    if any(
        a["source_digest"] != binding[source_bindings[a["source_kind"]]] for a in anchors.values()
    ):
        raise ValueError("ANCHOR_BINDING_CHANGED")
    if value["schema_version"] == "plan-check-record-v1" and any(
        a["source_kind"] == "reference_context" for a in anchors.values()
    ):
        raise ValueError("NEW_SOURCE_REQUIRES_V2")
    finding_ids = {f["finding_id"] for f in model["findings"]}
    if len(finding_ids) != len(model["findings"]):
        raise ValueError("DUPLICATE_FINDING")
    for f in model["findings"]:
        if not {f["target_anchor"], *f["evidence_anchors"]} <= anchors.keys():
            raise ValueError("UNKNOWN_ANCHOR")
    if (
        set(model["coverage"]["checked"])
        != set(
            [
                "goal_fidelity",
                "internal_consistency",
                "scope",
                "reference_support",
                "downstream_feasibility",
            ]
        )
        or model["coverage"]["unchecked"]
    ):
        if decision["route"] in ["accept_plan", "rebuild_once"]:
            raise ValueError("INCOMPLETE_CHECKS")
    if decision["route"] == "accept_plan" and (
        model["verdict"] != "pass" or model["findings"] or model["unresolved"]
    ):
        raise ValueError("UNRESOLVED_PLAN_CANNOT_PASS")
    if model["verdict"] == "reject" and decision["route"] in [
        "accept_plan",
        "rebuild_once",
    ]:
        raise ValueError("REJECT_CANNOT_BE_AUTO_REPAIRED")
    if decision["route"] == "rebuild_once":
        if (
            decision["rebuilds_already_reserved"]
            or value["request_stage"] != "plan_check"
            or model["verdict"] != "issue"
        ):
            raise ValueError("ONE_INITIAL_PLAN_REBUILD_ONLY")
        if model["unresolved"] or set(decision["verified_finding_ids"]) != finding_ids:
            raise ValueError("ALL_FINDINGS_MUST_BE_RESOLVED")
        proofs = {p["proof_id"]: p for p in value["proofs"]}
        if len(proofs) != len(value["proofs"]):
            raise ValueError("DUPLICATE_PROOF")
        if (
            not decision["proof_ids"]
            or not decision["verified_finding_ids"]
            or not set(decision["proof_ids"]) <= proofs.keys()
        ):
            raise ValueError("INDEPENDENT_PROOF_REQUIRED")
        if not set(decision["verified_finding_ids"]) <= finding_ids:
            raise ValueError("UNKNOWN_VERIFIED_FINDING")
        confirmed = set()
        for pid in decision["proof_ids"]:
            proof = proofs[pid]
            if (
                proof["verifier_id"] not in plan_verifiers.APPROVED_PLAN_VERIFIERS
                or proof["verifier_version"]
                != plan_verifiers.APPROVED_PLAN_VERIFIERS[proof["verifier_id"]].version
                or not proof["machine_checked"]
                or proof["conclusion"] != "confirmed_local_plan_defect"
            ):
                raise ValueError("VERIFIER_NOT_APPROVED")
            if any(
                proof[k] != binding[k] for k in ["plan_digest", "input_digest", "reference_digest"]
            ):
                raise ValueError("PROOF_BINDING_CHANGED")
            if not set(proof["evidence_anchors"]) <= anchors.keys():
                raise ValueError("UNKNOWN_PROOF_ANCHOR")
            if not set(proof["finding_ids"]) <= finding_ids:
                raise ValueError("UNKNOWN_PROOF_FINDING")
            confirmed.update(proof["finding_ids"])
        if not set(decision["verified_finding_ids"]) <= confirmed:
            raise ValueError("FINDING_NOT_VERIFIED")
        for f in model["findings"]:
            if f["finding_id"] in decision["verified_finding_ids"] and (
                anchors[f["target_anchor"]]["source_kind"] != "plan"
                or f["suggested_action"] != "consider_rebuild"
                or f["category"]
                not in [
                    "plan_internal_conflict",
                    "unsupported_commitment",
                    "coverage_plan_gap",
                ]
            ):
                raise ValueError("WRONG_REPAIR_TARGET")


def record_digest(value: object, kind: str = "record") -> str:
    version = (
        "v2"
        if kind == "record"
        and isinstance(value, dict)
        and value.get("schema_version") == "plan-check-record-v2"
        else "v1"
    )
    return digest("plan-check-" + kind, version, record=value)


def pointer_value(root: Any, pointer: str) -> Any:
    """Resolve strict RFC6901 tokens; never eval, filesystem or an inferred nearby field."""
    if not pointer.startswith("/"):
        raise LearningContractError("PLAN_ANCHOR_INVALID")
    try:
        for token in pointer[1:].split("/"):
            # Reject invalid escape sequences rather than accepting an alias.
            if "~" in token.replace("~0", "").replace("~1", ""):
                raise ValueError
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(root, list):
                if not token.isascii() or not token.isdigit() or str(int(token)) != token:
                    raise ValueError
                root = root[int(token)]
            elif isinstance(root, dict):
                root = root[token]
            else:
                raise ValueError
        return root
    except (ValueError, IndexError, KeyError):
        raise LearningContractError("PLAN_ANCHOR_INVALID") from None


def verify_snapshots(plan: LearningPlanVersion) -> None:
    checks = [
        (plan.plan_digest, digest("plan", "learning-plan-v1", plan=plan.plan_json)),
        (plan.input_digest, digest("input", "learning-input-v1", snapshot=plan.input_snapshot)),
        (
            plan.references_digest,
            digest("references", "learning-references-v1", references=plan.references_snapshot),
        ),
        (plan.policy_digest, digest("policy", plan.policy_version, policy=plan.policy_snapshot)),
    ]
    if any(actual != expected for actual, expected in checks):
        raise LearningContractError("PLAN_SNAPSHOT_CHANGED")


def anchor_text(plan: LearningPlanVersion, anchor: dict[str, Any]) -> str:
    roots = {
        "user_request": plan.input_snapshot,
        "plan": plan.plan_json,
        "reference": plan.references_snapshot,
        "reference_context": plan.input_snapshot,
    }
    field = pointer_value(roots[anchor["source_kind"]], anchor["json_pointer"])
    if not isinstance(field, str):
        raise LearningContractError("PLAN_ANCHOR_NOT_TEXT")
    raw = field.encode("utf-8")
    start, end = anchor["start_utf8"], anchor["end_utf8"]
    try:
        if not 0 <= start < end <= len(raw):
            raise ValueError
        raw[:start].decode("utf-8")
        raw[end:].decode("utf-8")
        return raw[start:end].decode("utf-8")
    except (ValueError, UnicodeError):
        raise LearningContractError("PLAN_ANCHOR_RANGE_INVALID") from None


def verify_review_input(
    plan: LearningPlanVersion,
    operation_id: UUID,
    expected_binding: dict[str, Any] | None = None,
) -> None:
    """Mechanical checks before any Provider request. Semantic truth is not inferred."""
    from app.services.learning_policy import POLICY_VERSION, active_policy_digest

    verify_snapshots(plan)
    if (
        not all(
            isinstance(v, UUID)
            for v in (
                plan.id,
                plan.user_id,
                plan.learning_unit_id,
                plan.origin_operation_id,
                operation_id,
            )
        )
        or type(plan.version) is not int
        or plan.version < 1
        or plan.schema_version != "learning-plan-v1"
        or plan.policy_version != POLICY_VERSION
        or plan.policy_digest != active_policy_digest()
    ):
        raise LearningContractError("PLAN_REVIEW_BINDING_INVALID")
    if expected_binding is None:
        if operation_id != plan.origin_operation_id:
            raise LearningContractError("PLAN_REVIEW_BINDING_INVALID")
    elif expected_binding != dict(
        owner_id=plan.user_id,
        unit_id=plan.learning_unit_id,
        operation_id=operation_id,
        plan_id=plan.id,
        origin_operation_id=plan.origin_operation_id,
        plan_version=plan.version,
        plan_digest=plan.plan_digest,
        input_digest=plan.input_digest,
        reference_digest=plan.references_digest,
        policy_digest=plan.policy_digest,
    ):
        raise LearningContractError("PLAN_REVIEW_BINDING_INVALID")
    snapshot = cast(dict[str, Any], plan.input_snapshot)
    if "references" in snapshot and canonical(snapshot["references"]) != canonical(
        plan.references_snapshot
    ):
        raise LearningContractError("PLAN_REFERENCE_BINDING_MISMATCH")
    metadata = snapshot.get("metadata", {})
    fields = (
        "node_id",
        "graph_version",
        "graph_digest",
        "profile_version",
        "profile_evidence_digest",
        "code_language",
        "goal",
    )
    if not isinstance(metadata, dict) or any(
        k in metadata and plan.plan_json.get(k) != metadata[k] for k in fields
    ):
        raise LearningContractError("PLAN_METADATA_BINDING_MISMATCH")
    plan_value = cast(dict[str, Any], plan.plan_json)
    node_values = snapshot.get(
        "node_ids", [plan_value["node_id"], *plan_value["prerequisite_node_ids"]]
    )
    if not isinstance(node_values, list) or not all(isinstance(n, str) for n in node_values):
        raise LearningContractError("PLAN_METADATA_BINDING_MISMATCH")
    nodes = set(node_values)
    validate_plan(plan.plan_json, node_ids=nodes, references=plan.references_snapshot)
    reference = snapshot.get("reference_context")
    source = reference.get("source") if isinstance(reference, dict) else None
    if isinstance(source, dict) and "reference_id" in source:
        match = plan.references_snapshot.get(source["reference_id"])
        if not isinstance(match, dict) or any(
            source[k] != match.get(k) for k in ("reference_id", "version", "digest") if k in source
        ):
            raise LearningContractError("PLAN_REFERENCE_BINDING_MISMATCH")
        if source["reference_id"].startswith("graph-node:"):
            node = reference.get("node") if isinstance(reference, dict) else None
            if (
                not isinstance(node, dict)
                or node.get("id") != plan.plan_json["node_id"]
                or source.get("version") != plan.plan_json["graph_version"]
                or source["reference_id"] != f"graph-node:{source.get('version')}:{node.get('id')}"
                or source.get("digest") != digest("graph-node", "graph-reference-v1", node=node)
            ):
                raise LearningContractError("PLAN_REFERENCE_BINDING_MISMATCH")


async def owned_review_binding(
    db: AsyncSession,
    plan: LearningPlanVersion,
    *,
    owner_id: UUID,
    operation_id: UUID,
) -> dict[str, Any]:
    """Check current owner/operation/plan/version in SQL before external review, including reuse."""
    op = (
        await db.execute(
            select(
                LearningOperation.user_id,
                LearningOperation.learning_unit_id,
                LearningOperation.status,
            ).where(LearningOperation.id == operation_id)
        )
    ).one_or_none()
    latest = (
        await db.execute(
            select(
                LearningPlanVersion.id,
                LearningPlanVersion.version,
                LearningPlanVersion.origin_operation_id,
                LearningPlanVersion.plan_digest,
                LearningPlanVersion.input_digest,
                LearningPlanVersion.references_digest,
                LearningPlanVersion.policy_digest,
            )
            .where(
                LearningPlanVersion.user_id == owner_id,
                LearningPlanVersion.learning_unit_id == plan.learning_unit_id,
            )
            .order_by(LearningPlanVersion.version.desc())
            .limit(1)
        )
    ).one_or_none()
    if (
        op is None
        or latest is None
        or op.user_id != owner_id
        or op.learning_unit_id != plan.learning_unit_id
        or op.status not in ("accepted", "running")
    ):
        raise LearningContractError("PLAN_REVIEW_BINDING_INVALID")
    binding = dict(
        owner_id=owner_id,
        unit_id=op.learning_unit_id,
        operation_id=operation_id,
        plan_id=latest.id,
        origin_operation_id=latest.origin_operation_id,
        plan_version=latest.version,
        plan_digest=latest.plan_digest,
        input_digest=latest.input_digest,
        reference_digest=latest.references_digest,
        policy_digest=latest.policy_digest,
    )
    verify_review_input(plan, operation_id, binding)
    return binding


async def save_plan_check(db: AsyncSession, record: object) -> PlanCheck:
    value = validate_evidence(record)
    b = value["binding"]
    plan = await db.get(LearningPlanVersion, UUID(b["plan_id"]))
    op = await db.get(LearningOperation, UUID(b["operation_id"]))
    if (
        plan is None
        or op is None
        or str(plan.user_id) != b["owner_id"]
        or str(plan.learning_unit_id) != b["unit_id"]
        or op.user_id != plan.user_id
        or op.learning_unit_id != plan.learning_unit_id
        or plan.version != b["plan_version"]
        or any(
            b[k] != expected
            for k, expected in [
                ("plan_digest", plan.plan_digest),
                ("input_digest", plan.input_digest),
                ("reference_digest", plan.references_digest),
                ("policy_digest", plan.policy_digest),
            ]
        )
    ):
        raise LearningContractError("PLAN_CHECK_BINDING_INVALID")
    verify_snapshots(plan)
    roots = {
        "user_request": plan.input_snapshot,
        "plan": plan.plan_json,
        "reference": plan.references_snapshot,
        "reference_context": plan.input_snapshot,
    }
    for a in value["anchor_catalog"]:
        field = pointer_value(roots[a["source_kind"]], a["json_pointer"])
        if not isinstance(field, str):
            raise LearningContractError("PLAN_ANCHOR_NOT_TEXT")
        raw = field.encode("utf-8")
        start, end = a["start_utf8"], a["end_utf8"]
        try:
            if not 0 <= start < end <= len(raw):
                raise ValueError
            # Both boundaries must be valid UTF-8 character boundaries.
            raw[:start].decode("utf-8")
            raw[start:end].decode("utf-8")
            raw[end:].decode("utf-8")
        except (ValueError, UnicodeError):
            raise LearningContractError("PLAN_ANCHOR_RANGE_INVALID") from None
    row = PlanCheck(
        id=UUID(value["check_id"]),
        user_id=plan.user_id,
        learning_unit_id=plan.learning_unit_id,
        operation_id=op.id,
        plan_id=plan.id,
        stage=value["request_stage"],
        record_digest=record_digest(value),
        record=value,
        created_at=datetime.fromisoformat(value["created_at"]),
    )
    db.add(row)
    await db.flush()
    return row


async def owned_plan_check(db: AsyncSession, *, owner_id: UUID, check_id: UUID) -> PlanCheck:
    row = await db.scalar(
        select(PlanCheck).where(PlanCheck.id == check_id, PlanCheck.user_id == owner_id)
    )
    if row is None:
        raise LearningContractError("PLAN_CHECK_NOT_FOUND")
    if row.record_digest != record_digest(row.record):
        raise LearningContractError("PLAN_CHECK_CHANGED")
    return row


async def save_plan_resolution(
    db: AsyncSession,
    *,
    owner_id: UUID,
    value: object,
    trusted_reviewer_id: str,
    trusted_identity_source: str,
) -> PlanCheckResolution:
    """Internal storage; trusted OS authorization must precede this call, never a public body."""
    v = validate_evidence(value, "resolution")
    if v["reviewer_id"] != trusted_reviewer_id or v["identity_source"] != trusted_identity_source:
        raise LearningContractError("PLAN_RESOLUTION_IDENTITY_INVALID")
    parent = await owned_plan_check(db, owner_id=owner_id, check_id=UUID(v["check_id"]))
    if v["expected_check_digest"] != parent.record_digest:
        raise LearningContractError("PLAN_CHECK_CHANGED")
    await lock_learning_owner(db, owner_id)
    previous = await db.scalar(
        select(PlanCheckResolution).where(
            PlanCheckResolution.user_id == owner_id,
            PlanCheckResolution.idempotency_key == v["idempotency_key"],
        )
    )
    if previous is not None:
        keys = [
            "check_id",
            "expected_check_digest",
            "reviewer_id",
            "identity_source",
            "kind",
            "reason",
        ]
        if any(previous.record[k] != v[k] for k in keys):
            raise LearningContractError("PLAN_RESOLUTION_IDEMPOTENCY_CONFLICT")
        return previous
    row = PlanCheckResolution(
        id=UUID(v["resolution_id"]),
        user_id=parent.user_id,
        learning_unit_id=parent.learning_unit_id,
        operation_id=parent.operation_id,
        plan_id=parent.plan_id,
        check_id=parent.id,
        idempotency_key=v["idempotency_key"],
        record=v,
        record_digest=record_digest(v, "resolution"),
        created_at=datetime.fromisoformat(v["created_at"]),
    )
    db.add(row)
    await db.flush()
    return row


async def save_rebuild_event(
    db: AsyncSession, *, owner_id: UUID, record: object
) -> PlanRebuildEvent:
    """Evidence only. Empty verifier registry makes reservation impossible in this version."""
    v = validate_evidence(record, "rebuild_event")
    parent = await owned_plan_check(db, owner_id=owner_id, check_id=UUID(v["trigger_check_id"]))
    validated = validate_evidence(parent.record)
    b = validated["binding"]
    if (
        validated["server_assessment"]["route"] != "rebuild_once"
        or v["operation_id"] != b["operation_id"]
        or v["prior_plan_id"] != b["plan_id"]
        or any(
            v[k] != b[target]
            for k, target in [
                ("prior_plan_digest", "plan_digest"),
                ("input_digest", "input_digest"),
                ("reference_digest", "reference_digest"),
                ("policy_digest", "policy_digest"),
            ]
        )
        or v["proof_ids"] != validated["server_assessment"]["proof_ids"]
    ):
        raise LearningContractError("PLAN_REBUILD_NOT_AUTHORIZED")
    if v["event_type"] == "reserved":
        if v["new_plan_id"] is not None or v["new_plan_digest"] is not None:
            raise LearningContractError("PLAN_REBUILD_EVENT_INVALID")
    else:
        prior = await db.scalar(
            select(PlanRebuildEvent).where(
                PlanRebuildEvent.operation_id == parent.operation_id,
                PlanRebuildEvent.event_type == "reserved",
            )
        )
        if prior is None or prior.check_id != parent.id:
            raise LearningContractError("PLAN_REBUILD_RESERVATION_MISSING")
        if v["event_type"] == "completed":
            new = (
                await db.get(LearningPlanVersion, UUID(v["new_plan_id"]))
                if v["new_plan_id"]
                else None
            )
            old = await db.get(LearningPlanVersion, parent.plan_id)
            if (
                new is None
                or old is None
                or new.version != old.version + 1
                or new.origin_operation_id != parent.operation_id
                or new.user_id != parent.user_id
                or new.learning_unit_id != parent.learning_unit_id
                or new.plan_digest != v["new_plan_digest"]
                or new.input_digest != b["input_digest"]
                or new.references_digest != b["reference_digest"]
                or new.policy_digest != b["policy_digest"]
            ):
                raise LearningContractError("PLAN_REBUILD_BINDING_CHANGED")
        elif v["new_plan_id"] is not None or v["new_plan_digest"] is not None:
            raise LearningContractError("PLAN_REBUILD_EVENT_INVALID")
    row = PlanRebuildEvent(
        id=UUID(v["event_id"]),
        user_id=parent.user_id,
        learning_unit_id=parent.learning_unit_id,
        operation_id=parent.operation_id,
        plan_id=parent.plan_id,
        check_id=parent.id,
        event_type=v["event_type"],
        record=v,
        record_digest=record_digest(v, "rebuild_event"),
        created_at=datetime.fromisoformat(v["created_at"]),
    )
    db.add(row)
    await db.flush()
    return row
