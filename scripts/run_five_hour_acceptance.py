"""One frozen case per command; no live request without an exact new approval."""

# ruff: noqa: E402
import argparse
import asyncio
from dataclasses import asdict
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import sys
import subprocess
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID, uuid4
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from acceptance_support.five_hour_runtime import (
    ORDER,
    RunLedger,
    private_directory,
    read_json,
    require,
    write_once,
)
from acceptance_support.luna_admission_gate import env_metadata
from acceptance_support.luna_high_candidate import CONFIG
from acceptance_support.luna_review_routing import ExplicitRouter
from acceptance_support.luna_schema_projection import ProjectedReviewAdapter
from acceptance_support.qwen_review_budget import canonical, sha
from acceptance_support.provider_error_decode import header_metadata, safe_fields
from check_five_hour_materials import (
    BASE,
    check_materials,
    validate_evaluation,
    verify_freeze,
)
from app.agents.goal_node_resolver import resolve_goal_node
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow, PlanInputs
from app.core.config import ProviderSettings
from app.core.database import create_database_engine
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.main import app  # noqa: F401 -- register ORM, never start a public server
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningOperation
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_review import LearningReviewRecord
from app.models.learning_state import LearningPathVersion
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.hybrid_learning_publication import current_publication
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.owned_learning import published_scenes
from app.services.planned_learning_flow import run_planned_operation
from prepare_luna_admission import candidates
from prepare_five_hour_materials import uid
from run_luna_admission import safe_failure

PACKAGE = ROOT / "docs/acceptance/phase-1-five-hour-execution-r01"
PRIVATE = ROOT / "local-materials/phase-1-five-hour-execution-r01"
DATABASE = "edumind_catalog_five_hour_r01"
RAW_RESPONSE_LIMIT = 4 * 1024 * 1024
DECODED_RESPONSE_LIMIT = 4 * 1024 * 1024


def inspect_body(raw, headers, keys, *, complete):
    metadata, encoding = header_metadata(headers)
    require(
        encoding in {"identity", "gzip", "deflate"}, "RESPONSE_ENCODING_UNSUPPORTED"
    )
    if encoding == "identity":
        decoded = bytes(raw)
    else:
        decoder = zlib.decompressobj(31 if encoding == "gzip" else 15)
        decoded = decoder.decompress(raw, DECODED_RESPONSE_LIMIT + 1)
        require(
            not decoder.unconsumed_tail and not decoder.unused_data,
            "DECODED_RESPONSE_LIMIT",
        )
        if complete:
            require(decoder.eof, "TRUNCATED_COMPRESSED_RESPONSE")
    require(len(decoded) <= DECODED_RESPONSE_LIMIT, "DECODED_RESPONSE_LIMIT")
    require(
        not any(k.encode() in decoded or k.encode() in raw for k in keys),
        "SECRET_REFLECTED",
    )
    return decoded, metadata


def verify_package(package=PACKAGE):
    check_materials()
    m = read_json(package / "manifest.json")
    require(
        subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip()
        == m["branch"],
        "EXECUTION_BRANCH_CHANGED",
    )
    require(m["material_root"] == verify_freeze(), "MATERIAL_CHANGED")
    require(env_metadata(ROOT / ".env") == m["env_metadata"], "CREDENTIAL_FILE_CHANGED")
    for name, expected in m["files"].items():
        path = ROOT / name
        require(
            path.resolve().is_relative_to(ROOT)
            and not path.is_symlink()
            and sha(path.read_bytes()) == expected,
            "EXECUTION_FREEZE_CHANGED",
        )
    require(
        m["requests_max"] == 60 and m["wall_seconds"] == 18000 and m["order"] == ORDER,
        "BUDGET_OR_ORDER_CHANGED",
    )
    environment = read_json(package / "environment-check.json")
    require(
        environment["pytest_exit"] == 0
        and environment["real_provider_calls"] == 0
        and environment["database"] == DATABASE,
        "ISOLATION_VERIFICATION_REQUIRED",
    )
    return m, sha(canonical(m))


