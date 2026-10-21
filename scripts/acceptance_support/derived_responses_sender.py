"""Trusted diagnostic transport composition, unregistered and without an env/key reader.

The caller must independently establish real human run approval, cost proof and consent.
Synthetic tests inject a mock transport and lease; importing this module sends nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field

import httpx

from app.core.provider_target import ProviderTargetGuard, TargetPolicy, TargetValidationError
from app.services.deepseek_responses import _check_status, _result, _wire_target
from app.services.provider_gateway import ProviderError
from app.services.provider_protocol import strict_json

from .claim_review_prototype import encoded
from .derived_diagnostic_budget import HASH, exact, hashed, require
from .phase1_budget import ERRORS, GateFailure

LIMIT = 2 * 1024 * 1024


def reflected(value, key):
    if isinstance(value, str):
        return key in value or re.search(r"sk-[A-Za-z0-9_-]{16,}", value) is not None
    if isinstance(value, dict):
        return any(reflected(k, key) or reflected(v, key) for k, v in value.items())
    if isinstance(value, list):
        return any(reflected(v, key) for v in value)
    return False


@dataclass(frozen=True)
class CredentialLease:
    # Never serialize the lease or include it in an exception/evidence record.
    key: str = field(repr=False)
    reference: str
    version: int
    consent_sha256: str
    root_sha256: str
    expires_at: float


class FrozenResponsesSender:
    """One consume transition, one POST; raw frozen bytes never pass through an SDK.

    An approved DerivedBudget and a trusted current credential/consent lease are inputs,
    not an authentication mechanism. No CLI or production registration is provided.
    """

    def __init__(self, budget, target, *, credentials, resolver=None, transport=None):
        exact(
            target,
            "version base_url model transport credential_ref credential_version consent_sha256",
        )
        require(target["version"] == "derived-deepseek-target-v1", "TARGET_CHANGED")
        require(target["base_url"] == "https://api.deepseek.com", "TARGET_CHANGED")
        require(target["model"] == budget.manifest["target"]["model"], "TARGET_CHANGED")
        require(target["transport"] == "responses_json_schema", "TARGET_CHANGED")
        require(
            type(target["credential_ref"]) is str and bool(target["credential_ref"]),
            "TARGET_CHANGED",
        )
        require(
            type(target["credential_version"]) is int and target["credential_version"] > 0,
            "TARGET_CHANGED",
        )
        require(
            type(target["consent_sha256"]) is str and HASH.fullmatch(target["consent_sha256"]),
            "TARGET_CHANGED",
        )
        require(hashed(target) == budget.manifest["target"]["target_sha256"], "TARGET_CHANGED")
        self.budget = budget
        self.target_bytes = encoded(target)
        self.credentials = credentials
        self.resolver = resolver
        self.transport = transport

    async def send(self, number):
        # This transaction gates every credential read and DNS/HTTP operation. A repeat
        # call fails here, before inspecting its previously consumed byte string.
        wire = self.budget.consume(number)
        digest = None
        observed = {}
        try:
            target = strict_json(self.target_bytes)
            require(
                hashed(target) == self.budget.manifest["target"]["target_sha256"], "TARGET_CHANGED"
            )
            policy = self.budget.manifest["stages"][strict_json(wire)["text"]["format"]["name"]]
            with self.budget._db() as db:
                self.budget._gate(db)
                row = db.execute(
                    "SELECT attempt_deadline FROM children WHERE number=?", (number,)
                ).fetchone()
                remaining = min(
                    row[0] - time.time(), self.budget._attempt_mono[number] - time.monotonic()
                )
            require(remaining > 0, "TIMEOUT")
            async with asyncio.timeout(remaining):
                # Guard DNS with the same whole-attempt deadline, and connect to the
                # approved IP rather than allowing httpx to resolve the host again.
                kwargs = {} if self.resolver is None else {"resolver": self.resolver}
                guard = ProviderTargetGuard(target["base_url"], TargetPolicy(), **kwargs)
                approved = await asyncio.to_thread(guard.approve_base)
                endpoint, host = _wire_target(approved)
                lease = self.credentials()
                require(
                    isinstance(lease, CredentialLease)
                    and lease.reference == target["credential_ref"]
                    and type(lease.version) is int
                    and lease.version == target["credential_version"]
                    and lease.consent_sha256 == target["consent_sha256"]
                    and lease.root_sha256 == self.budget.freeze
                    and type(lease.expires_at) in (int, float)
                    and lease.expires_at > time.time()
                    and type(lease.key) is str
                    and bool(lease.key)
                    and all(32 < ord(c) < 127 for c in lease.key),
                    "SAFETY_FAILURE",
                )
                with self.budget._db() as db:
                    self.budget._gate(db)
                require(
                    time.time() < row[0]
                    and time.monotonic() < self.budget._attempt_mono[number]
                    and lease.expires_at > time.time(),
                    "TIMEOUT",
                )
                transport = self.transport
                if transport is None:
                    transport = httpx.AsyncHTTPTransport(retries=0)
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(remaining),
                ) as client:
                    request = client.build_request(
                        "POST",
                        endpoint,
                        content=wire,
                        headers={
                            "Host": host,
                            "Authorization": "Bearer " + lease.key,
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                        },
                    )
                    request.extensions["sni_hostname"] = approved.hostname
                    require(request.content == wire, "SAFETY_FAILURE")
                    chunks = bytearray()
                    response = await client.send(request, stream=True, follow_redirects=False)
                    try:
                        _check_status(response)
                        # Raw bytes: do not permit a compressed bomb to be inflated first.
                        require(
                            response.headers.get("Content-Encoding", "identity").lower()
                            == "identity",
                            "INVALID_OUTPUT",
                        )
                        async for chunk in response.aiter_raw():
                            require(len(chunks) + len(chunk) <= LIMIT, "INVALID_OUTPUT")
                            chunks.extend(chunk)
                    finally:
                        await response.aclose()
                digest = hashlib.sha256(chunks).hexdigest()
                # Drop the complete observation before it can enter persistent receipts
                # when a vendor reflects either the exact credential or a key-like token.
                require(
                    lease.key.encode() not in chunks
                    and not re.search(rb"sk-[A-Za-z0-9_-]{16,}", chunks),
                    "SAFETY_FAILURE",
                )
                payload = strict_json(bytes(chunks))
                require(not reflected(payload, lease.key), "SAFETY_FAILURE")
                require(type(payload) is dict and not payload.get("error"), "INVALID_OUTPUT")
                usage = payload.get("usage")
                if type(usage) is dict:
                    observed = {k: usage.get(k) for k in ("input_tokens", "output_tokens")}
                    details = usage.get("output_tokens_details")
                    if type(details) is dict:
                        observed["reasoning_tokens"] = details.get("reasoning_tokens")
                # Unexpected tool/refusal/non-message output is never executed or used.
                output = payload.get("output")
                require(
                    type(output) is list
                    and all(
                        type(item) is dict and item.get("type") in ("message", "reasoning")
                        for item in output
                    ),
                    "INVALID_OUTPUT",
                )
                result = _result(payload)
                require(
                    result.output_text_counts is not None
                    and result.output_text_counts.messages == 1
                    and result.output_text_counts.blocks == 1,
                    "INVALID_OUTPUT",
                )
                value = strict_json(result.text)
                require(len(encoded(value)) <= policy["max_result_bytes"], "RESULT_TOO_LARGE")
                usage = payload.get("usage")
                require(type(usage) is dict, "INVALID_OUTPUT")
                details = usage.get("output_tokens_details")
                require(details is None or type(details) is dict, "INVALID_OUTPUT")
                reasoning = None if details is None else details.get("reasoning_tokens")
                self.budget.finish(
                    number,
                    value=value,
                    model=result.model_id,
                    status=payload.get("status"),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    reasoning_tokens=reasoning,
                    response_sha256=digest,
                )
                return {"number": number, "response_sha256": digest, "completed": True}
        except BaseException as exc:
            if isinstance(exc, GateFailure):
                code = exc.code if exc.code in ERRORS else "SAFETY_FAILURE"
            elif isinstance(exc, ProviderError):
                code = exc.code.value if exc.code.value in ERRORS else "TARGET_CHANGED"
            elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                code = "TIMEOUT"
            elif isinstance(exc, TargetValidationError):
                code = "TARGET_CHANGED"
            elif isinstance(exc, httpx.RequestError):
                code = "TEMPORARILY_UNAVAILABLE"
            else:
                code = "SAFETY_FAILURE"
            # finish() may already have halted persistently; preserve that first cause.
            try:
                self.budget.abort(number, error_code=code, response_sha256=digest, **observed)
            except GateFailure:
                pass
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise GateFailure(code) from None
