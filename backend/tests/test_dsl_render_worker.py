"""Actual isolated DSL media and persisted lease/failure qualification, never real model calls."""

import asyncio
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.animation_dsl_review import (
    REVIEW_VERSION,
    AnimationDSLReviewAgent,
    digest,
)
from app.core.database import create_database_engine
from app.models.animation import AnimationJob
from app.services import animation_dsl_renderer as renderer
from app.services.animation_dsl_candidates import (
    admit_current_policy,
    build_dsl_reference,
    revoke_candidate,
    save_dsl_review,
)
from app.services.animation_dsl_compiler import compile_animation_dsl
from app.services.animation_dsl_runtime import FONT_DIGEST, IMAGE
from app.services.animation_renderer import RenderedCandidate, RenderError
from app.services.animation_worker import claim_animation_job, fail_animation_job
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.workers.dsl_render import dsl_cache_key, render_dsl_job

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / "docs/agents/animation-dsl-v1/valid-all-actions.json").read_bytes()
GRAPH = KnowledgeGraphRepository.from_file(ROOT / "data/knowledge_graph.yaml")
URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
DOCKER = os.getenv("EDUMIND_DOCKER_TESTS") == "1"


@pytest.fixture
def dynamic_test_mode(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")


@pytest.fixture
def compiled():
    return compile_animation_dsl(RAW, knowledge_point_id="arrays")


def test_candidate_source_change_rejected_before_docker(compiled, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(renderer, "_docker", lambda *a, **k: calls.append(a))
    with pytest.raises(RenderError, match="DSL_RENDER_UNAVAILABLE"):
        renderer.render_compiled_dsl(replace(compiled, source="import os"), work_root=tmp_path)
    assert not calls and list(tmp_path.iterdir()) == []


def test_unavailable_docker_has_exact_isolation_flags_and_no_model_secrets(
    compiled, monkeypatch, tmp_path
):
    calls = []

    def unavailable(args, **kwargs):
        calls.append(args)
        raise RenderError("DSL_RENDER_UNAVAILABLE")

    monkeypatch.setattr(renderer, "_docker", unavailable)
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "TEST_ONLY_SECRET")
    with pytest.raises(RenderError, match="DSL_RENDER_UNAVAILABLE"):
        renderer.render_compiled_dsl(compiled, work_root=tmp_path)
    command = calls[0]
    assert command[:3] == ["run", "-d", "--rm"]
    assert command[-3:] == [IMAGE, "python", "/input/container_runner.py"]
    for flag, value in [
        ("--network", "none"),
        ("--cpus", "2"),
        ("--memory", "1g"),
        ("--pids-limit", "128"),
        ("--user", "10001:10001"),
        ("--cap-drop", "ALL"),
    ]:
        assert command[command.index(flag) + 1] == value
    assert "--read-only" in command and "no-new-privileges" in command
    assert sum(arg.startswith("type=bind,") for arg in command) == 1
    assert "size=268435456" in " ".join(command)
    assert "TEST_ONLY_SECRET" not in " ".join(command) and "docker.sock" not in " ".join(command)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("seconds", [0, -1, 121, float("inf"), float("nan")])
def test_execution_timeout_cannot_be_expanded(compiled, seconds, tmp_path):
    with pytest.raises(RenderError, match="DSL_RENDER_UNAVAILABLE"):
        renderer.render_compiled_dsl(compiled, timeout_seconds=seconds, work_root=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not DOCKER, reason="actual Docker required")
def test_real_dsl_media_source_identity_and_literal_code(compiled, tmp_path):
    result = renderer.render_compiled_dsl(compiled, work_root=tmp_path)
    try:
        assert result.duration_seconds == 30.8
        assert result.srt_path.read_text() == compiled.subtitles
        assert result.srt_sha256 == compiled.subtitles_sha256
        assert not (result.attempt_dir / "input").exists()
        assert result.mp4_path.stat().st_size > 0
        # Independently inspect the copied MP4, not renderer metadata or .ready.
        decoded = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--user",
                "10001:10001",
                "--cpus",
                "1",
                "--memory",
                "512m",
                "--pids-limit",
                "32",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                IMAGE,
                "python",
                "-c",
                "import sys,io,av; m=av.open(io.BytesIO(sys.stdin.buffer.read()));"
                "s=m.streams.video[0];print(s.width,s.height,s.average_rate)",
            ],
            input=result.mp4_path.read_bytes(),
            capture_output=True,
            timeout=15,
            check=True,
        )
        assert decoded.stdout.strip() == b"1280 720 15"
    finally:
        result.cleanup()
    # Unknown Manim code is never accepted from a caller's patched CompiledDSL dataclass.
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not DOCKER, reason="actual Docker required")
def test_real_timeout_stops_owned_container_and_discards_partial_media(compiled, tmp_path):
    name = "edumind-render-" + uuid4().hex
    with pytest.raises(RenderError, match="DSL_RENDER_TIMEOUT|DSL_RENDER_UNAVAILABLE"):
        renderer.render_compiled_dsl(
            compiled, work_root=tmp_path, timeout_seconds=0.05, container_name=name
        )
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        capture_output=True,
        timeout=5,
        check=True,
    )
    assert not result.stdout.strip() and list(tmp_path.iterdir()) == []