def authorize(package=PACKAGE):
    m, digest = verify_package(package)
    a = read_json(package / "run-approval.json")
    require(
        a
        == {
            "manifest_sha256": digest,
            "decision": "approve_limited_execution_and_scope",
            "requests_max": 60,
            "wall_seconds": 18000,
            "fees": "uncapped",
            "evaluator": "GPT_not_independent_human",
            "reviewer": "Lee",
            "source_user_message": a.get("source_user_message"),
        }
        and bool(a["source_user_message"]),
        "EXACT_NEW_APPROVAL_REQUIRED",
    )
    return m, digest


def isolated_environment():
    # Reuse an existing allowlisted test-only container; never discover a production DB URL.
    import run_catalog_db_tests as isolated

    isolated.CONTAINER = "edumind-phase1-t037-pg"
    return isolated.test_environment(DATABASE)


async def verify_database(url, *, require_empty=False):
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    require(
        parsed.host == "127.0.0.1"
        and parsed.port == 15437
        and parsed.database == DATABASE,
        "TEST_DATABASE_REQUIRED",
    )
    engine = create_database_engine(url)
    try:
        async with engine.connect() as conn:
            require(
                await conn.scalar(text("SELECT current_database()")) == DATABASE,
                "WRONG_DATABASE",
            )
            require(
                await conn.scalar(text("SELECT version_num FROM alembic_version"))
                == "0031_teaching_context",
                "MIGRATION_REQUIRED",
            )
            if require_empty:
                require(
                    await conn.scalar(text("SELECT count(*) FROM users")) == 0,
                    "FRESH_ISOLATED_DATABASE_REQUIRED",
                )
    finally:
        await engine.dispose()


def load_keys(expected_metadata, path=ROOT / ".env"):
    require(env_metadata(path) == expected_metadata, "CREDENTIAL_FILE_CHANGED")
    wanted = {
        "EDUMIND_PROVIDER_API_KEY",
        "EDUMIND_PROVIDER_BASE_URL",
        "EDUMIND_PROVIDER_MODEL",
        "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
        "EDUMIND_GENERATION_API_KEY",
    }
    values = {}
    archived, group = [], {}
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        for line in stream:
            if line.lstrip().startswith("#"):
                k, sep, value = line.lstrip().lstrip("#").strip().partition("=")
                k = k.strip()
                if sep and k in {
                    "EDUMIND_PROVIDER_BASE_URL",
                    "EDUMIND_PROVIDER_API_KEY",
                    "EDUMIND_PROVIDER_MODEL",
                }:
                    if k == "EDUMIND_PROVIDER_BASE_URL":
                        if group:
                            archived.append(group)
                        group = {}
                    require(k not in group, "DUPLICATE_ARCHIVED_CREDENTIAL_FIELD")
                    group[k] = value.strip().strip('"').strip("'")
                continue
            k, sep, value = line.strip().partition("=")
            if sep and k in wanted:
                require(k not in values, "DUPLICATE_CREDENTIAL_FIELD")
                values[k] = value.strip().strip('"').strip("'")
    if group:
        archived.append(group)
    require(env_metadata(path) == expected_metadata, "CREDENTIAL_FILE_CHANGED")
    require(
        values.get("EDUMIND_PROVIDER_BASE_URL") == CONFIG.review_base
        and values.get("EDUMIND_PROVIDER_MODEL") == CONFIG.review_model
        and values.get("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT")
        == "responses_json_schema",
        "CONNECTION_CHANGED",
    )
    generation_key = values.get("EDUMIND_GENERATION_API_KEY", "")
    if not generation_key:
        matches = [
            v
            for v in archived
            if v.get("EDUMIND_PROVIDER_BASE_URL") == CONFIG.generation_base
            and v.get("EDUMIND_PROVIDER_MODEL") == CONFIG.generation_model
            and v.get("EDUMIND_PROVIDER_API_KEY")
        ]
        require(len(matches) == 1, "ONE_EXACT_ARCHIVED_DEEPSEEK_CONNECTION_REQUIRED")
        generation_key = matches[0]["EDUMIND_PROVIDER_API_KEY"]
    keys = (
        generation_key,
        values.get("EDUMIND_PROVIDER_API_KEY", ""),
    )
    require(
        all(k and all(32 < ord(c) < 127 for c in k) for k in keys),
        "GENERATION_OR_REVIEW_KEY_MISSING",
    )
    return keys


