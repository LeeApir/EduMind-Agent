"""ADR0040 final D02 wire proposal. Exact approval required; no production admission."""

import asyncio
import hashlib
import json
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from acceptance_support.p15_candidate_compatibility import evidence, parse, redact_check
from acceptance_support.p15_diagnostic_ledger import Refused, digest
from app.core.config import ProviderSettings
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.free_course_scheduler import Reply, SendPolicy
from app.services.provider_gateway import ProviderError
from isolated_diagnostics import p15_split_provider as prior
from isolated_diagnostics import p15_review_turn_metadata as compat
from isolated_diagnostics.p15_course_sol_bridge import review_request
from isolated_diagnostics.p15_d02_observation_d02 import checked_record


from isolated_diagnostics.p15_full_exploration_r05 import (
    ExplorationJournal as ExplorationJournal,
    ExplorationLedger as ExplorationLedger,
)


class RecordedExploration(httpx.AsyncBaseTransport):
    def __init__(self, adapter, identity, stage, role, target, transport):
        self.adapter, self.j, self.identity = adapter, adapter.journal, identity
        self.stage, self.role, self.target, self.transport = (
            stage,
            role,
            target,
            transport,
        )
        self.proof, self.usage, self.opinion = None, None, None

    async def handle_async_request(self, request):
        j, a = self.j, self.adapter
        if self.stage not in (
            "free_course_plan_generation",
            "free_scene_generation",
            "development_scene_review",
        ):
            raise Refused("FINAL_D02_STAGE_REQUIRED")
        route = a.policy_data["providers"][self.role]
        endpoint = urlsplit(route["url"])
        if (
            request.url.host not in self.target.addresses
            or request.url.path != endpoint.path
            or request.url.scheme != "https"
            or request.headers.get("host") != endpoint.hostname
            or request.extensions.get("sni_hostname") != endpoint.hostname
        ):
            raise Refused("PINNED_WIRE_TARGET_CHANGED")
        raw = request.content
        for key in a.keys.values():
            redact_check(raw, key)
        body = parse(raw)
        cap = body.get("max_output_tokens")
        if (
            body.get("model") != route["model"]
            or body.get("stream") is not False
            or body.get("reasoning")
            != {"effort": "low" if self.role == "review" else "none"}
            or type(cap) is not int
            or not 1 <= cap <= 8000
            or len(raw) > 131072
        ):
            raise Refused("REQUEST_OUTSIDE_FROZEN_SCOPE")
        ticket = digest(
            {
                "identity": self.identity.packed(),
                "stage": self.stage,
                "request_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        with j.reservation_lock():
            j.guard()
            calls = j.events("live_dispatch_reserved")
            if j.ledger.db.execute(
                "SELECT 1 FROM attempts WHERE batch=? AND state IN ('reserved','sent','unknown')",
                (j.batch,),
            ).fetchone():
                raise Refused("PENDING_OR_UNKNOWN_CALL_NO_RESEND")
            own = [v for v in calls if v["provider"] == self.role]
            if len(own) >= (182 if self.role == "generation" else 68):
                raise Refused("ROLE_REQUEST_LIMIT")
            if (
                self.role == "generation"
                and sum(v["identity"] == self.identity.packed() for v in own) >= 13
            ):
                raise Refused("COURSE_REQUEST_LIMIT")
            if (
                self.stage == "development_review_probe"
                and sum(v["stage"] == self.stage for v in calls) >= 20
            ):
                raise Refused("PROBE_REQUEST_LIMIT")
            # Zero means no token/currency reservation in this expressly waived ledger.
            j.ledger.reserve(
                j.batch, j.package, ticket, input_max=0, output_max=0, fee_max=0
            )
            j.record(
                "live_dispatch_reserved",
                {
                    "ticket": ticket,
                    "provider": self.role,
                    "stage": self.stage,
                    "identity": self.identity.packed(),
                    "request_sha256": hashlib.sha256(raw).hexdigest(),
                    "requested_output_tokens": cap,
                    "verified_bound": False,
                },
            )
            evidence(j.output / f"{ticket}-request.json", raw)
            j.ledger.mark_sent(j.batch, j.package, ticket)
        try:
            response = await self.transport.handle_async_request(request)
            evidence(
                j.output / f"{ticket}-status.json",
                {"http_status": response.status_code},
            )
            content = bytearray()
            try:
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2097152:
                        raise Refused("RESPONSE_TOO_LARGE")
            finally:
                await response.aclose()
            response_raw = bytes(content)
            for key in a.keys.values():
                redact_check(response_raw, key)
            evidence(j.output / f"{ticket}-response.json", response_raw)
            payload = parse(response_raw)
            if (
                response.status_code != 200
                or not isinstance(payload, dict)
                or payload.get("status") != "completed"
                or payload.get("model") != route["model"]
                or payload.get("error") is not None
                or payload.get("store") is not False
                or payload.get("tools") not in (None, [])
            ):
                raise Refused("RESPONSE_PROTOCOL_FAILED")
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                raise Refused("REPORTED_USAGE_REQUIRED")
            inp, out, total = [
                usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
            ]
            if (
                not all(type(n) is int and n >= 0 for n in (inp, out, total))
                or total != inp + out
            ):
                raise Refused("REPORTED_USAGE_INVALID")
            j.record(
                "unbounded_usage_observed",
                {
                    "ticket": ticket,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "requested_output_tokens": cap,
                    "reported_over_request": out > cap,
                    "actual_fee_micros": None,
                },
            )
            if self.role == "review":
                if self.stage == "development_scene_review":
                    submitted = parse(body["input"][-1]["content"])
                    expected_body = review_request(self.stage, submitted)
                    if (
                        body["input"] != expected_body["input"]
                        or body.get("text", {}).get("format", {}).get("schema")
                        != compat.schema()
                        or body.get("text", {}).get("format", {}).get("strict")
                        is not True
                    ):
                        raise Refused("EXACT_V2_REVIEW_REQUEST_REQUIRED")
                else:
                    raise Refused("UNKNOWN_REVIEW_STAGE")
                planned = j.events("planned_slots")
                self.opinion, observation = checked_record(
                    raw,
                    response_raw,
                    stage=self.stage,
                    identity=self.identity.packed(),
                    ticket=ticket,
                    slots=planned[0]["slots"] if len(planned) == 1 else [],
                )
                j.record("review_protocol_observation", observation)
            else:
                details = usage.get("output_tokens_details")
                if details is not None and (
                    not isinstance(details, dict)
                    or details.get("reasoning_tokens", 0) != 0
                ):
                    raise Refused("UNEXPECTED_REASONING")
                if not isinstance(payload.get("output"), list) or any(
                    not isinstance(i, dict) or i.get("type") != "message"
                    for i in payload["output"]
                ):
                    raise Refused("UNREQUESTED_OUTPUT_TYPE")
                expected = "\n\n".join(
                    m["content"] for m in body["input"] if m["role"] == "system"
                )
                if payload.get("instructions") not in (None, expected):
                    raise Refused("INSTRUCTIONS_CHANGED")
            self.proof = hashlib.sha256(response_raw).hexdigest()
            self.usage = (inp, out)
            j.ledger.settle(
                j.batch,
                ticket,
                outcome="complete",
                proof_sha256=self.proof,
                input_used=inp,
                output_used=out,
            )
            j.guard()
            return httpx.Response(200, content=response_raw, request=request)
        except BaseException:
            row = j.ledger.db.execute(
                "SELECT state FROM attempts WHERE batch=? AND id=?", (j.batch, ticket)
            ).fetchone()
            if row and row["state"] == "sent":
                j.ledger.settle(j.batch, ticket, outcome="unknown")
            j.ledger.halt(j.batch, "provider_contract_failure")
            raise

    async def aclose(self):
        pass


class ExplorationAdapter:
    """Bound flags stay FALSE. Only ExperimentalScheduler admits this explicit exception."""

    def __init__(self, journal, keys, target_factory, transport_factory):
        self.journal, self.keys = journal, dict(keys)
        self.policy_data = prior.approved_design()
        self.policy_data["stages"]["development_scene_review"]["schema_sha256"] = (
            digest(compat.schema())
        )
        self.policy_data["providers"]["review"]["reasoning"] = "low"
        self.target_factory, self.transport_factory = target_factory, transport_factory
        if set(keys) != {"generation", "review"} or len(set(keys.values())) != 2:
            raise Refused("DISTINCT_PROVIDER_KEYS_REQUIRED")
        self._configuration = digest(
            {
                "policy": self.policy_data,
                "key_hashes": {
                    k: hashlib.sha256(v.encode()).hexdigest()
                    for k, v in self.keys.items()
                },
            }
        )

    def bound(self, identity):
        self.journal.bind(identity)
        adapter = self

        class Bound(ExplorationAdapter):
            policy = SendPolicy(
                package_id=adapter.journal.batch,
                requests=250,
                bounded_output_verified=False,
            )

            async def send(self, request, *, retry_safe):
                return await adapter.send(identity, request, retry_safe=retry_safe)

            def input_upper_bound(self, request):
                raise Refused("NO_VERIFIED_INPUT_BOUND")

        return Bound.__new__(Bound)

    async def send(self, identity, request, *, retry_safe):
        self.journal.guard()
        self.journal.require_identity(identity)
        if retry_safe is not False:
            raise Refused("RETRY_FORBIDDEN")
        if (
            digest(
                {
                    "policy": self.policy_data,
                    "key_hashes": {
                        k: hashlib.sha256(v.encode()).hexdigest()
                        for k, v in self.keys.items()
                    },
                }
            )
            != self._configuration
        ):
            raise Refused("CONFIGURATION_CHANGED")
        try:
            prior.design.route(
                self.policy_data, request.stage, digest(dict(request.json_schema))
            )
        except ValueError:
            raise Refused("STAGE_OR_SCHEMA_NOT_FROZEN") from None
        role = self.policy_data["stages"][request.stage]["provider"]
        route = self.policy_data["providers"][role]
        if request.stage == "development_scene_review":
            submitted = parse(request.prompt.messages[-1].content)
            if not any(
                v["payload"] == submitted for v in self.journal.sources(identity)
            ):
                raise Refused("EXACT_FROZEN_REVIEW_SOURCE_REQUIRED")
            if not any(
                v["identity"] == identity.packed()
                and v["source_sha256"] == submitted["source_sha256"]
                for v in self.journal.events("scene_review_started")
            ):
                raise Refused("SCENE_REVIEW_START_REQUIRED")
        windows = self.journal.events("new_window")
        deadline = windows[0].get("deadline_epoch") if windows else None
        seconds = (
            min(120, deadline - self.journal.ledger.clock()[0])
            if deadline is not None
            else 120
        )
        if seconds <= 0:
            raise Refused("EXPLICIT_WINDOW_EXPIRED")
        async with asyncio.timeout(seconds):
            target = await asyncio.to_thread(self.target_factory, role)
            endpoint = route["url"].removesuffix("/responses")
            if (
                target.url != endpoint
                or target.hostname != urlsplit(endpoint).hostname
                or target.port != 443
            ):
                raise Refused("APPROVED_TARGET_CHANGED")
            transport = self.transport_factory()
            wire = RecordedExploration(
                self, identity, request.stage, role, target, transport
            )

            class Adapter(DeepSeekResponsesAdapter):
                async def _response(self, body):
                    if role == "review":
                        body["store"] = False
                        body["text"]["format"]["strict"] = True
                    return await super()._response(body)

            gateway = Adapter(
                ProviderSettings(endpoint, self.keys[role], route["model"]),
                SimpleNamespace(approve_base=lambda: target),
                transport=wire,
                reasoning_effort="low" if role == "review" else "none",
            )
            try:
                try:
                    result = await gateway.generate_structured(request)
                except ProviderError:
                    if wire.proof and wire.usage:
                        if role == "review" and wire.opinion is not None:
                            return Reply(
                                "complete_response",
                                wire.proof,
                                wire.opinion,
                                *wire.usage,
                            )
                        return Reply("complete_response", wire.proof, {}, *wire.usage)
                    raise Refused("UNVERIFIED_PROVIDER_RESULT") from None
                if not wire.proof or not wire.usage:
                    raise Refused("MISSING_EXACT_RESPONSE_PROOF")
                return Reply("complete_response", wire.proof, result.value, *wire.usage)
            finally:
                await transport.aclose()


async def review_pending(router, identity, *, verify_current):
    j = router.journal
    for target in j.sources(identity):
        key = target["payload"]["source_sha256"]
        if key in {
            v["source_sha256"]
            for v in j.events("scene_review_finished")
            if v["identity"] == identity.packed()
        }:
            continue
        with j.ledger.transaction():
            j.guard()
            if key in {
                v["source_sha256"]
                for v in j.events("scene_review_started")
                if v["identity"] == identity.packed()
            }:
                raise Refused("INTERRUPTED_REVIEW_NO_RESEND")
            j.record(
                "scene_review_started",
                {"source_sha256": key, "identity": identity.packed()},
            )
        try:
            if await verify_current(target) is not True:
                raise Refused("SOURCE_NO_LONGER_CURRENT")
            request = prior.StructuredRequest(
                prior.TextRequest(
                    (
                        prior.ChatMessage(
                            "system",
                            (compat.BASE / "scene-review-prompt.txt").read_text(),
                        ),
                        prior.ChatMessage(
                            "user",
                            json.dumps(
                                target["payload"], ensure_ascii=False, sort_keys=True
                            ),
                        ),
                    ),
                    max_output_tokens=8000,
                ),
                compat.schema(),
                "development_scene_review",
            )
            reply = await router.send(identity, request, retry_safe=False)
            if await verify_current(target) is not True:
                raise Refused("SOURCE_CHANGED_DURING_REVIEW")
            if isinstance(reply.value, dict) and any(
                re.search(r"~(?![01])", str(v.get("source_pointer", "")))
                for v in reply.value.get("issues", [])
                if isinstance(v, dict)
            ):
                raise Refused("INVALID_JSON_POINTER_ESCAPE")
            verdict = prior.design.validate_opinion(target["payload"], reply.value)
            opinion = {
                "source_sha256": key,
                "identity": identity.packed(),
                "opinion": reply.value,
                "response_sha256": reply.evidence_digest,
                "mock_only": False,
            }
            j.record("scene_review_finished", opinion)
            if verdict != "pass":
                j.record(
                    "scene_advisory_pause",
                    {
                        "source_sha256": key,
                        "identity": identity.packed(),
                        "verdict": verdict,
                    },
                )
                return "paused_for_delegated_assistant"
        except BaseException:
            j.ledger.halt(j.batch, "provider_contract_failure")
            raise
    j.require_reviews_complete(identity)
    return "live_reviews_complete"
