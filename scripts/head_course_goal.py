"""T108 finite development app and one foreground request; real sends need exact approval."""

import argparse
import asyncio
from datetime import datetime
import getpass
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import sys
import time
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services import head_course_generation as generation  # noqa: E402
from app.services import head_course_materials as m  # noqa: E402
from app.agents import head_course_planning_wire as plan_wire  # noqa: E402
from app.services.free_course_snapshots import SnapshotError, canonical, digest  # noqa: E402
from scripts import head_course_deepseek_wire as direct  # noqa: E402

PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-goal-t108-r03"
REUSE_PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-reuse-t109"
FIXED_PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-fixed-t111"
DIRECT_PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-deepseek-t114"
EMPTY_PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-empty-t118"
EMPTY_R02_PACKAGE = EMPTY_PACKAGE.with_name("phase-1.5-head-empty-t118-r02")
EMPTY_PACKAGES = (EMPTY_PACKAGE, EMPTY_R02_PACKAGE)
DIRECT_PACKAGES = (DIRECT_PACKAGE, *EMPTY_PACKAGES)
FIXED_PACKAGES = (FIXED_PACKAGE, *DIRECT_PACKAGES)
DIRECT_VAULT = Path.home() / ".local/share/edumind" / direct.BATCH
EMPTY_VAULT = DIRECT_VAULT.with_name(direct.EMPTY_BATCH)
EMPTY_R02_VAULT = DIRECT_VAULT.with_name(direct.EMPTY_R02_BATCH)
FIXED_VAULT = Path.home() / ".local/share/edumind/head-fixed-r01"
OLD = ROOT / "docs/acceptance/phase-1.5-limited-c-preparation-t104/execute_once.py"
spec = importlib.util.spec_from_file_location("head_goal_raw_transport", OLD)
raw_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(raw_io)


def package_digest():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    for path, sha in manifest["files"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha:
            raise SnapshotError("HEAD_PACKAGE_CHANGED")
    return hashlib.sha256((PACKAGE / "manifest.json").read_bytes()).hexdigest()


def profile_goal():
    if PACKAGE in EMPTY_PACKAGES:
        return m.EMPTY_GOAL
    if PACKAGE in FIXED_PACKAGES:
        return m.FIXED_GOAL
    if PACKAGE == REUSE_PACKAGE:
        return m.REUSE_GOAL
    return m.GOAL


def profile_vault():
    if PACKAGE == EMPTY_R02_PACKAGE:
        return EMPTY_R02_VAULT
    return (
        EMPTY_VAULT
        if PACKAGE in EMPTY_PACKAGES
        else (DIRECT_VAULT if PACKAGE in DIRECT_PACKAGES else FIXED_VAULT)
    )


def direct_profile():
    if PACKAGE == EMPTY_R02_PACKAGE:
        return direct.EMPTY_R02_DATABASE, direct.EMPTY_R02_BATCH
    if PACKAGE == EMPTY_PACKAGE:
        return direct.EMPTY_DATABASE, direct.EMPTY_BATCH
    return direct.DATABASE, direct.BATCH


def planning_body(inputs):
    request = plan_wire.build_request(inputs)
    return dict(
        model="deepseek-flash",
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        max_output_tokens=8000,
        temperature=0.2,
        input=[
            dict(role=msg.role, content=msg.content) for msg in request.prompt.messages
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_head_goal_plan",
                strict=True,
                schema=dict(request.json_schema),
            )
        ),
    )


async def database(action):
    from app.core.database import create_database_engine
    from sqlalchemy.ext.asyncio import AsyncSession

    generation.require_development_database()
    engine = create_database_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            result = await action(db)
            await db.commit()
            return result
    finally:
        await engine.dispose()


