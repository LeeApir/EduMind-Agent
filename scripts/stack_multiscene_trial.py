"""Foreground T139 preparation, one send per stage, and reviewed private admission."""

import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import httpx
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.free_course_planning import PlanningOutcome, request_digest
from app.agents.free_scene_generation import SceneOutcome
from app.core.database import create_database_engine
from app.models.auth import User
from app.services import free_course_planning as plans
from app.services import free_scene_availability as availability
from app.services import free_scene_generation as scenes
from app.services import stack_multiscene as stack
from app.services import stack_multiscene_materials as basis
from app.services.free_course_recovery import Recovery
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical, digest
from app.services.free_scene_validation import validate_candidate
from scripts import course_trial_transport as transport_io
from scripts import head_course_deepseek_wire as direct
from scripts.head_course_goal import raw_io

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs/acceptance/phase-1.5-stack-boundaries-t138"
VAULT = Path.home() / ".local/share/edumind" / basis.VERSION
FIXED_VAULT = VAULT.with_name(basis.FIXED_BATCH)
DATABASE = "edumind_catalog_p15_t139"
FIXED_DATABASE = "edumind_catalog_p15_t141"
FIXED_STAGES = ("normal", "rejections")
STAGES = ("plan", *FIXED_STAGES)
WINDOW = 1800
CHECKS = {
    "plan": ["goal_sources", "scene_allocation", "normal_before_rejections", "grounded_plan"],
    "normal": ["normal_five_frames", "lifo_explanation", "two_exercises", "fact_support"],
    "rejections": [
        "full_course_coherence", "rejections_nine_frames", "both_guards_and_returns",
        "unchanged_logical_storage_and_output", "old_output_is_not_new_pop",
        "six_exercises_and_solutions", "fact_support",
    ],
}


def sha(value):
    return sha256(value).hexdigest()


def read(path):
    return raw_io.wire.strict_json(path.read_bytes())


def save(vault, name, value):
    raw_io.exclusive(vault / name, canonical(value))


def manifest_sha(*, fixed=False):
    path = PACK / ("fixed-execution-manifest.json" if fixed else "execution-manifest.json")
    manifest = read(path)
    if any(sha((ROOT / name).read_bytes()) != expected
           for name, expected in manifest["files"].items()):
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    if basis.materials()["materials_digest"] != manifest["materials_digest"]:
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    return sha(path.read_bytes())


def approval_values(owner, manifest, *, fixture=False, fixed=False):
    return dict(
        batch=basis.FIXED_BATCH if fixed else basis.VERSION,
        owner=str(owner), manifest_sha256=manifest,
        mode="offline_fixture" if fixture else "actual_provider_response",
        approved=True, accept_batch_c2=not fixture, window_seconds=WINDOW,
        stage_budgets={stage: int(stage != "plan" or not fixed) for stage in STAGES},
        revision_budget=0,
    )


def require_database(url, *, fixture, fixed=False):
    parsed = make_url(url)
    database = FIXED_DATABASE if fixed else DATABASE
    if (parsed.drivername, parsed.host, parsed.port, parsed.database) != (
        "postgresql+asyncpg", "127.0.0.1", 15437, database + ("_test" if fixture else ""),
    ):
        raise SnapshotError("STACK_DEVELOPMENT_DATABASE_REQUIRED")


def body_for(stage, inputs):
    if stage == "plan":
        request = stack.wire_plan_request(inputs)
    else:
        if stage not in STAGES or not any(
            scene["scene_id"] == inputs["scene_id"] and scene["scene_key"] == stage
            for scene in inputs["plan"]["scenes"]
        ):
            raise SnapshotError("STACK_STAGE_ORDER")
        request = stack.bound_scene_request(inputs)
    return dict(
        model="deepseek-flash", stream=False, store=False,
        reasoning=dict(effort="none"), max_output_tokens=request.prompt.max_output_tokens,
        temperature=request.prompt.temperature,
        input=[dict(role=msg.role, content=msg.content) for msg in request.prompt.messages],
        text=dict(format=dict(
            type="json_schema", name=f"edumind_stack_boundaries_{stage}", strict=True,
            schema=request.json_schema,
        )),
    )