async def seed(sessions, *, bad_hash=False):
    from test_animation_dsl_review import GENERATION, FakeGateway, target

    ids = await target(sessions)
    async with sessions() as db, db.begin():
        await admit_current_policy(db)
        ref = await build_dsl_reference(
            db, GRAPH, owner=ids[0], unit_id=ids[1], scene_id=ids[2], version=1
        )
    outcome = await AnimationDSLReviewAgent(FakeGateway()).review(
        RAW.decode().replace('"arrays"', '"array"'), reference=ref, generation_source=GENERATION
    )
    async with sessions() as db, db.begin():
        _, candidate = await save_dsl_review(
            db, GRAPH, owner=ids[0], unit_id=ids[1], scene_id=ids[2], version=1, outcome=outcome
        )
        cid = candidate.id
        compiled = outcome.compiled
        parameters = {"candidate_id": str(cid)}
        job = AnimationJob(
            user_id=ids[0],
            learning_unit_id=ids[1],
            scene_id=ids[2],
            scene_version=1,
            action_kind="request",
            idempotency_key=str(uuid4()),
            request_digest=digest({"candidate": str(cid), "scene": str(ids[2])}),
            parameters_digest=digest(parameters),
            parameters=parameters,
            template_id=None,
            template_version=None,
            render_kind="dsl",
            candidate_id=cid,
            review_rule_version=REVIEW_VERSION,
            source_sha256="f" * 64 if bad_hash else compiled.source_sha256,
            image_digest=IMAGE.split("@", 1)[1],
            font_digest=FONT_DIGEST,
            renderer_config_sha256=renderer.renderer_identity(),
            subtitle_version="animation-dsl-subtitles-v1",
            cache_key=dsl_cache_key(compiled, outcome.binding_sha256, ids[0]),
            status="queued",
            progress=0,
        )
        db.add(job)
        await db.flush()
        jid = job.id
    lease = await claim_animation_job(sessions)
    assert lease is not None and lease.job_id == jid
    return lease, cid


@pytest.mark.skipif(not URL, reason="dedicated PostgreSQL required")
@pytest.mark.parametrize("failure", ["hash", "withdrawn"])
def test_pg_unqualified_dsl_never_starts_container(
    monkeypatch, tmp_path, failure, dynamic_test_mode
):
    calls = []
    monkeypatch.setattr(renderer, "_docker", lambda *a, **k: calls.append(a))

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)
            if failure == "hash":
                async with sessions() as db, db.begin():
                    job = await db.get(AnimationJob, lease.job_id)
                    job.source_sha256 = "f" * 64
            if failure == "withdrawn":
                async with sessions() as db, db.begin():
                    await revoke_candidate(db, GRAPH, owner=lease.owner_id, candidate_id=cid)
            result = await render_dsl_job(sessions, GRAPH, lease, cid, work_root=tmp_path)
            assert result.media is None and result.error_code == "DSL_RENDER_UNAVAILABLE"
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "failed" and job.media_id is None and job.lease_token is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    assert not calls


@pytest.mark.skipif(not URL, reason="dedicated PostgreSQL required")
def test_pg_queued_invalid_identity_rejected_before_new_claim(monkeypatch, dynamic_test_mode):
    calls = []
    monkeypatch.setattr(renderer, "_docker", lambda *a, **k: calls.append(a))

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, _ = await seed(sessions)
            async with sessions() as db, db.begin():
                job = await db.get(AnimationJob, lease.job_id)
                job.status = "queued"
                job.lease_token = job.lease_expires_at = None
                job.source_sha256 = "f" * 64
            assert await claim_animation_job(sessions) is None
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "failed" and job.error_code == "ANIMATION_TARGET_UNAVAILABLE"
                assert job.attempt == 1 and job.media_id is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    assert not calls