class AuditTransport(httpx.AsyncBaseTransport):
    """Record exact header-free wires and bounded raw bodies, pinned to approved IPs."""

    def __init__(self, context, base, model, reasoning, target, inner=None):
        self.context, self.base, self.model, self.reasoning = (
            context,
            base,
            model,
            reasoning,
        )
        self.target = target
        self.inner = inner if inner is not None else httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        c = self.context
        base = urlsplit(self.base)
        body = json.loads(request.content)
        limit = body.get("max_output_tokens")
        require(
            request.method == "POST"
            and request.headers.get("host") == base.netloc
            and request.extensions.get("sni_hostname") == base.hostname
            and request.url.scheme == "https"
            and request.url.path == base.path + "/responses"
            and request.url.host in self.target.addresses
            and ipaddress.ip_address(request.url.host).is_global
            and (request.url.port or 443) == 443,
            "OUTBOUND_TARGET_CHANGED",
        )
        require(
            body.get("model") == self.model
            and body.get("reasoning") == {"effort": self.reasoning}
            and body.get("temperature") == 0
            and body.get("stream") is False
            and limit
            in ([8192] if self.model == CONFIG.review_model else [2048, 4096]),
            "WIRE_CONFIGURATION_CHANGED",
        )
        if not c["call_ids"]:
            expected = read_json(
                BASE
                / "requests"
                / (c["case"] + ("-plan" if c["case"].startswith("A") else "") + ".json")
            )
            require(
                sha(request.content) == expected["wire_sha256"],
                "FIRST_OR_FIXED_WIRE_CHANGED",
            )
        n = c["ledger"].reserve(c["case"], sha(request.content))
        c["call_ids"].append(n)
        write_once(
            c["directory"] / f"{n:02}-request.json",
            {
                "case_id": c["case"],
                "n": n,
                "wire_hex": request.content.hex(),
                "wire_sha256": sha(request.content),
                "model": self.model,
                "host": base.netloc,
                "sni": base.hostname,
                "path": request.url.path,
                "connect_ip": request.url.host,
                "reasoning_requested": self.reasoning,
                "parent_completed_calls": list(c["completed"]),
                "logical_input_sha256": c["logical_input_sha256"],
                "business_schema": c["business_schema"],
            },
        )
        started = time.monotonic()
        response = None
        raw = bytearray()
        raw_complete = False
        try:
            response = await self.inner.handle_async_request(request)
            async for chunk in response.stream:
                if len(raw) + len(chunk) > RAW_RESPONSE_LIMIT:
                    raw.extend(chunk[: RAW_RESPONSE_LIMIT - len(raw)])
                    raise ValueError("RAW_RESPONSE_LIMIT")
                raw.extend(chunk)
            raw = bytes(raw)
            raw_complete = True
            decoded, metadata = inspect_body(
                raw, response.headers, c["keys"], complete=True
            )
            raw_hash = write_once(c["directory"] / f"{n:02}-response.bin", raw)
            receipt = {
                "n": n,
                "http_status": response.status_code,
                "raw_bytes": len(raw),
                "raw_sha256": raw_hash,
                "raw_complete": True,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "usage": None,
                "usage_note": "adapter-validated usage is in parsed result; absent remains unknown",
                "safe_headers": metadata,
                "decoded_bytes": len(decoded),
                "safe_provider_error": safe_fields(decoded, request.content)
                if response.status_code >= 400
                else None,
            }
            write_once(c["directory"] / f"{n:02}-receipt.json", receipt)
            c["ledger"].complete_call(n, raw_hash)
            c["completed"].append({"n": n, "response_sha256": raw_hash})
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                stream=httpx.ByteStream(raw),
                request=request,
            )
        except BaseException as exc:
            c["ledger"].stop(
                "RESPONSE_INTEGRITY_FAILURE"
                if raw_complete
                else "SEND_OR_RECEIPT_UNCERTAIN"
            )
            body_hash = sha(bytes(raw))
            body_path = None
            # Preserve received partial bytes when safe. Never save a reflected secret
            # or an encoded body whose decoded size/contents cannot be bounded.
            if response is not None:
                try:
                    inspect_body(raw, response.headers, c["keys"], complete=False)
                    body_path = f"{n:02}-partial-response.bin"
                    write_once(c["directory"] / body_path, bytes(raw))
                except (ValueError, zlib.error):
                    body_path = None
            write_once(
                c["directory"] / f"{n:02}-failure-receipt.json",
                {
                    "n": n,
                    "http_status": response.status_code
                    if response is not None
                    else None,
                    "raw_bytes_saved_or_withheld": len(raw),
                    "raw_sha256": body_hash,
                    "raw_complete": raw_complete,
                    "partial_artifact": body_path,
                    "safe_headers": header_metadata(response.headers)[0]
                    if response is not None
                    else None,
                    "safe_failure": safe_failure(exc),
                    "usage": None,
                    "body_withheld_if_not_safely_inspectable": body_path is None,
                },
            )
            raise
        finally:
            if response is not None:
                await response.aclose()

    async def aclose(self):
        await self.inner.aclose()


