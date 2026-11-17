"""Pinned HTTPS adapter tests with synthetic keys and no real DNS or network."""

import asyncio
import json
import ssl
import threading
import time
from pathlib import Path

import httpx
import pytest

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as controller
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_pinned_transport_v1 as pinned
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.tests.test_p15_controlled_mock_v1 import attest, grant, handler_for
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC

KEYS = {
    "EDUMIND_DEEPSEEK_COMPAT_API_KEY": "synthetic-generation-key-901",
    "EDUMIND_AIAPI_REVIEW_API_KEY": "synthetic-review-key-902",
}
PUBLIC_IP = "1.1.1.1"


async def public_dns(host, port):
    assert host in {"api.deepseek.com", "aiapi.world"} and port == 443
    return (PUBLIC_IP,)


def make_adapter(handler, *, resolver=public_dns, keys=KEYS):
    return pinned.PinnedResponsesTransport(
        resolver=resolver, credentials=keys, transport=httpx.MockTransport(handler)
    )


def make_request(role="generation"):
    stage = "B_generate" if role == "generation" else "review_B"
    payload = old.baseline_input(SPEC) if role == "generation" else {"cells": []}
    body, _ = budget.build(stage, payload, budget.DevelopmentPolicy(200_000, 220_000, 8000))
    return httpx.Request("POST", wire.ROUTES[role]["url"], content=body)


@pytest.mark.parametrize("arm", ["B", "C"])
def test_both_full_chains_use_pinned_adapter_and_same_ledger(tmp_path, arm):
    seen, hostnames = [], []
    fixture = handler_for(arm, seen)

    def network(request):
        host = request.headers["host"]
        role = "generation" if host == "api.deepseek.com" else "review"
        route = wire.ROUTES[role]
        assert request.url.host == PUBLIC_IP and request.url.path == httpx.URL(route["url"]).path
        assert request.extensions["sni_hostname"] == host
        assert request.headers["authorization"] == "Bearer " + KEYS[route["credential_env"]]
        assert request.headers["accept-encoding"] == "identity"
        hostnames.append(host)
        synthetic = httpx.Request(
            "POST", route["url"], content=request.content,
            headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
        )
        return fixture(synthetic)

    path = tmp_path / "ledger.db"
    instance = controller.Controller(path, grant(arm, path), make_adapter(network))
    result = asyncio.run(instance.run(attest))
    assert result["status"] == "mock_advisory_pass"
    assert len(seen) == (4 if arm == "B" else 5)
    assert hostnames.count("aiapi.world") == 2
    assert instance.fixed_denominator_summary()["slots"][0]["outcome"] == "mechanical_complete"
    rows = list(instance.db.execute("SELECT request,response FROM attempts"))
    for row in rows:
        for key in KEYS.values():
            assert key.encode() not in bytes(row["request"])
            assert key.encode() not in bytes(row["response"])
    assert all(route["credential_env"] in KEYS for route in instance.package["runtime_contract"]["routes"].values())
    instance.close()
    for file in (path, Path(str(path) + ".anchor")):
        raw = file.read_bytes()
        assert all(key.encode() not in raw for key in KEYS.values())


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com/responses",
        "https://api.deepseek.com/responses?extra=1",
        "https://api.deepseek.com/other",
        "https://api.deepseek.com@attacker.invalid/responses",
        "https://1.1.1.1/responses",
        "https://api.deepseek.com:444/responses",
    ],
)
def test_changed_target_rejected_before_dns_or_credentials(url):
    def never(request):
        pytest.fail("must not send")

    async def never_dns(host, port):
        pytest.fail("must not resolve")

    adapter = make_adapter(never, resolver=never_dns)
    request = make_request()
    changed = httpx.Request("POST", url, content=request.content)
    with pytest.raises(c.ContractError, match="TRANSPORT_TARGET"):
        asyncio.run(adapter.handle_async_request(changed))


def test_cross_role_model_and_foreign_authorization_rejected_before_dns():
    async def never_dns(host, port):
        pytest.fail("must not resolve")

    adapter = make_adapter(lambda request: pytest.fail("must not send"), resolver=never_dns)
    request = make_request()
    body = json.loads(request.content)
    body["model"] = wire.ROUTES["review"]["model"]
    wrong = httpx.Request("POST", request.url, json=body)
    with pytest.raises(c.ContractError, match="TRANSPORT_MODEL"):
        asyncio.run(adapter.handle_async_request(wrong))
    request.headers["Authorization"] = "Bearer foreign-secret"
    with pytest.raises(c.ContractError, match="TRANSPORT_TARGET"):
        asyncio.run(adapter.handle_async_request(request))


