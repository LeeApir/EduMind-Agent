"""SSRF regression tests use controlled DNS answers and never open sockets."""

from collections.abc import Sequence

import pytest

from app.core.config import ProviderSettings
from app.core.provider_factory import build_server_provider_gateway
from app.core.provider_target import (
    ProviderTargetGuard,
    TargetPolicy,
    TargetValidationError,
    approve_target,
    target_policy_from_environment,
)
from app.services.provider_gateway import ProviderAdapter, ProviderError, ProviderErrorCode


def public_resolver(_host: str, _port: int) -> Sequence[str]:
    return ("8.8.8.8", "1.1.1.1")


def test_public_https_approves_all_dns_answers_and_exposes_pinned_ip() -> None:
    target = approve_target(
        "https://api.example.test/v1", policy=TargetPolicy(), resolver=public_resolver
    )
    assert target.hostname == "api.example.test"
    assert target.port == 443
    assert target.addresses == ("8.8.8.8", "1.1.1.1")
    assert target.connect_ip == "8.8.8.8"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test/v1",
        "file:///etc/passwd",
        "https://user:pass@api.example.test/v1",
        "https://api.example.test:0/v1",
        "https://api.example.test:99999/v1",
        "https://api.example.test/v1?token=secret",
        "https://api.example.test/v1#fragment",
        "https://api.example.test\\@127.0.0.1/v1",
        "https://api.example.test\n@127.0.0.1/v1",
        "https://[2001:4860:4860::8888%25en0]/v1",
    ],
)
def test_malformed_or_non_https_base_url_fails_closed(url: str) -> None:
    with pytest.raises(TargetValidationError, match="Provider target is not permitted"):
        approve_target(url, policy=TargetPolicy(), resolver=public_resolver)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.100.100.200",
        "168.63.129.16",
        "::ffff:168.63.129.16",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fd00:ec2::254",
        "::ffff:127.0.0.1",
    ],
)
def test_cloud_blocks_internal_and_metadata_addresses(address: str) -> None:
    url = f"https://[{address}]/v1" if ":" in address else f"https://{address}/v1"
    with pytest.raises(TargetValidationError):
        approve_target(url, policy=TargetPolicy())


def test_mixed_dns_answers_and_dns_failure_fail_closed() -> None:
    with pytest.raises(TargetValidationError):
        approve_target(
            "https://api.example.test/v1",
            policy=TargetPolicy(),
            resolver=lambda _host, _port: ("8.8.8.8", "10.0.0.2"),
        )
    with pytest.raises(TargetValidationError):
        approve_target(
            "https://api.example.test/v1",
            policy=TargetPolicy(),
            resolver=lambda _host, _port: (),
        )


def test_local_http_needs_local_mode_and_exact_ip_port_allowlist() -> None:
    policy = TargetPolicy(
        deployment="local", local_allowlist=frozenset({("127.0.0.1", 11434)})
    )
    target = approve_target("http://127.0.0.1:11434/v1", policy=policy)
    assert target.connect_ip == "127.0.0.1"
    with pytest.raises(TargetValidationError):
        approve_target("http://127.0.0.1:11435/v1", policy=policy)
    with pytest.raises(TargetValidationError):
        approve_target("http://127.0.0.1:11434/v1", policy=TargetPolicy())
    with pytest.raises(TargetValidationError):
        TargetPolicy(deployment="cloud", local_allowlist=policy.local_allowlist)
    with pytest.raises(TargetValidationError):
        TargetPolicy(
            deployment="local", local_allowlist=frozenset({("169.254.169.254", 80)})
        )
    with pytest.raises(TargetValidationError):
        TargetPolicy(
            deployment="local", local_allowlist=frozenset({("fd00:ec2::254", 80)})
        )


def test_local_dns_name_requires_every_answer_on_allowlist() -> None:
    policy = TargetPolicy(
        deployment="local", local_allowlist=frozenset({("127.0.0.1", 11434)})
    )
    target = approve_target(
        "http://model.test:11434/v1",
        policy=policy,
        resolver=lambda _host, _port: ("127.0.0.1",),
    )
    assert target.addresses == ("127.0.0.1",)
    with pytest.raises(TargetValidationError):
        approve_target(
            "http://model.test:11434/v1",
            policy=policy,
            resolver=lambda _host, _port: ("127.0.0.1", "10.0.0.2"),
        )


def test_environment_allowlist_requires_local_deployment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "cloud")
    monkeypatch.setenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", "127.0.0.1:11434")
    with pytest.raises(TargetValidationError):
        target_policy_from_environment()
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "local")
    assert target_policy_from_environment().local_allowlist == frozenset(
        {("127.0.0.1", 11434)}
    )


def test_dns_rebinding_is_rechecked_before_each_attempt() -> None:
    answers = iter((("8.8.8.8",), ("127.0.0.1",)))
    guard = ProviderTargetGuard(
        "https://api.example.test/v1",
        TargetPolicy(),
        resolver=lambda _host, _port: next(answers),
    )
    assert guard.approve_base().connect_ip == "8.8.8.8"
    with pytest.raises(TargetValidationError):
        guard.approve_base()


def test_redirect_revalidates_destination_and_dns_before_another_request() -> None:
    answers = iter((("8.8.8.8",), ("10.0.0.1",)))
    guard = ProviderTargetGuard(
        "https://api.example.test/v1",
        TargetPolicy(),
        resolver=lambda _host, _port: next(answers),
    )
    first = guard.approve_base()
    with pytest.raises(TargetValidationError):
        guard.approve_redirect(first, "/v1/chat/completions")

    safe_guard = ProviderTargetGuard(
        "https://api.example.test/v1", TargetPolicy(), resolver=public_resolver
    )
    first = safe_guard.approve_base()
    assert safe_guard.approve_redirect(first, "/v1/chat/completions").connect_ip == "8.8.8.8"
    for location in ("https://other.example.test/v1", "http://api.example.test/v1"):
        with pytest.raises(TargetValidationError):
            safe_guard.approve_redirect(first, location)

    def forbidden_dns(_host: str, _port: int) -> Sequence[str]:
        raise AssertionError("cross-origin redirects must be rejected before DNS")

    guard_without_dns = ProviderTargetGuard(
        "https://api.example.test/v1", TargetPolicy(), resolver=forbidden_dns
    )
    with pytest.raises(TargetValidationError):
        guard_without_dns.approve_redirect(first, "https://other.example.test/v1")


def test_factory_rejects_unsafe_target_before_adapter_receives_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "http://169.254.169.254/latest")
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "test-model")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "sensitive-key")
    monkeypatch.delenv("EDUMIND_PROVIDER_DEPLOYMENT", raising=False)
    monkeypatch.delenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", raising=False)
    calls = 0

    def adapter_factory(
        _settings: ProviderSettings, _guard: ProviderTargetGuard
    ) -> ProviderAdapter:
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe adapter must not be created")

    with pytest.raises(ProviderError) as raised:
        build_server_provider_gateway(adapter_factory)
    assert raised.value.code == ProviderErrorCode.INVALID_TARGET
    assert "169.254.169.254" not in str(raised.value)
    assert "sensitive-key" not in str(raised.value)
    assert calls == 0
