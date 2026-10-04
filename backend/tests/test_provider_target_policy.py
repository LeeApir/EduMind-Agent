"""Phase 1 target/transport regressions, controlled DNS and no real sockets."""

import asyncio
from collections.abc import Sequence

import httpx
import pytest

from app.core.config import ProviderSettings
from app.core.provider_target import (
    ProviderTargetGuard,
    TargetPolicy,
    TargetValidationError,
    approve_target,
    target_policy_from_environment,
)
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    TextRequest,
)

SECRET = "TEST_ONLY_TARGET_POLICY_KEY"
PROMPT = TextRequest(messages=(ChatMessage(role="user", content="synthetic context"),))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.1.1",
        "192.168.1.1",
        "100.64.0.1",
        "169.254.169.254",
        "100.100.100.200",
        "168.63.129.16",
        "0.0.0.0",
        "224.0.0.1",
        "255.255.255.255",
        "192.0.2.1",
        "198.18.0.1",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fec0::1",
        "ff02::1",
        "fd00:ec2::254",
        "::ffff:127.0.0.1",
        "::ffff:224.0.0.1",
        "::ffff:100.100.100.200",
        "::ffff:100.64.0.1",
        "64:ff9b::7f00:1",
        "64:ff9b:1::a00:1",
        "2002:0808:0808::1",
        "2001::1",
        "2001:4860:4860::8888%en0",
    ],
)
def test_all_nonpublic_or_translation_answers_block_before_dispatch(address, caplog):
    attempts = []
    settings = ProviderSettings("https://provider.test/v1", SECRET, "test-model")
    guard = ProviderTargetGuard(
        settings.base_url, TargetPolicy(), resolver=lambda host, port: ("8.8.8.8", address)
    )
    adapter = DeepSeekResponsesAdapter(
        settings, guard, transport=httpx.MockTransport(lambda request: attempts.append(request))
    )
    with pytest.raises(ProviderError) as failure:
        asyncio.run(adapter.generate_text(PROMPT))
    assert failure.value.code is ProviderErrorCode.INVALID_TARGET
    assert not attempts and SECRET not in str(failure.value) and SECRET not in caplog.text


@pytest.mark.parametrize("address", ["224.0.0.1", "fec0::1", "ff02::1", "64:ff9b::7f00:1"])
def test_admin_allowlist_cannot_enable_special_addresses(address):
    with pytest.raises(TargetValidationError):
        TargetPolicy("local", frozenset({(address, 11434)}))


@pytest.mark.parametrize(
    "url",
    [
        "https://user:TEST_ONLY_TARGET_POLICY_KEY@provider.test/v1",
        "https://provider.test/v1?api_key=TEST_ONLY_TARGET_POLICY_KEY",
        "https://provider.test/v1#TEST_ONLY_TARGET_POLICY_KEY",
        "https://provider.test\\@127.0.0.1/v1",
        "https://provider.test\x00/v1",
        "https://provider.test\t/v1",
        "https://%31%32%37.0.0.1/v1",
        "http://127.0.0.1:11434",
        "http://provider.test/v1",
    ],
)
def test_invalid_client_urls_do_not_reach_dns_and_errors_are_safe(url):
    def no_dns(host, port):
        pytest.fail("invalid URL reached DNS")

    with pytest.raises(TargetValidationError) as failure:
        approve_target(url, policy=TargetPolicy(), resolver=no_dns)
    assert SECRET not in str(failure.value)


def test_local_ipv6_and_all_answers_need_exact_admin_port(monkeypatch):
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "local")
    monkeypatch.setenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", "127.0.0.1:11434,[::1]:11434")
    policy = target_policy_from_environment()
    target = approve_target(
        "http://local-model.test:11434",
        policy=policy,
        resolver=lambda host, port: ("127.0.0.1", "::1"),
    )
    assert target.addresses == ("127.0.0.1", "::1")
    for url, answers in [
        ("http://local-model.test:11435", ("127.0.0.1",)),
        ("http://local-model.test:11434", ("127.0.0.1", "10.0.0.2")),
        ("http://local-model.test:11434", ("127.0.0.1", "8.8.8.8")),
    ]:
        with pytest.raises(TargetValidationError):
            approve_target(url, policy=policy, resolver=lambda h, p: answers)
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "cloud")
    with pytest.raises(TargetValidationError):
        target_policy_from_environment()