async def prepare(owner, cid, oid):
    from app.services.free_course_planning import load_inputs
    from app.services.free_course_snapshots import SnapshotRepository

    async def load(db):
        repo = SnapshotRepository(db, owner)
        op = await repo._operation(cid, oid)
        if (
            op.state not in ("queued", "running")
            or op.cancel_requested_at is not None
            or op.deadline_at <= await repo._now()
        ):
            raise SnapshotError("HEAD_OPERATION_STOPPED")
        inputs = await load_inputs(db, owner, cid, oid)
        if inputs.get("head_support") != m.support_for_goal(inputs["original_goal"]):
            raise SnapshotError("HEAD_REQUEST_MISMATCH")
        window = direct.operation_window(op)
        if bool(window) != (PACKAGE in DIRECT_PACKAGES):
            raise SnapshotError("HEAD_DIRECT_WINDOW_MISMATCH")
        if window:
            from sqlalchemy.engine import make_url
            from app.core.database import get_database_url

            if (
                make_url(get_database_url()).database,
                op.config_snapshot.get("policy_version"),
            ) != direct_profile():
                raise SnapshotError("HEAD_DIRECT_OPERATION_REQUIRED")
        return dict(
            owner=str(owner),
            course_id=str(cid),
            operation_id=str(oid),
            planning_inputs=inputs,
            **window,
        )

    return await database(load)


async def save_plan(context, value, *, database_call=None):
    from app.agents.free_course_planning import (
        PlanningOutcome,
        request_digest,
    )
    from app.services.free_course_planning import persist_outcome
    from app.services.free_course_snapshots import SnapshotRepository
    from app.services.free_scene_availability import commit_outline

    inputs = context["planning_inputs"]
    value = plan_wire.to_local(value, inputs)
    outcome = PlanningOutcome(
        "needs_clarification" if value["needs_clarification"] else "ready",
        None,
        digest("planning-input", snapshot=inputs),
        request_digest(plan_wire.build_request(inputs)),
        value,
    )

    async def saved(db):
        owner, cid, oid = (
            UUID(context[k]) for k in ("owner", "course_id", "operation_id")
        )
        repo = SnapshotRepository(db, owner)
        fence = await repo.acquire_write_fence(cid, oid)
        row = await persist_outcome(
            db,
            owner,
            cid,
            fence,
            expected_head=None,
            call_key="head-goal-plan",
            inputs=inputs,
            outcome=outcome,
        )
        if value["needs_clarification"]:
            result = row
        else:
            await commit_outline(
                db,
                owner,
                cid,
                fence,
                plan_id=UUID(row["plan_id"]),
                key="head-goal-outline",
            )
            result = await generation.generation_context(db, owner, cid, oid)
        op = await repo._operation(cid, oid)
        op.lease_token = None
        op.lease_expires_at = None
        return result

    result = await (database_call or database)(saved)
    if value["needs_clarification"]:
        raise SnapshotError("HEAD_PLANNING_CLARIFICATION_STOP")
    return result


def read(path):
    return raw_io.wire.strict_json(path.read_bytes())


def verify_empty_request(stage, request, inputs, plan=None):
    """Bind only the runtime fields allowed by the T118 request templates."""
    name = {"plan": "planning", "generate": "teaching"}[stage]
    expected = read(PACKAGE / f"{name}-request.template.json")
    body = json.loads(expected["input"][1]["content"])
    ids = {
        field: str(UUID(inputs[field]))
        for field in ("course_id", "operation_id", "request_id")
    }
    if stage == "plan":
        body.update(ids)
        body["request_sources"]["request_1"]["request_id"] = ids["request_id"]
    else:
        body.update(source_binding=ids, plan=plan)
    expected["input"][1]["content"] = canonical(body).decode()
    if canonical(request) != canonical(expected):
        raise SnapshotError("HEAD_REQUEST_CHANGED")


