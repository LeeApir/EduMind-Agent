"""Memory lifecycle tests use synthetic secrets, no real Provider or keyring."""

import asyncio
import json
import os
import pickle
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.core.temporary_credentials as module
from app.core.credential_crypto import CredentialFailure
from app.core.database import create_database_engine
from app.core.temporary_credentials import (
    TemporaryBinding,
    TemporaryCredentialRegistry,
)
from app.services.temporary_credentials import TemporaryCredentialService
from tests.test_provider_connections_persistence import SECRET, create, identity, store


def binding() -> TemporaryBinding:
    return TemporaryBinding(uuid4(), "test-session-hash", uuid4(), 1, uuid4(), "generation", "test")


async def valid() -> bool:
    return True


async def register(registry, context, *, validity=valid, seconds=60):
    return await registry.register(
        context,
        SECRET,
        session_expires_at=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        validity=validity,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", uuid4()),
        ("session_hash", "another-session"),
        ("connection_id", uuid4()),
        ("config_version", 2),
        ("operation_id", uuid4()),
        ("purpose", "model_refresh"),
        ("model_id", "another-model"),
    ],
)
def test_binding_mismatch_does_not_consume_rightful_handle(field, value):
    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        try:
            handle = await register(registry, context)
            with pytest.raises(CredentialFailure):
                async with registry.lease(handle, replace(context, **{field: value})):
                    pytest.fail("mismatched binding accepted")
            async with registry.lease(handle, context) as lease:
                assert lease.read_secret() == SECRET
            with pytest.raises(CredentialFailure):
                async with registry.lease(handle, context):
                    pytest.fail("replayed handle accepted")
        finally:
            await registry.close()

    asyncio.run(run())


def test_concurrent_claims_capacity_and_owner_isolation():
    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        gate = asyncio.Event()
        try:
            handles = await asyncio.gather(*(register(registry, context) for _ in range(4)))
            with pytest.raises(CredentialFailure) as full:
                await register(registry, context)
            assert full.value.code == "TEMPORARY_CREDENTIAL_LIMIT"
            # A different owner/session has its own four-slot quota.
            other = replace(context, owner_id=uuid4(), session_hash="different")
            await register(registry, other)

            async def claim():
                try:
                    async with registry.lease(handles[0], context) as lease:
                        assert lease.read_secret() == SECRET
                        gate.set()
                        await asyncio.sleep(0.01)
                    return True
                except CredentialFailure:
                    return False

            results = await asyncio.gather(claim(), claim())
            assert sorted(results) == [False, True]
            assert gate.is_set()
            await register(registry, context)  # Claimed slot is released.
        finally:
            await registry.close()

    asyncio.run(run())


@pytest.mark.parametrize("termination", ["success", "failure", "cancel"])
def test_all_termination_paths_wipe_buffer_and_close_upstream(termination):
    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        handle = await register(registry, context)
        payload = registry._entries[handle].payload
        entered, upstream_closed = asyncio.Event(), asyncio.Event()
        captured = []

        async def operation():
            async with registry.lease(handle, context) as lease:
                captured.append(lease)
                assert lease.read_secret() == SECRET
                try:
                    entered.set()
                    if termination == "failure":
                        raise RuntimeError("synthetic operation failure")
                    if termination == "cancel":
                        await asyncio.Event().wait()
                finally:
                    upstream_closed.set()

        try:
            task = asyncio.create_task(operation())
            await entered.wait()
            if termination == "cancel":
                task.cancel()  # Same cleanup path for an HTTP disconnect.
            if termination == "success":
                await task
            else:
                with pytest.raises(
                    asyncio.CancelledError if termination == "cancel" else RuntimeError
                ):
                    await task
            assert upstream_closed.is_set() and not payload and not registry._entries
            with pytest.raises(CredentialFailure):
                captured[0].read_secret()
        finally:
            await registry.close()

    asyncio.run(run())


def test_pending_expiry_and_session_absolute_timer(monkeypatch):
    monkeypatch.setattr(module, "PENDING_SECONDS", 0.02)

    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        try:
            handle = await register(registry, context)
            payload = registry._entries[handle].payload
            await asyncio.sleep(0.04)
            assert not payload and handle not in registry._entries
            with pytest.raises(CredentialFailure):
                async with registry.lease(handle, context):
                    pytest.fail("expired pending entry accepted")
            with pytest.raises(CredentialFailure):
                await register(registry, context, seconds=-1)
            handle = await register(registry, context, seconds=0.04)

            async def operation():
                async with registry.lease(handle, context):
                    await asyncio.Event().wait()

            task = asyncio.create_task(operation())
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 0.5)
            assert not registry._entries
        finally:
            await registry.close()

    asyncio.run(run())


