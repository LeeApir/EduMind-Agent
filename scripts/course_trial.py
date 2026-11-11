"""Run an approved fixed trial or replay a sealed historical course by topic."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from app.core.database import create_database_engine
from app.services.course_trial_publication import (
    BINARY_SEARCH,
    BINARY_SEARCH_REVISION,
    NEW_BATCHES,
    QUEUE,
)
from app.services.course_trial_replay import import_course, projection, require_database
from app.services.course_trial_sources import ARCHIVES
from sqlalchemy.ext.asyncio import AsyncSession

from scripts import course_trial_generation as generation
from scripts.head_course_goal import ROOT, raw_io_audit

# Run each unchanged reader from its original commit. Its full manifest still validates even
# when the current runtime has evolved. Only the verified bundle crosses back to this process.
READ_FROZEN = """
import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path.cwd() / "backend"), str(Path.cwd())]
from scripts.head_course_goal import raw_io_audit
sys.addaudithook(raw_io_audit)
if sys.argv[1] in ("queue", "queue-revision", "binary-search", "binary-search-revision"):
    from scripts import course_trial_generation as trial
    from app.services import course_trial_publication as publication
    profile = getattr(publication, sys.argv[1].upper().replace("-", "_"))
    vault = trial.vault_path(profile)
    record = trial.replay(vault, profile=profile)
    review = trial.read(vault / "review.json")
elif sys.argv[1] == "head":
    from scripts import head_course_fact_revision as trial
    trial.select_profile("citation")
    record = trial.read_saved(trial.VAULT)
    review = trial.old.read(trial.VAULT / "final-review.json")
else:
    from scripts import stack_course_trial as trial
    record = trial.replay(trial.VAULT)
    review = trial.read(trial.VAULT / "review.json")
print(json.dumps([record, review], ensure_ascii=False))
"""


QUEUE_ARCHIVES = {
    QUEUE.topic: "898bbe4aedbc6f23e770997098737de645e905b5",
    "queue-revision": "f227dce7f30a92917bb8d176838e454202b5ff14",
}
BINARY_ARCHIVES = {
    "binary-search": "955c15ba50313b1fac8549dfece2bbfc5a908ada",
    "binary-search-revision": "9c74602db0fef0055efc0ff017af424968dcdfe1",
}


def read_frozen(topic):
    commit = (QUEUE_ARCHIVES | BINARY_ARCHIVES).get(topic) or ARCHIVES[topic].frozen_commit
    with TemporaryDirectory(prefix="edumind-trial-replay-") as tmp:
        checkout = Path(tmp)
        tar = checkout / "frozen.tar"
        with tar.open("wb") as out:
            subprocess.run(
                ["git", "archive", commit],
                cwd=ROOT,
                stdout=out,
                check=True,
            )
        with tarfile.open(tar) as source:
            source.extractall(checkout, filter="data")
        env = {
            key: os.environ[key]
            for key in ("HOME", "PATH", "TMPDIR")
            if key in os.environ
        }
        result = subprocess.run(
            [sys.executable, "-I", "-c", READ_FROZEN, topic],
            cwd=checkout,
            env=env,
            stdout=subprocess.PIPE,
            check=True,
        )
    return json.loads(result.stdout)


async def publish(owner, topic, record, review):
    require_database()
    engine = create_database_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
            return await import_course(db, owner, topic, record, review)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("inspect", "prepare", "send", "replay", "publish", "stop")
    )
    parser.add_argument(
        "--topic",
        required=True,
        choices=(
            *ARCHIVES,
            *QUEUE_ARCHIVES,
            BINARY_SEARCH.topic,
            "binary-search-revision",
        ),
    )
    parser.add_argument("--owner", type=UUID)
    parser.add_argument("--approval", type=Path)
    parser.add_argument(
        "--new-batch", action="store_true", help="select the T125 first-draft batch"
    )
    parser.add_argument("--stage", choices=("plan", "generate"))
    args = parser.parse_args()
    if args.action != "send":
        sys.addaudithook(raw_io_audit)
    if args.new_batch:
        profile = NEW_BATCHES.get(args.topic)
        if profile is None:
            parser.error("new batches support only the four first-draft topics")
        if args.action != "prepare" and (args.owner is not None or args.approval is not None):
            parser.error("--owner and --approval are only used by prepare")
        if args.stage and (
            args.action not in {"send", "replay"}
            or (args.stage == "plan" and not profile.model_planned)
        ):
            parser.error("--stage is for send/replay; only head has a plan stage")
        return generation.run(parser, args, profile)
    if args.stage:
        parser.error("--stage requires --new-batch")
    if args.topic in QUEUE_ARCHIVES or (args.topic in BINARY_ARCHIVES and args.action == "replay"):
        if (
            args.action != "replay"
            or args.owner is not None
            or args.approval is not None
        ):
            parser.error("sealed queue batches support replay only")
        record, _ = read_frozen(args.topic)
        print(record["candidate_digest"])
        return 0
    if args.topic in (BINARY_SEARCH.topic, "binary-search-revision"):
        if args.action != "prepare" and (
            args.owner is not None or args.approval is not None
        ):
            parser.error(
                "--owner and --approval are only used by prepare for binary-search trials"
            )
        profile = (
            BINARY_SEARCH
            if args.topic == BINARY_SEARCH.topic
            else BINARY_SEARCH_REVISION
        )
        return generation.run(parser, args, profile)
    if args.action not in {"replay", "publish"} or args.approval is not None:
        parser.error("archived topics support replay and publish")
    if (args.action == "publish") != (args.owner is not None):
        parser.error("publish requires --owner; replay does not accept --owner")
    record, review = read_frozen(args.topic)
    if args.action == "replay":
        _, _, assembled = projection(args.topic, record, review)
        result = assembled["replay_source"]
    else:
        result = asyncio.run(publish(args.owner, args.topic, record, review))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