def verify_saved(vault, stage, cipher):
    request = read(vault / f"{stage}.request.json")
    raw = raw_io.decrypt(vault / f"{stage}.raw.enc", cipher)
    receipt = read(vault / f"{stage}.body.json")
    if receipt != dict(
        http_status=200,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes=len(raw),
        body_complete=True,
    ):
        raise SnapshotError("HEAD_EVIDENCE_INCOMPLETE")
    attempt = read(vault / f"{stage}.attempt.json")
    if (
        attempt["package_sha256"] != package_digest()
        or attempt["request_sha256"] != hashlib.sha256(canonical(request)).hexdigest()
    ):
        raise SnapshotError("HEAD_REQUEST_CHANGED")
    context = read(vault / "context.json")
    goal = context["planning_inputs"]["original_goal"]
    adapter = direct if PACKAGE in DIRECT_PACKAGES else raw_io
    if goal in m.FIXED_EXAMPLES and (
        attempt["stage"] != stage
        or attempt["approval_sha256"]
        != hashlib.sha256((vault / "approval.bound.json").read_bytes()).hexdigest()
        or attempt["evidence_kind"]
        not in ("actual_provider_response", "offline_fixture")
    ):
        raise SnapshotError("HEAD_ATTEMPT_BINDING")
    if goal in (m.REUSE_GOAL, *m.FIXED_EXAMPLES) and stage != "plan":
        from app.services import head_course_reuse as reuse

        plan = verify_saved(vault, "plan", cipher)["plan"]
        payload = m.content_payload(context["planning_inputs"], plan)
        parent = (
            None
            if stage == "generate"
            else verify_saved(vault, "generate", cipher)["candidate"]
        )
        review = None if parent is None else read(vault / "repair-review.json")
        expected = reuse.record(
            payload,
            request,
            raw,
            adapter,
            evidence_kind=attempt["evidence_kind"],
            parent=parent,
            review=review,
        )
        if read(vault / f"{stage}.record.json") != expected:
            raise SnapshotError("HEAD_CANDIDATE_CHANGED")
        if (
            expected["strict_failure"] is not None
            and read(vault / "generate.strict-failure.json")
            != expected["strict_failure"]
        ):
            raise SnapshotError("HEAD_RECOVERY_FAILURE_CHANGED")
        return expected
    result, observation = adapter.observe_generation(request, raw)
    if stage == "plan":
        if goal in m.FIXED_EXAMPLES and (
            result.usage.input_tokens > 139264 or result.usage.output_tokens > 8000
        ):
            raise SnapshotError("HEAD_USAGE_OR_CREDENTIAL_ECHO")
        if request != planning_body(context["planning_inputs"]) or read(
            vault / "plan.output.json"
        ) != dict(result.value):
            raise SnapshotError("HEAD_PLAN_CHANGED")
        mapping = plan_wire.mapping_record(
            dict(result.value), context["planning_inputs"]
        )
        if read(vault / "plan.mapping.json") != mapping:
            raise SnapshotError("HEAD_PLAN_CHANGED")
        return mapping["value"]
    plan = verify_saved(vault, "plan", cipher)["plan"]
    payload = m.content_payload(context["planning_inputs"], plan)
    parent = (
        None
        if stage == "generate"
        else verify_saved(vault, "generate", cipher)["candidate"]
    )
    issues = None if parent is None else repair_issues(vault, parent)
    if request != m.body(payload, parent, issues):
        raise SnapshotError("HEAD_REQUEST_CHANGED")
    expected = dict(
        candidate=generation.candidate(
            payload,
            dict(result.value),
            parent=None if parent is None else parent["candidate_digest"],
        ),
        model=result.model_id,
        usage=dict(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        ),
        request=request,
        parent_candidate=parent,
        issues=issues,
        evidence_kind=attempt["evidence_kind"],
        receipt=receipt,
        observation=observation,
    )
    if read(vault / f"{stage}.record.json") != expected:
        raise SnapshotError("HEAD_CANDIDATE_CHANGED")
    return expected


def repair_issues(vault, parent):
    review = read(vault / "repair-review.json")
    if (
        review.get("candidate_digest") != parent["candidate_digest"]
        or review.get("verdict") != "ordinary_wording_repair"
        or not review.get("independent_evaluator")
    ):
        raise SnapshotError("HEAD_REPAIR_FORBIDDEN")
    issues = review["issues"]
    if not 1 <= len(issues) <= 8:
        raise SnapshotError("HEAD_REPAIR_FORBIDDEN")
    for issue in issues:
        if (
            issue.get("severity") != "minor"
            or issue.get("area") not in ("difficulty", "misconception")
            or not issue.get("quote")
            or not 1 <= len(issue.get("path", [])) <= 4
        ):
            raise SnapshotError("HEAD_REPAIR_FORBIDDEN")
        target = parent["raw_output"]
        for part in issue["path"]:
            target = target[part]
        if not isinstance(target, str) or issue["quote"] not in target:
            raise SnapshotError("HEAD_ISSUE_TARGET")
    return issues