def test_absolute_deadline_stops_continuous_tokens_independent_of_poll(monkeypatch):
    assert module.OPERATION_SECONDS == 180
    assert module.PENDING_SECONDS == 300
    assert module.POLL_SECONDS <= 1 and module.CHECK_SECONDS <= 1
    monkeypatch.setattr(module, "OPERATION_SECONDS", 0.04)

    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        handle = await register(registry, context)
        closed, tokens = asyncio.Event(), []
        start = asyncio.get_running_loop().time()

        async def operation():
            async with registry.lease(handle, context) as lease:
                try:
                    while True:
                        assert lease.read_secret() == SECRET
                        tokens.append("synthetic-token")
                        await asyncio.sleep(0.001)
                finally:
                    closed.set()

        try:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.create_task(operation()), 0.5)
            assert len(tokens) > 1 and closed.is_set()
            assert asyncio.get_running_loop().time() - start < 0.5
            assert not registry._entries
        finally:
            await registry.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["revoked", "database_error", "timeout", "cancelled_check"])
def test_cross_process_observer_fails_closed_and_cancels(failure, monkeypatch, caplog):
    monkeypatch.setattr(module, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(module, "CHECK_SECONDS", 0.01)

    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        revoked, entered = asyncio.Event(), asyncio.Event()

        async def check():
            if not revoked.is_set():
                return True
            if failure == "database_error":
                raise RuntimeError(SECRET["api_key"])
            if failure == "cancelled_check":
                raise asyncio.CancelledError
            if failure == "timeout":
                await asyncio.Event().wait()
            return False

        handle = await register(registry, context, validity=check)
        payload = registry._entries[handle].payload

        async def operation():
            async with registry.lease(handle, context):
                entered.set()
                await asyncio.Event().wait()

        try:
            task = asyncio.create_task(operation())
            await entered.wait()
            revoked.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 0.5)
            assert not payload and not registry._entries
            assert SECRET["api_key"] not in caplog.text
        finally:
            await registry.close()

    asyncio.run(run())


def test_revoke_restart_shutdown_and_no_serialization():
    async def run():
        registry, restarted, context = (
            TemporaryCredentialRegistry(),
            TemporaryCredentialRegistry(),
            binding(),
        )
        try:
            handle = await register(registry, context)
            assert len(handle) == 43 and SECRET["api_key"] not in handle
            with pytest.raises(CredentialFailure):
                async with restarted.lease(handle, context):
                    pytest.fail("new process restored temporary key")
            for obj in [registry, registry._entries[handle]]:
                with pytest.raises(TypeError):
                    pickle.dumps(obj)
                with pytest.raises(TypeError):
                    json.dumps(obj)
                assert SECRET["api_key"] not in repr(obj)
            entered = asyncio.Event()

            async def operation():
                async with registry.lease(handle, context) as lease:
                    with pytest.raises(TypeError):
                        pickle.dumps(lease)
                    assert SECRET["api_key"] not in repr(lease)
                    entered.set()
                    await asyncio.Event().wait()

            task = asyncio.create_task(operation())
            await entered.wait()
            registry.revoke(context.connection_id)
            with pytest.raises(asyncio.CancelledError):
                await task
            pending = await register(registry, context)
            payload = registry._entries[pending].payload
            await registry.close()
            assert not payload and not registry._entries
            with pytest.raises(CredentialFailure):
                await register(registry, context)
        finally:
            if not registry._closed:
                await registry.close()
            await restarted.close()

    asyncio.run(run())


def test_slow_database_teardown_does_not_delay_revocation(monkeypatch):
    monkeypatch.setattr(module, "POLL_SECONDS", 0.005)
    monkeypatch.setattr(module, "CHECK_SECONDS", 0.005)

    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        entered, revoked, teardown_done = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def check():
            if not revoked.is_set():
                return True
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.1)  # Simulate slow DB connection teardown.
                teardown_done.set()
                return False

        handle = await register(registry, context, validity=check)

        async def operation():
            async with registry.lease(handle, context):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(operation())
        try:
            await entered.wait()
            revoked.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 0.5)
            assert not teardown_done.is_set() and not registry._entries
            await registry.close()  # Shutdown does not wait for DB teardown either.
            await asyncio.wait_for(teardown_done.wait(), 0.5)
        finally:
            if not registry._closed:
                await registry.close()

    asyncio.run(run())


