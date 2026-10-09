"""Actual isolated API/ACK/database/rollback/revocation fault windows for T036."""

import hashlib
import json
import os
import signal
import time
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.models.animation import AnimationJob, AnimationJobAttempt, AnimationResourceBinding
from app.services.animation_host import inventory
from app.services.catalog_publication import revoke_catalog
from app.services.durable_job_dispatch import (
    QUEUE_NAME,
    TASK_NAME,
    DispatchMessage,
    route_queued_template_jobs,
)
from app.workers.animation_queue import create_queue_app
from tests import queue_acceptance_matrix as m

PLAN = m.ROOT / "docs/acceptance/phase-1-queue-v1/fault-matrix-protocol.json"
worker = None


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def wait(predicate, seconds=45):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("Actual fault boundary timed out")


def state(job_id):
    async def read(sessions):
        async with sessions() as db:
            job = await db.get(AnimationJob, UUID(job_id))
            attempt = (
                await db.get(AnimationJobAttempt, job.lease_token) if job.lease_token else None
            )
            bindings = await db.scalar(
                select(func.count())
                .select_from(AnimationResourceBinding)
                .where(AnimationResourceBinding.job_id == job.id)
            )
            return {
                "status": job.status,
                "attempt": job.attempt,
                "epoch": job.dispatch_epoch,
                "token": str(job.lease_token) if job.lease_token else None,
                "launch": attempt.launch_state if attempt else None,
                "bindings": bindings,
                "media_id": str(job.media_id) if job.media_id else None,
                "error_code": job.error_code,
            }

    return m.database(read)


def started(job_id):
    current = state(job_id)
    return current if current["status"] == "running" and current["launch"] == "started" else None


def complete(job_id):
    job = m.wait_job(job_id)
    assert job["status"] == "succeeded", job
    current = state(job_id)
    assert current["bindings"] == 1 and current["attempt"] <= 2
    return current


