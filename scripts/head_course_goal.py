"""T108 finite development app and one foreground request; real sends need exact approval."""

import argparse
import asyncio
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

PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-goal-t108-r03"
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
        if inputs.get("head_support") != m.SUPPORT:
            raise SnapshotError("HEAD_REQUEST_MISMATCH")
        return dict(
            owner=str(owner),
            course_id=str(cid),
            operation_id=str(oid),
            planning_inputs=inputs,
        )

    return await database(load)


async def save_plan(context, value):
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

    result = await database(saved)
    if value["needs_clarification"]:
        raise SnapshotError("HEAD_PLANNING_CLARIFICATION_STOP")
    return result


def read(path):
    return raw_io.wire.strict_json(path.read_bytes())


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
    result, observation = raw_io.observe_generation(request, raw)
    context = read(vault / "context.json")
    if stage == "plan":
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
    if (
        approval.get("package_sha256") != sha
        or approval.get("version") != m.VERSION
        or approval.get("accept_ADR0052_R03_and_batch_C2") is not True
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
    return sha


def send(stage, vault, approval, *, transport=None, key=None):
    import httpx
    from cryptography.fernet import Fernet
    from app.core.provider_target import TargetPolicy, approve_target

    sha = approval_check(vault, approval)
    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"one foreground request; stale means unknown/stop\n")
    try:
        rawkey = vault / "raw.key"
        if rawkey.is_symlink() or rawkey.stat().st_mode & 0o077:
            raise SnapshotError("HEAD_RAW_KEY_UNSAFE")
        cipher = Fernet(rawkey.read_bytes())
        context = read(vault / "context.json")
        if (
            len(list(vault.glob("*.attempt.json"))) >= 3
            or (vault / f"{stage}.attempt.json").exists()
        ):
            raise SnapshotError("HEAD_REQUEST_LIMIT")
        parent, issues = None, None
        if stage == "plan":
            if list(vault.glob("*.attempt.json")):
                raise SnapshotError("HEAD_ORDER")
            request = planning_body(context["planning_inputs"])
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
            if stage == "generate" and (vault / "repair.attempt.json").exists():
                raise SnapshotError("HEAD_ORDER")
            if stage == "repair":
                parent = verify_saved(vault, "generate", cipher)["candidate"]
                issues = repair_issues(vault, parent)
            request = m.body(payload, parent, issues)
        raw_request = canonical(request)
        if len(raw_request) > 131072:
            raise SnapshotError("HEAD_REQUEST_SIZE")
        target = approve_target(
            "https://api.deepseek.com/responses",
            policy=TargetPolicy(),
            **(
                {"resolver": lambda host, port: ["93.184.216.34"]}
                if isinstance(transport, httpx.MockTransport)
                else {}
            ),
        )
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        if key is None:
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise SnapshotError("HEAD_KEY_INVALID")
        approval_check(vault, approval)
        current = asyncio.run(
            prepare(*(UUID(context[k]) for k in ("owner", "course_id", "operation_id")))
        )
        if current != context:
            raise SnapshotError("HEAD_REQUEST_CHANGED")
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
                    output_reservation=8000,
                )
            ),
        )
        raw_io.exclusive(vault / f"{stage}.request.json", raw_request)
        # Explicitly still susceptible to pause/late-send after this check. No T102 fix claimed.
        with httpx.Client(
            transport=transport, timeout=90, trust_env=False, follow_redirects=False
        ) as client:
            with client.stream(
                "POST",
                f"https://{host}:443/responses",
                content=raw_request,
                extensions={"sni_hostname": target.hostname},
                headers={
                    "Host": target.hostname,
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                status = response.status_code
                encoding = response.headers.get("content-encoding", "identity")
                raw = raw_io.collect(response, vault / f"{stage}.raw.enc", cipher)
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
        result, observation = raw_io.observe_generation(request, raw)
        if (
            observation["reported_input_tokens"] > 139264
            or key in raw.decode(errors="replace")
            or key in canonical(dict(result.value)).decode()
        ):
            raise SnapshotError("HEAD_USAGE_OR_CREDENTIAL_ECHO")
        value = dict(result.value)
        if stage == "plan":
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
                        code=getattr(error, "code", None),
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


def serve():
    import uvicorn
    from app.core import provider_factory
    from fastapi.responses import JSONResponse
    from app.main import app

    generation.require_development_database()
    if not generation.development_enabled():
        raise SnapshotError("HEAD_DEVELOPMENT_REQUIRED")
    provider_factory.build_default_provider_gateway = forbidden
    provider_factory.build_server_provider_gateway = forbidden
    # Reuse the previous explicit loopback-only network guard, never inherit its fixed import route.
    sys.addaudithook(raw_io_audit)

    @app.middleware("http")
    async def no_extra_operations(request, call_next):
        if request.method == "POST" and request.url.path.endswith(
            ("/operations", "/tutor-turns")
        ):
            return JSONResponse(
                {"code": "HEAD_GOAL_EXTRA_OPERATION_DISABLED"}, status_code=409
            )
        return await call_next(request)

    uvicorn.run(app, host="127.0.0.1", port=8178, access_log=False)


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


def main():
    p = argparse.ArgumentParser(description=__doc__)
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
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL")) for k in os.environ
    ):
        p.error("Use clean environment; no Provider credentials or .env")
    if args.serve:
        serve()
        return
    if args.vault is None:
        p.error("--vault required")
    if args.prepare:
        if not all((args.owner, args.course, args.operation)):
            p.error("Actual existing owner/course/operation required")
        context = asyncio.run(prepare(args.owner, args.course, args.operation))
        raw_io.exclusive(args.vault / "context.json", canonical(context))
        raw_io.exclusive(
            args.vault / "plan.prepared-request.json",
            canonical(planning_body(context["planning_inputs"])),
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
            from cryptography.fernet import Fernet

            approval_check(args.vault, approval)
            if (args.vault / "ACTIVE").exists():
                raise SnapshotError("HEAD_ACTIVE_UNKNOWN")
            cipher = Fernet((args.vault / "raw.key").read_bytes())
            records = [verify_saved(args.vault, "generate", cipher)]
            if (args.vault / "repair.attempt.json").exists():
                records.append(verify_saved(args.vault, "repair", cipher))
            context = read(args.vault / "context.json")
            review = read(args.vault / "final-review.json")

            async def publish(db):
                return await generation.publish(
                    db,
                    UUID(context["owner"]),
                    UUID(context["course_id"]),
                    UUID(context["operation_id"]),
                    records,
                    review,
                )

            result = asyncio.run(database(publish))
            raw_io.exclusive(args.vault / "published.json", canonical(result))
            raw_io.exclusive(
                args.vault / "STOP", b"completed; unused requests expired\n"
            )
    except BaseException:
        if not (args.vault / "STOP").exists():
            raw_io.exclusive(args.vault / "STOP", b"failed/unknown; no retry\n")
        print(
            "STOPPED: preserve originals and failures; no next request.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print("Step complete; no next call scheduled. Preserve vault.")


if __name__ == "__main__":
    main()
