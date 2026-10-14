"""Actual signed catalog, Celery/Manim and loopback HTTP/browser T036 matrices."""

import asyncio
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from playwright.sync_api import sync_playwright
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_catalog_release import trusted_release, verify  # noqa: E402

from app.core.database import create_database_engine  # noqa: E402
from app.models.animation import (  # noqa: E402
    AnimationJobEvent,
    AnimationResourceBinding,
)
from app.services.catalog_package import load_package, read_json  # noqa: E402
from app.services.catalog_publication import publish_catalog  # noqa: E402
from tests.run_mvp03_animation_quality import correct_links  # noqa: E402

BASE = "https://127.0.0.1:8166"
PLAN = Path(
    os.environ.get(
        "EDUMIND_QUEUE_MATRIX_PROTOCOL",
        str(ROOT / "docs/acceptance/phase-1-queue-v1/matrix-protocol.json"),
    )
)
OUTPUT = Path(os.environ["EDUMIND_QUEUE_MATRIX_OUTPUT"])
CACHE = OUTPUT / "media-cache"
report = {
    "provider_requests": 0,
    "passed": False,
    "template_slots": [],
    "sse_slots": [],
    "faults": [],
    "qualification": (
        "actual signed catalog/PG/Redis/Celery/Manim/HTTP/Chromium; "
        "classroom uses explicit local MockProvider"
    ),
}
processes = []
logs = []
api_process = None
client = None
csrf = ""
owner = None
release_id = None


def save():
    temporary = OUTPUT / "matrix-result.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(OUTPUT / "matrix-result.json")


def database(work):
    async def execute():
        engine = create_database_engine()
        try:
            return await work(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(execute())


def environment(mode="catalog_only"):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
    }
    env.update(
        EDUMIND_PRODUCT_MODE=mode,
        EDUMIND_ANIMATION_DISPATCH="celery",
        EDUMIND_ANIMATION_CACHE_ROOT=str(CACHE),
        EDUMIND_RENDER_LOCK_ROOT=str(OUTPUT / "host-locks"),
        EDUMIND_KNOWLEDGE_GRAPH_VERSION="mvp-0.2.0",
    )
    return env


