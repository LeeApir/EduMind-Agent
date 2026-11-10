"""Run an approved fixed trial or replay a sealed historical course by topic."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.services.course_trial_publication import QUEUE, QUEUE_REVISION
from app.services.course_trial_replay import import_course, projection, require_database
from app.services.course_trial_sources import ARCHIVES
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
if sys.argv[1] == "queue":
    from scripts import course_trial_generation as trial
    from app.services.course_trial_publication import QUEUE
    record = trial.replay(trial.vault_path(QUEUE), profile=QUEUE)
    review = trial.read(trial.vault_path(QUEUE) / "review.json")
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


def read_frozen(topic):
    commit = (
        "898bbe4aedbc6f23e770997098737de645e905b5"
        if topic == QUEUE.topic
        else ARCHIVES[topic].frozen_commit
    )
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
        "--topic", required=True, choices=(*ARCHIVES, QUEUE.topic, "queue-revision")
    )
    parser.add_argument("--owner", type=UUID)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    if args.action != "send":
        sys.addaudithook(raw_io_audit)
    if args.topic == QUEUE.topic:
        if (
            args.action != "replay"
            or args.owner is not None
            or args.approval is not None
        ):
            parser.error("the stopped queue first draft supports replay only")
        record, _ = read_frozen(args.topic)
        print(record["candidate_digest"])
        return 0
    if args.topic == "queue-revision":
        if args.action != "prepare" and (
            args.owner is not None or args.approval is not None
        ):
            parser.error(
                "queue-revision --owner and --approval are only used by prepare"
            )
        return generation.run(parser, args, QUEUE_REVISION)
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
