"""Full diagnostic r05 draft. Exact scope/window approval required before live use."""

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
from acceptance_support.p15_candidate_compatibility import evidence, parse, redact_check
from acceptance_support.p15_diagnostic_ledger import Ledger, Refused, digest
from app.core.config import ProviderSettings
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.free_course_scheduler import Reply, SendPolicy
from app.services.provider_gateway import ProviderError
from isolated_diagnostics import p15_split_provider as prior
from isolated_diagnostics import p15_review_observability as compat
from acceptance_support.p15_diagnostic_execution import PROBE_PROMPT
from isolated_diagnostics.p15_course_sol_bridge import review_request
from isolated_diagnostics.p15_full_slot_r05 import run_slot
from isolated_diagnostics.p15_full_observation_r05 import checked_record


@dataclass(frozen=True)
class ExplorationLimits:
    requests: int = 250
    input_tokens: None = None
    output_tokens: None = None
    fee_micros: None = None
    wall_seconds: int = 10800

    def validate(self):
        if self != ExplorationLimits():
            raise Refused("EXPLORATION_LIMITS_CHANGED")


class ExplorationLedger(Ledger):
    """Count requests/time; expose all returned usage even for rejected responses."""

    def guard(self, batch, package):
        row = self.db.execute(
            "SELECT body FROM receipts WHERE batch=? AND kind='new_window' ORDER BY seq LIMIT 1",
            (batch,),
        ).fetchone()
        if row:
            end = parse(row[0]).get("deadline_epoch")
            if end is not None and self.clock()[0] >= end:
                self.stop(batch, "EXPLICIT_WINDOW_EXPIRED")
                raise Refused("EXPLICIT_WINDOW_EXPIRED")
        return super().guard(batch, package)

    def record(self, batch, kind, body, attempt=None):
        if kind == "human_review":
            if (
                body.get("review_type") != "delegated_assistant"
                or body.get("independent_human_truth") is not False
            ):
                raise Refused("DELEGATED_ASSISTANT_PROVENANCE_REQUIRED")
            kind = "assistant_review"
        return super().record(batch, kind, body, attempt)

    def usage(self, batch):
        rows = self.db.execute(
            "SELECT * FROM attempts WHERE batch=?", (batch,)
        ).fetchall()
        observed = [
            parse(r[0])
            for r in self.db.execute(
                "SELECT body FROM receipts WHERE batch=? AND kind='unbounded_usage_observed' ORDER BY seq",
                (batch,),
            )
        ]
        reported_input = sum(r["input_tokens"] for r in observed)
        reported_output = sum(r["output_tokens"] for r in observed)
        return {
            "prior_requests": 14,
            "workflow_requests": 14 + len(rows),
            "reported_all_responses_input": reported_input,
            "reported_all_responses_output": reported_output,
            "workflow_reported_input": 81890 + reported_input,
            "workflow_reported_output": 14958 + reported_output,
            "requests": len(rows),
            "input_tokens": sum(r["input_used"] or 0 for r in rows),
            "output_tokens": sum(r["output_used"] or 0 for r in rows),
            "fee_micros": None,
            "unknown_usage_requests": sum(r["input_used"] is None for r in rows),
        }

    def settle(
        self,
        batch,
        attempt,
        *,
        outcome,
        proof_sha256=None,
        input_used=None,
        output_used=None,
        fee_used=None,
    ):
        with self.transaction():
            row = self.db.execute(
                "SELECT * FROM attempts WHERE batch=? AND id=?", (batch, attempt)
            ).fetchone()
            if row is None or row["state"] not in ("sent", "unknown"):
                raise Refused("SETTLEMENT_CONFLICT")
            if outcome == "unknown":
                self.db.execute(
                    "UPDATE attempts SET state='unknown' WHERE batch=? AND id=?",
                    (batch, attempt),
                )
                self.stop(batch, "UNKNOWN_SEND")
                self.record(batch, "unknown", {"actual_fee_micros": None}, attempt)
                return
            if outcome != "complete" or not re.fullmatch(
                "[a-f0-9]{64}", proof_sha256 or ""
            ):
                raise Refused("VERIFIED_RESPONSE_REQUIRED")
            if any(type(v) is not int or v < 0 for v in (input_used, output_used)):
                raise Refused("REPORTED_USAGE_REQUIRED")
            self.db.execute(
                "UPDATE attempts SET state='complete',input_used=?,output_used=? WHERE batch=? AND id=?",
                (input_used, output_used, batch, attempt),
            )
            self.record(
                batch,
                "settled_observation",
                {
                    "proof_sha256": proof_sha256,
                    "reported_input": input_used,
                    "reported_output": output_used,
                    "actual_fee_micros": None,
                    "bounds_verified": False,
                },
                attempt,
            )


