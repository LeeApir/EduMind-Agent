"""Test-only browser server refuses real gateways and non-loopback network access."""

import pytest
from p15_acceptance_server import audit, forbidden


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_pg_connections_are_allowed(host):
    audit("socket.connect", (object(), (host, 15437)))
    audit("socket.getaddrinfo", (host, 15437, 0, 0, 0))


@pytest.mark.parametrize(
    "host", ["8.8.8.8", "169.254.169.254", "10.0.0.1", "provider.example", "api.openai.com"]
)
def test_remote_ip_and_dns_are_rejected_before_socket_access(host):
    with pytest.raises((RuntimeError, ValueError)):
        audit("socket.connect", (object(), (host, 443)))
    with pytest.raises((RuntimeError, ValueError)):
        audit("socket.getaddrinfo", (host, 443, 0, 0, 0))


def test_any_real_gateway_construction_is_forbidden():
    with pytest.raises(RuntimeError, match="T036_REAL_PROVIDER_FORBIDDEN"):
        forbidden("ignored-test-provider")