def approval_check(vault, approval):
    sha = package_digest()
    reuse = PACKAGE == REUSE_PACKAGE
    fixed = PACKAGE == FIXED_PACKAGE
    if PACKAGE in DIRECT_PACKAGES:
        if (
            vault != profile_vault()
            or vault.is_symlink()
            or not vault.is_dir()
            or vault.stat().st_mode & 0o077
        ):
            raise SnapshotError("HEAD_VAULT_STOPPED_OR_UNSAFE")
        if (vault / "STOP").exists():
            raise SnapshotError("HEAD_VAULT_STOPPED_OR_UNSAFE")
        context_bytes = (vault / "context.json").read_bytes()
        window = raw_io.wire.strict_json(context_bytes)["execution_window"]
        expected = dict(
            package_sha256=sha,
            version=m.FIXED_VERSION,
            batch=direct_profile()[1],
            context_sha256=hashlib.sha256(context_bytes).hexdigest(),
            explicit_user_authorization=True,
            max_http_requests=2 if PACKAGE in EMPTY_PACKAGES else 3,
            execution_window=window,
            planning_wire_version=plan_wire.VERSION,
            planning_prompt_version=plan_wire.PROMPT_VERSION,
        )
        expected[
            "accept_T118_and_batch_C2"
            if PACKAGE in EMPTY_PACKAGES
            else "accept_ADR0058_and_batch_C2"
        ] = True
        bound = vault / "approval.bound.json"
        if canonical(approval) != canonical(expected) or (
            bound.exists() and bound.read_bytes() != canonical(approval)
        ):
            raise SnapshotError("HEAD_EXACT_AUTHORIZATION_REQUIRED")
        start, end = (
            datetime.fromisoformat(window[key]).timestamp()
            for key in ("starts_at", "expires_at")
        )
        if end - start != direct.WINDOW_SECONDS or not start <= time.time() < end:
            raise SnapshotError("HEAD_DIRECT_WINDOW_CLOSED")
        return sha
    if fixed and (
        vault != FIXED_VAULT
        or type(approval.get("starts_epoch")) is not int
        or type(approval.get("expires_epoch")) is not int
        or approval.get("accept_ADR0055_and_batch_C2") is not True
        or approval.get("batch") != "head-fixed-r01"
    ):
        raise SnapshotError("HEAD_EXACT_AUTHORIZATION_REQUIRED")
    if (
        approval.get("package_sha256") != sha
        or approval.get("version")
        != (m.FIXED_VERSION if fixed else m.REUSE_VERSION if reuse else m.VERSION)
        or (
            not fixed
            and approval.get(
                "accept_ADR0053_and_batch_C2"
                if reuse
                else "accept_ADR0052_R03_and_batch_C2"
            )
            is not True
        )
        or (
            (reuse or fixed)
            and (
                type(approval.get("max_http_requests")) is not int
                or approval["max_http_requests"] != 3
            )
        )
        or approval.get("planning_wire_version") != plan_wire.VERSION
        or approval.get("planning_prompt_version") != plan_wire.PROMPT_VERSION
        or approval.get("explicit_user_authorization") is not True
        or not approval["starts_epoch"] <= time.time() < approval["expires_epoch"]
        or approval["expires_epoch"] - approval["starts_epoch"] != 600
    ):
        raise SnapshotError("HEAD_EXACT_AUTHORIZATION_REQUIRED")
    if (
        vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
        or (vault / "STOP").exists()
    ):
        raise SnapshotError("HEAD_VAULT_STOPPED_OR_UNSAFE")
    if fixed:
        bound = vault / "approval.bound.json"
        if approval.get("context_sha256") != hashlib.sha256(
            (vault / "context.json").read_bytes()
        ).hexdigest() or (bound.exists() and bound.read_bytes() != canonical(approval)):
            raise SnapshotError("HEAD_EXACT_AUTHORIZATION_REQUIRED")
    return sha


