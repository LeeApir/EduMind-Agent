"""Fixed JSON-only Celery transport; no result backend or model configuration."""

import asyncio
import json
import logging
import os
import sys
from uuid import UUID

from celery import Celery  # type: ignore[import-untyped]
from kombu import Queue  # type: ignore[import-untyped]

from app.core.config import ConfigurationError
from app.services.durable_job_dispatch import QUEUE_NAME, TASK_NAME, DispatchClaim, DispatchMessage


def create_queue_app() -> Celery:
    broker = os.getenv("EDUMIND_ANIMATION_BROKER_URL", "")
    if not broker.startswith(("redis://", "rediss://")):
        raise ConfigurationError("A private Redis broker configuration is required.")
    app = Celery("edumind_animation", broker=broker, backend=None)
    app.conf.update(
        task_queues=(Queue(QUEUE_NAME),),
        task_default_queue=QUEUE_NAME,
        task_routes={TASK_NAME: {"queue": QUEUE_NAME}},
        task_create_missing_queues=False,
        accept_content=["json"],
        task_serializer="json",
        result_serializer="json",
        task_ignore_result=True,
        task_store_errors_even_if_ignored=False,
        task_publish_retry=False,
        broker_connection_retry=False,
        broker_connection_timeout=1,
        broker_transport_options={
            "visibility_timeout": 300,
            "socket_timeout": 1,
            "socket_connect_timeout": 1,
            "retry_on_timeout": False,
            "global_keyprefix": "edumind.animation:",
            "max_retries": 0,
        },
        task_send_sent_event=False,
        worker_send_task_events=False,
        worker_enable_remote_control=False,
        worker_hijack_root_logger=False,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_soft_time_limit=150,
        task_time_limit=180,
    )
    return app


async def send_dispatch(claim: DispatchClaim) -> None:
    """Killable child bounds DNS/connect/publish total, including unknown publish outcome."""
    # Whitelist env: no DB/Provider/KEK/session credential crosses into transport child.
    env = {
        k: os.environ[k]
        for k in ("PATH", "SYSTEMROOT", "EDUMIND_ANIMATION_BROKER_URL")
        if k in os.environ
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.workers.animation_queue",
        str(claim.outbox_id),
        json.dumps(claim.message.payload(), separators=(",", ":")),
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(4.5):
            code = await process.wait()
        if code != 0:
            raise RuntimeError("BROKER_UNAVAILABLE")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def main() -> None:
    logging.disable(logging.CRITICAL)
    try:
        outbox_id = str(UUID(sys.argv[1]))
        message = DispatchMessage.parse(json.loads(sys.argv[2]))
        app = create_queue_app()
        app.send_task(
            TASK_NAME,
            args=[message.payload()],
            task_id=outbox_id,
            queue=QUEUE_NAME,
            serializer="json",
            retry=False,
            ignore_result=True,
            argsrepr="(<internal dispatch>,)",
            kwargsrepr="{}",
        )
        app.close()
    except Exception:
        # Parent persists a fixed code; never emit transport exceptions/URLs.
        sys.exit(1)


if __name__ == "__main__":
    main()
