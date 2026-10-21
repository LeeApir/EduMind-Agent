"""One fixed render task; PG conditional claim is the delivery deduplication authority."""

import argparse
import asyncio
import logging
import os

from celery import Celery, current_app, shared_task, signals  # type: ignore[import-untyped]
from celery.app.trace import setup_worker_optimizations  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.services.animation_host import require_known_inventory
from app.services.animation_worker import claim_animation_job, run_one_animation_job
from app.services.durable_job_dispatch import TASK_NAME, DispatchMessage
from app.workers.animation_queue import create_queue_app


async def consume(payload: object) -> None:
    try:
        message = DispatchMessage.parse(payload)
    except ValueError:
        logging.getLogger(__name__).warning("INVALID_DISPATCH_MESSAGE")
        return
    engine = create_database_engine()
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await require_known_inventory(sessions)
        lease = await claim_animation_job(sessions, message=message)
        if lease is not None:
            await run_one_animation_job(sessions, lease=lease)
    finally:
        await engine.dispose()


def render_animation(payload: object) -> None:
    try:
        asyncio.run(consume(payload))
    except Exception:
        logging.getLogger(__name__).warning("ANIMATION_CONSUMER_INTERRUPTED")


# Explicit registration preserves the typed callable boundary with untyped Celery.
render_animation = shared_task(name=TASK_NAME, ignore_result=True)(render_animation)


def build_consumer() -> Celery:
    app = create_queue_app()
    app.conf.imports = ("app.workers.animation_consumer",)
    app.finalize()
    for name in tuple(app.tasks):
        if name != TASK_NAME:
            app.tasks.pop(name)
    return app


def initialize_consumer_process(**kwargs: object) -> None:
    # macOS spawn starts with an empty fast-trace cache. Initialize the fixed
    # app in every child, including replacement children after WorkerLost.
    if current_app.main == "edumind_animation":
        setup_worker_optimizations(current_app)
        for name in tuple(current_app.tasks):
            if name != TASK_NAME:
                current_app.tasks.pop(name)


signals.worker_process_init.connect(initialize_consumer_process, weak=False)


def main() -> None:
    if any(k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL")) for k in os.environ):
        raise RuntimeError("RENDER_WORKER_SENSITIVE_ENVIRONMENT")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", choices=("prefork", "solo"), default="prefork")
    pool = parser.parse_args().pool
    app = build_consumer()
    # Celery lacks upstream type stubs; retain the typed plain consumer above.
    app.worker_main(
        [
            "worker",
            "--loglevel=WARNING",
            "--concurrency=1",
            "--pool=" + pool,
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "--queues=edumind.animation.v1",
        ]
    )


if __name__ == "__main__":
    main()
