"""Trusted DSL matrix through real preparation/handoff/Celery/media, no real Provider."""

import hashlib
import json
import os
import signal
import sys
import time
from uuid import UUID

import httpx
from playwright.sync_api import sync_playwright
from sqlalchemy import func, select

from tests import queue_acceptance_matrix as m

sys.path.insert(0, str(m.ROOT / "backend/tests"))
from test_animation_dsl_review import GENERATION, FakeGateway  # noqa: E402

from app.agents.animation_dsl_review import AnimationDSLReviewAgent, canonical, digest  # noqa: E402
from app.core.auth import token_hash  # noqa: E402
from app.models.animation import AnimationResourceBinding  # noqa: E402
from app.models.learning import LearningScene, LearningUnit  # noqa: E402
from app.services.animation_dsl_candidates import (  # noqa: E402
    admit_current_policy,
    build_dsl_reference,
)
from app.services.animation_dsl_handoff import handoff_video_plan  # noqa: E402
from app.services.animation_intent import intent_from_payload  # noqa: E402
from app.services.animation_preparation import reserve_preparation  # noqa: E402
from app.services.knowledge_graph_versions import configured_graph_repository  # noqa: E402
from app.services.video_dsl_generation import VideoPlan  # noqa: E402

PLAN = m.ROOT / "docs/acceptance/phase-1-dsl-v1/matrix-protocol.json"
GRAPH = configured_graph_repository()
plans = {}
session_hash = None
unit = None
scene = None


def save():
    m.save()


def prepare_target(sessions):
    async def execute():
        async with sessions() as db, db.begin():
            await admit_current_policy(db)
            target = LearningUnit(user_id=m.owner, knowledge_point_id="array", status="ready")
            db.add(target)
            await db.flush()
            target_scene = LearningScene(
                learning_unit_id=target.id,
                scene_key="animation",
                scene_order=1,
                scene_type="video",
                version=1,
                generation_status="complete",
                review_status="passed",
            )
            db.add(target_scene)
            await db.flush()
            return target.id, target_scene.id

    return execute()


def handoff(sessions, case, key, cold):
    async def execute():
        intent = intent_from_payload(
            {
                "knowledge_point_id": "array",
                "operation": "compare",
                "parameters": {"values": case["values"]},
                "presentation": "standard",
            }
        )
        async with sessions() as db:
            reservation = await reserve_preparation(
                db,
                GRAPH,
                owner=m.owner,
                session_hash=session_hash,
                unit_id=unit,
                scene_id=scene,
                scene_version=1,
                intent=intent,
                idempotency_key=key,
            )
            reference = await build_dsl_reference(
                db, GRAPH, owner=m.owner, unit_id=unit, scene_id=scene, version=1
            )
            if case["id"] not in plans:
                mock = FakeGateway()
                outcome = await AnimationDSLReviewAgent(mock).review(
                    canonical(case["dsl"]),
                    reference=reference,
                    generation_source=GENERATION,
                    animation_intent=intent.payload(),
                )
                assert outcome.approved and len(mock.calls) == 1
                plans[case["id"]] = VideoPlan(
                    "generated_dsl",
                    digest({"intent": intent.payload(), "reference": reference.sha256}),
                    outcome=outcome,
                )
            plan = plans[case["id"]]
            job = await handoff_video_plan(
                db,
                GRAPH,
                owner=m.owner,
                session_hash=session_hash,
                operation_id=reservation.operation.id,
                execution_token=reservation.operation.execution_token,
                plan=plan,
            )
            assert job is not None and job.render_kind == "dsl"
            assert job.status == ("queued" if cold else "succeeded")
            return {
                "job_id": str(job.id),
                "compiled_sha256": plan.outcome.compiled.source_sha256,
                "dsl_sha256": plan.outcome.compiled.validated.dsl_sha256,
                "srt": plan.outcome.compiled.subtitles,
            }

    return execute()


def check_media(page, job_id, row, expected_srt=None):
    job = m.wait_job(job_id)
    assert job["status"] == "succeeded", job
    media = job["media_id"]
    result = m.media_play(page, media)
    assert 30 <= result["duration"] <= 90
    row.update(job_id=job_id, media_id=media, **result)
    for suffix in ("mp4", "srt"):
        exported = m.client.get(m.BASE + f"/api/animation-media/{media}/{suffix}?download=true")
        assert exported.status_code == 200 and len(exported.content) > 20
        row[suffix + "_sha256"] = hashlib.sha256(exported.content).hexdigest()
        if suffix == "srt":
            assert "-->" in exported.text
            if expected_srt is not None:
                assert exported.text == expected_srt
    return job