def launch(arguments, label, mode="catalog_only"):
    log = (OUTPUT / (label + ".log")).open("ab")
    logs.append(log)
    process = subprocess.Popen(
        [sys.executable, "-u", *arguments],
        cwd=ROOT / "backend",
        env=environment(mode),
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    processes.append(process)
    return process


def start_api(mock=False):
    global api_process
    arguments = [
        "-m",
        "tests.queue_acceptance_server",
        "--key",
        str(OUTPUT / "key.pem"),
        "--cert",
        str(OUTPUT / "cert.pem"),
    ]
    if mock:
        arguments.append("--mock-classroom")
    api_process = launch(arguments, "api", "dynamic" if mock else "catalog_only")
    last_health = "not probed"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            response = httpx.get(BASE + "/health", verify=False, timeout=1, trust_env=False)
            last_health = "HTTP " + str(response.status_code)
            if response.status_code == 200:
                return
        except httpx.HTTPError as error:
            last_health = type(error).__name__
        time.sleep(0.1)
    raise RuntimeError(f"Isolated API failed to start: {last_health}; exit={api_process.poll()}")


def restart_api(mock=False):
    old = api_process.pid
    api_process.kill()
    api_process.wait(timeout=5)
    start_api(mock)
    return {"old_api_pid": old, "new_api_pid": api_process.pid}


def post(path, body=None, *, key=None, revision=None):
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": key or uuid4().hex, "Origin": BASE}
    if revision is not None:
        headers["If-Match-Classroom-Revision"] = str(revision)
    return client.post(BASE + path, json=body or {}, headers=headers)


def enroll(node):
    response = post("/api/catalog/sessions", {"release_id": str(release_id), "node_id": node})
    assert response.status_code == 201, response.text
    return response.json()["learning_unit_id"]


def wait_job(job_id, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        response = client.get(BASE + f"/api/animation-jobs/{job_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.15)
    raise RuntimeError("Actual Celery/Manim Job timed out")


def event_frames(response):
    frame = {"event": "", "data": "", "id": ""}
    for line in response.iter_lines():
        if not line:
            if frame["event"]:
                yield dict(frame)
            frame = {"event": "", "data": "", "id": ""}
        elif ":" in line:
            key, value = line.split(":", 1)
            if key in frame:
                frame[key] = value.strip()


def media_play(page, media_id):
    url = BASE + f"/api/animation-media/{media_id}/mp4"
    page.goto(BASE + "/health")
    return page.evaluate(
        """async url => {
      document.body.innerHTML = '<video muted controls></video>';
      const video = document.querySelector('video');
      const started = performance.now();
      const result = await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('MEDIA_TIMEOUT')), 10000);
        video.addEventListener('error', () => reject(new Error('DECODE_FAILED')), {once:true});
        video.addEventListener('loadeddata', async () => {
          try {await video.play();} catch(e){clearTimeout(timer);reject(e);}
        }, {once:true});
        video.addEventListener('playing', () => {clearTimeout(timer);resolve({
          duration:video.duration, play_ms:performance.now()-started});}, {once:true});
        video.src = url;
      });
      return result;
    }""",
        url,
    )


def signed_release(sessions):
    async def work():
        directory = ROOT / "data/course_catalog/linear-v1"
        digest, approval = trusted_release(
            directory, ROOT / "data/course_catalog/release-allowlist.json"
        )
        assert verify(directory, digest, approval)["publishable"]
        async with sessions() as db:
            release = await publish_catalog(
                db, load_package(directory), approval=read_json(approval), trusted_digest=digest
            )
            await db.commit()
            report["signed_release_digest"] = digest
            return release.id

    return work()


def percentile(rows, key, denominator, rank=0.95):
    values = [
        row[key] if row.get("ok") and isinstance(row.get(key), (int, float)) else math.inf
        for row in rows
    ] + [math.inf] * (denominator - len(rows))
    value = sorted(values)[math.ceil(rank * denominator) - 1]
    return value if math.isfinite(value) else "+inf"


def main():
    global client, csrf, owner, release_id
    plan = json.loads(PLAN.read_text())
    assert not (OUTPUT / "matrix-result.json").exists()
    assert not CACHE.exists(), "Fresh namespace required for twenty misses"
    for name, digest in plan["code_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    report["protocol_sha256"] = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    release_id = database(signed_release)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(OUTPUT / "key.pem"),
            "-out",
            str(OUTPUT / "cert.pem"),
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
        ],
        check=True,
        capture_output=True,
        timeout=20,
    )
    start_api()
    client = httpx.Client(verify=False, timeout=15, trust_env=False)
    auth = client.post(BASE + "/api/auth/guest")
    assert auth.status_code == 201
    csrf, owner = auth.json()["csrf_token"], UUID(auth.json()["user"]["id"])
    units = {
        template: enroll(template) for template in ("linked-list-insertion", "linked-list-deletion")
    }
    launch(["-m", "app.workers.animation_consumer", "--pool=solo"], "worker")
    launch(["scripts/run_animation_dispatcher.py"], "publisher")
    launch(["scripts/run_animation_host_controller.py"], "controller")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        context.add_cookies(
            [
                {
                    "name": "edumind_session",
                    "value": client.cookies.get("edumind_session"),
                    "url": BASE,
                    "secure": True,
                    "httpOnly": True,
                }
            ]
        )
        page = context.new_page()
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        for slot in plan["template_slots"]:
            row = {**slot, "ok": False}
            started = time.monotonic()
            try:
                correct_links(slot["template_id"], slot["parameters"])
                response = post(
                    f"/api/learning-units/{units[slot['template_id']]}/animations",
                    {
                        "template_id": slot["template_id"],
                        "template_version": "1.0.0",
                        "scene_version": 1,
                        "parameters": slot["parameters"],
                    },
                    key=slot["id"],
                )
                expected = 202 if slot["cold"] else 200
                assert response.status_code == expected, response.text
                job_id = response.json()["id"]
                job = wait_job(job_id)
                assert job["status"] == "succeeded", job
                media_id = job["media_id"]
                playback = media_play(page, media_id)
                row["ready_seconds"] = time.monotonic() - started
                assert 30 <= playback["duration"] <= 90
                row.update(job_id=job_id, media_id=media_id, **playback)
                for suffix in ("mp4", "srt"):
                    exported = client.get(
                        BASE + f"/api/animation-media/{media_id}/{suffix}?download=true"
                    )
                    assert exported.status_code == 200 and len(exported.content) > 20
                    row[suffix + "_sha256"] = hashlib.sha256(exported.content).hexdigest()
                    if suffix == "srt":
                        assert "-->" in exported.text and exported.text.strip()
                if slot["cold"]:
                    page.screenshot(path=str(OUTPUT / (slot["id"] + ".png")))
                row["ok"] = True
            except Exception as error:
                row["failure"] = type(error).__name__ + ": " + str(error)[:300]
            report["template_slots"].append(row)
            save()
            print("template", slot["id"], row["ok"], flush=True)
        browser.close()
    assert sum(row["ok"] for row in report["template_slots"]) >= 98
    cold = [row for row in report["template_slots"] if row["cold"]]
    report["template_render_p95_seconds"] = percentile(cold, "ready_seconds", 20)
    assert (
        isinstance(report["template_render_p95_seconds"], float)
        and report["template_render_p95_seconds"] <= 90
    )
    # Actual socket close after one consumed Job event; replay from the durable cursor.
    for slot in plan["job_sse_slots"]:
        row = {**slot, "ok": False}
        job_id = report["template_slots"][slot["template_slot"]]["job_id"]
        path = BASE + f"/api/animation-jobs/{job_id}"
        try:
            with client.stream("GET", path + "/events") as stream:
                assert stream.status_code == 200
                first = next(event_frames(stream))
                cursor = int(first["id"])
            before = client.get(path).json()
            if slot["kind"] == "restart":
                row["restart"] = restart_api()
            elif slot["kind"] == "expired_cursor":

                async def expire(sessions):
                    async with sessions() as db:
                        await db.execute(
                            delete(AnimationJobEvent).where(
                                AnimationJobEvent.job_id == UUID(job_id),
                                AnimationJobEvent.event_id == cursor + 1,
                            )
                        )
                        await db.commit()

                database(expire)
            recovered = client.get(path + "/events", headers={"Last-Event-ID": str(cursor)})
            if slot["kind"] == "expired_cursor":
                assert recovered.status_code == 410
                snapshot = client.get(path).json()
                recovered = client.get(
                    path + "/events", headers={"Last-Event-ID": str(snapshot["last_event_id"])}
                )
            assert recovered.status_code == 200
            after = client.get(path).json()
            assert after["status"] == before["status"] == "succeeded"
            assert after["media_id"] == before["media_id"]
            row.update(job_id=job_id, cursor=cursor, media_id=after["media_id"], ok=True)
        except Exception as error:
            row["failure"] = type(error).__name__ + ": " + str(error)[:200]
        report["sse_slots"].append(row)
        save()
    restart_api(mock=True)
    for slot in plan["classroom_sse_slots"]:
        row = {**slot, "ok": False}
        unit = enroll("linked-list-insertion")
        path = BASE + f"/api/learning-units/{unit}/classroom"
        try:
            assert post(f"/api/learning-units/{unit}/classroom").status_code == 201
            body = {"text": "继续讲解", "scene_version": 1}
            headers = {
                "X-CSRF-Token": csrf,
                "Origin": BASE,
                "Idempotency-Key": slot["id"],
                "If-Match-Classroom-Revision": "1",
            }
            operation = None
            with client.stream("POST", path + "/messages", json=body, headers=headers) as stream:
                assert stream.status_code == 200
                for frame in event_frames(stream):
                    data = json.loads(frame["data"])
                    if frame["event"] == "agent_start":
                        operation = data["operation_id"]
                    if frame["event"] == "message_ready":
                        break
            assert operation
            original = client.get(path + "/messages").json()
            if slot["kind"] == "restart":
                row["restart"] = restart_api(mock=True)
            calls = client.get(BASE + "/test-only/mock-calls").json()
            replay = client.post(path + "/messages", json=body, headers=headers)
            assert replay.status_code == 200 and '"status":"published"' in replay.text.replace(
                " ", ""
            )
            assert client.get(path + "/messages").json() == original
            assert client.get(BASE + "/test-only/mock-calls").json() == calls
            assert (
                client.get(BASE + "/api/classroom-operations/" + operation).json()["status"]
                == "published"
            )
            row.update(operation_id=operation, unit_id=unit, ok=True)
        except Exception as error:
            row["failure"] = type(error).__name__ + ": " + str(error)[:200]
        report["sse_slots"].append(row)
        save()
    assert len(report["sse_slots"]) == 100 and sum(row["ok"] for row in report["sse_slots"]) >= 99

    async def bindings(sessions):
        async with sessions() as db:
            for row in report["template_slots"]:
                if row["ok"]:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(AnimationResourceBinding)
                            .where(
                                AnimationResourceBinding.job_id == UUID(row["job_id"]),
                                AnimationResourceBinding.user_id == owner,
                            )
                        )
                        == 1
                    )

    database(bindings)
    report["matrix_passed"] = True
    # ADR84 extra windows are a separate group and cannot be hidden by this matrix.
    report["remaining_fault_windows"] = [
        "API accepted-before-send death",
        "ACK before/after",
        "DB loss",
        "running signed release withdrawal",
    ]
    save()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        report["matrix_error"] = type(error).__name__ + ": " + str(error)[:400]
        save()
        raise
    finally:
        if client:
            client.close()
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        for log in logs:
            log.close()