@pytest.mark.skipif(not URL or not DOCKER, reason="dedicated PostgreSQL and actual Docker required")
def test_pg_live_lease_actual_render_and_no_premature_publication(tmp_path, dynamic_test_mode):
    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)
            result = await render_dsl_job(sessions, GRAPH, lease, cid, work_root=tmp_path)
            assert result.error_code is None and result.media is not None
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "running" and job.media_id is None
                assert job.progress == 0.8
            assert result.media.srt_path.is_file()
            result.media.cleanup()
            await fail_animation_job(sessions, lease, code="DSL_RENDER_INTERRUPTED")
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.skipif(not URL or not DOCKER, reason="dedicated PostgreSQL and actual Docker required")
def test_pg_actual_container_crash_persists_failure_and_can_reclaim(
    monkeypatch, tmp_path, dynamic_test_mode
):
    from datetime import timedelta

    from app.models.learning import utc_now
    from app.services.animation_host import RenderHost
    from app.services.animation_worker import reclaim_expired_animation_jobs

    launch = RenderHost.launch

    def failed_launch(self, command):
        command = command[:-1] + ["-c", "raise SystemExit(3)"]
        return launch(self, command)

    monkeypatch.setattr(RenderHost, "launch", failed_launch)

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)
            result = await render_dsl_job(sessions, GRAPH, lease, cid, work_root=tmp_path)
            assert result.error_code == "DSL_RENDER_FAILED" and result.media is None
            async with sessions() as db, db.begin():
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "failed" and job.media_id is None
            # A worker-death lease is separately reclaimed by the existing PG reaper.
            new_lease, new_cid = await seed(sessions)
            async with sessions() as db, db.begin():
                job = await db.get(AnimationJob, new_lease.job_id)
                job.lease_expires_at = utc_now() - timedelta(seconds=1)
            assert await reclaim_expired_animation_jobs(sessions) >= 1
            resumed = await claim_animation_job(sessions)
            assert (
                resumed.job_id == new_lease.job_id
                and resumed.dispatch_epoch == new_lease.dispatch_epoch + 1
            )
            assert resumed.token != new_lease.token and resumed.attempt == 2
            result = await render_dsl_job(sessions, GRAPH, resumed, new_cid, work_root=tmp_path)
            assert result.error_code == "DSL_RENDER_FAILED"
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not URL or not DOCKER, reason="dedicated PostgreSQL and actual Docker required")
def test_pg_real_resource_quota_and_sandbox_failure_is_terminal(
    monkeypatch, tmp_path, dynamic_test_mode
):
    from app.services.animation_host import RenderHost

    launch = RenderHost.launch
    # Operator fault injection, never generated scene code. Uses the exact worker command/mount.
    probe = """
import socket, time
from pathlib import Path
try:
    socket.create_connection(("1.1.1.1", 80), timeout=1)
    raise AssertionError("network allowed")
except OSError:
    pass
for path in ("/etc/probe", "/input/DSLScene.py"):
    try:
        Path(path).write_text("forbidden")
        raise AssertionError("write allowed")
    except OSError:
        pass
assert not Path("/input/.env").exists()
try:
    with Path("/output/quota").open("wb") as stream:
        for _ in range(257):
            stream.write(b"x" * 1048576)
    raise AssertionError("quota ignored")
except OSError as error:
    assert error.errno == 28
Path("/output/quota").unlink()
Path("/output/.failed").write_text("DSL_RENDER_RESOURCE_LIMIT")
time.sleep(20)
"""

    def injected(self, command):
        return launch(self, command[:-1] + ["-c", probe])

    monkeypatch.setattr(RenderHost, "launch", injected)

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)
            result = await render_dsl_job(sessions, GRAPH, lease, cid, work_root=tmp_path)
            assert result.media is None and result.error_code == "DSL_RENDER_RESOURCE_LIMIT"
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "failed" and job.media_id is None and job.lease_token is None
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not URL, reason="dedicated PostgreSQL required")
@pytest.mark.parametrize("change", ["withdrawn", "lease"])
def test_pg_inflight_qualification_change_discards_artifact(
    monkeypatch, tmp_path, dynamic_test_mode, change
):
    from datetime import timedelta

    from app.models.learning import utc_now
    from app.services.animation_worker import reclaim_expired_animation_jobs
    from app.workers import dsl_render

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        loop = asyncio.get_running_loop()
        replacement = None
        try:
            lease, cid = await seed(sessions)

            async def invalidate():
                nonlocal replacement
                async with sessions() as db, db.begin():
                    if change == "withdrawn":
                        await revoke_candidate(db, GRAPH, owner=lease.owner_id, candidate_id=cid)
                    else:
                        job = await db.get(AnimationJob, lease.job_id)
                        job.lease_expires_at = utc_now() - timedelta(seconds=1)
                if change == "lease":
                    assert await reclaim_expired_animation_jobs(sessions) == 1
                    replacement = await claim_animation_job(sessions)
                    assert replacement.token != lease.token

            def render_fixture(compiled, **kwargs):
                # Fixture checks worker CAS/requalification; this is not media-decoding evidence.
                asyncio.run_coroutine_threadsafe(invalidate(), loop).result(timeout=10)
                attempt = tmp_path / "fixture"
                attempt.mkdir()
                mp4, srt = attempt / "DSLScene.mp4", attempt / "DSLScene.srt"
                mp4.write_bytes(b"worker-boundary-fixture")
                srt.write_text(compiled.subtitles)
                return RenderedCandidate(
                    attempt, mp4, srt, 30.8, "0" * 64, compiled.subtitles_sha256
                )

            monkeypatch.setattr(dsl_render, "render_compiled_dsl", render_fixture)
            result = await render_dsl_job(sessions, GRAPH, lease, cid, work_root=tmp_path)
            assert result.media is None and result.error_code == "DSL_RENDER_UNAVAILABLE"
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.media_id is None
                if change == "withdrawn":
                    assert job.status == "failed"
                else:
                    assert job.status == "running" and job.lease_token == replacement.token
            if replacement:
                await fail_animation_job(sessions, replacement, code="DSL_RENDER_INTERRUPTED")
        finally:
            await engine.dispose()

    asyncio.run(exercise())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not URL, reason="dedicated PostgreSQL required")
