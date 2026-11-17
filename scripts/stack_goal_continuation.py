"""Resume A/B teaching from reviewed T147 choices in new private operations."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet

from app.services import stack_goal_evidence as evidence
from app.services import stack_goal_selection as selector
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, canonical, digest
from scripts import stack_goal_selection_trial as previous
from scripts import stack_multiscene_trial as stack

BATCH = "stack-goal-continuation-v1"
VAULT = previous.VAULT.with_name(BATCH)
MANIFEST = stack.PACK / "selection-continuation-manifest.json"
SLOTS = ("A", "B")
SEQUENCE = (("A", "normal"), ("B", "normal"), ("B", "rejections"))


def manifest_sha():
    raw = MANIFEST.read_bytes()
    manifest = stack.read(MANIFEST)
    if (
        manifest["batch"] != BATCH or manifest["source_manifest_sha256"] != previous.manifest_sha()
        or manifest["sequence"] != [list(step) for step in SEQUENCE]
        or manifest["window_seconds"] != stack.WINDOW
        or manifest["budgets"] != dict(selection=0, body=len(SEQUENCE), revision=0)
        or any(stack.sha((stack.ROOT / file).read_bytes()) != expected
               for file, expected in manifest["files"].items())
    ):
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    return stack.sha(raw)


def read_archive(slot):
    """Read and verify the original HTTP exchange in its frozen T147 context."""
    manifest = stack.read(MANIFEST)
    parent = manifest["archives"][slot]
    vault = previous.VAULT
    directory = vault / slot
    request = (directory / "plan.request.json").read_bytes()
    raw = stack.raw_io.decrypt(
        directory / "plan.raw.enc", Fernet((directory / "raw.key").read_bytes())
    )
    inputs = previous.preview_inputs(slot)
    body = stack.body_for("plan", inputs)
    if (
        stack.sha((vault / "STOP").read_bytes()) != manifest["source_stop_sha256"]
        or stack.sha((directory / "run.json").read_bytes()) != parent["run_sha256"]
        or request != canonical(body)
        or stack.sha(request) != parent["request_sha256"]
        or stack.sha(raw) != parent["response_sha256"]
        or stack.read(directory / "plan.attempt.json") != dict(
            request_sha256=parent["request_sha256"], state="attempted_result_unknown")
        or stack.read(directory / "plan.body.json") != dict(
            http_status=200, encoding="identity", complete=True,
            raw_sha256=parent["response_sha256"], raw_bytes=len(raw))
    ):
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    result, observation = stack.direct.observe_generation(body, raw)
    return parent, directory, inputs, dict(result.value), observation


def replay_scope(review=None):
    manifest_sha()
    parent, path, inputs, raw, _ = read_archive("C")
    failure = path / "plan.failure.json"
    if (
        stack.sha(failure.read_bytes()) != parent["failure_sha256"]
        or stack.read(failure) != dict(attempted=True, code="STACK_SELECTION_EVIDENCE")
    ):
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    hashes = {key: parent[key] for key in ("request_sha256", "response_sha256")}
    if review is None:
        return evidence.inspect_scope(raw, inputs, **hashes)
    return evidence.reviewed_scope(raw, inputs, review=review, **hashes)


def reviewed_parent(slot):
    if slot not in SLOTS:
        raise SnapshotError("STACK_STAGE_NOT_AUTHORIZED")
    parent, path, inputs, raw, observation = read_archive(slot)
    value = selector.normalize(raw, inputs)
    if raw["selection"] != previous.SAMPLES[slot][1] or value["needs_clarification"]:
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    record = dict(
        stage="plan", evidence_kind="actual_provider_response", raw_output=raw,
        request_sha256=parent["request_sha256"], raw_sha256=parent["response_sha256"],
        materials_digest=stack.basis.materials_digest(stack.basis.SELECTION_BATCH),
        observation=observation, plan_source="goal_selected",
    )
    candidate = digest("stack-boundaries-candidate", record=record)
    review = stack.read(path / "plan.review.json")
    admitted = stack.read(path / "plan.admitted.json")
    run = stack.read(path / "run.json")
    if (
        candidate != parent["candidate_digest"]
        or stack.read(path / "plan.candidate.json") != dict(**record, candidate_digest=candidate)
        or stack.sha(canonical(review)) != parent["review_sha256"]
        or set(review) != {"candidates", "verdict", "reviewer", "checks", "notes"}
        or review["candidates"] != [candidate] or review["verdict"] != "pass"
        or review["checks"] != dict.fromkeys(previous.PLAN_CHECKS, "pass")
        or not all(isinstance(review[key], str) and review[key].strip()
                   for key in ("reviewer", "notes"))
        or stack.sha(canonical(admitted)) != parent["admission_sha256"]
        or admitted["version"] != 1 or admitted["candidate_digest"] != candidate
        or admitted["plan_id"] != parent["plan_id"]
        or admitted["plan_digest"] != parent["plan_digest"]
    ):
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    binding = dict(
        kind="reviewed_selection_replay", batch=stack.basis.SELECTION_BATCH, slot=slot,
        course_id=run["course_id"], operation_id=run["operation_id"],
        **{key: parent[key] for key in ("request_sha256", "response_sha256", "review_sha256",
                                       "candidate_digest", "plan_id", "plan_digest")},
    )
    return value["plan"], binding, UUID(run["approval"]["owner"])


def approval_values(owners, *, fixture=False):
    if set(owners) != set(SLOTS) or len({UUID(value) for value in owners.values()}) != len(SLOTS):
        raise SnapshotError("STACK_SELECTOR_OWNERS")
    return dict(
        batch=BATCH, owners=owners, manifest_sha256=manifest_sha(),
        mode="offline_fixture" if fixture else "actual_provider_response",
        approved=True, accept_batch_c2=not fixture, window_seconds=stack.WINDOW,
        selection_budget=0, body_budget=len(SEQUENCE), revision_budget=0,
    )


class ContinuationTrial(previous.GoalTrial):
    def __init__(self, batch, slot):
        super().__init__(batch, slot)
        self.stages = self.stages[1:]
        self.parent_plan, self.source, self.parent_owner = reviewed_parent(slot)
        self.policy_snapshot["selection_replay"] = self.source

    def bind_parent(self):
        owner, course_id, operation_id = self.context()

        async def persist(db):
            inputs = await stack.plans.load_inputs(db, owner, course_id, operation_id)
            if stack.sha(canonical(stack.body_for("plan", inputs))) != self.source["request_sha256"]:
                raise SnapshotError("STACK_ARCHIVE_BINDING")
            repo = SnapshotRepository(db, owner)
            fence = await repo.acquire_write_fence(course_id, operation_id)
            stored = await repo.store_plan(
                course_id, fence, expected_head=None, key=BATCH, candidate=self.parent_plan,
            )
            plan_id = UUID(stored["plan_id"])
            ready = await stack.availability.commit_outline(
                db, owner, course_id, fence, plan_id=plan_id, key=BATCH,
            )
            op = await repo._fence(course_id, fence)
            op.lease_token = op.lease_expires_at = None
            plan = await repo.get_plan(course_id, plan_id)
            return dict(**ready, plan_id=str(plan_id), plan_digest=plan["digest"],
                        selection_replay=self.source)

        stack.save(self.vault, "plan.admitted.json", self.db(persist))

    async def inputs(self, db, stage, *, minimum=0):
        inputs = await super().inputs(db, stage, minimum=minimum)
        if (
            inputs["plan"]["candidate"] != self.parent_plan
            or stack.read(self.vault / "plan.admitted.json")["selection_replay"] != self.source
        ):
            raise SnapshotError("STACK_ARCHIVE_BINDING")
        return inputs


class Batch(previous.Batch):
    def __init__(self, vault, url, *, transport=None):
        # Reuse the existing loopback database and MockTransport fences.
        super().__init__(previous.VAULT if transport is None else vault, url, transport=transport)
        if vault == previous.VAULT or (not self.fixture and vault != VAULT):
            raise SnapshotError("STACK_VAULT_REQUIRED")
        self.vault = vault

    def check_approval(self, approval):
        if approval.get("batch") != BATCH or approval != approval_values(
            approval["owners"], fixture=self.fixture,
        ):
            raise SnapshotError("STACK_EXACT_AUTHORIZATION_REQUIRED")

    def start(self, approval):
        self.check_approval(approval)
        trials = [ContinuationTrial(self, slot) for slot in SLOTS]
        if {UUID(value) for value in approval["owners"].values()} & {t.parent_owner for t in trials}:
            raise SnapshotError("STACK_SELECTOR_OWNERS")
        self.vault.mkdir(mode=0o700)
        start = datetime.now(UTC)
        run = dict(approval=approval, starts_at=start.isoformat(),
                   expires_at=(start + timedelta(seconds=stack.WINDOW)).isoformat())
        stack.save(self.vault, "batch.json", run)
        try:
            courses = {}
            for trial in trials:
                courses[trial.slot] = trial.start(trial.slot_approval())
                trial.bind_parent()
            stack.save(self.vault, "READY", courses)
            return {**run, "courses": courses}
        except BaseException:
            self.stop()
            raise

    def perform(self, action, slot, stage, *, review=None, key=None):
        if (slot, stage) not in SEQUENCE or action not in ("send", "inspect", "review"):
            raise SnapshotError("STACK_STAGE_NOT_AUTHORIZED")
        try:
            self.active()
        except SnapshotError as error:
            if error.code == "STACK_BATCH_WINDOW":
                self.stop()
            raise
        stack.raw_io.exclusive(self.vault / "ACTIVE", b"one foreground step; stale means stop\n")
        try:
            self.active()
            index = SEQUENCE.index((slot, stage))
            if any(not (self.vault / s / f"{p}.admitted.json").is_file()
                   for s, p in SEQUENCE[:index]):
                raise SnapshotError("STACK_SELECTOR_ORDER")
            try:
                trial = ContinuationTrial(self, slot)
            except Exception:
                self.stop()
                raise
            if action == "send":
                return trial.send(stage, key=key)
            if action == "inspect":
                return trial.inspect(stage)
            result = trial.review(stage, review)
            if index == len(SEQUENCE) - 1:
                self.halt()
            return result
        except BaseException:
            path = self.vault / slot
            if (path / "STOP").exists() or (
                action == "inspect" and (path / f"{stage}.attempt.json").is_file()
            ):
                self.stop()
            raise
        finally:
            (self.vault / "ACTIVE").unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("replay-c", "parents", "start", "send", "inspect", "review", "stop"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("stage", nargs="?")
    parser.add_argument("review", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "replay-c":
            result = replay_scope(stack.read(Path(args.value)) if args.value else None)
        elif args.action == "parents":
            manifest_sha()
            result = {slot: reviewed_parent(slot)[1] for slot in SLOTS}
        else:
            batch = Batch(VAULT, os.environ["EDUMIND_DATABASE_URL"])
            if args.action == "start":
                result = batch.start(stack.read(Path(args.value)))
            elif args.action == "stop":
                result = batch.stop()
            else:
                review = stack.read(args.review) if args.action == "review" else None
                result = batch.perform(args.action, args.value, args.stage, review=review)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        print("Refused or stopped; preserve evidence.", getattr(error, "code", type(error).__name__))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