def send(stage, vault, approval, *, transport=None, key=None):
    import httpx
    from cryptography.fernet import Fernet
    from scripts import course_trial_transport as transport_io

    sha = approval_check(vault, approval)
    adapter = direct if PACKAGE in DIRECT_PACKAGES else raw_io

    def send_window():
        if adapter is direct and (
            datetime.fromisoformat(
                approval["execution_window"]["expires_at"]
            ).timestamp()
            - time.time()
            < direct.IO_TIMEOUT
        ):
            raise SnapshotError("HEAD_DIRECT_WINDOW_TOO_SHORT")

    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"one foreground request; stale means unknown/stop\n")
    try:
        send_window()
        rawkey = vault / "raw.key"
        if rawkey.is_symlink() or rawkey.stat().st_mode & 0o077:
            raise SnapshotError("HEAD_RAW_KEY_UNSAFE")
        cipher = Fernet(rawkey.read_bytes())
        context = read(vault / "context.json")
        goal = context["planning_inputs"]["original_goal"]
        reuse_mode = goal in (m.REUSE_GOAL, *m.FIXED_EXAMPLES)
        fixed = goal in m.FIXED_EXAMPLES
        if goal != profile_goal():
            raise SnapshotError("HEAD_PACKAGE_PROFILE_MISMATCH")
        if (
            (PACKAGE in EMPTY_PACKAGES and stage not in ("plan", "generate"))
            or len(list(vault.glob("*.attempt.json")))
            >= (2 if PACKAGE in EMPTY_PACKAGES else 3)
            or (vault / f"{stage}.attempt.json").exists()
        ):
            raise SnapshotError("HEAD_REQUEST_LIMIT")
        parent, issues = None, None
        if stage == "plan":
            if list(vault.glob("*.attempt.json")):
                raise SnapshotError("HEAD_ORDER")
            request = planning_body(context["planning_inputs"])
            if fixed and (
                vault / "plan.prepared-request.json"
            ).read_bytes() != canonical(request):
                raise SnapshotError("HEAD_REQUEST_CHANGED")
        else:
            plan = verify_saved(vault, "plan", cipher)["plan"]
            payload = m.content_payload(context["planning_inputs"], plan)
            review = read(vault / "plan-review.json")
            if (
                review.get("plan_digest") != digest("head-plan", plan=plan)
                or review.get("verdict") != "pass"
                or not review.get("independent_evaluator")
                or review.get("planning_basis_binding")
                != payload["planning_basis"]["binding"]
            ):
                raise SnapshotError("HEAD_PLAN_REVIEW_REQUIRED")
            if PACKAGE in EMPTY_PACKAGES:
                from app.services.head_course_reuse import validate_plan_review

                validate_plan_review(review, payload)
            if stage == "generate" and (vault / "repair.attempt.json").exists():
                raise SnapshotError("HEAD_ORDER")
            if stage == "repair":
                if fixed and (vault / "final-review.json").exists():
                    raise SnapshotError("HEAD_FINAL_REVIEW_ALREADY_RECORDED")
                parent = verify_saved(vault, "generate", cipher)["candidate"]
                if reuse_mode:
                    from app.services.head_course_reuse import revision_body

                    issues = read(vault / "repair-review.json")
                    request = revision_body(parent, issues)
                else:
                    issues = repair_issues(vault, parent)
            if stage != "repair" or not reuse_mode:
                request = m.body(payload, parent, issues)
        raw_request = canonical(request)
        if PACKAGE in EMPTY_PACKAGES:
            verify_empty_request(
                stage,
                request,
                context["planning_inputs"],
                plan if stage == "generate" else None,
            )
        if len(raw_request) > 131072:
            raise SnapshotError("HEAD_REQUEST_SIZE")
        target = transport_io.resolve_target(transport)
        if key is None:
            if adapter is direct and not sys.stdin.isatty():
                raise SnapshotError("HEAD_DIRECT_TTY_REQUIRED")
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise SnapshotError("HEAD_KEY_INVALID")
        approval_check(vault, approval)
        current = asyncio.run(
            prepare(*(UUID(context[k]) for k in ("owner", "course_id", "operation_id")))
        )
        if current != context:
            raise SnapshotError("HEAD_REQUEST_CHANGED")
        approval_binding = {}
        if fixed:
            approval_check(vault, approval)
            if stage == "plan":
                raw_io.exclusive(vault / "approval.bound.json", canonical(approval))
            approval_binding = dict(
                approval_sha256=hashlib.sha256(canonical(approval)).hexdigest()
            )
        send_window()
        raw_io.exclusive(
            vault / f"{stage}.attempt.json",
            canonical(
                dict(
                    stage=stage,
                    package_sha256=sha,
                    request_sha256=hashlib.sha256(raw_request).hexdigest(),
                    state="attempted_unknown",
                    evidence_kind="offline_fixture"
                    if isinstance(transport, httpx.MockTransport)
                    else "actual_provider_response",
                    local_input_reservation=139264,
                    output_reservation=request["max_output_tokens"],
                    **approval_binding,
                )
            ),
        )
        raw_io.exclusive(vault / f"{stage}.request.json", raw_request)
        if adapter is direct:
            approval_check(vault, approval)
            send_window()
        # Explicitly still susceptible to pause/late-send after this check. No T102 fix claimed.
        status, encoding, raw = transport_io.send_and_seal(
            target, key, raw_request, vault / f"{stage}.raw.enc", cipher, transport=transport
        )
        if raw_io.decrypt(vault / f"{stage}.raw.enc", cipher) != raw:
            raise SnapshotError("HEAD_EVIDENCE_INCOMPLETE")
        receipt = dict(
            http_status=status,
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            raw_bytes=len(raw),
            body_complete=True,
        )
        raw_io.exclusive(vault / f"{stage}.body.json", canonical(receipt))
        approval_check(vault, approval)
        if status != 200 or encoding != "identity":
            raise SnapshotError("HEAD_HTTP_OR_ENCODING")
        if reuse_mode and stage != "plan":
            from app.services import head_course_reuse as reuse

            record = reuse.record(
                payload,
                request,
                raw,
                adapter,
                evidence_kind="offline_fixture"
                if isinstance(transport, httpx.MockTransport)
                else "actual_provider_response",
                parent=parent,
                review=issues,
            )
            if (
                key in raw.decode(errors="replace")
                or key in canonical(record["output"]).decode()
            ):
                raise SnapshotError("HEAD_USAGE_OR_CREDENTIAL_ECHO")
            if record["strict_failure"] is not None:
                raw_io.exclusive(
                    vault / "generate.strict-failure.json",
                    canonical(record["strict_failure"]),
                )
            raw_io.exclusive(vault / f"{stage}.record.json", canonical(record))
            verify_saved(vault, stage, cipher)
            lock.unlink()
            return
        result, observation = adapter.observe_generation(request, raw)
        if (
            observation["reported_input_tokens"] > 139264
            or (fixed and result.usage.output_tokens > request["max_output_tokens"])
            or key in raw.decode(errors="replace")
            or key in canonical(dict(result.value)).decode()
        ):
            raise SnapshotError("HEAD_USAGE_OR_CREDENTIAL_ECHO")
        value = dict(result.value)
        if stage == "plan":
            if (
                adapter is direct
                and plan_wire.to_local(value, context["planning_inputs"])["plan"]
                is None
            ):
                raise SnapshotError("HEAD_DIRECT_PLAN_NOT_READY")
            raw_io.exclusive(vault / "plan.output.json", canonical(value))
            raw_io.exclusive(
                vault / "plan.mapping.json",
                canonical(plan_wire.mapping_record(value, context["planning_inputs"])),
            )
            saved = asyncio.run(save_plan(context, value))
            raw_io.exclusive(vault / "plan.binding.json", canonical(saved))
        else:
            record = dict(
                candidate=generation.candidate(
                    payload,
                    value,
                    parent=None if parent is None else parent["candidate_digest"],
                ),
                model=result.model_id,
                usage=dict(
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                ),
                request=request,
                parent_candidate=parent,
                issues=issues,
                evidence_kind="offline_fixture"
                if isinstance(transport, httpx.MockTransport)
                else "actual_provider_response",
                receipt=receipt,
                observation=observation,
            )
            raw_io.exclusive(vault / f"{stage}.record.json", canonical(record))
        verify_saved(vault, stage, cipher)
        lock.unlink()
    except BaseException as error:
        failure = vault / f"{stage}.failure.json"
        if not failure.exists():
            raw_io.exclusive(
                failure,
                canonical(
                    dict(
                        stage=stage,
                        state="failed_or_unknown",
                        error_type=type(error).__name__,
                        code=getattr(
                            error,
                            "code",
                            str(error)
                            if isinstance(error, raw_io.wire.PilotError)
                            else None,
                        ),
                    )
                ),
            )
        if not (vault / "STOP").exists():
            raw_io.exclusive(
                vault / "STOP", b"failed/unknown; preserve everything; no restart\n"
            )
        raise