def test_pg_cancellation_reaps_late_thread_output(monkeypatch, tmp_path, dynamic_test_mode):
    import threading

    from app.services.animation_host import RenderHost
    from app.workers import dsl_render

    started, release = threading.Event(), threading.Event()
    original_stop = RenderHost.stop

    def stopped(self):
        result = original_stop(self)
        release.set()
        return result

    def render_fixture(compiled, **kwargs):
        started.set()
        assert release.wait(timeout=10)
        attempt = tmp_path / "late"
        attempt.mkdir()
        mp4, srt = attempt / "DSLScene.mp4", attempt / "DSLScene.srt"
        mp4.write_bytes(b"late-worker-fixture")
        srt.write_text(compiled.subtitles)
        return RenderedCandidate(attempt, mp4, srt, 30.8, "0" * 64, compiled.subtitles_sha256)

    monkeypatch.setattr(RenderHost, "stop", stopped)
    monkeypatch.setattr(dsl_render, "render_compiled_dsl", render_fixture)

    async def exercise():
        engine = create_database_engine(URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            lease, cid = await seed(sessions)
            task = asyncio.create_task(
                render_dsl_job(sessions, GRAPH, lease, cid, work_root=tmp_path)
            )
            assert await asyncio.to_thread(started.wait, 10)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            async with sessions() as db:
                job = await db.get(AnimationJob, lease.job_id)
                assert job.status == "failed" and job.error_code == "DSL_RENDER_INTERRUPTED"
                assert job.media_id is None and job.lease_token is None
        finally:
            release.set()
            await engine.dispose()

    asyncio.run(exercise())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(not DOCKER, reason="actual Docker required")
@pytest.mark.parametrize("mode", ["chinese", "missing_font", "missing_glyph"])
def test_real_fixed_font_gate(mode, tmp_path):
    from app.services.animation_renderer import IMAGE as BASE_IMAGE

    (tmp_path / "font_check.py").write_bytes(
        (ROOT / "backend/app/dsl_runtime/font_check.py").read_bytes()
    )
    text = "中文标题字幕访问" if mode != "missing_glyph" else chr(0x10FFFF)
    source = "Text(" + repr(text) + ")"
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--user",
        "10001:10001",
        "--cpus",
        "1",
        "--memory",
        "512m",
        "--pids-limit",
        "32",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=32m,mode=1777",
        "--mount",
        f"type=bind,source={tmp_path},destination=/input,readonly",
        "-e",
        "XDG_CACHE_HOME=/tmp",
        "--entrypoint",
        "python",
        BASE_IMAGE if mode == "missing_font" else IMAGE,
        "-c",
        "import sys;sys.path.insert(0,'/input');from font_check import check_font;"
        "check_font(" + repr(source.encode()) + ");print('FONT_OK')",
    ]
    result = subprocess.run(command, capture_output=True, timeout=15)
    if mode == "chinese":
        assert result.returncode == 0 and result.stdout.strip() == b"FONT_OK"
    else:
        assert result.returncode != 0 and b"DSL_RENDER_UNAVAILABLE" in result.stderr
        assert b"FONT_OK" not in result.stdout
