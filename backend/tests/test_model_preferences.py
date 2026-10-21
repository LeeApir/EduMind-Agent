"""Real-PG preference versions and priorities, Mock-only explicit fallback dispatch."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_provider_connection_test_api import Budget, create, output, probe_api  # noqa: F401
from test_provider_connections_api import (
    DB_URL,
    KEY,
    ROOT,
    guest,
    pg,
    private,
    restore,
    schema,
    setup_api,  # noqa: F401
)

from app.core.auth import token_hash
from app.core.credential_crypto import CredentialFailure, CredentialKeyring
from app.core.database import create_database_engine
from app.main import app
from app.models.provider_model_snapshots import ProviderModelSnapshot
from app.services import model_preferences as service
from app.services.model_preferences import RouteChoice
from app.services.provider_connection_dispatch import ConnectionConsent, ConnectionRoute
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    TaskProfile,
    TextRequest,
)

URL = "/api/model-preferences"


def route(cid, version=1, model="private-model", categories=None):
    return {
        "connection_id": cid,
        "config_version": version,
        "model_id": model,
        "data_categories": categories or ["learning_goal"],
    }


def body(cid, expected=0, **fields):
    value = {
        "expected_version": expected,
        "route": route(cid),
        "fallbacks": [],
        "consent_accepted": True,
    }
    value.update(fields)
    return value


def put(client, headers, profile, value):
    return client.put(URL + "/" + profile, json=value, headers=headers)


def internal(users, token, action):
    async def run():
        engine = create_database_engine(DB_URL)
        try:
            store = ProviderConnectionStore(
                async_sessionmaker(engine),
                None,
                keyring_loader=CredentialKeyring.from_environment,
                resolver=lambda *args: ["8.8.8.8"],
            )
            return await action(store, CredentialIdentity(next(iter(users)), token_hash(token)))
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture
def preference_api(probe_api):  # noqa: F811 -- imported fixture
    return probe_api


@pg
def test_four_profiles_separate_review_private_reads_no_key_or_network(preference_api, monkeypatch):
    client, users, dns, _, sent = preference_api
    token, headers = guest(client, users)
    main, reviewer = create(client, headers), create(client, headers, display_name="review")
    before = len(dns)
    monkeypatch.delenv("EDUMIND_CREDENTIAL_KEYRING_JSON")
    assert client.get(URL).json() == {"preferences": []}
    for profile in ("fast", "default", "quality", "review"):
        cid = reviewer if profile == "review" else main
        out = put(client, headers, profile, body(cid))
        private(out)
        assert out.status_code == 200, out.text
        schema("ModelPreference").validate(out.json())
        assert out.json()["version"] == 1 and out.json()["state"] == "available"
    assert len(client.get(URL).json()["preferences"]) == 4
    saved = client.get(URL).json()
    with TestClient(app, base_url="https://testserver") as restarted:
        restore(restarted, token)
        assert restarted.get(URL).json() == saved
    assert len(dns) == before and not sent

    async def check(store, owner):
        selection = await service.select_route(store, owner, TaskProfile.REVIEW)
        assert selection.choice.route.connection_id == UUID(reviewer)
        assert selection.source == "user_task_profile"

    internal(users, token, check)
    assert client.get("/api/runtime").json() == {"mode": "catalog_only"}
    _, other_headers = guest(client, users)
    assert client.get(URL).json() == {"preferences": []}
    denied = put(client, other_headers, "review", body(reviewer))
    assert denied.status_code == 404 and not sent
    restore(client, token)
    assert len(client.get(URL).json()["preferences"]) == 4


@pg
def test_create_and_update_versions_have_one_race_winner(preference_api):
    client, users, _, _, sent = preference_api
    _, headers = guest(client, users)
    cid = create(client, headers)

    def write(expected):
        return put(client, headers, "default", body(cid, expected))

    for expected in (0, 1):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(write, [expected, expected]))
        assert sorted(r.status_code for r in responses) == [200, 409]
        for r in responses:
            private(r)
    assert client.get(URL).json()["preferences"][0]["version"] == 2 and not sent


@pg
@pytest.mark.parametrize(
    "invalid",
    [
        "csrf",
        "profile",
        "consent",
        "version",
        "duplicate_data",
        "extra",
        "fallback_error",
        "duplicate_errors",
        "too_many",
        "duplicate_route",
        "stale",
        "deleted",
    ],
)
def test_invalid_writes_preserve_prior_choice(preference_api, invalid):
    client, users, _, _, sent = preference_api
    _, headers = guest(client, users)
    cid = create(client, headers)
    assert put(client, headers, "default", body(cid)).status_code == 200
    value = body(cid, 1)
    profile = "default"
    expected = 422
    if invalid == "csrf":
        headers = {}
        expected = 403
    elif invalid == "profile":
        profile = "invalid"
    elif invalid == "consent":
        value["consent_accepted"] = False
        expected = 409
    elif invalid == "version":
        value["expected_version"] = 0
        expected = 409
    elif invalid == "duplicate_data":
        value["route"]["data_categories"] = ["learning_goal", "learning_goal"]
    elif invalid == "extra":
        value["api_key"] = KEY
    elif invalid == "fallback_error":
        value["fallbacks"] = [
            {"route": route(cid, model="other"), "on_errors": ["AUTHENTICATION_FAILED"]}
        ]
    elif invalid == "duplicate_errors":
        value["fallbacks"] = [
            {"route": route(cid, model="other"), "on_errors": ["TIMEOUT", "TIMEOUT"]}
        ]
    elif invalid == "too_many":
        value["fallbacks"] = [
            {"route": route(cid, model=str(i)), "on_errors": ["TIMEOUT"]} for i in range(4)
        ]
    elif invalid == "duplicate_route":
        value["fallbacks"] = [{"route": route(cid), "on_errors": ["TIMEOUT"]}]
    elif invalid == "stale":
        value["route"]["config_version"] = 2
        expected = 409
    elif invalid == "deleted":
        assert (
            client.delete(ROOT + "/" + cid, headers={**headers, "If-Match": "1"}).status_code == 204
        )
        expected = 404
    out = put(client, headers, profile, value)
    private(out)
    assert out.status_code == expected, out.text
    current = client.get(URL).json()["preferences"][0]
    assert current["version"] == 1 and current["fallbacks"] == [] and not sent


@pg
def test_priority_missing_only_and_invalid_selection_not_system_fallback(preference_api):
    client, users, _, _, sent = preference_api
    token, headers = guest(client, users)
    default = create(client, headers)
    quality = create(client, headers, display_name="quality")
    assert put(client, headers, "default", body(default)).status_code == 200
    assert put(client, headers, "quality", body(quality)).status_code == 200

    async def check(store, owner):
        fast = await service.select_route(store, owner, TaskProfile.FAST)
        assert fast.source == "user_default" and fast.choice.route.connection_id == UUID(default)
        chosen = await service.select_route(store, owner, TaskProfile.QUALITY)
        assert chosen.source == "user_task_profile" and chosen.choice.route.connection_id == UUID(
            quality
        )
        override = RouteChoice(
            ConnectionRoute(UUID(default), 1, "override", frozenset({"learning_goal"})),
            consent_accepted=True,
        )
        chosen = await service.select_route(store, owner, TaskProfile.QUALITY, override=override)
        assert chosen.source == "task_override" and chosen.choice == override
        with pytest.raises(CredentialFailure):
            await service.select_route(
                store, owner, TaskProfile.FAST, override=RouteChoice(override.route)
            )

    internal(users, token, check)
    assert (
        client.patch(
            ROOT + "/" + quality, headers={**headers, "If-Match": "1"}, json={"display_name": "new"}
        ).status_code
        == 200
    )
    choices = client.get(URL).json()["preferences"]
    assert next(p for p in choices if p["task_profile"] == "quality")["state"] == "consent_required"
    assert (
        client.delete(ROOT + "/" + default, headers={**headers, "If-Match": "1"}).status_code == 204
    )
    assert (
        next(p for p in client.get(URL).json()["preferences"] if p["task_profile"] == "default")[
            "state"
        ]
        == "unavailable"
    )

    async def remains(store, owner):
        chosen = await service.select_route(store, owner, TaskProfile.FAST)
        assert chosen.source == "user_default" and chosen.choice.route.connection_id == UUID(
            default
        )
        with pytest.raises(CredentialFailure) as e:
            await service.validate_route(store, owner, chosen.choice.route)
        assert e.value.code == "NOT_FOUND"

    internal(users, token, remains)
    assert not sent


@pg
def test_disabled_connection_is_unavailable_and_never_selects_system(preference_api):
    client, users, _, _, sent = preference_api
    token, headers = guest(client, users)
    cid = create(client, headers)
    assert put(client, headers, "default", body(cid)).status_code == 200
    assert (
        client.patch(
            ROOT + "/" + cid, headers={**headers, "If-Match": "1"}, json={"enabled": False}
        ).status_code
        == 200
    )
    assert client.get(URL).json()["preferences"][0]["state"] == "unavailable"

    async def check(store, owner):
        selected = await service.select_route(store, owner, TaskProfile.QUALITY)
        assert selected.source == "user_default" and selected.choice.route.connection_id == UUID(
            cid
        )
        with pytest.raises(CredentialFailure) as e:
            await service.validate_route(store, owner, selected.choice.route)
        assert e.value.code == "CREDENTIAL_UNAVAILABLE"

    internal(users, token, check)
    assert not sent


async def seed_models(store, owner, cid, *, structured=None):
    async with store.factory() as db, db.begin():
        row = await store._row(db, owner, UUID(cid), 1)
        from datetime import datetime, timezone

        db.add(
            ProviderModelSnapshot(
                connection_id=row.id,
                config_version=1,
                refreshed_at=datetime.now(timezone.utc),
                models=[
                    {
                        "id": "private-model",
                        "capabilities": {
                            "version": "test-declared-v1",
                            "streaming": True,
                            "structured_output": structured,
                            "source": "declared",
                        },
                    }
                ],
            )
        )


@pg
@pytest.mark.parametrize(
    "case",
    [
        "success",
        "auth",
        "invalid",
        "no_consent",
        "wrong_data",
        "wrong_trigger",
        "budget",
        "unknown_review",
        "catalog_only",
    ],
)
def test_explicit_bounded_fallback_dispatch_and_review_failure(
    preference_api, monkeypatch, case, caplog
):
    client, users, _, _, _ = preference_api
    token, headers = guest(client, users)
    primary = create(client, headers, base_url="https://primary.test/v1")
    backup = create(client, headers, base_url="https://backup.test/v1")
    fallback = {"route": route(backup), "on_errors": ["RATE_LIMITED"]}
    if case == "wrong_trigger":
        fallback["on_errors"] = ["TIMEOUT"]
    assert (
        put(
            client,
            headers,
            "review" if case == "unknown_review" else "default",
            body(primary, fallbacks=[fallback]),
        ).status_code
        == 200
    )
    monkeypatch.setenv(
        "EDUMIND_PRODUCT_MODE", "catalog_only" if case == "catalog_only" else "dynamic"
    )
    sent, records, budgets = [], [], Budget()

    def handler(request):
        sent.append(request)
        if request.headers["host"] == "primary.test":
            if case == "auth":
                return httpx.Response(401, text=KEY)
            if case == "invalid":
                return httpx.Response(200, text=KEY)
            return httpx.Response(429, text=KEY)
        return httpx.Response(200, json=output("synthetic result"))

    async def check(store, owner):
        await seed_models(store, owner, primary)
        await seed_models(store, owner, backup)
        selected = await service.select_route(
            store, owner, TaskProfile.REVIEW if case == "unknown_review" else TaskProfile.DEFAULT
        )
        first, second = selected.choice.route, selected.choice.fallbacks[0].route
        consents = (
            (ConnectionConsent(first, True),)
            if case == "no_consent"
            else (ConnectionConsent(first, True), ConnectionConsent(second, True))
        )
        request = TextRequest((ChatMessage("user", "synthetic learning context"),))
        if case == "unknown_review":
            request = StructuredRequest(request, {"type": "object"})

        async def authorize(dispatch):
            await budgets.authorize_attempt(dispatch)
            if case == "budget" and dispatch.route == second:
                raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

        kwargs = dict(
            operation_id=uuid4(),
            consents=consents,
            data_categories=frozenset(
                {"profile_evidence"} if case == "wrong_data" else {"learning_goal"}
            ),
            authorize_attempt=authorize,
            transport=httpx.MockTransport(handler),
            record=records.append,
        )
        if case == "success":
            result = await service.generate_selected(store, owner, selected, request, **kwargs)
            assert result.text == "synthetic result"
        elif case in {"no_consent", "wrong_data", "budget", "catalog_only"}:
            with pytest.raises(CredentialFailure) as e:
                await service.generate_selected(store, owner, selected, request, **kwargs)
            assert e.value.code == {
                "budget": "BUDGET_NOT_AUTHORIZED",
                "catalog_only": "FEATURE_UNAVAILABLE",
            }.get(case, "CONSENT_REQUIRED")
        else:
            with pytest.raises(ProviderError) as e:
                await service.generate_selected(store, owner, selected, request, **kwargs)
            assert (
                e.value.code
                == {
                    "auth": ProviderErrorCode.AUTHENTICATION_FAILED,
                    "invalid": ProviderErrorCode.INVALID_OUTPUT,
                    "unknown_review": ProviderErrorCode.CAPABILITY_UNAVAILABLE,
                    "wrong_trigger": ProviderErrorCode.RATE_LIMITED,
                }[case]
            )

    internal(users, token, check)
    expected = (
        2
        if case == "success"
        else 0
        if case in {"wrong_data", "unknown_review", "catalog_only"}
        else 1
    )
    assert len(sent) == expected and KEY not in caplog.text and KEY not in json.dumps(records)
    assert all("authorization" not in r.headers for r in sent)
    if case == "success":
        assert len(budgets.attempts) == 2 and len(records) == 2
        assert records[1]["target"] == "https://backup.test/v1"
        assert (
            records[1]["fallback_reason"] == "RATE_LIMITED" and records[1]["outcome"] == "success"
        )


@pg
def test_empty_owner_resolves_system_but_has_no_default_send_grant(preference_api, monkeypatch):
    client, users, _, _, sent = preference_api
    token, _ = guest(client, users)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    async def check(store, owner):
        selected = await service.select_route(store, owner, TaskProfile.QUALITY)
        assert selected.choice is None and selected.source == "system_default"

        async def forbid(dispatch):
            pytest.fail("system default reached selected-connection budget")

        with pytest.raises(CredentialFailure) as e:
            await service.generate_selected(
                store,
                owner,
                selected,
                TextRequest((ChatMessage("user", "synthetic"),)),
                operation_id=uuid4(),
                consents=(),
                data_categories=frozenset({"learning_goal"}),
                authorize_attempt=forbid,
            )
        assert e.value.code == "BUDGET_NOT_AUTHORIZED"

    internal(users, token, check)
    assert not sent