class EvidenceGateway:
    def __init__(self, router, context):
        self.router, self.context = router, context

    async def generate_structured(self, request, *, retry_safe=False):
        c = self.context
        c["logical_input_sha256"] = sha(
            canonical(
                {
                    "messages": [asdict(m) for m in request.prompt.messages],
                    "schema": request.json_schema,
                }
            )
        )
        c["business_schema"] = request.json_schema
        result = await self.router.generate_structured(request, retry_safe=retry_safe)
        require(
            not any(k in canonical(dict(result.value)).decode() for k in c["keys"]),
            "SECRET_REFLECTED",
        )
        write_once(
            c["directory"] / f"{c['call_ids'][-1]:02}-parsed.json",
            {
                "value": dict(result.value),
                "usage": asdict(result.usage),
                "model": result.model_id,
                "transport_audit": asdict(result.transport_audit),
            },
        )
        return result


async def independent_review(case, gateway):
    cs = candidates(case)
    chosen = (
        cs
        if case["scope"] == "unit"
        else tuple(c for c in cs if c.role == case["selected_role"])
    )
    m = case["material"]
    payload = (
        {"unit": m, "reference_context": m["reference_context"]}
        if case["scope"] == "unit"
        else {
            "plan": m["plan"],
            "candidate": chosen[0].payload(),
            "reference_context": m["reference_context"],
        }
    )
    record = await review_once(
        gateway,
        CallWindow(),
        binding=m["binding"],
        target_digest=m["unit_digest"]
        if case["scope"] == "unit"
        else chosen[0].content_digest,
        payload=payload,
        candidates=chosen,
        scope=case["scope"],
        input_snapshot=case["input_snapshot"],
    )
    return {
        "review": record,
        "course_state": None,
        "production_publish_performed": False,
    }