def main():
    global session_hash, unit, scene
    plan = json.loads(PLAN.read_text())
    for path, digest_value in plan["code_sha256"].items():
        assert hashlib.sha256((m.ROOT / path).read_bytes()).hexdigest() == digest_value, path
    assert not m.CACHE.exists()
    m.report.update(
        protocol_sha256=hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        dsl_slots=[],
        cache_slots=[],
        human_review="pending",
        qualification=(
            "TEST_ONLY target, trusted fixed DSL, explicit Mock review; "
            "actual PG/Celery/Manim/HTTP/Chromium"
        ),
    )
    m.release_id = m.database(m.signed_release)
    import subprocess

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(m.OUTPUT / "key.pem"),
            "-out",
            str(m.OUTPUT / "cert.pem"),
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    m.start_api(mock=True)
    m.client = httpx.Client(verify=False, timeout=15, trust_env=False)
    auth = m.client.post(m.BASE + "/api/auth/guest")
    assert auth.status_code == 201
    m.csrf, m.owner = auth.json()["csrf_token"], UUID(auth.json()["user"]["id"])
    session_hash = token_hash(m.client.cookies.get("edumind_session"))
    unit, scene = m.database(prepare_target)
    template_units = {
        name: m.enroll(name) for name in ("linked-list-insertion", "linked-list-deletion")
    }
    for args, label in (
        (["-m", "app.workers.animation_consumer", "--pool=solo"], "worker"),
        (["scripts/run_animation_dispatcher.py"], "publisher"),
        (["scripts/run_animation_host_controller.py"], "controller"),
    ):
        m.launch(args, label, "dynamic")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        context.add_cookies(
            [
                {
                    "name": "edumind_session",
                    "value": m.client.cookies.get("edumind_session"),
                    "url": m.BASE,
                    "secure": True,
                    "httpOnly": True,
                }
            ]
        )
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        for slot in plan["dsl_slots"]:
            case = plan["trusted_cases"][slot["case_index"]]
            row = {**slot, "ok": False}
            start = time.monotonic()
            try:
                receipt = m.database(
                    lambda sessions: handoff(sessions, case, slot["id"], slot["cold"])
                )
                check_media(page, receipt["job_id"], row, receipt["srt"])
                row.update(
                    ready_seconds=time.monotonic() - start,
                    compiled_sha256=receipt["compiled_sha256"],
                    dsl_sha256=receipt["dsl_sha256"],
                    ok=True,
                )
            except Exception as error:
                row["failure"] = type(error).__name__ + ": " + str(error)[:300]
            m.report["dsl_slots"].append(row)
            save()
            print("dsl", slot["id"], row["ok"], flush=True)
        assert sum(row["ok"] for row in m.report["dsl_slots"]) >= 98
        cold = [row for row in m.report["dsl_slots"] if row["cold"]]
        m.report["dsl_uncached_p95_seconds"] = m.percentile(cold, "ready_seconds", 20)
        assert isinstance(m.report["dsl_uncached_p95_seconds"], float)
        assert m.report["dsl_uncached_p95_seconds"] <= 90
        for slot in plan["template_slots"]:
            row = {**slot, "ok": False}
            start = time.monotonic()
            try:
                m.correct_links(slot["template_id"], slot["parameters"])
                response = m.post(
                    f"/api/learning-units/{template_units[slot['template_id']]}/animations",
                    {
                        "template_id": slot["template_id"],
                        "template_version": "1.0.0",
                        "scene_version": 1,
                        "parameters": slot["parameters"],
                    },
                    key=slot["id"],
                )
                assert response.status_code == (202 if slot["cold"] else 200), response.text
                check_media(page, response.json()["id"], row)
                row.update(ready_seconds=time.monotonic() - start, ok=True)
            except Exception as error:
                row["failure"] = type(error).__name__ + ": " + str(error)[:300]
            m.report["template_slots"].append(row)
            save()
            print("template", slot["id"], row["ok"], flush=True)
        assert sum(row["ok"] for row in m.report["template_slots"]) >= 98
        for slot in plan["cache_slots"]:
            row = {**slot, "ok": False}
            start = time.monotonic()
            try:
                if slot["source"] == "dsl":
                    case = plan["trusted_cases"][slot["case_index"]]
                    receipt = m.database(
                        lambda sessions: handoff(sessions, case, slot["id"], False)
                    )
                    job_id, subtitles = receipt["job_id"], receipt["srt"]
                else:
                    case = plan["template_slots"][slot["case_index"]]
                    response = m.post(
                        f"/api/learning-units/{template_units[case['template_id']]}/animations",
                        {
                            "template_id": case["template_id"],
                            "template_version": "1.0.0",
                            "scene_version": 1,
                            "parameters": case["parameters"],
                        },
                        key=slot["id"],
                    )
                    assert response.status_code == 200
                    job_id, subtitles = response.json()["id"], None
                check_media(page, job_id, row, subtitles)
                row["ready_seconds"] = time.monotonic() - start
                assert row["ready_seconds"] <= 2
                row["ok"] = True
            except Exception as error:
                row["failure"] = type(error).__name__ + ": " + str(error)[:300]
            m.report["cache_slots"].append(row)
            save()
        browser.close()
    assert len(m.report["cache_slots"]) == 100 and all(row["ok"] for row in m.report["cache_slots"])
    for source in ("dsl", "template"):
        rows = [row for row in m.report["cache_slots"] if row["source"] == source]
        m.report[source + "_cache_p95_seconds"] = m.percentile(rows, "ready_seconds", 50)

    async def bindings(sessions):
        async with sessions() as db:
            for row in m.report["dsl_slots"] + m.report["cache_slots"]:
                if row["ok"]:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(AnimationResourceBinding)
                            .where(AnimationResourceBinding.job_id == UUID(row["job_id"]))
                        )
                        == 1
                    )

    m.database(bindings)
    m.report["automatic_matrix_passed"] = True
    save()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        m.report["matrix_error"] = type(error).__name__ + ": " + str(error)[:400]
        save()
        raise
    finally:
        if m.client:
            m.client.close()
        for process in reversed(m.processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except Exception:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        for log in m.logs:
            log.close()
