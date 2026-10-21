"""Owner/target/intent-bound reuse of currently qualified candidates, never media authority."""

import asyncio
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.animation_dsl_review import (
    DSLReference,
    DSLReviewOutcome,
    GenerationSource,
    ModelSource,
    binding,
    canonical,
    digest,
)
from app.models.animation_dsl import DSLCandidate, DSLCandidateRevocation, DSLReviewRecord
from app.services.animation_dsl_candidates import (
    DSLCandidateUnavailable,
    policy_manifest,
    qualified_candidate,
)
from app.services.animation_dsl_compiler import compile_animation_dsl
from app.services.animation_intent import VideoIntent
from app.services.knowledge_graph import KnowledgeGraphRepository


class ReviewedDSLCandidateCache:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        graph: KnowledgeGraphRepository,
        *,
        owner: UUID,
        expected_sources: tuple[ModelSource, ModelSource] | None = None,
    ):
        self.factory, self.graph, self.owner = factory, graph, owner
        self.expected_sources = expected_sources

    async def lookup(self, intent: VideoIntent, reference: DSLReference) -> DSLReviewOutcome | None:
        payload = intent.payload()
        async with self.factory() as db:
            records = (
                await db.execute(
                    select(DSLCandidate.id, DSLReviewRecord)
                    .join(DSLReviewRecord, DSLCandidate.review_id == DSLReviewRecord.id)
                    .where(
                        DSLCandidate.user_id == self.owner,
                        DSLCandidate.policy_id == digest(policy_manifest()),
                        DSLCandidate.id.not_in(select(DSLCandidateRevocation.candidate_id)),
                        DSLReviewRecord.evidence["reference"].astext == reference.sha256,
                        DSLReviewRecord.evidence["animation_intent"] == payload,
                    )
                    .order_by(DSLCandidate.created_at.desc(), DSLCandidate.id.desc())
                    .limit(4)
                )
            ).all()
            for cid, record in records:
                try:
                    candidate = await qualified_candidate(
                        db, self.graph, owner=self.owner, candidate_id=cid
                    )
                    compiled = await asyncio.to_thread(
                        compile_animation_dsl,
                        candidate.canonical_dsl,
                        knowledge_point_id=reference.knowledge_point_id,
                    )
                    data = record.evidence["generation"]
                    generation = GenerationSource(
                        ModelSource(**data["source"]),
                        data["prompt_sha256"],
                        data["sampling_sha256"],
                    )
                    source = ModelSource(**record.evidence["review_source"])
                    if self.expected_sources is not None and (generation.source, source) != (
                        self.expected_sources
                    ):
                        continue
                    if self.expected_sources is not None:
                        from app.agents.animation_dsl_generation import SAMPLING

                        if generation.sampling_sha256 != digest(SAMPLING):
                            continue
                    bound = binding(compiled, reference, generation, canonical(payload))
                    reviewed = digest(
                        {
                            "binding": bound,
                            "verdict": "pass",
                            "issues": [],
                            "source": asdict(source),
                        }
                    )
                    if (
                        bound != record.binding_sha256
                        or reviewed != record.review_sha256
                        or record.issue_positions
                        or compiled.identity_sha256 != record.evidence["identity"]
                    ):
                        continue
                    return DSLReviewOutcome(
                        compiled,
                        reference,
                        generation,
                        source,
                        "pass",
                        (),
                        bound,
                        reviewed,
                        animation_intent_json=canonical(payload),
                    )
                except (DSLCandidateUnavailable, ValueError, KeyError, TypeError, OSError):
                    continue
        return None