async def generated_course(case, gateway, url):
    # The frozen input fixture is preserved byte-for-byte. Raw-goal selection is checked
    # independently with the production resolver, never forced to the expected node.
    class NoMappingCalls:
        async def generate_structured(self, *args, **kwargs):
            raise ValueError("UNPLANNED_GOAL_MAPPING_CALL")

    graph = default_knowledge_graph_repository()
    resolution = await resolve_goal_node(
        case["original_request"], graph=graph, gateway=NoMappingCalls()
    )
    snapshot = case["input_snapshot"]
    selected = resolution.node
    clarification = None
    if selected is None:
        clarification = read_json(PACKAGE / "goal-clarifications.json")[case["id"]]
        require(
            clarification["original_request_sha256"]
            == sha(case["original_request"].encode())
            and clarification["reviewer"] == "Lee"
            and clarification["source_user_message"]
            and clarification["selected_node_id"]
            in {n.id for n in resolution.candidates},
            "EXPLICIT_GOAL_CLARIFICATION_REQUIRED",
        )
        selected = graph.get_node(clarification["selected_node_id"])
    require(
        selected is not None and selected.id == snapshot["metadata"]["node_id"],
        "RAW_GOAL_BINDING_FAILED",
    )
    i = PlanInputs(
        snapshot["metadata"],
        snapshot["references"],
        frozenset(snapshot["node_ids"]),
        snapshot["learner_evidence"],
        case["reference_context"],
        teaching_context=snapshot["teaching_context"],
    )
    engine = create_database_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            owner = UUID(uid(case["id"] + ":owner"))
            require(await db.get(User, owner) is None, "OWNER_ALREADY_USED")
            db.add(User(id=owner, is_guest=True))
            await db.flush()
            db.add(
                LearningPathVersion(
                    id=UUID(i.teaching_context["path_version_id"]),
                    user_id=owner,
                    target_node_id=selected.id,
                    version=1,
                    graph_version=graph.graph_version,
                    profile_version=1,
                    mastery_revision_watermark=0,
                    planner_rule_version="frozen-test-path-fixture",
                    nodes=[{"node_id": selected.id}],
                    current_node_id=selected.id,
                    prerequisite_node_ids=[],
                    next_node_id=None,
                    reasons=[],
                )
            )
            op = LearningOperation(
                user_id=owner,
                idempotency_key=case["id"],
                request_digest=sha(canonical(case)),
                goal=case["original_request"],
                preferred_language="c",
            )
            db.add(op)
            await db.commit()
            oid = op.id
            error = None
            result = None
            try:
                result = await run_planned_operation(
                    db, owner_id=owner, operation_id=oid, inputs=i, gateway=gateway
                )
            except Exception as exc:
                # Production service has persisted failed/rejected state. Keep evidence;
                # technical/semantic decision is made by the evaluator, never auto-pass.
                error = safe_failure(exc)
            op = await db.get(LearningOperation, oid, populate_existing=True)
            plans = (
                await db.scalars(
                    select(LearningPlanVersion).where(
                        LearningPlanVersion.origin_operation_id == oid
                    )
                )
            ).all()
            reviews = (
                await db.scalars(
                    select(LearningReviewRecord).where(
                        LearningReviewRecord.operation_id == oid
                    )
                )
            ).all()
            resources = (
                await db.scalars(
                    select(GeneratedResource).where(
                        GeneratedResource.learning_unit_id == op.learning_unit_id
                    )
                )
            ).all()
            publication = (
                await current_publication(
                    db, owner_id=owner, unit_id=op.learning_unit_id
                )
                if op.learning_unit_id
                else None
            )
            scenes = (
                await published_scenes(db, owner, op.learning_unit_id)
                if op.learning_unit_id
                else []
            )
            foreign = (
                await published_scenes(db, uuid4(), op.learning_unit_id)
                if op.learning_unit_id
                else []
            )
            require(not foreign, "CROSS_OWNER_LEAK")
            require(
                (op.status == "completed") == bool(publication),
                "PUBLICATION_STATE_MISMATCH",
            )
            require(op.status == "completed" or not scenes, "PENDING_CONTENT_VISIBLE")
            if publication:
                exact = await current_publication(
                    db,
                    owner_id=owner,
                    unit_id=op.learning_unit_id,
                    version=publication.version,
                )
                require(
                    exact.id == publication.id
                    and publication.approval_source == "auto"
                    and len(scenes) == 3,
                    "EXACT_PUBLICATION_FAILED",
                )
            return {
                "result": result,
                "safe_error": error,
                "course_state": op.status,
                "operation_id": str(oid),
                "owner_id": str(owner),
                "learning_unit_id": str(op.learning_unit_id)
                if op.learning_unit_id
                else None,
                "operation_calls": op.generation_call_count,
                "raw_goal_selection": {
                    "node_id": resolution.node.id if resolution.node else None,
                    "reason": resolution.reason,
                    "candidates": [n.id for n in resolution.candidates],
                    "manual_clarification": clarification,
                    "selected_node_id": selected.id,
                },
                "input_boundary": "frozen PlanInputs fixture; actual resolver checked separately; not a full HTTP input/profile/path integration test",
                "plans": [
                    {
                        "id": str(p.id),
                        "plan": p.plan_json,
                        "input_snapshot": p.input_snapshot,
                    }
                    for p in plans
                ],
                "reviews": [r.record for r in reviews],
                "resources": [
                    {
                        "id": str(r.id),
                        "version": r.version,
                        "content": r.content,
                        "content_digest": r.content_digest,
                        "review_status": r.review_status,
                    }
                    for r in resources
                ],
                "isolated_publication": None
                if not publication
                else {
                    "version": publication.version,
                    "material": publication.material,
                    "approval_source": publication.approval_source,
                },
                "production_publish_performed": False,
                "new_code_executed": False,
            }
    finally:
        await engine.dispose()