def forbidden(*args, **kwargs):
    raise RuntimeError("HEAD_GOAL_NO_BACKGROUND_PROVIDER")


def serve(port=8178, *, stack_only=False, replay_only=False, queue_only=False, binary_search_only=False):
    import uvicorn
    from app.core import provider_factory
    from fastapi.responses import JSONResponse
    from app.main import app

    if replay_only:
        from app.services.course_trial_replay import require_database

        require_database()
    elif stack_only or queue_only or binary_search_only:
        from app.services.course_trial_publication import BINARY_SEARCH, QUEUE, STACK, require_database

        profile = BINARY_SEARCH if binary_search_only else QUEUE if queue_only else STACK
        require_database(profile=profile)
    else:
        generation.require_development_database()
        if not generation.development_enabled():
            raise SnapshotError("HEAD_DEVELOPMENT_REQUIRED")
    provider_factory.build_default_provider_gateway = forbidden
    provider_factory.build_server_provider_gateway = forbidden
    # Reuse the previous explicit loopback-only network guard, never inherit its fixed import route.
    sys.addaudithook(raw_io_audit)

    @app.middleware("http")
    async def no_extra_operations(request, call_next):
        path = request.url.path.rstrip("/")
        if request.method == "POST" and (
            path.endswith(("/operations", "/tutor-turns"))
            or (
                (stack_only or queue_only or binary_search_only or replay_only)
                and path.endswith("/free-courses")
            )
        ):
            return JSONResponse(
                {"code": "HEAD_GOAL_EXTRA_OPERATION_DISABLED"}, status_code=409
            )
        return await call_next(request)

    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)


