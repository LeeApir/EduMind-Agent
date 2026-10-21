"""Private evidence and explicit stage adapters for a separately activated admission run."""

import asyncio
import ipaddress
import json
import time
from copy import deepcopy
from dataclasses import asdict
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from acceptance_support.five_hour_runtime import require, write_once
from acceptance_support.plan_admission import (
    CONFIG,
    CandidateGateway,
    CandidateReviewAdapter,
    LaneGateway,
)
from acceptance_support.plan_admission_run import pointer
from acceptance_support.provider_error_decode import safe_fields
from acceptance_support.qwen_review_budget import canonical, sha
from prepare_plan_admission import plan_row
from run_five_hour_acceptance import (  # existing bounded response decoder
    inspect_body,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.hybrid_resource_review import review_once
from app.agents.plan_check import inspect_plan
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.core.config import ProviderSettings
from app.core.database import create_database_engine
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningOperation
from app.models.learning_budget import LearningCorrectionPermit, LearningGenerationAttempt
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review import LearningReviewRecord
from app.models.learning_review_case import LearningReviewCase
from app.models.learning_state import LearningPathVersion
from app.models.plan_check import PlanCheck, PlanRebuildEvent
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.hybrid_learning_publication import current_publication
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_contract import LearningContractError, digest
from app.services.learning_policy import POLICY_VERSION, active_policy_digest
from app.services.learning_review_history import case_review_history
from app.services.learning_stage_gateway import LearningStageGateway
from app.services.owned_learning import published_scenes
from app.services.planned_learning_flow import run_planned_operation
from app.services.provider_gateway import ProviderGateway
from app.services.unit_material import restore_material

DATABASE = "edumind_catalog_plan_admission_r02"


def inputs_for(case):
    s = case["input_snapshot"]
    return PlanInputs(
        s["metadata"],
        s["references"],
        frozenset(s["node_ids"]),
        s["learner_evidence"],
        case["reference_context"],
        teaching_context=s.get("teaching_context"),
    )


class WireTransport(httpx.AsyncBaseTransport):
    """No header persistence, redirect/retry or secret reflection. Adapter pins public target."""

    def __init__(self, context, role, target, inner=None):
        self.context, self.role, self.target = context, role, target
        self.inner = (
            inner if inner is not None else httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        )

    async def handle_async_request(self, request):
        c, cfg = self.context, CONFIG[self.role]
        base = urlsplit(cfg["base_url"])
        body = json.loads(request.content)
        require(
            request.method == "POST"
            and request.url.scheme == "https"
            and request.url.host in self.target.addresses
            and ipaddress.ip_address(request.url.host).is_global
            and (request.url.port or 443) == 443
            and request.url.path == base.path + "/responses"
            and request.headers.get("host") == base.netloc
            and request.extensions.get("sni_hostname") == base.hostname,
            "OUTBOUND_TARGET_CHANGED",
        )
        require(
            body.get("model") == cfg["model"]
            and body.get("reasoning") == {"effort": cfg["reasoning"]}
            and body.get("temperature") == 0
            and body.get("stream") is False
            and body.get("max_output_tokens") == c["expected_cap"],
            "WIRE_CONFIG_CHANGED",
        )
        require(not any(k.encode() in request.content for k in c["keys"]), "SECRET_IN_REQUEST_BODY")
        # Recheck just before physical send; reservation already committed by EvidenceGateway.
        with c["ledger"].db() as db:
            remaining = c["ledger"].clock(db)
        require(remaining > 0, "GLOBAL_DEADLINE")
        n = c["active_call"]
        directory = c["directory"]
        c["wire_request_sha256"] = write_once(
            directory / f"{n:02}-request.json",
            dict(
                wire=json.loads(request.content),
                wire_hex=request.content.hex(),
                wire_sha256=sha(request.content),
                host=base.netloc,
                sni=base.hostname,
                path=request.url.path,
                connect_ip=request.url.host,
                stage=c["stage"],
                logical_request_sha256=c["logical_request_sha256"],
            ),
        )
        response, raw = None, bytearray()
        c["actual_wire_sha256"] = sha(request.content)
        c["expected_config_sha256"] = sha(
            json.dumps(
                dict(
                    provider="deepseek_responses",
                    host=base.hostname,
                    model=body["model"],
                    reasoning=body.get("reasoning"),
                    temperature=body.get("temperature"),
                    max_output_tokens=body.get("max_output_tokens"),
                ),
                sort_keys=True,
            ).encode()
        )
        started = time.monotonic()
        try:
            response = await self.inner.handle_async_request(request)
            async for chunk in response.stream:
                require(len(raw) + len(chunk) <= 4 * 1024 * 1024, "RAW_RESPONSE_LIMIT")
                raw.extend(chunk)
            decoded, metadata = inspect_body(raw, response.headers, c["keys"], complete=True)
            c["decoded_response_sha256"] = sha(decoded)
            c["raw_response_sha256"] = write_once(directory / f"{n:02}-response.bin", bytes(raw))
            write_once(
                directory / f"{n:02}-receipt.json",
                dict(
                    status=response.status_code,
                    raw_sha256=c["raw_response_sha256"],
                    raw_bytes=len(raw),
                    decoded_bytes=len(decoded),
                    safe_headers=metadata,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    provider_error=safe_fields(decoded, request.content)
                    if response.status_code >= 400
                    else None,
                ),
            )
            return httpx.Response(
                response.status_code, headers=response.headers, content=bytes(raw), request=request
            )
        except BaseException:
            c["ledger"].stop("TRANSPORT_OR_RESPONSE_FAILURE")
            # Unsafe/oversized/reflected bodies are deliberately withheld, never printed.
            write_once(
                directory / f"{n:02}-failure.json",
                dict(
                    kind="transport_or_response_failure",
                    response_status=response.status_code if response else None,
                    received_bytes=len(raw),
                    received_sha256=sha(bytes(raw)),
                    body_withheld=True,
                    usage=None,
                ),
            )
            raise
        finally:
            if response is not None:
                await response.aclose()

    async def aclose(self):
        await self.inner.aclose()


def review_sources(request, n):
    """Resolve exact supplied anchor fields, never adjacent text, into a private audit view."""
    payload = json.loads(request.prompt.messages[-1].content)
    sources = {}
    for anchor in payload.get("anchor_catalog", []):
        if "resource_id" in anchor:
            candidates = payload.get("unit", {}).get("candidates", [])
            if "candidate" in payload:
                candidates = [payload["candidate"]]
            candidate = next(c for c in candidates if c["resource_id"] == anchor["resource_id"])
            field = pointer(candidate["envelope"]["content"], anchor["json_pointer"])
        elif anchor["source_kind"] == "user_request":
            field = payload["authoritative_teaching_goal"]["user_request"]
        else:
            root = (
                payload["unverified_plan"]
                if anchor["source_kind"] == "plan"
                else payload["reference_bindings"]
            )
            field = pointer(root, anchor["json_pointer"])
        require(isinstance(field, str), "ANCHOR_STRING_REQUIRED")
        excerpt = field.encode("utf-8")[anchor["start_utf8"] : anchor["end_utf8"]].decode("utf-8")
        require(bool(excerpt), "ANCHOR_EMPTY")
        sources[f"{n}:{anchor['anchor_id']}"] = dict(source_text=excerpt, catalog=anchor)
    return sources


class EvidenceGateway:
    def __init__(self, gateway, context):
        self.gateway, self.c = gateway, context

    async def generate_structured(self, request, *, retry_safe=False):
        c = self.c
        require(not retry_safe, "RETRY_FORBIDDEN")
        logical = dict(
            stage=request.stage, prompt=asdict(request.prompt), schema=request.json_schema
        )
        raw = canonical(logical)
        require(not any(k.encode() in raw for k in c.get("keys", [])), "SECRET_IN_LOGICAL_REQUEST")
        n, remaining = c["ledger"].reserve(c["spec"]["slot_id"], request.stage, sha(raw))
        c.update(
            active_call=n,
            stage=request.stage,
            expected_cap=request.prompt.max_output_tokens,
            logical_request_sha256=sha(raw),
        )
        c["call_ids"].append(n)
        for field in (
            "actual_wire_sha256",
            "expected_config_sha256",
            "decoded_response_sha256",
            "wire_request_sha256",
            "raw_response_sha256",
        ):
            c.pop(field, None)
        try:
            write_once(c["directory"] / f"{n:02}-logical.json", logical)
            c.setdefault("review_sources", {}).update(review_sources(request, n))
            async with asyncio.timeout(remaining):
                result = await self.gateway.generate_structured(request, retry_safe=False)
            require(
                result.transport_audit.request_digest == c.get("actual_wire_sha256")
                and result.transport_audit.response_digest == c.get("decoded_response_sha256")
                and result.transport_audit.config_digest == c.get("expected_config_sha256"),
                "ACTUAL_TRANSPORT_AUDIT_MISMATCH",
            )
            parsed = dict(
                value=dict(result.value),
                usage=asdict(result.usage),
                model=result.model_id,
                transport_audit=asdict(result.transport_audit),
            )
            require(
                not any(k.encode() in canonical(parsed) for k in c.get("keys", [])),
                "SECRET_REFLECTED",
            )
            h = write_once(c["directory"] / f"{n:02}-parsed.json", parsed)
            item = dict(
                n=n,
                stage=request.stage,
                logical_request_sha256=sha(raw),
                parsed_sha256=h,
                wire_request_sha256=c.get("wire_request_sha256"),
                raw_response_sha256=c.get("raw_response_sha256"),
                actual_wire_sha256=c.get("actual_wire_sha256"),
                decoded_response_sha256=c.get("decoded_response_sha256"),
            )
            write_once(c["directory"] / f"{n:02}-evidence.json", item)
            c["ledger"].complete(n, sha(canonical(item)))
            c["calls"].append(item)
            return result
        except BaseException:
            c["ledger"].stop("REQUEST_OR_CONTRACT_FAILURE")
            raise


def live_gateway(context, *, keys, inner_factory=None, guard_factory=None):
    """Build adapters after activation. The default guard enforces public SSRF policy."""
    context["keys"] = keys
    transports = []

    def adapter(role, cls, key):
        cfg = CONFIG[role]
        guard = (
            guard_factory(cfg["base_url"])
            if guard_factory
            else ProviderTargetGuard(cfg["base_url"], TargetPolicy())
        )
        target = guard.approve_base()
        wire = WireTransport(
            context, role, target, inner=inner_factory(role) if inner_factory else None
        )
        transports.append(wire)
        return ProviderGateway(
            cls(
                ProviderSettings(cfg["base_url"], key, cfg["model"]),
                guard,
                transport=wire,
                reasoning_effort=cfg["reasoning"],
            )
        )

    pair = LearningStageGateway(
        adapter("generation", DeepSeekResponsesAdapter, keys[0]),
        adapter("review", CandidateReviewAdapter, keys[1]),
    )
    return EvidenceGateway(CandidateGateway(pair), context), transports


async def draft(case, gateway):
    inputs = inputs_for(case)
    window = CallWindow()
    plan = await generate_shared_plan(gateway, inputs, window)
    b = {key: str(uuid4()) for key in ("owner_id", "unit_id", "operation_id", "plan_id")}
    b.update(
        plan_version=1,
        plan_digest=digest("plan", "learning-plan-v1", plan=plan),
        input_digest=digest("input", "learning-input-v1", snapshot=inputs.snapshot()),
        references_digest=digest(
            "references", "learning-references-v1", references=inputs.references
        ),
        policy_version=POLICY_VERSION,
        policy_digest=active_policy_digest(),
    )
    ws = PlannedScenes(
        plan, b, reference_context=inputs.reference_context, input_snapshot=inputs.snapshot()
    )
    candidates = []
    for role in ("explanation", "code", "exercise"):
        candidate = await ws.generate(gateway, window, role)
        candidates.append(candidate.payload())
        ws.disposition(
            role, candidate.id, "needs_human"
        )  # Private draft bridge, no review/pass/publication.
    return dict(
        plan=plan,
        binding=b,
        input_snapshot=inputs.snapshot(),
        candidates=candidates,
        review_calls=0,
        production_publish_performed=False,
    )


async def fixed(case, gateway):
    ws, material = restore_material(case["material"])
    record = await review_once(
        gateway,
        CallWindow(),
        binding=material["binding"],
        target_digest=material["unit_digest"],
        payload=dict(unit=material, reference_context=material["reference_context"]),
        candidates=ws.candidates(),
        scope="unit",
        input_snapshot=case["input_snapshot"],
    )
    return dict(review=record, production_publish_performed=False)


async def plan_only(case, gateway):
    row = plan_row(
        dict(
            material=dict(binding=case["binding"], plan=case["plan"]),
            input_snapshot=case["input_snapshot"],
        )
    )
    record = await inspect_plan(gateway, CallWindow(), row, row.origin_operation_id)
    return dict(plan_check=record, production_publish_performed=False)


def validate_database_url(url, database=DATABASE):
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    require(
        parsed.host == "127.0.0.1"
        and parsed.port == 15437
        and parsed.database == database
        and database.startswith("edumind_catalog_plan_admission_"),
        "ISOLATED_DATABASE_REQUIRED",
    )


async def verify_database(url, *, empty=False, database=DATABASE):
    validate_database_url(url, database)
    engine = create_database_engine(url)
    try:
        async with engine.connect() as conn:
            require(
                await conn.scalar(text("SELECT current_database()")) == database, "WRONG_DATABASE"
            )
            require(
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0033_learning_shared_budget",
                "MIGRATION_REQUIRED",
            )
            if empty:
                require(
                    await conn.scalar(text("SELECT count(*) FROM users")) == 0,
                    "FRESH_DATABASE_REQUIRED",
                )
    finally:
        await engine.dispose()


async def full_pipeline(case, gateway, url, *, database=DATABASE):
    validate_database_url(url, database)
    require(case["id"] == "G03", "FULL_PIPELINE_INPUT_CHANGED")
    inputs = inputs_for(case)
    snapshot = deepcopy(case["input_snapshot"])
    require(
        inputs.snapshot() == snapshot
        and inputs.metadata["goal"] == case["original_request"]
        and inputs.teaching_context["original_request"] == case["original_request"],
        "RAW_GOAL_CHANGED",
    )
    graph = default_knowledge_graph_repository()
    selected = graph.get_node(inputs.metadata["node_id"])
    require(selected is not None and selected.id == "stack", "SELECTED_NODE_CHANGED")
    engine = create_database_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            owner = uuid4()
            db.add(User(id=owner, is_guest=True))
            await db.flush()
            db.add(
                LearningPathVersion(
                    id=UUID(inputs.teaching_context["path_version_id"]),
                    user_id=owner,
                    target_node_id=selected.id,
                    version=1,
                    graph_version=graph.graph_version,
                    profile_version=1,
                    mastery_revision_watermark=0,
                    planner_rule_version="frozen-admission-selected-node",
                    nodes=[{"node_id": selected.id}],
                    current_node_id=selected.id,
                    prerequisite_node_ids=[],
                    next_node_id=None,
                    reasons=[],
                )
            )
            op = LearningOperation(
                user_id=owner,
                idempotency_key="plan-admission-G03",
                request_digest=sha(canonical(case)),
                goal=case["original_request"],
                preferred_language="c",
            )
            db.add(op)
            await db.commit()
            oid = op.id
            # Unexpected technical errors propagate to the outer irreversible stop.
            try:
                result = await run_planned_operation(
                    db, owner_id=owner, operation_id=oid, inputs=inputs, gateway=gateway
                )
            except BaseException as exc:
                # Export durable history even after a network/schema/cancellation failure.
                # The outer ledger is already stopped for technical failures.
                result = dict(
                    status="not_completed",
                    safe_error_code=exc.code
                    if isinstance(exc, LearningContractError)
                    else "PROVIDER_OR_RUNTIME_FAILURE",
                )
            return await collect_full(db, owner, oid, snapshot, result, inputs.reference_context)
    finally:
        await engine.dispose()


async def collect_full(db, owner, oid, snapshot, result, reference_context):
    op = await db.get(LearningOperation, oid, populate_existing=True)
    plans = (
        await db.scalars(
            select(LearningPlanVersion)
            .where(LearningPlanVersion.origin_operation_id == oid)
            .order_by(LearningPlanVersion.version)
        )
    ).all()
    checks = (await db.scalars(select(PlanCheck).where(PlanCheck.operation_id == oid))).all()
    events = (
        await db.scalars(select(PlanRebuildEvent).where(PlanRebuildEvent.operation_id == oid))
    ).all()
    reviews = (
        await db.scalars(
            select(LearningReviewRecord)
            .where(LearningReviewRecord.operation_id == oid)
            .order_by(LearningReviewRecord.id)
        )
    ).all()
    resources = (
        await db.scalars(
            select(GeneratedResource)
            .where(GeneratedResource.learning_unit_id == op.learning_unit_id)
            .order_by(GeneratedResource.created_at)
        )
    ).all()
    attempts = (
        await db.scalars(
            select(LearningGenerationAttempt)
            .where(LearningGenerationAttempt.operation_id == oid)
            .order_by(LearningGenerationAttempt.ordinal)
        )
    ).all()
    permits = (
        await db.scalars(
            select(LearningCorrectionPermit).where(LearningCorrectionPermit.operation_id == oid)
        )
    ).all()
    cases = (
        await db.scalars(select(LearningReviewCase).where(LearningReviewCase.operation_id == oid))
    ).all()
    history = [await case_review_history(db, c) for c in cases]
    publication = (
        await current_publication(db, owner_id=owner, unit_id=op.learning_unit_id)
        if op.learning_unit_id
        else None
    )
    scenes = await published_scenes(db, owner, op.learning_unit_id) if op.learning_unit_id else []
    require(
        not op.learning_unit_id or not await published_scenes(db, uuid4(), op.learning_unit_id),
        "CROSS_OWNER_LEAK",
    )
    require(
        (op.status == "completed") == bool(publication)
        and (op.status == "completed" or not scenes),
        "PUBLICATION_GATE_FAILED",
    )
    expected_snapshot = {**snapshot, "reference_context": reference_context}
    require(
        all(p.input_snapshot == expected_snapshot for p in plans), "ACTUAL_INPUT_SNAPSHOT_CHANGED"
    )
    require(
        not events and op.generation_rebuild_count == 0 and op.generation_mapping_count == 0,
        "UNPLANNED_MAPPING_OR_REBUILD",
    )
    return dict(
        result=result,
        owner_id=str(owner),
        operation_id=str(oid),
        unit_id=str(op.learning_unit_id),
        original_snapshot=snapshot,
        actual_snapshots=[p.input_snapshot for p in plans],
        permitted_snapshot_addition=dict(reference_context=reference_context),
        binding_boundary=(
            "Frozen selected stack node/PlanInputs; new isolated owner/operation; "
            "not full HTTP/profile/path acceptance"
        ),
        course_state=op.status,
        operation_calls=op.generation_call_count,
        plans=[
            dict(
                id=str(p.id),
                plan=p.plan_json,
                binding=dict(plan_digest=p.plan_digest, input_digest=p.input_digest),
            )
            for p in plans
        ],
        plan_checks=[p.record for p in checks],
        reviews=[r.record for r in reviews],
        resources=[
            dict(
                id=str(r.id),
                content=r.content,
                version=r.version,
                content_digest=r.content_digest,
                review_status=r.review_status,
            )
            for r in resources
        ],
        attempts=[dict(ordinal=a.ordinal, stage=a.stage) for a in attempts],
        correction_permits=[dict(role=p.role, ordinal=p.ordinal, used=p.used) for p in permits],
        case_histories=history,
        isolated_publication=None
        if not publication
        else dict(
            version=publication.version,
            material=publication.material,
            approval_source=publication.approval_source,
        ),
        production_publish_performed=False,
        new_code_executed=False,
    )


async def execute(spec, case, gateway, *, database_url=None):
    if spec["lane"] == "full_pipeline":
        require(database_url is not None, "ISOLATED_DATABASE_REQUIRED")
        return await full_pipeline(case, gateway, database_url)
    guard = LaneGateway(gateway, spec["lane"])
    if spec["lane"] == "plan_review":
        return await plan_only(case, guard)
    if spec["lane"] == "fixed_review":
        return await fixed(case, guard)
    return await draft(case, guard)
