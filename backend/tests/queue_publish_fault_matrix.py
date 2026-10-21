"""Real publisher death after Redis send and recovery before Worker consumption."""

import hashlib
import json
import os
import subprocess

import httpx
from redis import Redis

from tests import queue_acceptance_matrix as m
from tests import queue_fault_matrix as f

PLAN = m.ROOT / "docs/acceptance/phase-1-queue-v1/publish-fault-protocol.json"


def main():
    plan = json.loads(PLAN.read_text())
    for name, digest in plan["code_sha256"].items():
        assert hashlib.sha256((m.ROOT / name).read_bytes()).hexdigest() == digest, name
    m.report["protocol_sha256"] = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    m.release_id = m.database(m.signed_release)
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
    m.launch(["scripts/run_animation_host_controller.py"], "controller")
    job_id = f.create(unit, 87)
    marker = m.OUTPUT / "sent-marker"
    os.environ["EDUMIND_TEST_PUBLISH_MARKER"] = str(marker)
    publisher = m.launch(["-m", "tests.queue_publish_boundary"], "boundary-publisher")
    os.environ.pop("EDUMIND_TEST_PUBLISH_MARKER")
    f.wait(marker.exists, 15)
    assert marker.read_text() == job_id
    before = f.state(job_id)
    assert before["status"] == "queued" and before["attempt"] == 0
    f.stop(publisher)
    broker = Redis.from_url(os.environ["EDUMIND_ANIMATION_BROKER_URL"])
    queue = "edumind.animation:edumind.animation.v1"
    try:
        initial = broker.llen(queue)
        assert initial >= 1
        # Real 30-second publisher lease expiry, no forged database timestamps.
        m.launch(["scripts/run_animation_dispatcher.py"], "recovered-publisher")
        f.wait(lambda: broker.llen(queue) > initial, 45)
        duplicates = broker.llen(queue)
        f.launch_worker()
        after = f.complete(job_id)
        assert after["attempt"] == 1
        f.wait(lambda: broker.llen(queue) == 0, 10)
        assert f.state(job_id) == after
        f.record(
            "actual-publisher-after-send-death",
            job_id=job_id,
            before=before,
            after=after,
            actual_redis_deliveries=duplicates,
        )
    finally:
        broker.close()
    m.report["passed"] = True
    m.save()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        m.report["publish_fault_error"] = type(error).__name__ + ": " + str(error)[:400]
        m.save()
        raise
    finally:
        if m.client:
            m.client.close()
        for process in reversed(m.processes):
            f.stop(process)
        for log in m.logs:
            log.close()
