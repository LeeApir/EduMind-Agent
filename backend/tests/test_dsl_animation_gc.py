"""Real PG + private namespace locks and orphan age gates; no media quality claims."""

import asyncio
import hashlib
import os
import time
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_animation_dsl_review import RAW

from app.core.database import create_database_engine
from app.services.animation_dsl_compiler import compile_animation_dsl
from app.services.animation_dsl_gc import collect_private_dsl_orphans
from app.services.animation_dsl_media_cache import AnimationDSLMediaCache, private_dsl_root
from app.services.animation_renderer import RenderedCandidate

pytestmark = pytest.mark.skipif(
    not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="dedicated PG required"
)


def test_pg_private_orphan_namespace_lock_and_24h_age(tmp_path):
    async def exercise():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            cache = AnimationDSLMediaCache(tmp_path / "cache")
            owner, key = uuid4(), "a" * 64
            compiled = compile_animation_dsl(RAW, knowledge_point_id="arrays")
            candidate_dir = tmp_path / "fixture"
            candidate_dir.mkdir()
            mp4, srt = candidate_dir / "fixture.mp4", candidate_dir / "fixture.srt"
            # Byte fixture tests cleanup only, never publication/decode acceptance.
            mp4.write_bytes(b"GC-ONLY-NOT-FORMAL-MEDIA")
            srt.write_text(compiled.subtitles)
            candidate = RenderedCandidate(
                candidate_dir,
                mp4,
                srt,
                compiled.validated.duration_ms / 1000,
                hashlib.sha256(mp4.read_bytes()).hexdigest(),
                compiled.subtitles_sha256,
            )
            with cache.lock(owner, key):
                cache.publish_locked(owner, key, compiled, candidate)
            root = private_dsl_root(cache.base, owner)
            assert await collect_private_dsl_orphans(sessions, cache, owner=owner, key=key) == 0
            for path in [root / "entries" / f"{key}.json", *list((root / "objects").iterdir())]:
                os.utime(path, (time.time() - 90000, time.time() - 90000))
            context = cache.lock(owner, key)
            await asyncio.to_thread(context.__enter__)
            gc = asyncio.create_task(
                collect_private_dsl_orphans(sessions, cache, owner=owner, key=key)
            )
            await asyncio.sleep(0.1)
            assert not gc.done() and (root / "entries" / f"{key}.json").exists()
            await asyncio.to_thread(context.__exit__, None, None, None)
            assert await gc == 3
            assert not list((root / "objects").iterdir()) and not list((root / "entries").iterdir())
        finally:
            await engine.dispose()

    asyncio.run(exercise())
