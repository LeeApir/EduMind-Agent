"""Server-bound references and immutable candidate persistence with current qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.animation_dsl_review import (
    PROMPT_SHA256,
    REVIEW_SCHEMA_SHA256,
    REVIEW_VERSION,
    REVIEWER_SHA256,
    DSLReference,
    DSLReviewOutcome,
    binding,
    canonical,
    digest,
)
from app.models.animation_dsl import (
    DSLCandidate,
    DSLCandidateRevocation,
    DSLPolicy,
    DSLPolicyRevocation,
    DSLReviewRecord,
)
from app.models.catalog import CatalogRelease
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_dsl_compiler import (
    COMPILER_POLICY_SHA256,
    COMPILER_SHA256,
    COMPILER_VERSION,
    POLICY,
    STATIC_SHA256,
    compile_animation_dsl,
)
from app.services.animation_dsl_validation import POLICY_SHA256, SCHEMA_SHA256, VALIDATOR_SHA256
from app.services.catalog_package import CatalogError
from app.services.catalog_publication import release_package
from app.services.knowledge_graph import KnowledgeGraphRepository


class DSLCandidateUnavailable(ValueError):
    def __init__(self) -> None:
        super().__init__("DSL_CANDIDATE_UNAVAILABLE")


def policy_manifest() -> dict[str, object]:
    # Explicit admission freezes exact implementation and renderer versions. No secret/config URL.
    return {
        "version": "animation-dsl-admission-v1",
        "candidate_store": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "review_gateway": hashlib.sha256(
            (Path(__file__).parent / "animation_dsl_review_gateway.py").read_bytes()
        ).hexdigest(),
        "dsl_renderer": hashlib.sha256(
            (Path(__file__).parent / "animation_dsl_renderer.py").read_bytes()
        ).hexdigest(),
        "dsl_worker": hashlib.sha256(
            (Path(__file__).parents[1] / "workers/dsl_render.py").read_bytes()
        ).hexdigest(),
        "dsl_runner": hashlib.sha256(
            (Path(__file__).parents[1] / "dsl_runtime/container_runner.py").read_bytes()
        ).hexdigest(),
        "dsl_media_verifier": hashlib.sha256(
            (Path(__file__).parents[1] / "dsl_runtime/verify_media.py").read_bytes()
        ).hexdigest(),
        "candidate_cache": hashlib.sha256(
            (Path(__file__).parent / "animation_dsl_candidate_cache.py").read_bytes()
        ).hexdigest(),
        "intent_validator": hashlib.sha256(
            (Path(__file__).parent / "animation_intent.py").read_bytes()
        ).hexdigest(),
        "generator": hashlib.sha256(
            (Path(__file__).parents[1] / "agents/animation_dsl_generation.py").read_bytes()
        ).hexdigest(),
        "generation_gateway": hashlib.sha256(
            (Path(__file__).parent / "animation_dsl_generation_gateway.py").read_bytes()
        ).hexdigest(),
        "generation_prompt": hashlib.sha256(
            (Path(__file__).parents[3] / "data/animation_dsl/generate-v1/prompt.md").read_bytes()
        ).hexdigest(),
        "video_planner": hashlib.sha256(
            (Path(__file__).parent / "video_dsl_generation.py").read_bytes()
        ).hexdigest(),
        "schema": SCHEMA_SHA256,
        "validator": VALIDATOR_SHA256,
        "semantic_policy": POLICY_SHA256,
        "compiler_version": COMPILER_VERSION,
        "compiler": COMPILER_SHA256,
        "static": STATIC_SHA256,
        "compiler_policy": COMPILER_POLICY_SHA256,
        "review_version": REVIEW_VERSION,
        "review_schema": REVIEW_SCHEMA_SHA256,
        "review_prompt": PROMPT_SHA256,
        "reviewer": REVIEWER_SHA256,
        "runtime": POLICY,
        "python_version": platform.python_version(),
    }


async def admit_current_policy(db: AsyncSession) -> str:
    """Explicit trusted operator action; never called automatically by candidate save/read."""
    manifest = policy_manifest()
    key = digest(manifest)
    await db.execute(
        insert(DSLPolicy)
        .values(id=key, manifest=manifest)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    if await db.get(DSLPolicyRevocation, key) is not None:
        raise DSLCandidateUnavailable()
    return key  # Caller owns the transaction.


async def _target(
    db: AsyncSession, *, owner: UUID, unit_id: UUID, scene_id: UUID, version: int, lock: bool
) -> tuple[LearningUnit, LearningScene]:
    # Read to discover immutable release id, then lock release -> unit -> scene.
    unit = await db.scalar(
        select(LearningUnit)
        .where(LearningUnit.id == unit_id, LearningUnit.user_id == owner)
        .execution_options(populate_existing=True)
    )
    if unit is None:
        raise DSLCandidateUnavailable()
    release_id = unit.catalog_release_id
    if release_id is not None:
        release = await db.get(
            CatalogRelease, release_id, with_for_update=lock, populate_existing=True
        )
        try:
            if release is None:
                raise DSLCandidateUnavailable()
            release_package(release)
        except CatalogError:
            raise DSLCandidateUnavailable() from None
    if lock:
        unit = await db.scalar(
            select(LearningUnit)
            .where(LearningUnit.id == unit_id, LearningUnit.user_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    scene_query = (
        select(LearningScene)
        .where(
            LearningScene.id == scene_id,
            LearningScene.learning_unit_id == unit_id,
            LearningScene.version == version,
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        scene_query = scene_query.with_for_update()
    scene = await db.scalar(scene_query)

    if (
        unit is None
        or unit.catalog_release_id != release_id
        or unit.status != "ready"
        or not unit.knowledge_point_id
        or scene is None
        or scene.generation_status != "complete"
        or scene.review_status != "passed"
    ):
        raise DSLCandidateUnavailable()
    return unit, scene


async def build_dsl_reference(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    unit_id: UUID,
    scene_id: UUID,
    version: int,
    lock: bool = False,
) -> DSLReference:
    unit, scene = await _target(
        db, owner=owner, unit_id=unit_id, scene_id=scene_id, version=version, lock=lock
    )
    node = graph.get_node(unit.knowledge_point_id or "")
    if node is None:
        raise DSLCandidateUnavailable()
    prerequisites = [graph.get_node(key) for key in node.prerequisites]
    if any(item is None for item in prerequisites):
        raise DSLCandidateUnavailable()
    target = {
        "unit_id": str(unit.id),
        "unit_version": unit.version,
        "objective_sha256": digest(unit.learning_objectives),
        "snapshot_sha256": digest(scene.input_snapshot),
        "scene_id": str(scene.id),
        "scene_version": scene.version,
        "scene_key": scene.scene_key,
        "scene_type": scene.scene_type,
        "knowledge_point_id": unit.knowledge_point_id,
        "release_id": str(unit.catalog_release_id) if unit.catalog_release_id else None,
    }
    graph_hash = digest(
        {
            "version": graph.graph_version,
            "nodes": [asdict(n) for n in graph.all_nodes()],
            "relations": [asdict(r) for r in graph.all_relations()],
        }
    )
    payload = {
        "context_version": "animation-dsl-reference-v1",
        "target": target,
        "graph_version": graph.graph_version,
        "node": asdict(node),
        "prerequisites": [asdict(n) for n in prerequisites if n],
        "known_profile": {},
    }
    result = DSLReference(canonical(payload), digest(target), graph_hash, node.id)
    try:
        result.payload()  # Missing or oversized context is never truncated.
    except ValueError:
        raise DSLCandidateUnavailable() from None
    return result


async def _policy(db: AsyncSession, key: str, *, lock: bool) -> DSLPolicy:
    policy = await db.get(DSLPolicy, key, with_for_update=lock, populate_existing=True)
    if (
        policy is None
        or key != digest(policy_manifest())
        or policy.manifest != policy_manifest()
        or await db.get(DSLPolicyRevocation, key) is not None
    ):
        raise DSLCandidateUnavailable()
    return policy


def evidence(outcome: DSLReviewOutcome) -> dict[str, object]:
    compiled, valid = outcome.compiled, outcome.compiled.validated
    return {
        "animation_intent": json.loads(outcome.animation_intent_json)
        if outcome.animation_intent_json
        else None,
        "dsl": valid.dsl_sha256,
        "trace": valid.trace_sha256,
        "schema": valid.schema_sha256,
        "validator": valid.validator_sha256,
        "semantic_policy": valid.policy_sha256,
        "compiler": compiled.compiler_sha256,
        "compiler_policy": compiled.compiler_policy_sha256,
        "compiler_version": compiled.compiler_version,
        "compiled_source": compiled.source_sha256,
        "ast": compiled.ast_sha256,
        "subtitle": compiled.subtitles_sha256,
        "identity": compiled.identity_sha256,
        "reference": outcome.reference.sha256,
        "target": outcome.reference.target_sha256,
        "graph": outcome.reference.graph_sha256,
        "generation": asdict(outcome.generation_source),
        "review_source": asdict(outcome.review_source) if outcome.review_source else None,
        "review_version": REVIEW_VERSION,
        "review_prompt": PROMPT_SHA256,
        "review_schema": REVIEW_SCHEMA_SHA256,
        "reviewer": REVIEWER_SHA256,
    }


async def save_dsl_review(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    unit_id: UUID,
    scene_id: UUID,
    version: int,
    outcome: DSLReviewOutcome,
) -> tuple[DSLReviewRecord, DSLCandidate | None]:
    # Recompute outside qualification locks; a dataclass/old pass is not admission authority.
    checked = await asyncio.to_thread(
        compile_animation_dsl,
        outcome.compiled.validated.canonical_json,
        knowledge_point_id=outcome.reference.knowledge_point_id,
    )
    if (
        checked != outcome.compiled
        or binding(
            checked, outcome.reference, outcome.generation_source, outcome.animation_intent_json
        )
        != outcome.binding_sha256
        or outcome.review_sha256
        != digest(
            {
                "binding": outcome.binding_sha256,
                "verdict": outcome.verdict,
                "issues": [asdict(i) for i in outcome.issues],
                "source": asdict(outcome.review_source) if outcome.review_source else None,
            }
        )
        or outcome.verdict not in {"pass", "revise", "reject", "unavailable"}
        or outcome.approved
        and (outcome.issues or outcome.review_source is None)
    ):
        raise DSLCandidateUnavailable()
    reference = await build_dsl_reference(
        db, graph, owner=owner, unit_id=unit_id, scene_id=scene_id, version=version, lock=True
    )
    if reference != outcome.reference:
        raise DSLCandidateUnavailable()
    policy_id = digest(policy_manifest())
    await _policy(db, policy_id, lock=True)
    record = DSLReviewRecord(
        id=uuid4(),
        user_id=owner,
        learning_unit_id=unit_id,
        scene_id=scene_id,
        scene_version=version,
        verdict=outcome.verdict,
        binding_sha256=outcome.binding_sha256,
        review_sha256=outcome.review_sha256,
        evidence=evidence(outcome),
        error_code=outcome.error_code,
        issue_positions=[
            {"area": i.area, "severity": i.severity, "action_index": i.action_index}
            for i in outcome.issues
        ],
    )  # No failed candidate/reviewer free text.
    db.add(record)
    await db.flush()
    candidate = None
    if outcome.approved:
        candidate = DSLCandidate(
            id=uuid4(),
            user_id=owner,
            learning_unit_id=unit_id,
            scene_id=scene_id,
            scene_version=version,
            review_id=record.id,
            verdict="pass",
            binding_sha256=record.binding_sha256,
            policy_id=policy_id,
            canonical_dsl=checked.validated.canonical_json,
            trace_json=checked.validated.trace_json,
            dsl_sha256=checked.validated.dsl_sha256,
            trace_sha256=checked.validated.trace_sha256,
        )
        db.add(candidate)
        await db.flush()
    return record, candidate  # No commit; T028 handoff may compose one atomic transaction.


async def qualified_candidate(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    candidate_id: UUID,
    lock: bool = False,
) -> DSLCandidate:
    candidate = await db.scalar(
        select(DSLCandidate).where(DSLCandidate.id == candidate_id, DSLCandidate.user_id == owner)
    )
    if candidate is None:
        raise DSLCandidateUnavailable()
    reference = await build_dsl_reference(
        db,
        graph,
        owner=owner,
        unit_id=candidate.learning_unit_id,
        scene_id=candidate.scene_id,
        version=candidate.scene_version,
        lock=lock,
    )
    if lock:
        candidate = await db.get(
            DSLCandidate, candidate_id, with_for_update=True, populate_existing=True
        )
        if candidate is None:
            raise DSLCandidateUnavailable()
    await _policy(db, candidate.policy_id, lock=lock)
    record = await db.get(DSLReviewRecord, candidate.review_id)
    if (
        record is None
        or record.verdict != "pass"
        or record.evidence.get("reference") != reference.sha256
        or record.evidence.get("graph") != reference.graph_sha256
        or record.evidence.get("dsl") != candidate.dsl_sha256
        or record.evidence.get("trace") != candidate.trace_sha256
        or await db.get(DSLCandidateRevocation, candidate.id) is not None
    ):
        raise DSLCandidateUnavailable()
    return candidate


async def revoke_candidate(
    db: AsyncSession,
    graph: KnowledgeGraphRepository,
    *,
    owner: UUID,
    candidate_id: UUID,
    reason: str = "SAFETY_WITHDRAWN",
) -> None:
    if reason not in {"SAFETY_WITHDRAWN", "VERSION_RETIRED"}:
        raise DSLCandidateUnavailable()
    # Target -> candidate -> policy. No Job/cache locks; revocation is permanent and idempotent.
    candidate = await db.scalar(
        select(DSLCandidate).where(DSLCandidate.id == candidate_id, DSLCandidate.user_id == owner)
    )
    if candidate is None:
        raise DSLCandidateUnavailable()
    await _target(
        db,
        owner=owner,
        unit_id=candidate.learning_unit_id,
        scene_id=candidate.scene_id,
        version=candidate.scene_version,
        lock=True,
    )
    await db.get(DSLCandidate, candidate_id, with_for_update=True)
    await db.get(DSLPolicy, candidate.policy_id, with_for_update=True)
    await db.execute(
        insert(DSLCandidateRevocation)
        .values(candidate_id=candidate_id, user_id=owner, reason_code=reason)
        .on_conflict_do_nothing(index_elements=["candidate_id"])
    )


async def revoke_policy(
    db: AsyncSession, policy_id: str, *, reason: str = "SAFETY_WITHDRAWN"
) -> None:
    if reason not in {"SAFETY_WITHDRAWN", "VERSION_RETIRED"}:
        raise DSLCandidateUnavailable()
    if await db.get(DSLPolicy, policy_id, with_for_update=True) is None:
        raise DSLCandidateUnavailable()
    await db.execute(
        insert(DSLPolicyRevocation)
        .values(policy_id=policy_id, reason_code=reason)
        .on_conflict_do_nothing(index_elements=["policy_id"])
    )
