"""The two exact reviewed archives admitted by the T120 replay entry."""

from dataclasses import dataclass
from hashlib import sha256

from app.services.free_course_snapshots import SnapshotError, canonical


@dataclass(frozen=True)
class Archive:
    frozen_commit: str
    batch: str
    plan_source: str
    historical_stage: str
    candidate_digest: str
    request_sha256: str
    raw_sha256: str
    review_sha256: str
    revision_approval_sha256: str | None = None


ARCHIVES = {
    "head": Archive(
        "655d25bced995097a014d0dce2e0757c48b3c3f2",
        "head-empty-citation-revision-r01",
        "model_planned",
        "authorized_citation_revision",
        "4fffbdcf36878edcb3ef2364100d03ef10b0a6dbac8835bdc64138db32c2fd74",
        "0f7a1769b5cd745401562abb171ea365a303d03e4a9443f8e698ed58ef25563e",
        "ba1819be3d4113c1edce510b11601d113cbde9db489cb273674f962d6e7921c1",
        "11a09b1f67bc1bf943515fdc3e1f9f65e50d25996d22139e9f291821680c1ddd",
        "2e24ccf2b8f0ed3b66c3771286f0fd97d4739dd8798c28a0b315136ddbc17faa",
    ),
    "stack": Archive(
        "d1d4c2da74f44fdcc3e59ca012a69553d3b788d6",
        "stack-lifo-deepseek-r01",
        "fixed_outline",
        "first_draft",
        "5ce963dc990e2d7e7dd93853fef3ff390ed26bdd145e15551d74ec426e3abd50",
        "b2fb7641186f5153707e63d3e6d37824461573f8b77883c3aee7997dd512cafe",
        "9135083cdab6fbcd598cb5e86e4cb56756e6bf47ec3b918cdfea6b6fe32f0c5b",
        "496c17c6f6efc5d786cb5e04c0d4833c16f247801b7bd064222b0d9d4a02a9ef",
    ),
}


def verified_course(topic, record, review):
    """Reapply the existing topic checks and pin the historical review, request and response."""
    archive = ARCHIVES.get(topic)
    if archive is None:
        raise SnapshotError("TRIAL_REPLAY_TOPIC")
    candidate = record.get("candidate", record)
    if candidate.get("candidate_digest") != archive.candidate_digest:
        raise SnapshotError("TRIAL_REPLAY_CANDIDATE")
    if (
        review.get("candidate_digest") != archive.candidate_digest
        or sha256(canonical(review)).hexdigest() != archive.review_sha256
    ):
        raise SnapshotError("TRIAL_REPLAY_REVIEW")
    receipt = record.get("receipt", {})
    if receipt.get("raw_sha256") != archive.raw_sha256:
        raise SnapshotError("TRIAL_REPLAY_RESPONSE")

    if topic == "head":
        from app.services import head_course_citation_revision as citation
        from app.services import head_course_evidence_publication as publication

        if (
            record.get("protocol_version") != citation.VERSION
            or candidate.get("parent_digest") != citation.PARENT
            or record.get("attempt", {}).get("evidence_kind") != "actual_provider_response"
            or sha256(canonical(record.get("approval"))).hexdigest()
            != archive.revision_approval_sha256
            or sha256(canonical(record["request"])).hexdigest() != archive.request_sha256
        ):
            raise SnapshotError("TRIAL_REPLAY_REVISION")
        # Includes the original scope/approval, frozen parent, single-leaf merge and full review.
        assembled = publication.assembled(record, review)
        goal, plan = (candidate["payload"][key] for key in ("original_goal", "plan"))
    else:
        from app.services import stack_course_materials as materials
        from app.services import stack_course_publication as publication

        if (
            receipt.get("request_sha256") != archive.request_sha256
            or sha256(canonical(materials.request())).hexdigest() != archive.request_sha256
            or record.get("context", {}).get("evidence_kind") != "actual_provider_response"
            or record != publication.candidate(record["context"], record["raw_output"], receipt)
        ):
            raise SnapshotError("TRIAL_REPLAY_BINDING")
        assembled = publication.assembly(record, review)
        goal, plan = materials.GOAL, materials.outline()

    return goal, plan, assembled