@pytest.mark.parametrize("addresses", [("1.1.1.1", "127.0.0.1"), ("169.254.169.254",), ()])
def test_dns_mixed_private_or_empty_stops_before_http(addresses):
    async def resolver(host, port):
        return addresses

    adapter = make_adapter(lambda request: pytest.fail("must not send"), resolver=resolver)
    with pytest.raises(c.ContractError, match="TRANSPORT_DNS"):
        asyncio.run(adapter.handle_async_request(make_request()))


def test_redirect_is_not_followed_and_stops_controller(tmp_path):
    sent = []

    def redirect(request):
        sent.append((request.url.host, request.url.path))
        return httpx.Response(
            302, headers={"Location": "https://evil.invalid"},
            stream=httpx.ByteStream(b'{"error":"redirect"}')
        )

    path = tmp_path / "ledger.db"
    instance = controller.Controller(path, grant("B", path), make_adapter(redirect))
    with pytest.raises(Exception):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT state,http_status FROM attempts").fetchone()
    assert len(sent) == 1 and row["http_status"] == 302
    assert instance.batch_status() == "stopped"
    instance.close()


@pytest.mark.parametrize("mode", ["oversize", "secret", "unicode_secret", "exception", "compressed"])
def test_bad_response_preserves_unknown_without_exposing_key(tmp_path, mode):
    key = KEYS["EDUMIND_DEEPSEEK_COMPAT_API_KEY"]

    def bad(request):
        if mode == "oversize":
            return httpx.Response(200, stream=httpx.ByteStream(b"x" * (pinned.MAX_RESPONSE + 1)))
        if mode == "secret":
            return httpx.Response(200, stream=httpx.ByteStream(("echo " + key).encode()))
        if mode == "unicode_secret":
            return httpx.Response(
                200, stream=httpx.ByteStream("".join(f"\\u{ord(ch):04x}" for ch in key).encode())
            )
        if mode == "compressed":
            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=b"x")
        raise RuntimeError("transport exception with " + key)

    path = tmp_path / "ledger.db"
    instance = controller.Controller(path, grant("B", path), make_adapter(bad))
    with pytest.raises(c.ContractError) as raised:
        asyncio.run(instance.run(attest))
    assert str(raised.value) == {
        "oversize": "TRANSPORT_RESPONSE_SIZE",
        "secret": "TRANSPORT_SECRET_ECHO",
        "unicode_secret": "TRANSPORT_SECRET_ECHO",
        "exception": "TRANSPORT_FAILURE",
        "compressed": "TRANSPORT_CONTENT_ENCODING",
    }[mode]
    assert key not in str(raised.value)
    row = instance.db.execute("SELECT * FROM attempts").fetchone()
    assert row["state"] == "unknown" and row["response"] is None
    assert row["input_reserved"] > 0 and instance.batch_status() == "stopped"
    instance.close()
    assert all(secret.encode() not in path.read_bytes() for secret in KEYS.values())


def test_secret_in_outgoing_body_is_rejected_before_reservation(tmp_path):
    path = tmp_path / "ledger.db"
    instance = controller.Controller(path, grant("B", path), make_adapter(lambda request: pytest.fail("send")))
    payload = old.baseline_input(SPEC)
    payload["forbidden"] = KEYS["EDUMIND_AIAPI_REVIEW_API_KEY"]
    with pytest.raises(c.ContractError, match="TRANSPORT_SECRET_IN_REQUEST"):
        asyncio.run(instance._exchange("B_generate", payload))
    assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    instance.close()
    assert all(secret.encode() not in path.read_bytes() for secret in KEYS.values())