class ExplorationJournal(prior.Journal):
    def __init__(self, ledger, batch, package, output):
        if not batch.startswith("p15-split-experiment-"):
            raise Refused("NEW_EXPERIMENT_BATCH_REQUIRED")
        self.ledger, self.batch, self.package, self.output = (
            ledger,
            batch,
            package,
            Path(output),
        )

    @classmethod
    def create(cls, output, batch, package, grant, *, clock=None):
        output = Path(output)
        output.mkdir(mode=0o700, exist_ok=False)
        ledger = ExplorationLedger(output / "ledger.sqlite", clock=clock)
        try:
            ledger.start(
                batch,
                package,
                ExplorationLimits(),
                grant,
                pinned_approval_sha256=digest(grant),
            )
            j = cls(ledger, batch, package, output)
            j.record(
                "new_window",
                {
                    "deadline_epoch": grant.get("window_deadline_epoch"),
                    "old_deadline_not_extended": True,
                    "prior_requests": 14,
                },
            )
            j.record(
                "explicit_exception",
                {
                    "adr": "ADR-0034",
                    "verified_input_bound": None,
                    "verified_output_bound": None,
                    "actual_fee_cap": None,
                    "human_review_waived": False,
                    "production_admission": False,
                },
            )
            for path in output.glob("ledger.sqlite*"):
                os.chmod(path, 0o600)
            return j
        except BaseException:
            ledger.close()
            raise

    def require_reviews_complete(self, identity):
        if not getattr(self, "_failure_import", False):
            return super().require_reviews_complete(identity)
        self.guard(allow_pause=True)
        self.require_identity(identity)
        if not self.sources(identity):
            raise Refused("SCENE_SET_NOT_FROZEN")
        # Only a failing report reaches this path; the inherited importer halts it.
        # Missing scene reviews remain explicitly missing, never fabricated as pass.


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
                elif self.stage == "development_review_probe":
                    slots = j.events("planned_slots")
                    selected = (
                        [
                            s
                            for s in slots[0]["slots"]
                            if s["slot_id"] == self.identity.slot_id
                        ]
                        if len(slots) == 1
                        else []
                    )
                    if (
                        len(selected) != 1
                        or selected[0]["kind"] != "probe"
                        or body["input"]
                        != [
                            {"role": "system", "content": PROBE_PROMPT},
                            {"role": "user", "content": selected[0]["content"]},
                        ]
                    ):
                        raise Refused("EXACT_PROBE_CONTENT_WITHOUT_GOLD_REQUIRED")
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


async def run_experimental_slot(slot, sessions, adapter):
    j = adapter.journal
    identity = prior.Identity(
        slot["slot_id"],
        str(uuid5(NAMESPACE_URL, j.batch + "/" + slot["slot_id"])),
        "EXPERIMENT_PENDING_COURSE",
    )
    j.bind(identity)
    result = await run_slot(
        slot, sessions, adapter.bound(identity), j.ledger, j.batch, j.package
    )
    if slot["kind"] != "course":
        j.freeze(identity, [])
        return result
    plans = result["tables"].get("free_course_plans", [])
    if not result["engineering_pass"] or not plans:
        return result
    actual = prior.Identity(
        identity.slot_id + ":scene-review",
        identity.owner_id,
        str(plans[0]["course_id"]),
    )
    j.bind(actual)
    targets = await prior.load_targets(sessions, actual)
    j.freeze(actual, targets)

    async def current(target):
        return target in await prior.load_targets(sessions, actual)

    state = await review_pending(adapter, actual, verify_current=current)
    return {
        **result,
        "scene_review_identity": actual.packed(),
        "scene_source_hashes": [v["payload"]["source_sha256"] for v in targets],
        "scene_review_state_at_first_observation": state,
        "experimental_unbounded_admission": True,
        "production_bound_evidence": False,
    }


# Same exact scene/quote/manual rules, with truthful live labels instead of Mock labels.
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