def raw_io_audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        host = (
            args[1][0]
            if event == "socket.connect" and isinstance(args[1], tuple)
            else args[0]
            if event == "socket.getaddrinfo"
            else None
        )
        if (
            host is not None
            and host != "localhost"
            and not ipaddress.ip_address(host).is_loopback
        ):
            raise RuntimeError("HEAD_GOAL_SERVER_EXTERNAL_NETWORK_FORBIDDEN")


def publish_saved(vault, approval):
    approval_check(vault, approval)
    if (vault / "ACTIVE").exists():
        raise SnapshotError("HEAD_ACTIVE_UNKNOWN")
    if PACKAGE in DIRECT_PACKAGES:
        lock = vault / "ACTIVE"
        raw_io.exclusive(lock, b"single foreground publication\n")
        result = publish_chain(vault, approval)
        lock.unlink()
        return result
    return publish_chain(vault, approval)


def publish_chain(vault, approval):
    from cryptography.fernet import Fernet

    rawkey = vault / "raw.key"
    if PACKAGE in FIXED_PACKAGES and (
        rawkey.is_symlink() or rawkey.stat().st_mode & 0o077
    ):
        raise SnapshotError("HEAD_RAW_KEY_UNSAFE")
    cipher = Fernet(rawkey.read_bytes())
    records = [verify_saved(vault, "generate", cipher)]
    if (vault / "repair.attempt.json").exists():
        records.append(verify_saved(vault, "repair", cipher))
    if PACKAGE in FIXED_PACKAGES:
        plan_attempt = read(vault / "plan.attempt.json")
        if any(
            record["evidence_kind"] != plan_attempt["evidence_kind"]
            for record in records
        ):
            raise SnapshotError("HEAD_ATTEMPT_BINDING")
    context = read(vault / "context.json")
    review = read(vault / "final-review.json")

    async def publish(db):
        return await generation.publish(
            db,
            UUID(context["owner"]),
            UUID(context["course_id"]),
            UUID(context["operation_id"]),
            records,
            review,
        )

    if PACKAGE in (REUSE_PACKAGE, *FIXED_PACKAGES):
        from app.services import head_course_reuse as reuse

        plan_raw = raw_io.decrypt(vault / "plan.raw.enc", cipher)
        chain = dict(
            context=context,
            plan_request=read(vault / "plan.request.json"),
            plan_raw_response=plan_raw.decode(),
            plan_review=read(vault / "plan-review.json"),
            records=records,
            final_review=review,
        )

        async def publish_reuse(db):
            return await reuse.publish(
                db,
                UUID(context["owner"]),
                UUID(context["course_id"]),
                UUID(context["operation_id"]),
                chain,
            )

        if PACKAGE in DIRECT_PACKAGES:
            approval_check(vault, approval)
        result = asyncio.run(database(publish_reuse))
    else:
        result = asyncio.run(database(publish))
    raw_io.exclusive(vault / "published.json", canonical(result))
    raw_io.exclusive(vault / "STOP", b"completed; unused requests expired\n")
    return result


