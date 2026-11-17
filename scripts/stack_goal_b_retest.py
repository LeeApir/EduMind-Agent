"""Run only B's two stages using the reviewed T147 choice and existing trial."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from cryptography.fernet import Fernet

from app.services.free_course_snapshots import SnapshotError
from scripts import stack_goal_continuation as continuation
from scripts import stack_goal_selection_trial as selection
from scripts import stack_multiscene_trial as stack

BATCH = "stack-goal-b-retest-v1"
VAULT = continuation.VAULT.with_name(BATCH)
MANIFEST = stack.PACK / "selection-b-retest-manifest.json"
SLOT = "B"
STAGES = ("normal", "rejections")


def manifest_sha():
    data = stack.read(MANIFEST)
    if (
        data["batch"] != BATCH or data["source_manifest_sha256"] != continuation.manifest_sha()
        or data["slot"] != SLOT or data["stages"] != list(STAGES)
        or data["budgets"] != dict(selection=0, body=len(STAGES), revision=0)
        or data["window_seconds"] != stack.WINDOW
        or any(stack.sha((stack.ROOT / path).read_bytes()) != expected
               for path, expected in data["files"].items())
    ):
        raise SnapshotError("STACK_PACKAGE_CHANGED")
    return stack.sha(MANIFEST.read_bytes())


def verify_source():
    manifest_sha()
    manifest = stack.read(MANIFEST)
    old = continuation.VAULT
    folder = old / SLOT
    failure = manifest["previous_failure"]
    raw = stack.raw_io.decrypt(folder / "normal.raw.enc", Fernet((folder / "raw.key").read_bytes()))
    if (
        stack.sha((old / "STOP").read_bytes()) != failure["stop_sha256"]
        or stack.sha((folder / "normal.request.json").read_bytes()) != failure["request_sha256"]
        or stack.sha(raw) != failure["response_sha256"]
        or stack.read(folder / "normal.attempt.json") != dict(
            request_sha256=failure["request_sha256"], state="attempted_result_unknown")
        or stack.read(folder / "normal.body.json") != dict(
            http_status=401, encoding="identity", complete=True,
            raw_sha256=failure["response_sha256"], raw_bytes=len(raw))
        or stack.read(folder / "normal.failure.json") != dict(
            code="STACK_BODY_RECEIPT", attempted=True)
        or stack.raw_io.wire.strict_json(raw)["error"]["type"] != "authentication_error"
    ):
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    _, source, owner = continuation.reviewed_parent(SLOT)
    if (
        source != manifest["reviewed_choice"]
        or stack.read(folder / "plan.admitted.json")["selection_replay"] != source
    ):
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    return source, {owner, *(UUID(value) for value in
                            stack.read(old / "batch.json")["approval"]["owners"].values())}


def approval_values(owner, *, fixture=False):
    return dict(
        batch=BATCH, owners={SLOT: str(UUID(str(owner)))}, manifest_sha256=manifest_sha(),
        mode="offline_fixture" if fixture else "actual_provider_response",
        approved=True, accept_batch_c2=not fixture, window_seconds=stack.WINDOW,
        selection_budget=0, body_budget=len(STAGES), revision_budget=0,
    )


class Batch(selection.Batch):
    def __init__(self, vault, url, *, transport=None):
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise SnapshotError("STACK_OFFLINE_TRANSPORT_REQUIRED")
        self.vault, self.url, self.transport = vault, url, transport
        self.fixture = transport is not None
        selection.require_database(url, fixture=self.fixture)
        if vault in (selection.VAULT, continuation.VAULT) or (not self.fixture and vault != VAULT):
            raise SnapshotError("STACK_VAULT_REQUIRED")

    def check_approval(self, approval):
        if approval.get("batch") != BATCH or approval != approval_values(
            approval["owners"][SLOT], fixture=self.fixture,
        ):
            raise SnapshotError("STACK_EXACT_AUTHORIZATION_REQUIRED")

    def start(self, approval):
        self.check_approval(approval)
        _, old_owners = verify_source()
        if UUID(approval["owners"][SLOT]) in old_owners:
            raise SnapshotError("STACK_SELECTOR_OWNERS")
        trial = continuation.ContinuationTrial(self, SLOT)
        self.vault.mkdir(mode=0o700)
        start = datetime.now(UTC)
        run = dict(approval=approval, starts_at=start.isoformat(),
                   expires_at=(start + timedelta(seconds=stack.WINDOW)).isoformat())
        stack.save(self.vault, "batch.json", run)
        try:
            courses = {SLOT: trial.start(trial.slot_approval())}
            trial.bind_parent()
            stack.save(self.vault, "READY", courses)
            return {**run, "courses": courses}
        except BaseException:
            self.stop()
            raise

    def perform(self, action, stage, *, review=None, key=None):
        if stage not in STAGES or action not in ("send", "inspect", "review"):
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
            folder = self.vault / SLOT
            if stage == "rejections" and not (folder / "normal.admitted.json").is_file():
                raise SnapshotError("STACK_SELECTOR_ORDER")
            try:
                trial = continuation.ContinuationTrial(self, SLOT)
            except Exception:
                self.stop()
                raise
            try:
                if action == "send":
                    return trial.send(stage, key=key)
                if action == "inspect":
                    return trial.inspect(stage)
                result = trial.review(stage, review)
                if stage == "rejections":
                    self.halt()
                return result
            except BaseException:
                if (folder / "STOP").exists() or (
                    action == "inspect" and (folder / f"{stage}.attempt.json").is_file()
                ):
                    self.stop()
                raise
        finally:
            (self.vault / "ACTIVE").unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("source", "start", "send", "inspect", "review", "stop"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("review", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "source":
            result = verify_source()[0]
        else:
            batch = Batch(VAULT, os.environ["EDUMIND_DATABASE_URL"])
            if args.action == "start":
                result = batch.start(stack.read(Path(args.value)))
            elif args.action == "stop":
                result = batch.stop()
            else:
                review = stack.read(args.review) if args.action == "review" else None
                result = batch.perform(args.action, args.value, review=review)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        print("Refused or stopped; preserve evidence.", getattr(error, "code", type(error).__name__))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