def create(unit, number):
    response = m.post(
        f"/api/learning-units/{unit}/animations",
        {
            "template_id": "linked-list-insertion",
            "template_version": "1.0.0",
            "scene_version": 1,
            "parameters": {"values": [11, 22, 33, 44, 55, 66, 77], "index": 4, "value": number},
        },
        key=f"T036-real-fault-{number:02}",
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def launch_worker(extra=None):
    global worker
    saved = {key: os.environ.get(key) for key in (extra or {})}
    os.environ.update(extra or {})
    try:
        module = (
            "tests.queue_ack_worker"
            if extra and "EDUMIND_TEST_ACK_JOB" in extra
            else ("app.workers.animation_consumer")
        )
        worker = m.launch(["-m", module, "--pool=solo"], "fault-worker")
        return worker
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def deliver(job_id, epoch):
    app = create_queue_app()
    try:
        app.send_task(
            TASK_NAME,
            args=[DispatchMessage(UUID(job_id), epoch).payload()],
            queue=QUEUE_NAME,
            serializer="json",
            retry=False,
            ignore_result=True,
            argsrepr="(<internal dispatch>,)",
            kwargsrepr="{}",
        )
    finally:
        app.close()


def record(kind, **evidence):
    m.report["faults"].append({"kind": kind, "ok": True, **evidence})
    m.save()
    print("fault", kind, "passed", flush=True)


def main():
    plan = json.loads(PLAN.read_text())
    for name, digest in plan["code_sha256"].items():
        assert hashlib.sha256((m.ROOT / name).read_bytes()).hexdigest() == digest, name
    m.report["protocol_sha256"] = hashlib.sha256(PLAN.read_bytes()).hexdigest()
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
    m.start_api()
    m.client = httpx.Client(verify=False, timeout=15, trust_env=False)
    auth = m.client.post(m.BASE + "/api/auth/guest")
    assert auth.status_code == 201
    m.csrf = auth.json()["csrf_token"]
    unit = m.enroll("linked-list-insertion")
    m.launch(["scripts/run_animation_host_controller.py"], "fault-controller")
    publisher = m.launch(["scripts/run_animation_dispatcher.py"], "fault-publisher")
    # Accepted transaction exists while publisher is physically paused, then API dies.
    os.kill(publisher.pid, signal.SIGSTOP)
    job_id = create(unit, 81)
    initial = state(job_id)
    assert initial["status"] == "queued" and initial["attempt"] == 0
    restart = m.restart_api()
    assert state(job_id) == initial
    launch_worker()
    os.kill(publisher.pid, signal.SIGCONT)
    record(
        "accepted-before-send/API-death",
        job_id=job_id,
        before=initial,
        after=complete(job_id),
        restart=restart,
    )
    stop(worker)
    # Pause actual Celery Request.acknowledge before or after the locked Redis ACK.
    for index, boundary in enumerate(("before", "after")):
        job_id = create(unit, 82 + index)
        marker = m.OUTPUT / ("ack-" + boundary + ".json")
        launch_worker(
            {
                "EDUMIND_TEST_ACK_JOB": job_id,
                "EDUMIND_TEST_ACK_BOUNDARY": boundary,
                "EDUMIND_TEST_ACK_MARKER": str(marker),
            }
        )
        wait(marker.exists, 60)
        evidence = json.loads(marker.read_text())
        assert evidence["acknowledged"] is (boundary == "after")
        before = state(job_id)
        assert before["status"] == "succeeded"
        stop(worker)
        launch_worker()
        # Genuine transport redelivery plus an old epoch; no extra render or binding.
        deliver(job_id, before["epoch"])
        deliver(job_id, max(1, before["epoch"] - 1))
        time.sleep(2)
        after = complete(job_id)
        assert after == before
        record(
            "ACK-" + boundary + "-death/duplicate",
            job_id=job_id,
            ack=evidence,
            before=before,
            after=after,
        )
        stop(worker)
    # Disconnect only this Worker's real PG tunnel, leaving API/reaper PG available.
    url = make_url(os.environ["EDUMIND_DATABASE_URL"])
    drop, ready = m.OUTPUT / "drop-proxy", m.OUTPUT / "proxy-ready"
    m.launch(
        [
            "-m",
            "tests.queue_database_proxy",
            "--port",
            "16466",
            "--target",
            str(url.port),
            "--drop",
            str(drop),
            "--ready",
            str(ready),
        ],
        "database-proxy",
    )
    wait(ready.exists, 10)
    job_id = create(unit, 84)
    launch_worker(
        {"EDUMIND_DATABASE_URL": url.set(port=16466).render_as_string(hide_password=False)}
    )
    old = wait(lambda: started(job_id), 40)
    drop.write_text("disconnect")
    stop_started = time.monotonic()
    old_container = "edumind-render-" + UUID(old["token"]).hex
    wait(lambda: old_container not in inventory(), 10)
    cleanup_seconds = time.monotonic() - stop_started
    assert cleanup_seconds <= 10
    stop(worker)
    recovered = wait(lambda: state(job_id) if state(job_id)["status"] == "queued" else None, 45)
    assert recovered["epoch"] > old["epoch"]
    launch_worker()
    after = complete(job_id)
    assert after["attempt"] == 2
    record(
        "real-Worker-DB-loss",
        job_id=job_id,
        before=old,
        recovered=recovered,
        after=after,
        container_cleanup_seconds=cleanup_seconds,
    )
    stop(worker)
    # Roll the same accepted queued job to PG, then keep Celery consuming stale messages.
    job_id = create(unit, 85)
    before = state(job_id)

    async def rollback(sessions):
        return await route_queued_template_jobs(sessions, (UUID(job_id),), backend="pg_poll")

    assert m.database(rollback) == 1
    launch_worker()
    deliver(job_id, before["epoch"])
    pg = m.launch(["scripts/run_animation_worker.py", "--poll-seconds", "0.1"], "pg-worker")
    after = complete(job_id)
    assert after["epoch"] > before["epoch"] and after["attempt"] == 1
    record("real-rolling-rollback", job_id=job_id, before=before, after=after)
    stop(pg)
    # Owner exports remain authorized; a distinct real guest receives no permission.
    notes = m.client.get(m.BASE + f"/api/learning-units/{unit}/notes.md")
    assert notes.status_code == 200 and "链表" in notes.text
    other = httpx.Client(verify=False, timeout=15, trust_env=False)
    try:
        assert other.post(m.BASE + "/api/auth/guest").status_code == 201
        for suffix in ("mp4", "srt"):
            assert (
                other.get(m.BASE + f"/api/animation-media/{after['media_id']}/{suffix}").status_code
                == 404
            )
    finally:
        other.close()
    record(
        "notes-and-owner-export-authorization",
        notes_sha256=hashlib.sha256(notes.content).hexdigest(),
    )
    # Irreversible withdrawal is last and touches only the new test DB publication.
    job_id = create(unit, 86)
    old = wait(lambda: started(job_id), 40)

    async def withdraw(sessions):
        async with sessions() as db:
            await revoke_catalog(db, m.release_id)
            await db.commit()

    m.database(withdraw)
    end = wait(
        lambda: state(job_id) if state(job_id)["status"] in {"failed", "cancelled"} else None, 45
    )
    assert end["bindings"] == 0 and end["media_id"] is None
    assert m.client.get(m.BASE + f"/api/learning-units/{unit}/notes.md").status_code == 404
    record("running-signed-release-withdrawal", job_id=job_id, before=old, after=end)
    m.report["passed"] = True
    m.save()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        m.report["fault_matrix_error"] = type(error).__name__ + ": " + str(error)[:400]
        m.save()
        raise
    finally:
        if m.client:
            m.client.close()
        for process in reversed(m.processes):
            if process.poll() is None:
                # A paused publisher is still our own process and must be killed too.
                stop(process)
        for log in m.logs:
            log.close()
