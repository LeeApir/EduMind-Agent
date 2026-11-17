"""Pinned HTTPS adapter, exercised only with synthetic credentials and Mock HTTP.

The current controller admits only ``offline`` instances.  A future separately
approved execution package must provide its own verified authorization gate
before enabling the live resolver, credential source, or network transport.
"""

import asyncio
import ipaddress
import json
import re
from copy import deepcopy
from collections.abc import Awaitable, Callable, Mapping
from threading import Lock
from typing import Any, Coroutine
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.provider_target import TargetPolicy, approve_target
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire

MAX_RESPONSE = 2 * 1024 * 1024
MAX_JSON_DEPTH = 64
VERSION = "pinned-responses-transport-v1-offline-only"


def _valid_key(value: object) -> bool:
    # RFC 6750 bearer-token characters; quotes/backslashes are not bearer tokens.
    return (
        type(value) is str
        and 8 <= len(value) <= 1024
        and re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", value) is not None
    )
SAFE_ERRORS = frozenset(
    {
        "TRANSPORT_TARGET",
        "TRANSPORT_REQUEST",
        "TRANSPORT_MODEL",
        "TRANSPORT_DNS",
        "TRANSPORT_CREDENTIAL",
        "TRANSPORT_SECRET_IN_REQUEST",
        "TRANSPORT_CONTENT_ENCODING",
        "TRANSPORT_RESPONSE_SIZE",
        "TRANSPORT_SECRET_ECHO",
        "TRANSPORT_STOPPED",
    }
)


def real_http_transport() -> httpx.AsyncHTTPTransport:
    """Create the reviewed network primitive; construction itself does not send."""
    return httpx.AsyncHTTPTransport(retries=0, trust_env=False, verify=True)


def _secret_visible(raw: bytes, key: str) -> bool:
    """Fail closed on invalid JSON; inspect bounded nested JSON/text encodings."""
    if key.encode("ascii") in raw:
        return True
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return True
    for _ in range(3):
        text = re.sub(
            r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), text
        )
        if key in text:
            return True
    try:
        root = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return True
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            return True
        if isinstance(item, str):
            original = item
            for _ in range(3):
                if key in item:
                    return True
                decoded = re.sub(
                    r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), item
                ).replace(r"\/", "/")
                if decoded == item:
                    break
                item = decoded
            if key in item:
                return True
            try:
                nested = json.loads(original)
            except (ValueError, UnicodeError, RecursionError):
                continue
            # A JSON string can encode another JSON document. Do not recurse
            # forever on plain numbers or booleans represented as text.
            if isinstance(nested, (dict, list, str)) and nested != original:
                stack.append((nested, depth + 1))
        if isinstance(item, dict):
            stack.extend((value, depth + 1) for value in item.keys())
            stack.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, list):
            stack.extend((value, depth + 1) for value in item)
    return False