def main():
    global PACKAGE
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--profile",
        choices=["t108", "reuse", "fixed", "direct", "empty", "empty-r02"],
        default="t108",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--inspect", action="store_true")
    group.add_argument("--serve", action="store_true")
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--send", choices=["plan", "generate", "repair"])
    group.add_argument("--publish", action="store_true")
    p.add_argument("--vault", type=Path)
    p.add_argument("--approval", type=Path)
    p.add_argument("--owner", type=UUID)
    p.add_argument("--course", type=UUID)
    p.add_argument("--operation", type=UUID)
    args = p.parse_args()
    if args.profile == "reuse":
        PACKAGE = REUSE_PACKAGE
    if args.profile == "fixed":
        PACKAGE = FIXED_PACKAGE
    if args.profile == "direct":
        PACKAGE = DIRECT_PACKAGE
    if args.profile == "empty":
        PACKAGE = EMPTY_PACKAGE
    if args.profile == "empty-r02":
        PACKAGE = EMPTY_R02_PACKAGE
    if args.inspect:
        print(
            json.dumps(
                dict(
                    package_sha256=package_digest(),
                    provider_calls=0,
                    status="prepared_not_authorized",
                )
            )
        )
        return
    if any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "DEEPSEEK", "OPENAI"))
        for k in os.environ
    ):
        p.error("Use clean environment; no Provider credentials or .env")
    if args.serve:
        serve()
        return
    if args.vault is None:
        p.error("--vault required")
    if PACKAGE in FIXED_PACKAGES and (
        args.vault != profile_vault()
        or args.vault.is_symlink()
        or not args.vault.is_dir()
        or args.vault.stat().st_mode & 0o077
    ):
        p.error("Use the new dedicated fixed-batch vault with mode 0700")
    if args.prepare:
        if PACKAGE in DIRECT_PACKAGES:
            package_digest()
        if not all((args.owner, args.course, args.operation)):
            p.error("Actual existing owner/course/operation required")
        context = asyncio.run(prepare(args.owner, args.course, args.operation))
        if PACKAGE in FIXED_PACKAGES and (
            (args.vault / "STOP").exists()
            or context["planning_inputs"]["original_goal"] != profile_goal()
        ):
            raise SnapshotError("HEAD_PACKAGE_PROFILE_MISMATCH")
        prepared = planning_body(context["planning_inputs"])
        if PACKAGE in EMPTY_PACKAGES:
            verify_empty_request("plan", prepared, context["planning_inputs"])
        raw_io.exclusive(args.vault / "context.json", canonical(context))
        raw_io.exclusive(
            args.vault / "plan.prepared-request.json",
            canonical(prepared),
        )
        print(
            "Actual app goal snapshotted. No Provider call; authorization still required."
        )
        return
    if args.approval is None:
        p.error("Exact separate approval required")
    approval = read(args.approval)
    try:
        if args.send:
            send(args.send, args.vault, approval)
        else:
            publish_saved(args.vault, approval)
    except BaseException as error:
        if not (args.vault / "STOP").exists():
            if PACKAGE in FIXED_PACKAGES:
                raw_io.exclusive(
                    args.vault / "terminal.failure.json",
                    canonical(
                        dict(
                            stage=args.send or "publish",
                            error_type=type(error).__name__,
                            code=getattr(error, "code", None),
                        )
                    ),
                )
            raw_io.exclusive(args.vault / "STOP", b"failed/unknown; no retry\n")
        print(
            "STOPPED: preserve originals and failures; no next request.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print("Step complete; no next call scheduled. Preserve vault.")


if __name__ == "__main__":
    main()
