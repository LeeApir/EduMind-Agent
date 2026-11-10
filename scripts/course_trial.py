"""Select a sealed course trial by topic and replay or admit it without Provider traffic."""

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
from app.services.course_trial_replay import import_course, projection, require_database
from app.services.course_trial_sources import ARCHIVES
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
if sys.argv[1] == "head":
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
    archive = ARCHIVES[topic]
    with TemporaryDirectory(prefix="edumind-trial-replay-") as tmp:
        checkout = Path(tmp)
        tar = checkout / "frozen.tar"
        with tar.open("wb") as out:
            subprocess.run(
                ["git", "archive", archive.frozen_commit],
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
    parser.add_argument("action", choices=("replay", "publish"))
    parser.add_argument("--topic", required=True, choices=ARCHIVES)
    parser.add_argument("--owner", type=UUID)
    args = parser.parse_args()
    if (args.action == "publish") != (args.owner is not None):
        parser.error("publish requires --owner; replay does not accept --owner")
    sys.addaudithook(raw_io_audit)
    record, review = read_frozen(args.topic)
    if args.action == "replay":
        _, _, assembled = projection(args.topic, record, review)
        result = assembled["replay_source"]
    else:
        result = asyncio.run(publish(args.owner, args.topic, record, review))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
