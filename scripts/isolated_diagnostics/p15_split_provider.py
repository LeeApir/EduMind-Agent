"""ADR0033 isolated orchestration: explicit MockTransport only; never live authority.

Kept outside historical acceptance_support glob freezes so prior receipts remain verifiable.
"""

import asyncio
import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

import check_p15_split_provider_design as design
import httpx
from acceptance_support.p15_candidate_compatibility import evidence, parse, redact_check
from acceptance_support.p15_diagnostic_execution import Execution, run_slot
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest

from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.free_course_scheduler import Reply, SendPolicy
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    TextRequest,
)

ROOT, BASE = design.ROOT, design.BASE
SCENE_SCHEMA = parse((BASE / "scene-review.schema.json").read_bytes())
SCENE_PROMPT = (BASE / "scene-review-prompt.txt").read_text()
MOCK_LIMITS = Limits(250, 4976000, 1216000, 20000000, 10800)


def approved_design():
    design.check()
    manifest_sha = hashlib.sha256((BASE / "manifest.json").read_bytes()).hexdigest()
    grant = parse((ROOT / "docs/ADR/0033-approval-20261027.json").read_bytes())
    if (
        grant.get("design_manifest_sha256") != manifest_sha
        or grant.get("decisions") != ["A", "B", "C", "E"]
        or grant.get("real_requests_authorized") != 0
        or not grant.get("human_message")
        or not grant.get("evidence_ref")
    ):
        raise Refused("EXACT_OFFLINE_DESIGN_APPROVAL_REQUIRED")
    return parse((BASE / "policy.json").read_bytes())


def refuse_live():
    # Must precede credentials, DNS, database setup and real output creation.
    raise Refused("ADR0033_D_INPUT_OUTPUT_BOUNDS_UNVERIFIED_NO_LIVE_AUTHORITY")


@dataclass(frozen=True)
class Identity:
    slot_id: str
    owner_id: str
    course_id: str

    def packed(self):
        if not self.slot_id or not self.owner_id or not self.course_id:
            raise Refused("IDENTITY_REQUIRED")
        return {
            "slot_id": self.slot_id,
            "owner_id": self.owner_id,
            "course_id": self.course_id,
        }


