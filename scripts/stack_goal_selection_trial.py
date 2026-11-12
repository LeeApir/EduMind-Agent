"""The six approved sample steps using the existing foreground stack trial."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy.engine import make_url

from app.services import stack_goal_selection as selector
from app.services import stack_multiscene_materials as basis
from app.services.free_course_snapshots import SnapshotError
from scripts import stack_multiscene_trial as stack
from scripts.head_course_goal import raw_io

SAMPLES = {
    "A": ("想懂压栈、弹栈和后来压进去的先出来，不用讲动态扩容。", "operations", ("plan", "normal")),
    "B": ("先学压入弹出，再看塞满时压不进、一个也没有时弹不出的原因。",
          "operations_and_rejections", ("plan", "normal", "rejections")),
    "C": ("理解栈操作和动态扩容", "out_of_scope", ("plan",)),
}
SEQUENCE = (
    ("A", "plan"), ("B", "plan"), ("C", "plan"),
    ("A", "normal"), ("B", "normal"), ("B", "rejections"),
)
PLAN_CHECKS = ["selection_semantics", "original_evidence", "scope_complete"]
DATABASE = "edumind_catalog_p15_t146"
VAULT = stack.VAULT.with_name(basis.SELECTION_BATCH)
MANIFEST = stack.PACK / "selection-execution-manifest.json"


def require_database(url, *, fixture=False):
    parsed = make_url(url)
    if (parsed.drivername, parsed.host, parsed.port, parsed.database) != (
        "postgresql+asyncpg", "127.0.0.1", 15437, DATABASE + ("_test" if fixture else ""),
    ):
        raise SnapshotError("STACK_DEVELOPMENT_DATABASE_REQUIRED")


def manifest_sha():
    raw = MANIFEST.read_bytes()
    manifest = stack.read(MANIFEST)
    if any(stack.sha((stack.ROOT / name).read_bytes()) != expected
           for name, expected in manifest["files"].items()):
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    if (
        manifest["materials_digest"] != basis.materials_digest(basis.SELECTION_BATCH)
        or manifest["sequence"] != [list(step) for step in SEQUENCE]
        or manifest["max_http_requests"] != len(SEQUENCE)
        or manifest["window_seconds"] != stack.WINDOW
    ):
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    return stack.sha(raw)


def approval_values(owners, *, fixture=False):
    if set(owners) != set(SAMPLES) or len({UUID(v) for v in owners.values()}) != len(SAMPLES):
        raise SnapshotError("STACK_SELECTOR_OWNERS")
    return dict(
        batch=basis.SELECTION_BATCH, owners=owners, manifest_sha256=manifest_sha(),
        mode="offline_fixture" if fixture else "actual_provider_response",
        approved=True, accept_batch_c2=not fixture, window_seconds=stack.WINDOW,
        selection_budget=3, body_budget=3, revision_budget=0,
    )


class GoalTrial(stack.Trial):
    def __init__(self, batch, slot):
        self.parent, self.slot = batch, slot
        self.vault, self.url, self.transport = batch.vault / slot, batch.url, batch.transport
        self.fixture = batch.fixture
        self.goal, self.expected_selection, self.stages = SAMPLES[slot]
        self.batch = basis.SELECTION_BATCH
        self.fixed = False
        self.evidence = True
        self.plan_source = "goal_selected"
        self.checks = {**stack.EVIDENCE_CHECKS, "plan": PLAN_CHECKS}
        self.policy_snapshot = {"finite_stack_foreground": True, "plan_source": self.plan_source}

    def slot_approval(self):
        approval = self.parent.record()["approval"]
        return dict(
            owner=approval["owners"][self.slot], slot=self.slot,
            manifest_sha256=approval["manifest_sha256"],
        )

    def approval(self, value):
        if value != self.slot_approval():
            raise SnapshotError("STACK_EXACT_AUTHORIZATION_REQUIRED")
        return UUID(value["owner"])

    def active(self):
        self.parent.active()
        super().active()

    async def inputs(self, db, stage, *, minimum=0):
        self.parent.active(minimum=minimum)
        inputs = await super().inputs(db, stage, minimum=minimum)
        request = inputs if stage == "plan" else inputs["request"]
        if request["original_goal"] != self.goal:
            raise SnapshotError("STACK_SELECTOR_SAMPLE")
        return inputs

    def plan_result(self, raw, inputs):
        value = selector.normalize(raw, inputs)
        if raw["selection"] != self.expected_selection:
            raise SnapshotError("STACK_SELECTOR_WRONG_UNIT")
        return ("needs_clarification" if value["needs_clarification"] else "ready"), raw

    def is_final(self, stage):
        return stage == self.stages[-1]


class Batch:
    def __init__(self, vault, url, *, transport=None):
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise SnapshotError("STACK_OFFLINE_TRANSPORT_REQUIRED")
        self.vault, self.url, self.transport = vault, url, transport
        self.fixture = transport is not None
        require_database(url, fixture=self.fixture)
        if not self.fixture and vault != VAULT:
            raise SnapshotError("STACK_VAULT_REQUIRED")

    def check_approval(self, approval):
        if approval != approval_values(approval["owners"], fixture=self.fixture):
            raise SnapshotError("STACK_EXACT_AUTHORIZATION_REQUIRED")

    def record(self):
        if self.vault.is_symlink() or self.vault.stat().st_mode & 0o077:
            raise SnapshotError("STACK_VAULT_REQUIRED")
        run = stack.read(self.vault / "batch.json")
        self.check_approval(run["approval"])
        return run

    def start(self, approval):
        self.check_approval(approval)
        self.vault.mkdir(mode=0o700)
        start = datetime.now(UTC)
        run = dict(approval=approval, starts_at=start.isoformat(),
                   expires_at=(start + timedelta(seconds=stack.WINDOW)).isoformat())
        stack.save(self.vault, "batch.json", run)
        try:
            courses = {}
            for slot in SAMPLES:
                trial = GoalTrial(self, slot)
                courses[slot] = trial.start(trial.slot_approval())
            stack.save(self.vault, "READY", courses)
            return {**run, "courses": courses}
        except BaseException:
            self.stop()
            raise

    def active(self, *, minimum=0):
        if (self.vault / "STOP").exists():
            raise SnapshotError("STACK_BATCH_STOPPED")
        if not (self.vault / "READY").is_file():
            raise SnapshotError("STACK_BATCH_NOT_READY")
        run = self.record()
        start = datetime.fromisoformat(run["starts_at"])
        end = datetime.fromisoformat(run["expires_at"])
        now = datetime.now(UTC)
        if (
            end - start != timedelta(seconds=stack.WINDOW)
            or not start <= now < end
            or end - now < timedelta(seconds=minimum)
        ):
            raise SnapshotError("STACK_BATCH_WINDOW")

    def halt(self):
        try:
            raw_io.exclusive(self.vault / "STOP", b"goal-selection batch closed\n")
        except FileExistsError:
            pass

    def stop(self):
        self.record()
        self.halt()
        for slot in SAMPLES:
            trial = GoalTrial(self, slot)
            if (trial.vault / "run.json").exists():
                try:
                    trial.stop()
                except Exception as error:
                    path = self.vault / f"{slot}.cancel.failure.json"
                    if not path.exists():
                        stack.save(self.vault, path.name, dict(code=type(error).__name__))

    def perform(self, action, slot, stage, *, review=None, key=None):
        if (slot, stage) not in SEQUENCE or action not in ("send", "inspect", "review"):
            raise SnapshotError("STACK_STAGE_NOT_AUTHORIZED")
        try:
            self.active()
        except SnapshotError as error:
            if error.code == "STACK_BATCH_WINDOW":
                self.stop()
            raise
        raw_io.exclusive(self.vault / "ACTIVE", b"one foreground step; stale means stop\n")
        try:
            self.active()
            index = SEQUENCE.index((slot, stage))
            if any(not (self.vault / s / f"{p}.admitted.json").is_file()
                   for s, p in SEQUENCE[:index]):
                raise SnapshotError("STACK_SELECTOR_ORDER")
            trial = GoalTrial(self, slot)
            try:
                if action == "send":
                    return trial.send(stage, key=key)
                if action == "inspect":
                    return trial.inspect(stage)
                result = trial.review(stage, review)
                if index == len(SEQUENCE) - 1:
                    self.halt()
                return result
            except BaseException:
                if (trial.vault / "STOP").exists() or (
                    action == "inspect" and (trial.vault / f"{stage}.attempt.json").is_file()
                ):
                    self.stop()
                raise
        finally:
            (self.vault / "ACTIVE").unlink()


def preview_inputs(slot):
    goal = SAMPLES[slot][0]
    ids = [str(UUID(int=i)) for i in (1, 2, 3)]
    return dict(
        original_goal=goal, teaching_language="zh-CN", code_language="C",
        course_id=ids[0], operation_id=ids[1], request_id=ids[2],
        request_sources={"request_1": dict(request_id=ids[2], version=1, text=goal)},
        learner_evidence={}, profile_id=None, profile_version=None,
        stack_boundaries=basis.SELECTION_BATCH,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preview", "start", "send", "inspect", "review", "stop"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("stage", nargs="?")
    parser.add_argument("review", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "preview":
            value = stack.body_for("plan", preview_inputs(args.value))
        else:
            batch = Batch(VAULT, os.environ["EDUMIND_DATABASE_URL"])
            if args.action == "start":
                value = batch.start(stack.read(Path(args.value)))
            elif args.action == "stop":
                value = batch.stop()
            else:
                review = stack.read(args.review) if args.action == "review" else None
                value = batch.perform(args.action, args.value, args.stage, review=review)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except Exception as error:
        print("Refused or stopped; preserve evidence.", getattr(error, "code", type(error).__name__))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
