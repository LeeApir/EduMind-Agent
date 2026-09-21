"""Fail-closed target validation for server-side Provider requests."""

import ipaddress
import re
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from os import getenv
from urllib.parse import urljoin, urlsplit

Resolver = Callable[[str, int], Sequence[str]]
LocalEndpoint = tuple[str, int]

_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_CLOUD_METADATA = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("168.63.129.16"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)


def _is_cloud_metadata(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip in _CLOUD_METADATA or (
        isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped in _CLOUD_METADATA
    )


class TargetValidationError(ValueError):
    """Safe error that never includes the rejected URL or DNS response."""

    def __init__(self) -> None:
        super().__init__("Provider target is not permitted.")


@dataclass(frozen=True, slots=True)
class TargetPolicy:
    deployment: str = "cloud"
    local_allowlist: frozenset[LocalEndpoint] = frozenset()

    def __post_init__(self) -> None:
        if self.deployment not in {"cloud", "local"}:
            raise TargetValidationError
        if self.deployment == "cloud" and self.local_allowlist:
            raise TargetValidationError
        for address, port in self.local_allowlist:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                raise TargetValidationError from None
            if (
                str(ip) != address
                or not 1 <= port <= 65535
                or ip.is_global
                or ip.is_link_local
                or ip.is_unspecified
                or ip.is_multicast
                or _is_cloud_metadata(ip)
            ):
                raise TargetValidationError


@dataclass(frozen=True, slots=True)
class ApprovedTarget:
    """Network adapter must connect to one of these IPs, never resolve host again."""

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]

    @property
    def connect_ip(self) -> str:
        return self.addresses[0]


def target_policy_from_environment() -> TargetPolicy:
    """Local access requires both local deployment and exact IP:port entries."""
    deployment = getenv("EDUMIND_PROVIDER_DEPLOYMENT", "cloud")
    entries = getenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", "")
    allowlist: set[LocalEndpoint] = set()
    if entries.strip():
        for entry in entries.split(","):
            try:
                parsed = urlsplit("//" + entry.strip())
                host = parsed.hostname
                port = parsed.port
                if (
                    host is None
                    or port is None
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError
                allowlist.add((str(ipaddress.ip_address(host)), port))
            except ValueError:
                raise TargetValidationError from None
    return TargetPolicy(deployment=deployment, local_allowlist=frozenset(allowlist))


def resolve_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Return every A/AAAA candidate; DNS failures fail closed."""
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise TargetValidationError from None
    return tuple(dict.fromkeys(str(record[4][0]) for record in records))


def _hostname(raw_host: str) -> str:
    if "%" in raw_host:
        raise TargetValidationError
    try:
        return str(ipaddress.ip_address(raw_host))
    except ValueError:
        pass
    host = raw_host.rstrip(".").lower()
    labels = host.split(".")
    if not host or len(host) > 253 or not all(_DNS_LABEL.fullmatch(label) for label in labels):
        raise TargetValidationError
    return host


def approve_target(
    url: str,
    *,
    policy: TargetPolicy,
    resolver: Resolver = resolve_addresses,
    allow_query: bool = False,
) -> ApprovedTarget:
    """Validate URL and all resolved IPs before one outbound connection."""
    if url != url.strip() or any(
        ord(char) < 32 or ord(char) == 127 or char == "\\" for char in url
    ):
        raise TargetValidationError
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (parsed.query and not allow_query)
        ):
            raise TargetValidationError
        hostname = _hostname(parsed.hostname)
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise TargetValidationError
    except ValueError:
        raise TargetValidationError from None

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    try:
        answers = (str(literal),) if literal is not None else tuple(resolver(hostname, port))
        addresses = tuple(dict.fromkeys(str(ipaddress.ip_address(answer)) for answer in answers))
    except (OSError, ValueError, UnicodeError):
        raise TargetValidationError from None
    if not addresses:
        raise TargetValidationError

    ip_values = tuple(ipaddress.ip_address(address) for address in addresses)
    public = all(ip.is_global and not _is_cloud_metadata(ip) for ip in ip_values)
    local = policy.deployment == "local" and all(
        (address, port) in policy.local_allowlist for address in addresses
    )
    if not (public or local) or (parsed.scheme != "https" and not local):
        raise TargetValidationError
    return ApprovedTarget(url=url, hostname=hostname, port=port, addresses=addresses)


def approve_redirect(
    previous: ApprovedTarget,
    location: str,
    *,
    policy: TargetPolicy,
    resolver: Resolver = resolve_addresses,
) -> ApprovedTarget:
    """Revalidate a same-origin redirect; never forward credentials to another origin."""
    if not location or any(
        ord(char) < 32 or ord(char) == 127 or char == "\\" for char in location
    ):
        raise TargetValidationError
    try:
        candidate_url = urljoin(previous.url, location)
        parsed = urlsplit(candidate_url)
        hostname = _hostname(parsed.hostname or "")
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise TargetValidationError from None
    if (
        hostname != previous.hostname
        or port != previous.port
        or parsed.scheme != urlsplit(previous.url).scheme
    ):
        raise TargetValidationError
    candidate = approve_target(
        candidate_url, policy=policy, resolver=resolver, allow_query=True
    )
    return candidate


@dataclass(frozen=True, slots=True)
class ProviderTargetGuard:
    """Re-resolve on each attempt; the adapter must use the returned pinned IP."""

    base_url: str
    policy: TargetPolicy
    resolver: Resolver = resolve_addresses

    def approve_base(self) -> ApprovedTarget:
        return approve_target(self.base_url, policy=self.policy, resolver=self.resolver)

    def approve_redirect(self, previous: ApprovedTarget, location: str) -> ApprovedTarget:
        return approve_redirect(previous, location, policy=self.policy, resolver=self.resolver)
