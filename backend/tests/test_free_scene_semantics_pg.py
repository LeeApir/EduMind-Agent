"""Real isolated PG, frozen v3 producer vs v4 producer; no real Provider or generated code run."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from test_free_course_api import dbwork
from test_free_course_api import migrate as migrate
from test_free_scene_answer_contract import closed_candidate
from test_free_scene_generation import Gateway, authorize, prepare, response
from test_p15_split_provider import only_pg_network as only_pg_network

from app.agents import free_scene_generation as agent
from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services import free_scene_generation as storage
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository

ROOT = Path(__file__).resolve().parents[2]
LEGACY_COMMIT = "97130f5"


def legacy_producer(tmp_path):
    # Import the exact previously committed producer and unchanged Schema; no fake version tag.
    for suffix in (".py", ".schema.json"):
        path = "backend/app/agents/free_scene_generation" + suffix
        data = subprocess.run(
            ["git", "show", LEGACY_COMMIT + ":" + path],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        (tmp_path / ("legacy_scene" + suffix)).write_bytes(data)
    name = "edumind_test_frozen_scene_v3"
    spec = importlib.util.spec_from_file_location(name, tmp_path / "legacy_scene.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.PROMPT_VERSION == "free-scene-generation-v3"
    assert module.SCHEMA == agent.SCHEMA
    return module


def test_v4_semantic_request_keeps_actual_v3_facts_immutable(tmp_path, monkeypatch):
    legacy = legacy_producer(tmp_path)

    async def run(sessions):
        owner, other = uuid4(), uuid4()
        try:
            async with sessions() as db:
                db.add_all([User(id=owner, is_guest=True), User(id=other, is_guest=True)])
                await db.commit()
                repo, cid, fence, pid, plan, _ = await prepare(db, owner)
                data = await storage.load_inputs(
                    db,
                    owner,
                    cid,
                    fence.operation_id,
                    plan_id=pid,
                    scene_id=UUID(plan["scenes"][2]["scene_id"]),
                    expected_head=1,
                )
            old_raw = response()
            old_raw["blocks"][2]["items"][0].update(
                question="请用一句话说明数组如何定位", answer_key="按偏移定位元素"
            )
            old_gateway = Gateway(old_raw)
            old_outcome = await legacy.generate_once(old_gateway, data, authorize_send=authorize)
            async with sessions() as db:
                with monkeypatch.context() as previous:
                    previous.setattr(storage, "build_request", legacy.build_request)
                    previous.setattr(storage, "PROMPT_VERSION", legacy.PROMPT_VERSION)
                    old = await storage.persist_outcome(
                        db,
                        owner,
                        cid,
                        fence,
                        call_key="legacy-v3",
                        inputs=data,
                        outcome=old_outcome,
                    )
                    await db.commit()
                old_row = await db.get(FreeSceneGenerationResult, UUID(old["result_id"]))
                old_digest = old_row.response_digest
                old_identity = old_row.request_digest
            new_gateway = Gateway(closed_candidate())
            new_outcome = await agent.generate_once(new_gateway, data, authorize_send=authorize)
            payload = json.loads(new_gateway.requests[0].prompt.messages[-1].content)
            assert payload["prompt_version"] == "free-scene-generation-v4"
            assert (
                payload["response_contract"]["semantic_contract"]["semantic_correctness_verified"]
                is False
            )
            assert payload["upstream"] == data["upstream"] and len(data["upstream"]) == 2
            assert payload["request"] == data["request"]
            assert new_outcome.request_digest != old_identity
            async with sessions() as db:
                fresh = await storage.persist_outcome(
                    db, owner, cid, fence, call_key="fresh-v4", inputs=data, outcome=new_outcome
                )
                assert fresh == await storage.persist_outcome(
                    db, owner, cid, fence, call_key="fresh-v4", inputs=data, outcome=new_outcome
                )
                with pytest.raises(SnapshotError, match="SCENE_INPUT_MISMATCH"):
                    await storage.persist_outcome(
                        db,
                        owner,
                        cid,
                        fence,
                        call_key="legacy-v3",
                        inputs=data,
                        outcome=old_outcome,
                    )
                with pytest.raises(SnapshotError):
                    await storage.persist_outcome(
                        db,
                        other,
                        cid,
                        fence,
                        call_key="wrong-owner",
                        inputs=data,
                        outcome=new_outcome,
                    )
                await db.commit()
            async with sessions() as db:
                rows = (
                    await db.scalars(
                        select(FreeSceneGenerationResult).where(
                            FreeSceneGenerationResult.course_id == cid
                        )
                    )
                ).all()
                assert len(rows) == 2
                assert {r.prompt_version for r in rows} == {
                    "free-scene-generation-v3",
                    "free-scene-generation-v4",
                }
                previous = next(r for r in rows if r.id == UUID(old["result_id"]))
                assert previous.response_json == old_raw and previous.response_digest == old_digest
                assert previous.request_digest == old_identity
                fresh_row = next(r for r in rows if r.id == UUID(fresh["result_id"]))
                assert fresh_row.response_json == closed_candidate()
                assert fresh_row.input_snapshot == data
                assert fresh_row.request_digest == new_outcome.request_digest
                assert (
                    len(
                        (
                            await db.scalars(
                                select(FreeCourseSceneVersion).where(
                                    FreeCourseSceneVersion.course_id == cid
                                )
                            )
                        ).all()
                    )
                    == 2
                )  # Pre-existing upstream only; no ready/publication.
                assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 1
                for row in rows:
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(
                                text(
                                    "UPDATE free_course_scene_generation_results "
                                    "SET prompt_version='forged' WHERE id=:i"
                                ),
                                {"i": row.id},
                            )
            assert len(old_gateway.requests) == len(new_gateway.requests) == 1
        finally:
            async with sessions() as db, db.begin():
                await db.execute(
                    text("DELETE FROM users WHERE id IN (:a,:b)"), dict(a=owner, b=other)
                )

    dbwork(run)