def test_late_cancelled_validator_error_is_consumed_without_logging():
    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        entered, completed = asyncio.Event(), asyncio.Event()
        loop = asyncio.get_running_loop()
        events = []
        previous = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, event: events.append(event))

        async def check():
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.01)
                completed.set()
                raise RuntimeError(SECRET["api_key"])

        task = asyncio.create_task(register(registry, context, validity=check))
        try:
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await completed.wait()
            await asyncio.sleep(0.01)
            assert not events and not registry._entries
        finally:
            await registry.close()
            loop.set_exception_handler(previous)

    asyncio.run(run())


def test_lease_rejects_other_task_and_shutdown_cancels_active_operation():
    async def run():
        registry, context = TemporaryCredentialRegistry(), binding()
        handle = await register(registry, context)
        entered, captured = asyncio.Event(), []
        payload = registry._entries[handle].payload

        async def operation():
            async with registry.lease(handle, context) as lease:
                captured.append(lease)
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(operation())
        try:
            await entered.wait()
            with pytest.raises(CredentialFailure):
                captured[0].read_secret()
            await registry.close()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not payload and not registry._entries
        finally:
            if not registry._closed:
                await registry.close()

    asyncio.run(run())


def test_application_lifespan_owns_registry_without_requiring_database(monkeypatch):
    from fastapi import FastAPI

    from app.core.database import database_lifespan

    monkeypatch.delenv("EDUMIND_DATABASE_URL", raising=False)

    async def run():
        async with database_lifespan(FastAPI()) as state:
            runtime = state["database_runtime"]
            assert runtime.engine is None
            registry = runtime.temporary_credentials
            assert registry is not None
            handle = await register(registry, binding())
            payload = registry._entries[handle].payload
        assert registry._closed and not payload and not registry._entries
        assert runtime.engine is None

    asyncio.run(run())


@pytest.mark.skipif(not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated PG required")
def test_actual_pg_revocation_and_temporary_cleanup_preserve_persistent_key():
    async def run():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        registry = TemporaryCredentialRegistry()
        s = store(factory)
        service = TemporaryCredentialService(s, registry)
        try:
            owner, other = await identity(factory), await identity(factory)
            persistent_id = await create(s, owner)
            temporary = await s.create(
                owner,
                provider_type="openai-compatible",
                display_name="temporary",
                base_url="https://provider.example/v1",
                mode="temporary",
            )
            from uuid import UUID

            cid = UUID(str(temporary["id"]))
            with pytest.raises(CredentialFailure):
                await service.register(other, cid, 1, uuid4(), "generation", "test", SECRET)
            with pytest.raises(CredentialFailure):
                await service.register(
                    owner, persistent_id, 1, uuid4(), "generation", "test", SECRET
                )
            handle, context = await service.register(
                owner, cid, 1, uuid4(), "generation", "test", SECRET
            )
            entered, closed = asyncio.Event(), asyncio.Event()

            async def operation():
                async with registry.lease(handle, context) as lease:
                    assert lease.read_secret() == SECRET
                    try:
                        entered.set()
                        await asyncio.Event().wait()
                    finally:
                        closed.set()

            task = asyncio.create_task(operation())
            await entered.wait()
            with pytest.raises(CredentialFailure):
                await s.replace(owner, cid, 0, display_name="conflict")
            assert not task.done() and registry._entries[handle].alive
            # Real committed version change synchronously notifies this process.
            await s.replace(owner, cid, 1, base_url="https://changed.example/v1")
            with pytest.raises(asyncio.CancelledError):
                await task
            assert closed.is_set() and not registry._entries
            assert await s.decrypt(owner, persistent_id, 1) == SECRET
            handle, context = await service.register(
                owner, cid, 2, uuid4(), "generation", "test", SECRET
            )
            task = asyncio.create_task(operation())
            entered.clear()
            await entered.wait()
            await s.delete(owner, cid, 2)
            with pytest.raises(asyncio.CancelledError):
                await task
            # A different store instance models a mutation in another API process.
            temporary = await s.create(
                owner,
                provider_type="openai-compatible",
                display_name="other-process",
                base_url="https://provider.example/v1",
                mode="temporary",
            )
            cid = UUID(str(temporary["id"]))
            handle, context = await service.register(
                owner, cid, 1, uuid4(), "generation", "test", SECRET
            )
            entered.clear()
            task = asyncio.create_task(operation())
            await entered.wait()
            start = asyncio.get_running_loop().time()
            await store(factory).replace(owner, cid, 1, enabled=False)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2.2)
            assert asyncio.get_running_loop().time() - start < 2.2
            await registry.close()
            assert await s.decrypt(owner, persistent_id, 1) == SECRET
        finally:
            if not registry._closed:
                await registry.close()
            await engine.dispose()

    asyncio.run(run())