def success():
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "model": "test-model",
            "output": [
                {
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                }
            ],
        },
    )


def test_pinned_request_preserves_host_tls_and_has_no_environment_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    real_client = httpx.AsyncClient

    def observed_client(*args, **kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", observed_client)
    for address, hostname in [("8.8.8.8", "provider.test"), ("2001:4860:4860::8888", "v6.test")]:
        attempts = []
        calls = []

        def resolve(host, port) -> Sequence[str]:
            calls.append((host, port))
            # A second lookup would rebind; transport must use first pinned IP.
            return (address,) if len(calls) == 1 else ("127.0.0.1",)

        def respond(request):
            attempts.append(request)
            return success()

        settings = ProviderSettings(f"https://{hostname}:8443/v1", SECRET, "test-model")
        adapter = DeepSeekResponsesAdapter(
            settings,
            ProviderTargetGuard(settings.base_url, TargetPolicy(), resolve),
            transport=httpx.MockTransport(respond),
        )
        assert asyncio.run(adapter.generate_text(PROMPT)).text == "ok"
        assert len(attempts) == 1 and calls == [(hostname, 8443)]
        request = attempts[0]
        assert request.url.host == address and request.url.port == 8443
        assert request.url.path == "/v1/responses"
        assert request.headers["host"] == hostname + ":8443"
        assert request.extensions["sni_hostname"] == hostname
        assert request.headers["authorization"] == "Bearer " + SECRET
        assert SECRET not in str(request.url)


@pytest.mark.parametrize(
    "location", ["/elsewhere", "https://other.test", "http://169.254.169.254/latest"]
)
def test_no_redirect_is_followed_even_same_origin(location):
    attempts = []

    def respond(request):
        attempts.append(request)
        return httpx.Response(307, headers={"Location": location}, text=SECRET)

    settings = ProviderSettings("https://provider.test/v1", SECRET, "test-model")
    adapter = DeepSeekResponsesAdapter(
        settings,
        ProviderTargetGuard(settings.base_url, TargetPolicy(), lambda h, p: ("8.8.8.8",)),
        transport=httpx.MockTransport(respond),
    )
    with pytest.raises(ProviderError) as failure:
        asyncio.run(ProviderGateway(adapter).generate_text(PROMPT, retry_safe=True))
    assert failure.value.code is ProviderErrorCode.INVALID_TARGET
    assert len(attempts) == 1 and SECRET not in str(failure.value)


def test_retry_revalidates_dns_and_never_sends_key_to_rebound_address():
    attempts, resolutions = [], []

    def resolve(host, port):
        resolutions.append((host, port))
        return ("8.8.8.8",) if len(resolutions) == 1 else ("127.0.0.1",)

    def respond(request):
        attempts.append(request)
        return httpx.Response(503, text=SECRET)

    async def no_sleep(delay):
        pass

    settings = ProviderSettings("https://provider.test/v1", SECRET, "test-model")
    adapter = DeepSeekResponsesAdapter(
        settings,
        ProviderTargetGuard(settings.base_url, TargetPolicy(), resolve),
        transport=httpx.MockTransport(respond),
    )
    with pytest.raises(ProviderError) as failure:
        asyncio.run(ProviderGateway(adapter, sleep=no_sleep).generate_text(PROMPT, retry_safe=True))
    assert failure.value.code is ProviderErrorCode.INVALID_TARGET
    assert len(attempts) == 1 and len(resolutions) == 2


def test_resolver_exception_is_redacted():
    def broken(host, port):
        raise OSError(SECRET)

    with pytest.raises(TargetValidationError) as failure:
        approve_target("https://provider.test", policy=TargetPolicy(), resolver=broken)
    assert SECRET not in str(failure.value)