def test_transport_primitive_ignores_env_ca_and_proxy_without_network(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/definitely/missing/ca.pem")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    transport = pinned.real_http_transport()
    assert type(transport) is httpx.AsyncHTTPTransport
    assert transport._pool._retries == 0
    assert transport._pool._ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert transport._pool._ssl_context.check_hostname
    asyncio.run(transport.aclose())


def test_real_httpx_transport_uses_same_adapter_without_real_socket(tmp_path, monkeypatch):
    seen = []

    async def intercepted(self, request):
        seen.append((str(request.url), request.headers["host"], request.extensions["sni_hostname"]))
        assert request.headers["authorization"] == "Bearer " + KEYS["EDUMIND_DEEPSEEK_COMPAT_API_KEY"]
        return httpx.Response(200, stream=httpx.ByteStream(b'{"ok":true}'))

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", intercepted)
    transport = pinned.real_http_transport()
    adapter = pinned.PinnedResponsesTransport(resolver=public_dns, credentials=KEYS, transport=transport)
    assert adapter.offline_only is False
    path = tmp_path / "ledger.db"
    with pytest.raises(c.ContractError, match="MOCK_TRANSPORT_REQUIRED"):
        controller.Controller(path, grant("B", path), adapter)
    assert not path.exists()
    with pytest.raises(AttributeError):
        adapter.offline_only = True
    with pytest.raises(c.ContractError, match="EXACT_LIVE_PACKAGE_AUTHORIZATION_REQUIRED"):
        asyncio.run(adapter.handle_async_request(make_request()))
    with pytest.raises(c.ContractError, match="EXACT_LIVE_PACKAGE_AUTHORIZATION_REQUIRED"):
        asyncio.run(adapter._request(make_request()))
    assert not seen
    # Only the synthetic test bypasses the future authorization gate; the
    # actual network method is intercepted above and cannot open a socket.
    monkeypatch.setattr(pinned, "live_adapter_unavailable", lambda: None)
    response = asyncio.run(adapter.handle_async_request(make_request()))
    assert asyncio.run(response.aread()) == b'{"ok":true}'
    assert seen == [("https://1.1.1.1/responses", "api.deepseek.com", "api.deepseek.com")]


def test_adapter_reuse_failure_releases_second_ledger_lock(tmp_path):
    first_path, second_path = tmp_path / "first.db", tmp_path / "second.db"
    adapter = make_adapter(lambda request: pytest.fail("must not send"))
    first = controller.Controller(first_path, grant("B", first_path), adapter)
    with pytest.raises(c.ContractError, match="TRANSPORT_ALREADY_BOUND"):
        controller.Controller(second_path, grant("B", second_path), adapter)
    second = controller.Controller(
        second_path, grant("B", second_path), httpx.MockTransport(lambda request: pytest.fail("send"))
    )
    first.close()
    second.close()


def test_live_gate_and_credential_names_are_not_silent_defaults():
    with pytest.raises(c.ContractError, match="EXACT_LIVE_PACKAGE_AUTHORIZATION_REQUIRED"):
        pinned.live_adapter_unavailable()
    with pytest.raises(c.ContractError, match="TRANSPORT_CREDENTIAL_SOURCES"):
        make_adapter(lambda request: httpx.Response(200), keys={"wrong": "synthetic-key"})
    with pytest.raises(c.ContractError, match="TRANSPORT_CREDENTIAL"):
        make_adapter(
            lambda request: httpx.Response(200),
            keys={**KEYS, "EDUMIND_DEEPSEEK_COMPAT_API_KEY": 'synthetic-"-generation'},
        )


def test_swapping_credential_source_after_package_creation_stops_before_dns(tmp_path, monkeypatch):
    async def never_dns(host, port):
        pytest.fail("must not resolve")

    path = tmp_path / "ledger.db"
    adapter = make_adapter(lambda request: pytest.fail("must not send"), resolver=never_dns)
    instance = controller.Controller(path, grant("B", path), adapter)
    monkeypatch.setitem(
        wire.ROUTES["generation"], "credential_env", wire.ROUTES["review"]["credential_env"]
    )
    with pytest.raises(c.ContractError, match="MOCK_RUNTIME_BINDING"):
        asyncio.run(instance.run(attest))
    assert instance.batch_status() == "stopped"
    assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    instance.close()


def test_route_mutation_while_dns_waits_does_not_cross_send_credentials(monkeypatch):
    sent = []

    async def mutate_route(host, port):
        monkeypatch.setitem(
            wire.ROUTES["generation"], "credential_env", wire.ROUTES["review"]["credential_env"]
        )
        return (PUBLIC_IP,)

    adapter = make_adapter(lambda request: sent.append(1), resolver=mutate_route)
    with pytest.raises(c.ContractError, match="TRANSPORT_TARGET"):
        asyncio.run(adapter.handle_async_request(make_request()))
    assert not sent


def test_json_escaped_credential_is_detected_before_response_persistence(tmp_path):
    key = "synthetic-/-generation"
    keys = {**KEYS, "EDUMIND_DEEPSEEK_COMPAT_API_KEY": key}
    raw = json.dumps({"echo": key}).replace("/", r"\/").encode()
    assert key.encode() not in raw
    path = tmp_path / "ledger.db"
    adapter = make_adapter(lambda request: httpx.Response(200, stream=httpx.ByteStream(raw)), keys=keys)
    instance = controller.Controller(path, grant("B", path), adapter)
    with pytest.raises(c.ContractError, match="TRANSPORT_SECRET_ECHO"):
        asyncio.run(instance.run(attest))
    assert instance.db.execute("SELECT response FROM attempts").fetchone()[0] is None
    instance.close()
    assert key.encode() not in path.read_bytes()


@pytest.mark.parametrize("location", ["request", "response", "invalid_response", "nested_unicode", "double_unicode"])
def test_nested_encoded_or_invalid_json_never_persists_key(tmp_path, location):
    key = "synthetic-/-generation"
    keys = {**KEYS, "EDUMIND_DEEPSEEK_COMPAT_API_KEY": key}
    nested = json.dumps({"echo": key})
    if location == "nested_unicode":
        nested = "".join(f"\\u{ord(ch):04x}" for ch in key)
    if location == "double_unicode":
        nested = json.dumps("".join(f"\\u{ord(ch):04x}" for ch in key))
    raw = json.dumps({"output": [{"content": [{"text": nested}]}]}).encode()
    if location == "invalid_response":
        raw = ("bad " + json.dumps(key)[1:-1]).encode()
    assert pinned._secret_visible(raw, key)
    path = tmp_path / "ledger.db"
    adapter = make_adapter(lambda request: httpx.Response(200, stream=httpx.ByteStream(raw)), keys=keys)
    instance = controller.Controller(path, grant("B", path), adapter)
    if location == "request":
        payload = old.baseline_input(SPEC)
        payload["extra"] = nested
        with pytest.raises(c.ContractError, match="TRANSPORT_SECRET_IN_REQUEST"):
            asyncio.run(instance._exchange("B_generate", payload))
        assert instance.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    else:
        with pytest.raises(c.ContractError, match="TRANSPORT_SECRET_ECHO"):
            asyncio.run(instance.run(attest))
        assert instance.db.execute("SELECT response FROM attempts").fetchone()[0] is None
    instance.close()
    assert key.encode() not in path.read_bytes()


def test_late_dns_cannot_start_http_after_timeout_and_close(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)
    entered, release, resolved = threading.Event(), threading.Event(), threading.Event()
    sent = []

    async def delayed_dns(host, port):
        entered.set()
        await asyncio.to_thread(release.wait, 2)
        resolved.set()
        return (PUBLIC_IP,)

    path = tmp_path / "ledger.db"
    instance = controller.Controller(
        path, grant("B", path), make_adapter(lambda request: sent.append(1), resolver=delayed_dns)
    )
    with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
        asyncio.run(instance.run(attest))
    assert entered.is_set() and instance.batch_status() == "stopped"
    instance.close()
    release.set()
    assert resolved.wait(2)
    time.sleep(0.1)
    assert sent == []


def test_stop_wins_at_final_dispatch_fence(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    sent = []
    base = pinned.DispatchFence

    class PausingFence(base):
        def start(self, call):
            entered.set()
            release.wait(2)
            try:
                return super().start(call)
            finally:
                finished.set()

    monkeypatch.setattr(pinned, "DispatchFence", PausingFence)
    path = tmp_path / "ledger.db"
    instance = controller.Controller(
        path, grant("B", path), make_adapter(lambda request: sent.append(1))
    )
    with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
        asyncio.run(instance.run(attest))
    assert entered.is_set() and instance.batch_status() == "stopped"
    instance.close()
    release.set()
    assert finished.wait(2)
    time.sleep(0.05)
    assert sent == []


def test_stop_before_low_level_dispatch_even_if_client_send_was_scheduled(tmp_path, monkeypatch):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.05)
    entered, release, resumed = threading.Event(), threading.Event(), threading.Event()
    sent = []
    original = httpx.AsyncClient.send

    async def delayed_send(self, request, *args, **kwargs):
        if "authorization" in request.headers:
            entered.set()
            await asyncio.to_thread(release.wait, 2)
            resumed.set()
        return await original(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", delayed_send)
    path = tmp_path / "ledger.db"
    instance = controller.Controller(path, grant("B", path), make_adapter(lambda request: sent.append(1)))
    with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
        asyncio.run(instance.run(attest))
    assert entered.is_set() and instance.batch_status() == "stopped"
    instance.close()
    release.set()
    assert resumed.wait(2)
    time.sleep(0.1)
    assert sent == []


@pytest.mark.parametrize("where", ["dns", "response_body"])
def test_adapter_timeout_keeps_unknown_and_does_not_follow_up(tmp_path, monkeypatch, where):
    monkeypatch.setattr(controller, "HTTP_WALL_SECONDS", 0.08)
    sent = []

    async def resolver(host, port):
        if where == "dns":
            await asyncio.sleep(1)
        return (PUBLIC_IP,)

    class StallStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"first"
            await asyncio.sleep(1)
            yield b"late"

    def respond(request):
        sent.append(1)
        return httpx.Response(200, stream=StallStream())

    path = tmp_path / "ledger.db"
    instance = controller.Controller(path, grant("B", path), make_adapter(respond, resolver=resolver))
    with pytest.raises(c.ContractError, match="MOCK_HTTP_TIMEOUT"):
        asyncio.run(instance.run(attest))
    row = instance.db.execute("SELECT state,input_reserved,response FROM attempts").fetchone()
    assert row["state"] == "unknown" and row["input_reserved"] > 0 and row["response"] is None
    assert sent == ([] if where == "dns" else [1])
    assert instance.batch_status() == "stopped"
    instance.close()
