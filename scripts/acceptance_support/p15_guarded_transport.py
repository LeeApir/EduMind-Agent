"""Offline-only guarded diagnostic version. No live runner or authority inheritance.

Response echoes can expose contradictions, never prove a provider's actual context or
hard limits. Real transports remain disabled until those preflight proofs and a new
exact execution package are separately established.
"""

import hashlib
import ipaddress
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
from acceptance_support.p15_diagnostic_ledger import Refused
from acceptance_support.p15_diagnostic_transport import MAX_BYTES, redact_check
from acceptance_support.p15_strict_transport import StrictDiagnosticAdapter

VERSION = "p15-guarded-wire-v1-offline"


class GuardedWireTransport(httpx.AsyncBaseTransport):
    def __init__(self, underlying, output, key):
        if type(underlying) is not httpx.MockTransport:
            raise Refused("LIVE_TRANSPORT_REQUIRES_INDEPENDENT_PREFLIGHT_PROOF")
        self.underlying = underlying
        self.output = Path(output)
        self.output.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.output.is_symlink() or self.output.stat().st_mode & 0o077:
            raise Refused("PRIVATE_EVIDENCE_DIRECTORY_REQUIRED")
        self.key = key
        self.count = None
        self.body = None
        self.model_sent = False

    async def aclose(self):
        await self.underlying.aclose()

    def save(self, identity, suffix, raw):
        # A failed durable write must propagate before a response can be admitted.
        path = self.output / (identity + suffix)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def event(self, identity, suffix, **data):
        self.save(
            identity,
            suffix + ".json",
            json.dumps(
                dict(version=VERSION, **data), sort_keys=True, separators=(",", ":")
            ).encode(),
        )

    async def handle_async_request(self, request):
        identity = uuid4().hex
        reason = "TRANSPORT_OR_EVIDENCE_FAILURE"
        try:
            try:
                pinned_public = ipaddress.ip_address(request.url.host).is_global
            except ValueError:
                pinned_public = False
            allowed_host = request.url.host == "www.cbbb.fun" or (
                pinned_public
                and request.headers.get("host") == "www.cbbb.fun"
                and request.extensions.get("sni_hostname") == "www.cbbb.fun"
            )
            if (
                request.method != "POST"
                or request.url.scheme != "https"
                or not allowed_host
                or request.url.port not in (None, 443)
                or request.url.path not in ("/v1/responses", "/v1/responses/input_tokens")
                or request.url.query
                or request.url.userinfo
            ):
                raise Refused("UNFROZEN_ENDPOINT")
            redact_check(request.content, self.key)
            body = json.loads(request.content)
            counting = request.url.path.endswith("/input_tokens")
            if counting:
                if self.body is not None:
                    raise Refused("DUPLICATE_COUNT_REQUEST")
                self.body = request.content
            elif self.body != request.content or self.count is None or self.model_sent:
                raise Refused("COUNT_REQUEST_BINDING_MISSING")
            if not counting:
                self.model_sent = True
            self.event(
                identity,
                "-send",
                method="POST",
                origin="https://www.cbbb.fun",
                path=request.url.path,
                body_sha256=hashlib.sha256(request.content).hexdigest(),
                body_bytes=len(request.content),
            )
            response = await self.underlying.handle_async_request(request)
            status = response.status_code
            raw = bytearray()
            try:
                self.event(identity, "-status", http_status=status)
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise Refused("RESPONSE_TOO_LARGE")
            finally:
                await response.aclose()
            raw = bytes(raw)
            redact_check(raw, self.key)
            # Safe raw failure evidence is durable before parsing or validation.
            self.save(identity, "-body.json", raw)
            self.event(
                identity,
                "-received",
                http_status=status,
                response_sha256=hashlib.sha256(raw).hexdigest(),
                response_bytes=len(raw),
            )
            if status != 200:
                raise Refused("HTTP_STATUS_UNVERIFIED")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise Refused("RESPONSE_OBJECT_REQUIRED")
            if counting:
                value = payload.get("input_tokens")
                if (
                    payload.get("object") != "response.input_tokens"
                    or type(value) is not int
                    or not 0 < value <= 32000
                ):
                    raise Refused("INPUT_BOUND_UNVERIFIED")
                self.count = value
            else:
                issues = self.check_response(body, payload)
                if issues:
                    self.event(identity, "-rejected", issues=issues)
                    raise Refused("RESPONSE_INTEGRITY_UNVERIFIED")
            return httpx.Response(status, content=raw, request=request)
        except BaseException as exc:
            # Never serialize arbitrary exception text: it may contain credentials.
            if isinstance(exc, Refused) and str(exc) in {
                "UNFROZEN_ENDPOINT",
                "DUPLICATE_COUNT_REQUEST",
                "COUNT_REQUEST_BINDING_MISSING",
                "RESPONSE_TOO_LARGE",
                "HTTP_STATUS_UNVERIFIED",
                "RESPONSE_OBJECT_REQUIRED",
                "INPUT_BOUND_UNVERIFIED",
                "RESPONSE_INTEGRITY_UNVERIFIED",
                "CREDENTIAL_ECHO",
            }:
                reason = str(exc)
            elif isinstance(exc, (ValueError, UnicodeError)):
                reason = "MALFORMED_RESPONSE"
            self.event(identity, "-failure", reason=reason)
            raise

    def check_response(self, request, response):
        expected = "\n\n".join(m["content"] for m in request["input"] if m["role"] == "system")
        issues = []
        if response.get("instructions") != expected:
            issues.append("INSTRUCTIONS_UNVERIFIED")
        if response.get("max_output_tokens") != request["max_output_tokens"]:
            issues.append("OUTPUT_LIMIT_UNVERIFIED")
        text = response.get("text")
        fmt = text.get("format") if isinstance(text, dict) else None
        if (
            not isinstance(fmt, dict)
            or any(
                fmt.get(k) != request["text"]["format"].get(k) for k in ("type", "name", "schema")
            )
            or fmt.get("strict") is not True
        ):
            issues.append("SCHEMA_UNVERIFIED")
        if response.get("status") != "completed" or response.get("error") is not None:
            issues.append("RESPONSE_NOT_COMPLETE")
        usage = response.get("usage")
        if (
            not isinstance(usage, dict)
            or type(usage.get("input_tokens")) is not int
            or usage["input_tokens"] != self.count
        ):
            issues.append("INPUT_COUNT_MISMATCH")
        # The frozen outer transport still enforces model, output usage and durable limits.
        return issues


class GuardedStrictDiagnosticAdapter(StrictDiagnosticAdapter):
    """New explicit composition; unchanged strict/local schema validation and PG Reply."""

    def __init__(self, settings, guard, ledger, batch, package, output, transport_factory):
        def factory():
            return GuardedWireTransport(
                transport_factory(), Path(output) / "audit", settings.api_key
            )

        super().__init__(settings, guard, ledger, batch, package, output, factory)
