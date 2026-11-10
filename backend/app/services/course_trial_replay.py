"""Atomic, zero-attempt private admission for the two sealed T120 courses."""

from uuid import UUID

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.database import get_database_url
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.course_trial_sources import ARCHIVES, verified_course
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, digest
from app.services.head_course_replay import ORIGIN, fingerprint

RULE = "sealed-course-trial-replay-v1"
DATABASE = "edumind_catalog_p15_t120_replay"


def require_database(url=None):
    parsed = make_url(url or get_database_url())
    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.host != "127.0.0.1"
        or parsed.port != 15437
        or parsed.database != DATABASE
    ):
        raise SnapshotError("TRIAL_REPLAY_DATABASE")


def require_session(db):
    bind = db.bind
    if isinstance(bind, AsyncConnection):
        bind = bind.engine
    if not isinstance(bind, AsyncEngine):
        raise SnapshotError("TRIAL_REPLAY_DATABASE")
    require_database(bind.url.render_as_string(hide_password=False))


def projection(topic, record, review):
    goal, plan, assembled = verified_course(topic, record, review)
    archive = ARCHIVES[topic]
    original = assembled["generation_source"]
    if original["batch"] != archive.batch:
        raise SnapshotError("TRIAL_REPLAY_BATCH")
    source = dict(
        mapping_version=RULE,
        origin=ORIGIN,
        topic=topic,
        batch=archive.batch,
        plan_source=archive.plan_source,
        historical_stage=archive.historical_stage,
        new_provider_calls=0,
        **{
            key: original[key]
            for key in (
                "candidate_digest",
                "parent_digest",
                "model",
                "prompt_version",
                "plan_digest",
                "materials_digest",
            )
        },
    )
    return (
        goal,
        plan,
        dict(blocks=assembled["blocks"], actions=assembled["actions"], replay_source=source),
    )


def validate_replay(db, row, actual):
    require_session(db)
    stored = row.input_snapshot["trial_replay"]
    topic = stored["topic"]
    goal, plan, expected = projection(topic, stored["record"], stored["review"])
    snapshot = dict(inputs=actual, trial_replay=stored)
    if (
        row.origin_type != ORIGIN
        or row.schema_version != RULE
        or row.sent_attempts != 0
        or row.usage_json is not None
        or row.state != "candidate"
        or row.reason_code is not None
        or row.input_snapshot != snapshot
        or row.input_digest != digest(RULE, snapshot=snapshot)
        or row.request_digest != ARCHIVES[topic].request_sha256
        or row.response_json != expected
        or row.response_digest != fingerprint(row)
        or str(row.request_id) != actual["request"]["request_id"]
        or row.prompt_version != expected["replay_source"]["prompt_version"]
        or actual["request"]["original_goal"] != goal
        or actual["plan"]["candidate"] != plan
    ):
        raise SnapshotError("TRIAL_REPLAY_BINDING")
    return dict(
        state="accepted",
        reason_code=None,
        findings=[],
        cleaned=dict(
            content=dict(blocks=expected["blocks"], replay_source=expected["replay_source"]),
            actions=expected["actions"],
            dependencies=[],
        ),
    )


async def import_course(db, owner: UUID, topic, record, review):
    from app.services.free_scene_availability import commit_outline, commit_scene
    from app.services.free_scene_generation import load_inputs
    from app.services.free_scene_validation import validate_candidate

    require_session(db)
    goal, plan, response = projection(topic, record, review)
    source = response["replay_source"]
    repo = SnapshotRepository(db, owner)
    key = f"{RULE}:{topic}:{source['candidate_digest']}"
    async with db.begin_nested():
        created = await repo.create_course(goal, key=key, config={"prompt_version": RULE})
        cid, oid = UUID(created["course_id"]), UUID(created["operation_id"])
        current = await repo.get_course(cid)
        if current["head_version"] is not None:
            v2 = await repo.get_version(cid, 2)
            return dict(**created, version=2, scene_id=v2["scenes"][0]["scene_id"], imported=False)

        fence = await repo.acquire_write_fence(cid, oid)
        saved = await repo.store_plan(
            cid, fence, expected_head=None, key="trial-plan", candidate=plan
        )
        pid = UUID(saved["plan_id"])
        sid = UUID((await repo.get_plan(cid, pid))["scenes"][0]["scene_id"])
        outline = await commit_outline(db, owner, cid, fence, plan_id=pid, key="trial-outline")
        actual = await load_inputs(
            db, owner, cid, oid, plan_id=pid, scene_id=sid, expected_head=outline["version"]
        )
        snapshot = dict(inputs=actual, trial_replay=dict(topic=topic, record=record, review=review))
        row = FreeSceneGenerationResult(
            user_id=owner,
            course_id=cid,
            operation_id=oid,
            request_id=UUID(actual["request"]["request_id"]),
            lease_epoch=fence.epoch,
            call_key=RULE,
            expected_head=outline["version"],
            input_snapshot=snapshot,
            input_digest=digest(RULE, snapshot=snapshot),
            request_digest=ARCHIVES[topic].request_sha256,
            response_json=response,
            prompt_version=source["prompt_version"],
            schema_version=RULE,
            state="candidate",
            reason_code=None,
            plan_id=pid,
            scene_id=sid,
            sent_attempts=0,
            usage_json=None,
            origin_type=ORIGIN,
        )
        row.response_digest = fingerprint(row)
        db.add(row)
        await db.flush()
        checked = await validate_candidate(db, owner, cid, fence, result_id=row.id)
        ready = await commit_scene(
            db,
            owner,
            cid,
            fence,
            validation_id=UUID(checked["validation_id"]),
            expected_head=outline["version"],
            key="trial-ready",
        )
        operation = await repo._operation(cid, oid)
        operation.state = "succeeded"
        operation.lease_token = operation.lease_expires_at = None
        return dict(**created, version=ready["version"], scene_id=str(sid), imported=True)
