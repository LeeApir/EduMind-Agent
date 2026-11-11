"""One shared approval, window and stop marker for the T127 foreground run."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from app.services import course_trial_publication as publication
from app.services.course_trial_revision import VERSION
from app.services.free_course_snapshots import SnapshotError, canonical

from scripts.head_course_goal import raw_io


def root():
    return Path.home() / ".local/share/edumind" / publication.LIVE_BATCH


def approval_values(manifest_sha256, owner, *, approved):
    return dict(
        batch=publication.LIVE_BATCH,
        manifest_sha256=manifest_sha256,
        owner=str(owner),
        explicit_user_authorization=approved,
        accept_T127_scope_and_batch_C2=approved,
        window_seconds=publication.LIVE_WINDOW_SECONDS,
        operation_window_seconds=publication.WINDOW_SECONDS,
        max_http_requests=sum(publication.LIVE_REQUESTS.values()),
        stage_budgets=publication.LIVE_REQUESTS,
        max_revisions_per_topic=1,
        topics=list(publication.LIVE_REUSE),
        revision_version=VERSION,
    )


def check_approval(record, manifest_sha256):
    if not isinstance(record, dict) or not isinstance(record.get("owner"), str):
        raise SnapshotError("LIVE_EXACT_AUTHORIZATION_REQUIRED")
    try:
        owner = UUID(record["owner"])
    except ValueError:
        raise SnapshotError("LIVE_EXACT_AUTHORIZATION_REQUIRED") from None
    if canonical(record) != canonical(approval_values(manifest_sha256, owner, approved=True)):
        raise SnapshotError("LIVE_EXACT_AUTHORIZATION_REQUIRED")


def start(record, manifest_sha256):
    check_approval(record, manifest_sha256)
    # No database write, credential prompt or network access before exact approval.
    publication.require_database(profile=publication.LIVE_REUSE["head"])
    started = datetime.now(UTC)
    run = dict(
        approval=record,
        starts_at=started.isoformat(),
        expires_at=(started + timedelta(seconds=publication.LIVE_WINDOW_SECONDS)).isoformat(),
    )
    root().mkdir(mode=0o700)
    raw_io.exclusive(root() / "batch.json", canonical(run))
    return run


def binding(run):
    return dict(run_sha256=sha256(canonical(run)).hexdigest(), expires_at=run["expires_at"])


def private_root():
    directory = root()
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise SnapshotError("LIVE_AUTHORIZATION_REQUIRED")
    return directory


def load(manifest_sha256, *, active=False, profile=None, minimum=0):
    directory = private_root()
    record = directory / "batch.json"
    if record.is_symlink() or not record.is_file() or record.stat().st_mode & 0o077:
        raise SnapshotError("LIVE_AUTHORIZATION_REQUIRED")
    run = raw_io.wire.strict_json(record.read_bytes())
    if not isinstance(run, dict) or set(run) != {"approval", "starts_at", "expires_at"}:
        raise SnapshotError("LIVE_WINDOW_OR_BINDING")
    check_approval(run["approval"], manifest_sha256)
    start, end = (datetime.fromisoformat(run[name]) for name in ("starts_at", "expires_at"))
    if end - start != timedelta(seconds=publication.LIVE_WINDOW_SECONDS):
        raise SnapshotError("LIVE_WINDOW_OR_BINDING")
    if active:
        if (directory / "HALT").exists():
            raise SnapshotError("LIVE_BATCH_STOPPED")
        now = datetime.now(UTC)
        if not start <= now < end or end - now < timedelta(seconds=minimum):
            raise SnapshotError("LIVE_WINDOW_CLOSED")
        if profile is not None:
            topics = list(publication.LIVE_REUSE)
            run_sha = binding(run)["run_sha256"]
            for topic in topics[:topics.index(profile.topic)]:
                checkpoint = directory / topic / "published.json"
                if not checkpoint.is_file() or checkpoint.is_symlink():
                    raise SnapshotError("LIVE_PRIOR_TOPIC_REQUIRED")
                published = raw_io.wire.strict_json(checkpoint.read_bytes())
                if (
                    not isinstance(published, dict)
                    or published.get("topic") != topic
                    or published.get("run_sha256") != run_sha
                ):
                    raise SnapshotError("LIVE_PRIOR_TOPIC_REQUIRED")
    return run


def halt():
    try:
        raw_io.exclusive(
            private_root() / "HALT", b"four-topic run stopped; no more sends or admissions\n"
        )
    except FileExistsError:
        pass