async def execute_case(name, ledger, directory, url, keys):
    case = read_json(BASE / "cases" / (name + ".json"))
    context = dict(
        case=name,
        ledger=ledger,
        directory=directory,
        keys=keys,
        call_ids=[],
        completed=[],
        logical_input_sha256=None,
        business_schema=None,
    )
    transports = []
    try:
        adapters = []
        for base, model, reasoning, key, cls in (
            (
                CONFIG.generation_base,
                CONFIG.generation_model,
                "none",
                keys[0],
                DeepSeekResponsesAdapter,
            ),
            (
                CONFIG.review_base,
                CONFIG.review_model,
                "high",
                keys[1],
                ProjectedReviewAdapter,
            ),
        ):
            target = await asyncio.to_thread(
                ProviderTargetGuard(base, TargetPolicy()).approve_base
            )
            transport = AuditTransport(context, base, model, reasoning, target)
            transports.append(transport)
            adapters.append(
                cls(
                    ProviderSettings(base, key, model),
                    SimpleNamespace(approve_base=lambda t=target: t),
                    transport=transport,
                    reasoning_effort=reasoning,
                )
            )
        gateway = EvidenceGateway(ExplicitRouter(*adapters, config=CONFIG), context)
        result = (
            await generated_course(case, gateway, url)
            if name.startswith("A")
            else await independent_review(case, gateway)
        )
        result.update(
            case_id=name,
            actual_call_count=len(context["call_ids"]),
            call_ids=context["call_ids"],
        )
        records = result.get(
            "reviews", [result["review"]] if "review" in result else []
        )
        result["review_artifact_paths"] = []
        for record in records:
            path = directory / ("review-" + record["review_id"] + ".json")
            write_once(path, record)
            result["review_artifact_paths"].append(str(path.relative_to(ROOT)))
        result["artifact_hashes"] = {
            str(path.relative_to(ROOT)): sha(path.read_bytes())
            for path in directory.iterdir()
            if path.is_file()
        }
        digest = write_once(directory / "result.json", result)
        ledger.finish_case(name, digest)
        return {
            "case_id": name,
            "state": "awaiting_gpt",
            "result_sha256": digest,
            "actual_call_count": len(context["call_ids"]),
        }
    except BaseException as exc:
        ledger.stop("CASE_INTERRUPTED_OR_TECHNICAL_FAILURE")
        write_once(
            directory / "failure.json",
            {
                "case_id": name,
                "safe_failure": safe_failure(exc),
                "reserved_calls": context["call_ids"],
                "complete_responses": context["completed"],
                "usage": None,
                "unknown_usage_preserved": True,
                "no_automatic_replay": True,
            },
        )
        raise
    finally:
        async with asyncio.timeout(5):
            for transport in transports:
                await transport.aclose()