class DispatchFence:
    """Linearize stop and the initiation of an individual send."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._stopped = False

    def stop(self) -> None:
        with self._lock:
            self._stopped = True

    def is_set(self) -> bool:
        with self._lock:
            return self._stopped

    def start(self, call: Coroutine[Any, Any, httpx.Response]) -> asyncio.Task[httpx.Response]:
        begun = False

        async def guarded() -> httpx.Response:
            nonlocal begun
            begun = True
            if self.is_set():
                call.close()
                raise c.ContractError("TRANSPORT_STOPPED")
            return await call

        with self._lock:
            if self._stopped:
                call.close()
                raise c.ContractError("TRANSPORT_STOPPED")
            task = asyncio.create_task(guarded())
            task.add_done_callback(lambda _task: None if begun else call.close())
            return task


class _DispatchTransport(httpx.AsyncBaseTransport):
    """Place the stop/dispatch linearization immediately at the transport edge."""

    def __init__(self, inner: httpx.AsyncBaseTransport, fence: DispatchFence | None) -> None:
        self.inner, self.fence = inner, fence

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        call = self.inner.handle_async_request(request)
        return await (self.fence.start(call) if self.fence else asyncio.create_task(call))

    async def aclose(self) -> None:
        await self.inner.aclose()


class PinnedResponsesTransport(httpx.AsyncBaseTransport):
    """Fixed-route IP pinning with explicit, synthetic offline dependencies."""

    def __init__(
        self,
        *,
        resolver: Callable[[str, int], Awaitable[tuple[str, ...]]],
        credentials: Mapping[str, str],
        transport: httpx.MockTransport | httpx.AsyncHTTPTransport,
    ) -> None:
        c.require(
            type(transport) in (httpx.MockTransport, httpx.AsyncHTTPTransport),
            "TRANSPORT_KIND",
        )
        c.require(
            set(credentials) == {r["credential_env"] for r in wire.ROUTES.values()},
            "TRANSPORT_CREDENTIAL_SOURCES",
        )
        c.require(all(_valid_key(key) for key in credentials.values()), "TRANSPORT_CREDENTIAL")
        self._resolver = resolver
        self._credentials = dict(credentials)
        self._routes = deepcopy(wire.ROUTES)
        self._stop_fence: DispatchFence | None = None
        self._transport = transport

    @property
    def offline_only(self) -> bool:
        return type(self._transport) is httpx.MockTransport

    def _enforce_offline(self) -> None:
        if not self.offline_only:
            live_adapter_unavailable()

    def bind_stop_fence(self, fence: DispatchFence) -> None:
        c.require(self._stop_fence is None, "TRANSPORT_ALREADY_BOUND")
        self._stop_fence = fence

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # The accuracy/approval gate is intentionally absent from this
        # development task; a caller cannot bypass it via this adapter.
        self._enforce_offline()
        try:
            return await self._request(request)
        except Exception as exc:
            if isinstance(exc, c.ContractError) and str(exc) in SAFE_ERRORS:
                raise c.ContractError(str(exc)) from None
            raise c.ContractError("TRANSPORT_FAILURE") from None

    def ensure_request_safe(self, body: bytes) -> None:
        """Reject keys before the controller persists an outgoing body."""
        c.require(
            all(
                _valid_key(key)
                and not _secret_visible(body, key)
                for key in self._credentials.values()
            ),
            "TRANSPORT_SECRET_IN_REQUEST",
        )

    async def _request(self, request: httpx.Request) -> httpx.Response:
        """Verify target/model, pin all-public DNS, then attach only that role's key."""
        self._enforce_offline()
        c.require(self._routes == wire.ROUTES, "TRANSPORT_TARGET")
        matches = [role for role, route in self._routes.items() if str(request.url) == route["url"]]
        c.require(
            request.method == "POST"
            and len(matches) == 1
            and "authorization" not in request.headers
            and "proxy-authorization" not in request.headers,
            "TRANSPORT_TARGET",
        )
        role = matches[0]
        route = self._routes[role]
        body = request.content
        try:
            parsed = wire.strict_json(body)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise c.ContractError("TRANSPORT_REQUEST") from exc
        c.require(type(parsed) is dict and parsed.get("model") == route["model"], "TRANSPORT_MODEL")
        parts = urlsplit(route["url"])
        c.require(
            parts.scheme == "https" and parts.hostname is not None and parts.port in (None, 443)
            and not parts.username and not parts.password and not parts.query and not parts.fragment,
            "TRANSPORT_TARGET",
        )
        assert parts.hostname is not None
        addresses = await self._resolver(parts.hostname, 443)
        self._enforce_offline()
        c.require(self._routes == wire.ROUTES, "TRANSPORT_TARGET")
        c.require(self._stop_fence is None or not self._stop_fence.is_set(), "TRANSPORT_STOPPED")
        c.require(type(addresses) is tuple and bool(addresses), "TRANSPORT_DNS")
        try:
            target = approve_target(
                route["url"], policy=TargetPolicy(), resolver=lambda _host, _port: addresses
            )
        except ValueError as exc:
            raise c.ContractError("TRANSPORT_DNS") from exc
        c.require(target.hostname == parts.hostname and target.port == 443, "TRANSPORT_TARGET")
        key = self._credentials[route["credential_env"]]
        c.require(_valid_key(key), "TRANSPORT_CREDENTIAL")
        self.ensure_request_safe(body)
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        pinned = urlunsplit(("https", f"{host}:443", parts.path, "", ""))
        async with httpx.AsyncClient(
            transport=_DispatchTransport(self._transport, self._stop_fence),
            trust_env=False, follow_redirects=False, timeout=60.0
        ) as client:
            outgoing = client.build_request(
                "POST",
                pinned,
                content=body,
                headers={
                    "Host": target.hostname,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                    "Authorization": "Bearer " + key,
                },
            )
            outgoing.extensions["sni_hostname"] = target.hostname
            self._enforce_offline()
            c.require(self._routes == wire.ROUTES, "TRANSPORT_TARGET")
            c.require(self._stop_fence is None or not self._stop_fence.is_set(), "TRANSPORT_STOPPED")
            response = await client.send(outgoing, stream=True, follow_redirects=False)
            try:
                c.require(
                    response.headers.get("content-encoding", "identity").lower() == "identity",
                    "TRANSPORT_CONTENT_ENCODING",
                )
                content = bytearray()
                async for chunk in response.aiter_raw():
                    remaining = MAX_RESPONSE - len(content)
                    if len(chunk) > remaining:
                        # The prefix could contain part of the secret. Preserve
                        # the unknown reservation, not unverified response bytes.
                        raise c.ContractError("TRANSPORT_RESPONSE_SIZE")
                    content.extend(chunk)
                raw = bytes(content)
                c.require(
                    not any(_secret_visible(raw, secret) for secret in self._credentials.values()),
                    "TRANSPORT_SECRET_ECHO",
                )
                return httpx.Response(response.status_code, stream=httpx.ByteStream(raw))
            finally:
                await response.aclose()

    async def aclose(self) -> None:
        # A controller may make multiple requests with the same offline mock.
        return None


def live_adapter_unavailable() -> None:
    """A self-declared Mock grant is not a real execution authorization."""
    raise c.ContractError("EXACT_LIVE_PACKAGE_AUTHORIZATION_REQUIRED")
