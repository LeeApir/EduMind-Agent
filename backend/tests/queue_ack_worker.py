"""Pause the real fixed Celery consumer at one specified late-ACK boundary."""

import json
import os
import signal
from pathlib import Path

from celery.worker.request import Request

from app.workers.animation_consumer import main

original = Request.acknowledge


def acknowledge(request):
    target = os.environ["EDUMIND_TEST_ACK_JOB"]
    payload = request.args[0] if request.args else None
    matched = isinstance(payload, dict) and payload.get("job_id") == target
    if not matched:
        return original(request)
    boundary = os.environ["EDUMIND_TEST_ACK_BOUNDARY"]
    if boundary == "after":
        original(request)
    Path(os.environ["EDUMIND_TEST_ACK_MARKER"]).write_text(
        json.dumps({"boundary": boundary, "acknowledged": request.acknowledged, "job_id": target})
    )
    os.kill(os.getpid(), signal.SIGSTOP)
    raise RuntimeError("Test controller must kill this paused process")


if __name__ == "__main__":
    Request.acknowledge = acknowledge
    main()