def pointer_value(value, pointer):
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def check_audit_coverage(value, result, *, root=ROOT):
    """Require every assertion/citation, even in earlier corrected candidates.

    Checks evidence locations and quotes, never substitutes for semantic judgment.
    """
    expected_claims, expected_citations = set(), set()
    for path in result["review_artifact_paths"]:
        record = read_json(root / path)
        for i, f in enumerate(record["result"]["findings"]):
            for key in ("condition_or_counterexample", "impact"):
                expected_claims.add((path, f"/result/findings/{i}/{key}", f[key]))
            catalog = {a["anchor_id"]: a for a in record["anchor_catalog"]}
            for anchor_id in f["anchors"]:
                a = catalog[anchor_id]
                expected_citations.add(
                    (
                        path,
                        i,
                        anchor_id,
                        a["resource_digest"],
                        a["json_pointer"],
                        a["start_utf8"],
                        a["end_utf8"],
                    )
                )
        for key, entries in (
            ("unresolved", record["result"]["unresolved"]),
            ("coverage/unchecked", record["result"]["coverage"]["unchecked"]),
        ):
            for i, claim in enumerate(entries):
                expected_claims.add((path, f"/result/{key}/{i}", claim))
    observed_claims = {
        (c["review_artifact_path"], c["json_pointer"], c["quoted_text"])
        for c in value["claim_checks"]
    }
    observed_citations = {
        (
            c["review_artifact_path"],
            c["finding_index"],
            c["anchor_id"],
            c["resource_digest"],
            c["json_pointer"],
            c["start_utf8"],
            c["end_utf8"],
        )
        for c in value["citation_checks"]
    }
    require(observed_claims == expected_claims, "ALL_REVIEW_ASSERTIONS_REQUIRED")
    require(observed_citations == expected_citations, "ALL_REVIEW_CITATIONS_REQUIRED")
    if result["case_id"].startswith("A"):
        content = {r["id"]: r["content"] for r in result["resources"]}
    else:
        fixture = read_json(BASE / "cases" / (result["case_id"] + ".json"))
        content = {
            r["resource_id"]: r["envelope"]["content"]
            for r in fixture["material"]["candidates"]
        }
    for c in value["citation_checks"]:
        record = read_json(root / c["review_artifact_path"])
        anchor = next(
            a for a in record["anchor_catalog"] if a["anchor_id"] == c["anchor_id"]
        )
        field = pointer_value(content[anchor["resource_id"]], anchor["json_pointer"])
        raw = field.encode() if isinstance(field, str) else canonical(field)
        require(
            raw[c["start_utf8"] : c["end_utf8"]].decode() == c["quoted_text"],
            "CITATION_QUOTE_CHANGED",
        )


def apply_assessment(ledger, name, value):
    validate_evaluation(value)
    require(
        value["case_id"] == name and value["run_id"] == "five-hour-r01",
        "ASSESSMENT_WRONG_RUN",
    )
    require(value["actual"]["status"] != "not_run", "UNRUN_ASSESSMENT")
    result = read_json(PRIVATE / name / "result.json")
    state = next(c for c in ledger.snapshot()["cases"] if c[0] == name)
    require(
        state[1] == "awaiting_gpt" and state[2] == sha(canonical(result)),
        "RESULT_CHANGED",
    )
    verify_artifacts(result)
    require(
        value["actual"]["actual_call_count"] == result["actual_call_count"],
        "ASSESSMENT_COUNT_CHANGED",
    )
    check_audit_coverage(value, result)
    required_requests = {
        str((PRIVATE / name / f"{n:02}-{kind}.json").relative_to(ROOT))
        for n in result["call_ids"]
        for kind in ("request", "receipt")
    }
    required_responses = {
        str((PRIVATE / name / f"{n:02}-response.bin").relative_to(ROOT))
        for n in result["call_ids"]
    }
    require(
        set(value["actual"]["request_receipt_paths"]) == required_requests
        and set(value["actual"]["response_artifact_paths"]) == required_responses,
        "ALL_CALL_ARTIFACTS_REQUIRED",
    )
    if not name.startswith("A"):
        review = result["review"]
        require(
            value["actual"]["model_verdict"] == review["result"]["verdict"]
            and value["actual"]["local_verdict"] == review["local_routing"]["verdict"],
            "ASSESSMENT_VERDICT_CHANGED",
        )
    else:
        require(
            value["actual"]["course_state"] == result["course_state"],
            "ASSESSMENT_COURSE_STATE_CHANGED",
        )
    require(value["grades"]["impact"] in ("green", "yellow", "red"), "IMPACT_REQUIRED")
    for e in value["evidence"]:
        path = ROOT / e["artifact_path"]
        require(
            path.resolve().is_relative_to(ROOT)
            and not path.is_symlink()
            and sha(path.read_bytes()) == e["artifact_sha256"],
            "EVIDENCE_CHANGED",
        )
    # Core serious pass is an unconditional red irrespective of evaluator prose.
    serious_missed = (
        name in {"U01", "U02", "U03"}
        and result["review"]["local_routing"]["verdict"] != "reject"
    )
    red = value["grades"]["impact"] == "red" or serious_missed
    digest = write_once(PRIVATE / name / "evaluation.json", value)
    ledger.assess(name, digest, red=red)
    # Two low-risk auxiliary errors already exceed the fixed allowance.
    evaluated = [
        read_json(PRIVATE / c / "evaluation.json")
        for c in ORDER
        if (PRIVATE / c / "evaluation.json").exists()
    ]
    if (
        sum(
            v["grades"]["all_claims"] == "fail"
            or v["grades"]["all_citations"] == "fail"
            for v in evaluated
        )
        > 1
    ):
        ledger.stop("AUXILIARY_ERROR_ALLOWANCE_EXCEEDED")
    if not name.startswith("A") and value["grades"]["core_expected"] == "fail":
        ledger.stop("REQUIRED_CORE_CONDITION_UNREACHABLE")


