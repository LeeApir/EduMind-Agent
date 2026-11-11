"""Read the stopped T128 archive and import its exact, separately reviewed derivation."""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.services import binary_search_course_frames as frames
from app.services import course_trial_replay as admission
from app.services.course_trial_publication import LIVE_REUSE
from app.services.free_course_snapshots import SnapshotError, canonical
from scripts import course_trial_generation as trial
from scripts import course_trial_live as live

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "1ebc6997d556c8d0a5a3426137d30d75650d7ffc9813441ecd6fd4b7b3070df8"
REVIEW = ROOT / "docs/acceptance/phase-1.5-binary-search-frames-t129/assessment.json"


def archived_parent():
    profile = LIVE_REUSE["binary-search"]
    run = live.load(MANIFEST)
    vault = live.private_root() / "binary-search"
    key = vault / "raw.key"
    if (
        vault.is_symlink() or vault.stat().st_mode & 0o077
        or key.is_symlink() or key.stat().st_mode & 0o077
        or not (vault / "HALT").is_file() or not (vault.parent / "HALT").is_file()
        or (vault / "published.json").exists()
    ):
        raise SnapshotError("BINARY_FRAMES_ARCHIVE")
    ctx = trial.read(vault / "context.json")
    approval = trial.read(vault / "approval.bound.json")
    if (
        ctx["live_run"] != live.binding(run)
        or ctx["owner"] != run["approval"]["owner"]
        or approval != dict(
            approval=run["approval"], context_sha256=trial.sha(canonical(ctx))
        )
    ):
        raise SnapshotError("BINARY_FRAMES_CONTEXT")
    return trial.replay_stage(vault, ctx, Fernet(key.read_bytes()), profile=profile, stage="generate")


async def publish(parent):
    admission.require_database(topic="binary-search")
    review = trial.read(REVIEW)
    engine = create_database_engine()
    try:
        async with AsyncSession(engine) as db, db.begin():
            return await admission.import_course(
                db, UUID(parent["context"]["owner"]), "binary-search", parent, review
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("derive", "publish"))
    args = parser.parse_args()
    parent = archived_parent()
    output = frames.candidate(parent) if args.action == "derive" else asyncio.run(publish(parent))
    print(canonical(output).decode())