class Trial:
    def __init__(self, vault, url, *, transport=None, fixed=False):
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise SnapshotError("STACK_OFFLINE_TRANSPORT_REQUIRED")
        self.fixture = transport is not None
        require_database(url, fixture=self.fixture, fixed=fixed)
        if not self.fixture and vault != (FIXED_VAULT if fixed else VAULT):
            raise SnapshotError("STACK_VAULT_REQUIRED")
        self.fixed = fixed
        self.batch = basis.FIXED_BATCH if fixed else basis.VERSION
        self.plan_source = "fixed_outline" if fixed else "model_planned"
        self.policy_snapshot = {"finite_stack_foreground": True}
        if fixed:
            self.policy_snapshot["plan_source"] = self.plan_source
        self.stages = FIXED_STAGES if fixed else STAGES
        self.vault, self.url, self.transport = vault, url, transport

    def require_stage(self, stage):
        if stage not in self.stages:
            raise SnapshotError("STACK_STAGE_NOT_AUTHORIZED")

    def db(self, action):
        async def run():
            engine = create_database_engine(self.url)
            try:
                async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
                    return await action(db)
            finally:
                await engine.dispose()

        return asyncio.run(run())

    def approval(self, value):
        owner = UUID(value["owner"])
        if value != approval_values(
            owner, manifest_sha(fixed=self.fixed), fixture=self.fixture, fixed=self.fixed,
        ):
            raise SnapshotError("STACK_EXACT_AUTHORIZATION_REQUIRED")
        return owner

    def start(self, approval):
        owner = self.approval(approval)
        self.vault.mkdir(mode=0o700)

        async def prepare(db):
            guest = await db.get(User, owner)
            if guest is None or not guest.is_guest:
                raise SnapshotError("STACK_GUEST_REQUIRED")
            repo = SnapshotRepository(db, owner)
            created = await repo.create_course(
                basis.GOAL, key=self.batch, operation_window_seconds=WINDOW,
                config=dict(prompt_version=self.batch, policy_version=self.batch),
                policy_snapshot=self.policy_snapshot,
            )
            cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
            outline = await self.store_fixed_outline(db, repo, cid, oid) if self.fixed else None
            op = await repo._operation(cid, oid)
            return dict(**created, starts_at=op.created_at.isoformat(),
                        expires_at=op.deadline_at.isoformat()), outline

        try:
            created, outline = self.db(prepare)
            save(self.vault, "run.json", dict(approval=approval, **created))
            if outline is not None:
                save(self.vault, "plan.admitted.json", outline)
            raw_io.exclusive(self.vault / "raw.key", Fernet.generate_key())
            return created
        except BaseException:
            self.halt()
            raise

    async def store_fixed_outline(self, db, repo, cid, oid):
        inputs = await plans.load_inputs(db, repo.owner, cid, oid)
        candidate = stack.fixed_outline(inputs)
        outline_bytes = (PACK / "fixed-outline.json").read_bytes()
        audit = read(PACK / "fixed-outline-review.json")
        if (
            canonical(candidate) != outline_bytes
            or audit["outline_sha256"] != sha(outline_bytes)
            or audit["materials_digest"] != basis.materials()["materials_digest"]
            or audit["verdict"] != "pass"
        ):
            raise SnapshotError("STACK_FIXED_OUTLINE_BINDING")
        fence = await repo.acquire_write_fence(cid, oid)
        plan = await repo.store_plan(
            cid, fence, expected_head=None, key=self.batch + "-plan", candidate=candidate,
        )
        pid = UUID(plan["plan_id"])
        ready = await availability.commit_outline(
            db, repo.owner, cid, fence, plan_id=pid, key=self.batch + "-outline",
        )
        op = await repo._fence(cid, fence)
        op.lease_token = op.lease_expires_at = None
        return dict(
            **ready, plan_id=str(pid), plan_digest=(await repo.get_plan(cid, pid))["digest"],
            plan_source=self.plan_source,
            outline_sha256=audit["outline_sha256"],
            outline_review_sha256=sha((PACK / "fixed-outline-review.json").read_bytes()),
        )

    def context(self):
        if self.vault.is_symlink() or self.vault.stat().st_mode & 0o077:
            raise SnapshotError("STACK_VAULT_REQUIRED")
        run = read(self.vault / "run.json")
        return self.approval(run["approval"]), UUID(run["course_id"]), UUID(run["operation_id"])

    def active(self):
        if (self.vault / "STOP").exists():
            raise SnapshotError("STACK_BATCH_STOPPED")

    async def inputs(self, db, stage, *, minimum=0):
        self.require_stage(stage)
        self.active()
        owner, cid, oid = self.context()
        repo = SnapshotRepository(db, owner)
        op = await repo._operation(cid, oid)
        now = await repo._now()
        run = read(self.vault / "run.json")
        if (
            (op.created_at.isoformat(), op.deadline_at.isoformat())
            != (run["starts_at"], run["expires_at"])
            or op.state not in ("queued", "running")
            or op.cancel_requested_at is not None
            or op.deadline_at - op.created_at != timedelta(seconds=WINDOW)
            or not op.created_at <= now < op.deadline_at
            or op.deadline_at - now < timedelta(seconds=minimum)
            or op.config_snapshot.get("policy_version") != self.batch
            or op.policy_snapshot != self.policy_snapshot
        ):
            raise SnapshotError("STACK_WINDOW_OR_OPERATION")
        course = await repo.get_course(cid)
        head = STAGES.index(stage) or None
        if course["head_version"] != head:
            raise SnapshotError("STACK_STAGE_ORDER")
        if stage == "plan":
            return await plans.load_inputs(db, owner, cid, oid)
        approved = read(self.vault / "plan.admitted.json")
        plan = await repo.get_plan(cid, UUID(approved["plan_id"]))
        if plan["digest"] != approved["plan_digest"] or (
            self.fixed and (
                approved["plan_source"] != self.plan_source
                or approved["outline_sha256"] != sha(canonical(plan["candidate"]))
                or approved["outline_review_sha256"] != sha(
                    (PACK / "fixed-outline-review.json").read_bytes()
                )
            )
        ):
            raise SnapshotError("STACK_PLAN_BINDING")
        selected = next(s for s in plan["scenes"] if s["scene_key"] == stage)
        data = await scenes.load_inputs(
            db, owner, cid, oid, plan_id=UUID(plan["id"]),
            scene_id=UUID(selected["scene_id"]), expected_head=head,
        )
        if stage == "rejections":
            prior = read(self.vault / "normal.admitted.json")
            upstream, = data["upstream"]
            source = upstream["content"]["generation_source"]
            if (
                (upstream["scene_version_id"], upstream["digest"])
                != (prior["scene_version_id"], prior["scene_digest"])
                or source["candidate_digest"] != prior["candidate_digest"]
                or (source["batch"], source["plan_source"]) != (self.batch, self.plan_source)
            ):
                raise SnapshotError("STACK_UPSTREAM_BINDING")
        return data

    def halt(self):
        try:
            raw_io.exclusive(self.vault / "STOP", b"no further send or admission\n")
        except FileExistsError:
            pass

    def stop(self):
        self.halt()
        if not (self.vault / "run.json").exists():
            return
        owner, cid, oid = self.context()
        async def cancel():
            engine = create_database_engine(self.url)
            try:
                await Recovery(async_sessionmaker(engine)).cancel(owner, cid, oid, key=self.batch)
            finally:
                await engine.dispose()
        asyncio.run(cancel())

    def record(self, stage, inputs, request_bytes, raw, receipt):
        if receipt != dict(http_status=200, encoding="identity", complete=True,
                           raw_sha256=sha(raw), raw_bytes=len(raw)):
            raise SnapshotError("STACK_BODY_RECEIPT")
        request = body_for(stage, inputs)
        if request_bytes != canonical(request):
            raise SnapshotError("STACK_WIRE_BINDING")
        result, observation = direct.observe_generation(request, raw)
        raw_output = dict(result.value)
        if stage == "plan":
            if stack.wire_plan_response(raw_output, inputs)["needs_clarification"]:
                raise SnapshotError("STACK_PLAN_CLARIFICATION")
        else:
            stack.assemble(raw_output, inputs)
        record = dict(
            stage=stage, evidence_kind="offline_fixture" if self.fixture else "actual_provider_response",
            raw_output=raw_output, request_sha256=sha(request_bytes), raw_sha256=sha(raw),
            materials_digest=basis.materials()["materials_digest"], observation=observation,
            **(dict(plan_digest=inputs["plan"]["digest"], upstream=[
                {k: row[k] for k in ("scene_id", "scene_version_id", "digest")}
                for row in inputs["upstream"]
            ]) if stage != "plan" else {}),
        )
        if self.fixed:
            record["plan_source"] = self.plan_source
        return dict(**record, candidate_digest=digest("stack-boundaries-candidate", record=record))

    def send(self, stage, *, key=None):
        self.require_stage(stage)
        self.active()
        if (self.vault / f"{stage}.attempt.json").exists():
            raise SnapshotError("STACK_STAGE_ALREADY_SENT")
        raw_io.exclusive(self.vault / "ACTIVE", b"foreground operation; stale means stop\n")
        try:
            inputs = self.db(lambda db: self.inputs(db, stage, minimum=direct.IO_TIMEOUT))
            request = canonical(body_for(stage, inputs))
            if len(request) > 131072:
                raise SnapshotError("STACK_REQUEST_SIZE")
            if not self.fixture and (key is not None or not sys.stdin.isatty()):
                raise SnapshotError("STACK_TTY_REQUIRED")
            if key is None:
                key = getpass.getpass("Current DeepSeek API key (not saved): ")
            if not key or "\n" in key or "\r" in key:
                raise SnapshotError("STACK_KEY")
            target = transport_io.resolve_target(self.transport)
            current = self.db(lambda db: self.inputs(db, stage, minimum=direct.IO_TIMEOUT))
            if request != canonical(body_for(stage, current)):
                raise SnapshotError("STACK_WIRE_BINDING")
            self.active()
            raw_io.exclusive(self.vault / f"{stage}.request.json", request)
            save(self.vault, f"{stage}.attempt.json",
                 dict(request_sha256=sha(request), state="attempted_result_unknown"))
            archive = self.vault / f"{stage}.raw.enc"
            cipher = Fernet((self.vault / "raw.key").read_bytes())
            self.active()
            status, encoding, raw = transport_io.send_and_seal(
                target, key, request, archive, cipher, transport=self.transport,
                headers_path=self.vault / f"{stage}.headers.json",
            )
            if raw_io.decrypt(archive, cipher) != raw:
                raise SnapshotError("STACK_RAW_MISMATCH")
            receipt = dict(http_status=status, encoding=encoding, complete=True,
                           raw_sha256=sha(raw), raw_bytes=len(raw))
            save(self.vault, f"{stage}.body.json", receipt)
            if key.encode() in raw:
                raise SnapshotError("STACK_KEY_ECHO")
            current = self.db(lambda db: self.inputs(db, stage))
            candidate = self.record(stage, current, request, raw, receipt)
            save(self.vault, f"{stage}.candidate.json", candidate)
            return candidate["candidate_digest"]
        except BaseException as error:
            self.failure(stage, error)
            raise
        finally:
            (self.vault / "ACTIVE").unlink()

    def failure(self, stage, error):
        self.halt()
        save(self.vault, f"{stage}.failure.json", dict(
            code=getattr(error, "code", type(error).__name__),
            attempted=(self.vault / f"{stage}.attempt.json").exists(),
        ))
        try:
            self.stop()
        except Exception as cancel_error:
            save(self.vault, "cancel.failure.json", dict(
                code=getattr(cancel_error, "code", type(cancel_error).__name__),
            ))

    def review(self, stage, review):
        self.require_stage(stage)
        self.active()
        if (self.vault / f"{stage}.admitted.json").exists():
            raise SnapshotError("STACK_ALREADY_ADMITTED")
        raw_io.exclusive(self.vault / "ACTIVE", b"foreground admission\n")
        try:
            save(self.vault, f"{stage}.review.json", review)
            result = self.db(lambda db: self.admit(db, stage, review))
            save(self.vault, f"{stage}.admitted.json", result)
            if stage == "rejections":
                self.halt()
            return result
        except BaseException as error:
            self.failure(stage, error)
            raise
        finally:
            (self.vault / "ACTIVE").unlink()

    def verify(self, stage, inputs):
        request_bytes = (self.vault / f"{stage}.request.json").read_bytes()
        receipt = read(self.vault / f"{stage}.body.json")
        if read(self.vault / f"{stage}.attempt.json") != dict(
            request_sha256=sha(request_bytes), state="attempted_result_unknown",
        ):
            raise SnapshotError("STACK_WIRE_BINDING")
        raw = raw_io.decrypt(
            self.vault / f"{stage}.raw.enc", Fernet((self.vault / "raw.key").read_bytes())
        )
        candidate = self.record(stage, inputs, request_bytes, raw, receipt)
        if candidate != read(self.vault / f"{stage}.candidate.json"):
            raise SnapshotError("STACK_CANDIDATE_BINDING")
        return candidate

    def inspect(self, stage):
        inputs = self.db(lambda db: self.inputs(db, stage))
        record = self.verify(stage, inputs)
        material = basis.materials()
        assembled = None if stage == "plan" else stack.assemble(record["raw_output"], inputs)
        return dict(
            candidate=record, materials=material, assembled=assembled,
            upstream=[] if stage == "plan" else inputs["upstream"],
            required_checks=CHECKS[stage],
        )

    async def admit(self, db, stage, review):
        owner, cid, oid = self.context()
        repo = SnapshotRepository(db, owner)
        fence = await repo.acquire_write_fence(cid, oid)
        inputs = await self.inputs(db, stage)
        candidate = self.verify(stage, inputs)
        binding = [candidate["candidate_digest"]]
        if stage == "rejections":
            binding.insert(0, read(self.vault / "normal.admitted.json")["candidate_digest"])
        if (
            set(review) != {"candidates", "verdict", "reviewer", "checks", "notes"}
            or review["candidates"] != binding or review["verdict"] != "pass"
            or not isinstance(review["reviewer"], str) or not review["reviewer"].strip()
            or review["checks"] != dict.fromkeys(CHECKS[stage], "pass")
            or not isinstance(review["notes"], str) or not review["notes"].strip()
        ):
            raise SnapshotError("STACK_REVIEW_REQUIRED")
        self.active()
        if stage == "plan":
            outcome = PlanningOutcome(
                "ready", None, digest("planning-input", snapshot=inputs),
                request_digest(stack.wire_plan_request(inputs)),
                stack.wire_plan_response(candidate["raw_output"], inputs),
            )
            row = await plans.persist_outcome(
                db, owner, cid, fence, expected_head=None, call_key=stage,
                inputs=inputs, outcome=outcome,
            )
            pid = UUID(row["plan_id"])
            ready = await availability.commit_outline(
                db, owner, cid, fence, plan_id=pid, key="stack-boundaries-outline"
            )
            ready.update(plan_id=str(pid), plan_digest=(await repo.get_plan(cid, pid))["digest"])
        else:
            source = dict(
                origin="stack_boundaries_model_generation", batch=self.batch,
                model="deepseek-flash", prompt_version=stack.SCENE_PROMPT,
                plan_source=self.plan_source,
                plan_digest=candidate["plan_digest"], materials_digest=candidate["materials_digest"],
                candidate_digest=candidate["candidate_digest"], review_sha256=sha(canonical(review)),
                evidence_kind=candidate["evidence_kind"], scene_key=stage, parent_digest=None,
                source_request_sha256=candidate["request_sha256"],
                source_response_sha256=candidate["raw_sha256"],
            )
            outcome = SceneOutcome(
                "candidate", None, digest("scene-generation-input", snapshot=inputs),
                request_digest(stack.bound_scene_request(inputs)),
                dict(raw_output=candidate["raw_output"], generation_source=source),
                dict(input_tokens=candidate["observation"]["reported_input_tokens"],
                     output_tokens=candidate["observation"]["reported_total_output_tokens"]),
            )
            row = await scenes.persist_outcome(
                db, owner, cid, fence, call_key=stage, inputs=inputs, outcome=outcome,
            )
            checked = await validate_candidate(db, owner, cid, fence, result_id=UUID(row["result_id"]))
            ready = await availability.commit_scene(
                db, owner, cid, fence, validation_id=UUID(checked["validation_id"]),
                expected_head=inputs["expected_head"], key=f"stack-boundaries-{stage}",
            )
            scene = await repo.get_scene_snapshot(cid, ready["version"], UUID(inputs["scene_id"]))
            ready.update(scene_id=inputs["scene_id"], scene_digest=scene["digest"])
        op = await repo._fence(cid, fence)
        op.lease_token = op.lease_expires_at = None
        if stage == "rejections":
            op.state = "succeeded"
        self.active()
        return dict(**ready, candidate_digest=candidate["candidate_digest"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "start", "send", "inspect", "review", "stop"))
    parser.add_argument("--fixed-outline", action="store_true")
    parser.add_argument("value", nargs="?")
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    stages = FIXED_STAGES if args.fixed_outline else STAGES
    try:
        if args.action == "preview":
            if args.value not in stages or args.path is None:
                parser.error("preview requires an authorized stage and input snapshot")
            inputs = read(args.path)
            if args.fixed_outline and inputs["request"].get("stack_boundaries") != basis.FIXED_BATCH:
                raise SnapshotError("STACK_FIXED_OUTLINE_BINDING")
            value = body_for(args.value, inputs)
        else:
            vault = FIXED_VAULT if args.fixed_outline else VAULT
            trial = Trial(vault, os.environ["EDUMIND_DATABASE_URL"], fixed=args.fixed_outline)
            if args.action == "start":
                value = trial.start(read(Path(args.value)))
            elif args.action == "stop":
                value = trial.stop()
            else:
                if args.value not in stages:
                    parser.error("send/inspect/review requires an authorized stage")
                if args.action == "send":
                    value = trial.send(args.value)
                elif args.action == "inspect":
                    value = trial.inspect(args.value)
                else:
                    value = trial.review(args.value, read(args.path))
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except Exception as error:
        print("Refused or stopped; preserve evidence.", getattr(error, "code", type(error).__name__))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