class Journal:
    """Append-only private diagnostic receipts. All token/fee settlements are simulated."""

    def __init__(self, ledger: Ledger, batch: str, package: str, output: Path):
        if not batch.startswith("TEST_ONLY_SPLIT_"):
            raise Refused("MOCK_ONLY_BATCH_REQUIRED")
        self.ledger, self.batch, self.package, self.output = (
            ledger,
            batch,
            package,
            Path(output),
        )

    @classmethod
    def create_mock(cls, output, *, batch="TEST_ONLY_SPLIT_RUN", clock=None):
        policy = approved_design()
        if not batch.startswith("TEST_ONLY_SPLIT_"):
            raise Refused("MOCK_ONLY_BATCH_REQUIRED")
        output = Path(output)
        output.mkdir(mode=0o700, exist_ok=False)
        ledger = Ledger(output / "ledger.sqlite", clock=clock)
        source_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        package = digest(
            {"mock_only": True, "design": policy, "implementation_sha256": source_sha}
        )
        grant = {
            "package_sha256": package,
            "batch_id": batch,
            "limits": MOCK_LIMITS.__dict__,
            "scope": "PHASE-1.5-T038",
            "evidence_ref": "SYNTHETIC_OFFLINE_FIXTURE_NOT_LIVE_APPROVAL",
        }
        try:
            ledger.start(
                batch, package, MOCK_LIMITS, grant, pinned_approval_sha256=digest(grant)
            )
            ledger.record(
                batch,
                "mock_only_scope",
                {
                    "actual_provider_calls": 0,
                    "invoice_verified": False,
                    "implementation_sha256": source_sha,
                },
            )
            for file in output.glob("ledger.sqlite*"):
                os.chmod(file, 0o600)
        except BaseException:
            ledger.close()
            raise
        return cls(ledger, batch, package, output)

    def events(self, kind):
        return [
            parse(r[0])
            for r in self.ledger.db.execute(
                "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                (self.batch, kind),
            )
        ]

    def record(self, kind, body):
        self.ledger.record(self.batch, kind, body)

    @contextmanager
    def reservation_lock(self):
        fd = os.open(self.output / "mock-send.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused("CONCURRENT_MOCK_EXECUTOR") from None
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def bind(self, identity):
        values = identity.packed()
        with self.ledger.transaction():
            self.guard()
            existing = [
                v
                for v in self.events("slot_identity")
                if v["slot_id"] == identity.slot_id
            ]
            if existing and existing != [values]:
                raise Refused("OWNER_COURSE_SLOT_MISMATCH")
            if not existing:
                self.record("slot_identity", values)

    def guard(self, *, allow_pause=False):
        self.ledger.guard(self.batch, self.package)
        if not allow_pause:
            resolutions = {
                (digest(v["identity"]), v["source_sha256"])
                for v in self.events("scene_false_alarm_adjudicated")
            }
            if any(
                (digest(v["identity"]), v["source_sha256"]) not in resolutions
                for v in self.events("scene_advisory_pause")
            ):
                raise Refused("SCENE_ADVISORY_REQUIRES_HUMAN")

    def require_identity(self, identity):
        if identity.packed() not in self.events("slot_identity"):
            raise Refused("OWNER_COURSE_SLOT_MISMATCH")

    def freeze(self, identity, targets):
        with self.ledger.transaction():
            self.guard()
            self.require_identity(identity)
            if any(
                v["slot_id"] == identity.slot_id
                for v in self.events("scene_set_frozen")
            ):
                raise Refused("SCENE_SET_ALREADY_FROZEN")
            if (
                len(targets) > 8
                or len(self.events("scene_source_frozen")) + len(targets) > 48
            ):
                raise Refused("SCENE_REVIEW_LIMIT")
            ids = [v["scene_id"] for v in targets]
            if len(set(ids)) != len(ids):
                raise Refused("DUPLICATE_SCENE")
            for target in targets:
                if target["identity"] != identity.packed() or target["payload"][
                    "source_sha256"
                ] != design.digest(target["payload"]["source"]):
                    raise Refused("SOURCE_BINDING_CHANGED")
                self.record("scene_source_frozen", target)
            self.record("scene_set_frozen", {**identity.packed(), "scene_ids": ids})

    def sources(self, identity):
        self.require_identity(identity)
        return [
            v
            for v in self.events("scene_source_frozen")
            if v["identity"] == identity.packed()
        ]

    def review_checkpoint(self, identity):
        self.require_identity(identity)
        keys = {v["payload"]["source_sha256"] for v in self.sources(identity)}
        return digest(
            {
                "identity": identity.packed(),
                "sources": self.sources(identity),
                "opinions": [
                    v
                    for v in self.events("scene_review_finished")
                    if v["source_sha256"] in keys and v["identity"] == identity.packed()
                ],
                "human_adjudications": [
                    v
                    for v in self.events("scene_false_alarm_adjudicated")
                    if v["source_sha256"] in keys and v["identity"] == identity.packed()
                ],
            }
        )

    def require_reviews_complete(self, identity):
        self.guard()
        sets = [
            v
            for v in self.events("scene_set_frozen")
            if v["slot_id"] == identity.slot_id
        ]
        if not sets:
            raise Refused("SCENE_SET_NOT_FROZEN")
        completed = {
            v["source_sha256"]
            for v in self.events("scene_review_finished")
            if v["identity"] == identity.packed()
        }
        if any(
            v["payload"]["source_sha256"] not in completed
            for v in self.sources(identity)
        ):
            raise Refused("SCENE_REVIEWS_PENDING")

    def adjudicate_scene(self, identity, source_sha256, report):
        with self.ledger.transaction():
            self.guard(allow_pause=True)
            self.require_identity(identity)
            if source_sha256 not in {
                v["payload"]["source_sha256"] for v in self.sources(identity)
            }:
                raise Refused("SOURCE_NOT_OWNED_BY_SLOT")
            rows = [
                v
                for v in self.events("scene_review_finished")
                if v["source_sha256"] == source_sha256
                and v["identity"] == identity.packed()
            ]
            if len(rows) != 1 or rows[0]["opinion"]["verdict"] not in (
                "revise",
                "reject",
                "uncertain",
            ):
                raise Refused("NO_ADJUDICABLE_MODEL_ERROR")
            if source_sha256 in {
                v["source_sha256"]
                for v in self.events("scene_false_alarm_adjudicated")
                + self.events("scene_human_stop_adjudicated")
                if v["identity"] == identity.packed()
            }:
                raise Refused("ALREADY_ADJUDICATED")
            if (
                report.get("source_sha256") != source_sha256
                or report.get("opinion_sha256") != digest(rows[0]["opinion"])
                or report.get("decision")
                not in ("false_alarm", "confirmed_severe", "unresolved")
                or not all(
                    isinstance(report.get(k), str) and report[k].strip()
                    for k in ("reviewer", "reviewed_at", "evidence_ref", "reason")
                )
            ):
                raise Refused("EXACT_HUMAN_ADJUDICATION_REQUIRED")
            if (
                report["decision"] == "false_alarm"
                and rows[0]["opinion"]["verdict"] == "uncertain"
            ):
                raise Refused("UNCERTAINTY_CANNOT_BE_LABELLED_FALSE_ALARM")
            self.record(
                "scene_false_alarm_adjudicated"
                if report["decision"] == "false_alarm"
                else "scene_human_stop_adjudicated",
                {
                    **report,
                    "identity": identity.packed(),
                    "model_opinion_preserved": True,
                },
            )
            if report["decision"] != "false_alarm":
                self.ledger.stop(
                    self.batch,
                    "natural_severe_error"
                    if report["decision"] == "confirmed_severe"
                    else "human_pause",
                )

    def adjudicate_false_alarm(self, identity, source_sha256, report):
        if report.get("decision") != "false_alarm":
            raise Refused("FALSE_ALARM_DECISION_REQUIRED")
        return self.adjudicate_scene(identity, source_sha256, report)

    def simulated_usage_for(self, calls):
        ids = {v["ticket"] for v in calls}
        rows = self.ledger.db.execute(
            "SELECT * FROM attempts WHERE batch=?", (self.batch,)
        ).fetchall()
        return [
            sum(
                row[used] if row[used] is not None else row[reserved]
                for row in rows
                if row["id"] in ids
            )
            for used, reserved in (
                ("input_used", "input_max"),
                ("output_used", "output_max"),
                ("fee_used", "fee_max"),
            )
        ]


class _RecordedMock(httpx.AsyncBaseTransport):
    def __init__(self, router, identity, stage, provider):
        self.router, self.identity, self.stage, self.provider = (
            router,
            identity,
            stage,
            provider,
        )
        self.proof, self.usage = None, None

    async def handle_async_request(self, request):
        j = self.router.journal
        route = self.router.policy["providers"][self.provider]
        config = urlsplit(route["url"])
        if (
            request.url.host != "8.8.8.8"
            or request.url.path != config.path
            or request.headers.get("host") != config.hostname
            or request.extensions.get("sni_hostname") != config.hostname
        ):
            raise Refused("MOCK_WIRE_TARGET_CHANGED")
        raw = request.content
        for key in self.router.keys.values():
            redact_check(raw, key)
        body = parse(raw)
        cap = body.get("max_output_tokens")
        if (
            body.get("model") != route["model"]
            or body.get("reasoning") != {"effort": "none"}
            or body.get("stream") is not False
            or type(cap) is not int
            or not 1 <= cap <= 8000
            or len(raw) > 131072
        ):
            raise Refused("MOCK_WIRE_SCOPE_CHANGED")
        ticket = digest(
            {
                "identity": self.identity.packed(),
                "stage": self.stage,
                "request_sha": hashlib.sha256(raw).hexdigest(),
            }
        )
        price = (
            (Decimal(32000) * Decimal("0.30") + Decimal(cap) * Decimal("1.20"))
            if self.provider == "generation"
            else (Decimal(32000) * Decimal("2.50") + Decimal(cap) * Decimal("15.00"))
        )
        fee = int(price.to_integral_value(rounding=ROUND_CEILING))
        with j.reservation_lock():
            j.guard()
            j.require_identity(self.identity)
            if j.ledger.db.execute(
                "SELECT 1 FROM attempts WHERE batch=? AND state IN ('reserved','sent') LIMIT 1",
                (j.batch,),
            ).fetchone():
                j.ledger.halt(j.batch, "provider_contract_failure")
                raise Refused("CONCURRENT_OR_INTERRUPTED_MOCK_CALL_NO_RESEND")
            calls = j.events("mock_dispatch_reserved")
            own = [c for c in calls if c["provider"] == self.provider]
            role_limit = 182 if self.provider == "generation" else 68
            if len(own) >= role_limit:
                j.ledger.stop(j.batch, "ROLE_REQUEST_CAP")
                raise Refused("ROLE_REQUEST_CAP")
            role_caps = (
                (2800000, 672000, 3000000)
                if self.provider == "generation"
                else (2176000, 544000, 17000000)
            )
            if any(
                used + new > ceiling
                for used, new, ceiling in zip(
                    j.simulated_usage_for(own), (32000, cap, fee), role_caps
                )
            ):
                j.ledger.stop(j.batch, "ROLE_TOKEN_OR_FEE_CAP")
                raise Refused("ROLE_TOKEN_OR_FEE_CAP")
            if (
                self.provider == "generation"
                and sum(c["identity"] == self.identity.packed() for c in own) >= 13
            ):
                j.ledger.stop(j.batch, "COURSE_REQUEST_CAP")
                raise Refused("COURSE_REQUEST_CAP")
            course_calls = [c for c in own if c["identity"] == self.identity.packed()]
            if self.provider == "generation" and any(
                used + new > ceiling
                for used, new, ceiling in zip(
                    j.simulated_usage_for(course_calls)[:2],
                    (32000, cap),
                    (200000, 48000),
                )
            ):
                j.ledger.stop(j.batch, "COURSE_TOKEN_CAP")
                raise Refused("COURSE_TOKEN_CAP")
            if (
                self.stage == "development_review_probe"
                and sum(c["stage"] == self.stage for c in calls) >= 20
            ):
                j.ledger.stop(j.batch, "PROBE_REQUEST_CAP")
                raise Refused("PROBE_REQUEST_CAP")
            j.ledger.reserve(
                j.batch, j.package, ticket, input_max=32000, output_max=cap, fee_max=fee
            )
            j.ledger.mark_sent(j.batch, j.package, ticket)
            j.record(
                "mock_dispatch_reserved",
                {
                    "ticket": ticket,
                    "provider": self.provider,
                    "stage": self.stage,
                    "identity": self.identity.packed(),
                    "request_sha256": hashlib.sha256(raw).hexdigest(),
                    "mock_only": True,
                },
            )
        try:
            evidence(j.output / f"{ticket}-request.json", raw)
            transport = self.router.transports[self.provider]
            if type(transport) is not httpx.MockTransport:
                raise Refused("LIVE_TRANSPORT_FORBIDDEN")
            response = await transport.handle_async_request(request)
            data = bytearray()
            try:
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2097152:
                        raise Refused("RESPONSE_TOO_LARGE")
            finally:
                await response.aclose()
            response_raw = bytes(data)
            for key in self.router.keys.values():
                redact_check(response_raw, key)
            evidence(j.output / f"{ticket}-response.json", response_raw)
            evidence(
                j.output / f"{ticket}-status.json",
                {"http_status": response.status_code},
            )
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
                raise Refused("MOCK_RESPONSE_CONTRACT_FAILED")
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                raise Refused("USAGE_REQUIRED")
            inp, out, total = [
                usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
            ]
            if (
                not all(type(n) is int and n >= 0 for n in (inp, out, total))
                or inp > 32000
                or out > cap
                or total != inp + out
            ):
                raise Refused("USAGE_BOUND_OR_ARITHMETIC_FAILED")
            details = usage.get("output_tokens_details")
            if details is not None and (
                not isinstance(details, dict)
                or type(details.get("reasoning_tokens", 0)) is not int
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
            if payload.get("max_output_tokens") not in (None, cap):
                raise Refused("OUTPUT_CAP_CHANGED")
            with j.ledger.transaction():
                j.guard()
            self.proof, self.usage = (
                hashlib.sha256(response_raw).hexdigest(),
                (inp, out),
            )
            # Only a synthetic Mock settlement, never a service invoice or upper-bound proof.
            simulated_fee = int(
                (
                    (Decimal(inp) * Decimal("0.30") + Decimal(out) * Decimal("1.20"))
                    if self.provider == "generation"
                    else (
                        Decimal(inp) * Decimal("2.50") + Decimal(out) * Decimal("15.00")
                    )
                ).to_integral_value(rounding=ROUND_CEILING)
            )
            j.ledger.settle(
                j.batch,
                ticket,
                outcome="complete",
                proof_sha256=self.proof,
                input_used=inp,
                output_used=out,
                fee_used=simulated_fee,
            )
            j.record(
                "mock_wire_observed",
                {
                    "ticket": ticket,
                    "actual_provider_requests": 0,
                    "response_sha256": self.proof,
                    "reported_usage": [inp, out, total],
                    "invoice_verified": False,
                },
            )
            return httpx.Response(200, content=response_raw, request=request)
        except BaseException:
            j.ledger.settle(j.batch, ticket, outcome="unknown")
            raise

    async def aclose(self):
        pass


class Router:
    """No live constructor. Unknown bounds remain false even with a design approval."""

    def __init__(self, journal, transports, fixture_keys):
        self.policy = approved_design()
        if (
            set(transports) != {"generation", "review"}
            or any(type(v) is not httpx.MockTransport for v in transports.values())
            or set(fixture_keys) != {"generation", "review"}
            or len(set(fixture_keys.values())) != 2
            or any(
                not isinstance(k, str) or not k.startswith("TEST_ONLY_")
                for k in fixture_keys.values()
            )
        ):
            raise Refused("EXPLICIT_DISTINCT_MOCK_TRANSPORTS_AND_KEYS_REQUIRED")
        self._policy_sha256 = digest(self.policy)
        self._fixture_key_values = tuple(sorted(fixture_keys.items()))
        self.journal, self.transports, self.keys = (
            journal,
            transports,
            dict(fixture_keys),
        )

    def bound(self, identity):
        self.journal.bind(identity)
        router = self

        class Bound:
            policy = SendPolicy(
                package_id=router.journal.batch,
                requests=250,
                fee_micros=20000000,
                input_micros_per_token=3,
                output_micros_per_token=15,
                bounded_output_verified=False,
            )

            def input_upper_bound(self, request):
                raise Refused("LIVE_INPUT_BOUND_UNVERIFIED")

            async def send(self, request, *, retry_safe):
                return await router.send(identity, request, retry_safe=retry_safe)

        return Bound()

    async def send(self, identity, request, *, retry_safe):
        if (
            digest(self.policy) != self._policy_sha256
            or tuple(sorted(self.keys.items())) != self._fixture_key_values
            or set(self.transports) != {"generation", "review"}
            or any(type(v) is not httpx.MockTransport for v in self.transports.values())
        ):
            raise Refused("MOCK_ROUTE_KEYS_OR_TRANSPORT_CHANGED")
        if retry_safe is not False:
            raise Refused("RETRY_FORBIDDEN")
        self.journal.require_identity(identity)
        try:
            route = design.route(
                self.policy, request.stage, design.digest(dict(request.json_schema))
            )
        except ValueError:
            raise Refused("STAGE_OR_SCHEMA_NOT_FROZEN") from None
        role = self.policy["stages"][request.stage]["provider"]
        if request.stage == "development_scene_review":
            try:
                submitted = parse(request.prompt.messages[-1].content)
            except (ValueError, TypeError):
                raise Refused("EXACT_FROZEN_REVIEW_SOURCE_REQUIRED") from None
            if not any(
                v["payload"] == submitted for v in self.journal.sources(identity)
            ):
                raise Refused("EXACT_FROZEN_REVIEW_SOURCE_REQUIRED")
            if not any(
                v["identity"] == identity.packed()
                and v["source_sha256"] == submitted["source_sha256"]
                for v in self.journal.events("scene_review_started")
            ):
                raise Refused("REVIEW_RESERVATION_REQUIRED")
        endpoint = route["url"].removesuffix("/responses")
        target = ApprovedTarget(
            endpoint, urlsplit(endpoint).hostname, 443, ("8.8.8.8",)
        )
        wire = _RecordedMock(self, identity, request.stage, role)

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
            reasoning_effort="none",
        )
        try:
            async with asyncio.timeout(120):
                result = await gateway.generate_structured(request)
        except ProviderError:
            if wire.proof and wire.usage:
                return Reply("complete_response", wire.proof, {}, *wire.usage)
            raise Refused("MOCK_PROVIDER_OUTCOME_UNKNOWN") from None
        if not wire.proof or not wire.usage:
            raise Refused("EXACT_MOCK_WIRE_PROOF_REQUIRED")
        self.journal.guard()
        return Reply("complete_response", wire.proof, result.value, *wire.usage)


async def load_targets(sessions, identity):
    """Use owner-scoped repository checks, including real stored snapshot digests."""
    from sqlalchemy import select

    from app.models.free_course import FreeCourseRequest
    from app.services.free_course_snapshots import SnapshotRepository

    owner, cid = UUID(identity.owner_id), UUID(identity.course_id)
    async with sessions() as db:
        repo = SnapshotRepository(db, owner)
        course = await repo.get_course(cid)
        if course["head_version"] is None:
            raise Refused("NO_FINAL_COURSE_VERSION")
        manifest = await repo.get_version(cid, course["head_version"])
        plan = await repo.get_plan(cid, UUID(manifest["plan_id"]))
        req = await db.scalar(
            select(FreeCourseRequest).where(
                FreeCourseRequest.user_id == owner,
                FreeCourseRequest.course_id == cid,
                FreeCourseRequest.id == UUID(plan["request_id"]),
            )
        )
        if req is None:
            raise Refused("EXACT_REQUEST_NOT_FOUND")
        original = await repo.get_request(cid, req.version)
        # Repository plans preserve the candidate under its own envelope and normalize
        # scene identities separately. Do not confuse the wire plan with stored shape.
        constraints = {
            k: plan["candidate"][k]
            for k in ("objectives", "shared_example", "terminology", "conventions")
        }
        constraints["scenes"] = plan["scenes"]
        constraints["learner_evidence"] = original["evidence_snapshot"]
        constraints["teaching_language"], constraints["code_language"] = (
            course["teaching_language"],
            course["code_language"],
        )
        snapshots = {}
        for item in manifest["scenes"]:
            if item["scene_version_id"] is None:
                raise Refused("INCOMPLETE_SCENE_SET")
            snapshots[item["scene_id"]] = await repo.get_scene_snapshot(
                cid, course["head_version"], UUID(item["scene_id"])
            )
        result = []
        for item in manifest["scenes"]:
            sid = item["scene_id"]
            todo, seen, upstream = [sid], set(), []
            while todo:
                current = todo.pop()
                if current in seen:
                    continue
                seen.add(current)
                for dep in snapshots[current]["dependencies"]:
                    dsid = dep["scene_id"]
                    if (
                        dsid not in snapshots
                        or dep.get("scene_version_id")
                        != snapshots[dsid]["scene_version_id"]
                    ):
                        raise Refused("UPSTREAM_VERSION_NOT_EXACT")
                    if dsid == sid:
                        raise Refused("DEPENDENCY_CYCLE")
                    if dsid not in {v["scene_id"] for v in upstream}:
                        upstream.append({"scene_id": dsid, **snapshots[dsid]})
                    todo.append(dsid)
            payload = design.review_source(
                original_goal=course["original_goal"],
                plan_constraints=constraints,
                scene={"scene_id": sid, **snapshots[sid]},
                upstream=upstream,
            )
            result.append(
                {
                    "identity": identity.packed(),
                    "scene_id": sid,
                    "course_version_id": manifest["id"],
                    "course_digest": manifest["digest"],
                    "plan_id": plan["id"],
                    "plan_digest": plan["digest"],
                    "payload": payload,
                }
            )
        return result


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
            request = StructuredRequest(
                TextRequest(
                    (
                        ChatMessage("system", SCENE_PROMPT),
                        ChatMessage(
                            "user",
                            json.dumps(
                                target["payload"], ensure_ascii=False, sort_keys=True
                            ),
                        ),
                    ),
                    max_output_tokens=8000,
                ),
                SCENE_SCHEMA,
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
            verdict = design.validate_opinion(target["payload"], reply.value)
            opinion = {
                "source_sha256": key,
                "identity": identity.packed(),
                "opinion": reply.value,
                "response_sha256": reply.evidence_digest,
                "mock_only": True,
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
                return "paused_for_human"
        except BaseException:
            j.ledger.halt(j.batch, "provider_contract_failure")
            raise
    j.require_reviews_complete(identity)
    return "mock_reviews_complete"


async def run_split_slot(slot, sessions, fixture_scheduler_adapter, router):
    """Actual PG scheduler with caller's explicit synthetic policy; no live bounds supplied."""
    j = router.journal
    owner = uuid5(NAMESPACE_URL, j.batch + "/" + slot["slot_id"])
    # A placeholder course binding scopes mock calls until the generated PG id is known.
    identity = Identity(slot["slot_id"], str(owner), "TEST_ONLY_PENDING_COURSE")
    j.bind(identity)
    result = await run_slot(
        slot,
        sessions,
        fixture_scheduler_adapter(identity),
        j.ledger,
        j.batch,
        j.package,
    )
    if slot["kind"] == "probe":
        j.freeze(identity, [])
        return result
    plans = result["tables"].get("free_course_plans", [])
    if slot["kind"] == "negative":
        j.freeze(identity, [])
        return result
    if not result["engineering_pass"] or not plans:
        raise Refused("COURSE_NOT_COMPLETE")
    # Do not overwrite an identity receipt: append an explicit exact PG-course binding.
    actual = Identity(
        identity.slot_id + ":scene-review", str(owner), str(plans[0]["course_id"])
    )
    j.bind(actual)
    targets = await load_targets(sessions, actual)
    j.freeze(actual, targets)

    async def current(target):
        return target in await load_targets(sessions, actual)

    state = await review_pending(router, actual, verify_current=current)
    return {
        **result,
        "scene_review_identity": actual.packed(),
        "scene_source_hashes": [v["payload"]["source_sha256"] for v in targets],
        "scene_review_state_at_first_observation": state,
    }


class SplitExecution(Execution):
    """Original per-slot human checkpoint, plus exact scene-review checkpoint binding."""

    def __init__(self, journal, slots):
        super().__init__(
            journal.ledger,
            {"batch_id": journal.batch},
            journal.package,
            slots,
            journal.output,
        )
        self.journal = journal

    def start(self, approval):
        raise Refused("MOCK_BATCH_ALREADY_STARTED_NO_LIVE_AUTHORITY")

    async def advance(self, runner):
        self.journal.guard()
        return await super().advance(runner)

    def review(self, review):
        pending = self.events("slot_output")
        if not pending:
            raise Refused("NO_PENDING_REVIEW")
        self.verify_outputs(pending)
        value = parse((self.output / (pending[-1]["slot_id"] + ".json")).read_bytes())
        raw_identity = value.get("scene_review_identity")
        if raw_identity:
            identity = Identity(**raw_identity)
            self.journal.require_reviews_complete(identity)
            if review.get(
                "scene_review_checkpoint_sha256"
            ) != self.journal.review_checkpoint(identity):
                raise Refused("EXACT_SCENE_REVIEW_CHECKPOINT_REQUIRED")
        return super().review(review)
