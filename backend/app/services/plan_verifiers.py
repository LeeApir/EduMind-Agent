"""No production semantic verifier is approved. Test-only injection is not approval."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import uuid4

from app.models.learning_plan import LearningPlanVersion
from app.services.learning_contract import LearningContractError, digest


@dataclass(frozen=True)
class VerifiedDefect:
    finding_ids: tuple[str, ...]
    evidence_anchors: tuple[str, ...]
    premises: object


class PlanVerifier(Protocol):
    version: str

    def verify(
        self, plan: LearningPlanVersion, record: dict[str, Any]
    ) -> VerifiedDefect | None: ...


APPROVED_PLAN_VERIFIERS: Mapping[str, PlanVerifier] = MappingProxyType({})


def apply_verifiers(plan: LearningPlanVersion, record: dict[str, Any]) -> dict[str, Any]:
    """Only trusted registered code can mint proofs, not the model result or an env setting."""
    ids = plan.policy_snapshot.get("approved_plan_verifiers", [])
    if not isinstance(ids, list) or set(ids) != set(APPROVED_PLAN_VERIFIERS):
        raise LearningContractError("PLAN_VERIFIER_POLICY_MISMATCH")
    if record["binding"]["operation_id"] != str(plan.origin_operation_id):
        return record  # Reusing an already taught plan is not an initial pre-content correction.
    versions = {key: verifier.version for key, verifier in APPROVED_PLAN_VERIFIERS.items()}
    if plan.policy_snapshot.get("approved_plan_verifier_versions", {}) != versions:
        raise LearningContractError("PLAN_VERIFIER_POLICY_MISMATCH")
    m = record["model_result"]
    if (
        record["request_stage"] != "plan_check"
        or m["verdict"] != "issue"
        or m["unresolved"]
        or m["coverage"]["unchecked"]
        or not m["findings"]
    ):
        return record
    by_anchor = {a["anchor_id"]: a for a in record["anchor_catalog"]}
    if any(
        by_anchor.get(f["target_anchor"], {}).get("source_kind") != "plan"
        or f["suggested_action"] != "consider_rebuild"
        or f["category"]
        not in ("plan_internal_conflict", "unsupported_commitment", "coverage_plan_gap")
        for f in m["findings"]
    ):
        return record
    proofs: list[dict[str, Any]] = []
    for verifier_id, verifier in APPROVED_PLAN_VERIFIERS.items():
        result = verifier.verify(plan, record)
        if result is None:
            continue
        proofs.append(
            dict(
                proof_id=str(uuid4()),
                verifier_id=verifier_id,
                verifier_version=verifier.version,
                plan_digest=plan.plan_digest,
                input_digest=plan.input_digest,
                reference_digest=plan.references_digest,
                finding_ids=list(result.finding_ids),
                evidence_anchors=list(result.evidence_anchors),
                premises_digest=digest(
                    "plan-verifier-premises", verifier.version, premises=result.premises
                ),
                conclusion="confirmed_local_plan_defect",
                machine_checked=True,
            )
        )
    covered = {fid for p in proofs for fid in p["finding_ids"]}
    if covered != {f["finding_id"] for f in m["findings"]}:
        return record
    record["proofs"] = proofs
    record["server_assessment"].update(
        route="rebuild_once",
        reason_codes=["ALL_LOCAL_PLAN_DEFECTS_INDEPENDENTLY_VERIFIED"],
        verified_finding_ids=sorted(covered),
        proof_ids=[p["proof_id"] for p in proofs],
    )
    return record


def verify_proof_sources(plan: LearningPlanVersion, record: dict[str, Any]) -> None:
    """Recompute registered local premises before reserving any repair call."""
    for proof in record["proofs"]:
        verifier = APPROVED_PLAN_VERIFIERS.get(proof["verifier_id"])
        if verifier is None or verifier.version != proof["verifier_version"]:
            raise LearningContractError("PLAN_PROOF_SOURCE_INVALID")
        result = verifier.verify(plan, record)
        if (
            result is None
            or list(result.finding_ids) != proof["finding_ids"]
            or list(result.evidence_anchors) != proof["evidence_anchors"]
            or digest("plan-verifier-premises", verifier.version, premises=result.premises)
            != proof["premises_digest"]
        ):
            raise LearningContractError("PLAN_PROOF_SOURCE_INVALID")