def verify_artifacts(result):
    for name, digest in result["artifact_hashes"].items():
        path = ROOT / name
        require(
            path.resolve().is_relative_to(ROOT)
            and not path.is_symlink()
            and sha(path.read_bytes()) == digest,
            "CASE_ARTIFACT_CHANGED",
        )


def verify_prior_results(ledger):
    for name, state, result_hash, evaluation_hash in ledger.snapshot()["cases"]:
        if result_hash:
            result = read_json(PRIVATE / name / "result.json")
            require(sha(canonical(result)) == result_hash, "PRIOR_RESULT_CHANGED")
            verify_artifacts(result)
        if state == "assessed":
            evaluation = read_json(PRIVATE / name / "evaluation.json")
            require(
                sha(canonical(evaluation)) == evaluation_hash,
                "PRIOR_EVALUATION_CHANGED",
            )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command", choices=["check", "init", "run", "assess", "report", "stop"]
    )
    p.add_argument("--case", choices=ORDER)
    p.add_argument("--evaluation", type=Path)
    args = p.parse_args()
    if args.command == "check":
        m, digest = verify_package()
        print(
            json.dumps(
                {
                    "manifest_sha256": digest,
                    "materials_valid": True,
                    "runner_implemented": True,
                    "real_calls_in_this_command": 0,
                    "live_approval_present": (PACKAGE / "run-approval.json").exists(),
                    "preparation_t0_epoch": m["preparation_t0_epoch"],
                }
            )
        )
        return
    m, digest = authorize()
    private_directory(PRIVATE)
    with (PRIVATE / "process.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "init":
            require(
                time.time() < m["preparation_t0_epoch"] + 16200,
                "PREPARATION_WINDOW_EXPIRED",
            )
            require(not (PRIVATE / "run.sqlite").exists(), "RUN_ALREADY_INITIALIZED")
            env = isolated_environment()
            asyncio.run(
                verify_database(env["EDUMIND_DATABASE_URL"], require_empty=True)
            )
            metadata = m["env_metadata"]
            load_keys(metadata)
            write_once(PRIVATE / "credential-binding.json", metadata)
            ledger = RunLedger(
                PRIVATE / "run.sqlite", digest, t0=m["preparation_t0_epoch"]
            )
        else:
            ledger = RunLedger(PRIVATE / "run.sqlite", digest)
        if args.command == "run":
            require(args.case is not None, "CASE_REQUIRED")
            verify_prior_results(ledger)
            env = isolated_environment()
            url = env["EDUMIND_DATABASE_URL"]
            asyncio.run(verify_database(url))
            keys = load_keys(read_json(PRIVATE / "credential-binding.json"))
            ledger.start_case(args.case)
            directory = private_directory(PRIVATE / args.case)
            # This short-lived CLI process alone enables isolated publication. No server
            # launch, global .env mutation, route mount or production connection occurs.
            os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
            try:
                print(
                    json.dumps(
                        asyncio.run(
                            execute_case(args.case, ledger, directory, url, keys)
                        )
                    )
                )
            finally:
                os.environ.pop("EDUMIND_PRODUCT_MODE", None)
        elif args.command == "assess":
            require(
                args.case is not None and args.evaluation is not None,
                "ASSESSMENT_REQUIRED",
            )
            apply_assessment(ledger, args.case, read_json(args.evaluation))
        elif args.command == "stop":
            ledger.stop("EXPLICIT_STOP")
        print(json.dumps(ledger.snapshot()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not print traceback/exception objects, which may contain URLs or credentials.
        print(
            "Acceptance command failed closed; inspect bounded private evidence.",
            file=sys.stderr,
        )
        sys.exit(1)
