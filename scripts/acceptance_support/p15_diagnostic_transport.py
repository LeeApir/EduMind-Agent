"""T037 bounded Responses bridge; no default credentials, network or authorization.

The factory requires the separately verified T038 approval before a real transport can
be provided. Offline tests inject httpx.MockTransport. HTTP token-count calls consume the
same durable request cap; model attempts additionally consume PG's original limits.
"""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx
from acceptance_support.p15_diagnostic_ledger import Refused, digest

from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.free_course_scheduler import Reply, SendPolicy
from app.services.provider_gateway import ProviderError

MAX_BYTES = 2 * 1024 * 1024


class DiagnosticResponsesAdapter(DeepSeekResponsesAdapter):
    async def _response(self, body):
        # These fields enter the adapter's actual wire digest; never rewrite after hashing.
        body.update(store=False, service_tier="default")
        return await super()._response(body)


def redact_check(raw, key):
    text = raw.decode("utf-8")
    if key and (key in text or key in json.dumps(json.loads(text), ensure_ascii=False)):
        raise Refused("CREDENTIAL_ECHO")


class CountedTransport(httpx.AsyncBaseTransport):
    def __init__(self, underlying, ledger, batch, package, output, key):
        self.underlying = underlying
        self.ledger = ledger
        self.batch = batch
        self.package = package
        self.output = Path(output)
        self.output.mkdir(exist_ok=True)
        self.key = key
        self.proof = None
        self.usage = None
        self.model_id = None
        self.sent = False

    async def aclose(self):
        await self.underlying.aclose()

    async def read(self, response):
        data = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise Refused("RESPONSE_TOO_LARGE")
        finally:
            await response.aclose()
        raw = bytes(data)
        redact_check(raw, self.key)
        return raw

    async def handle_async_request(self, request):
        identity = uuid4().hex
        model_ticket = identity + "-model"
        count_ticket = identity + "-count"
        body = json.loads(request.content)
        if (
            body.get("model") != "gpt-6-luna"
            or body.get("reasoning") != {"effort": "none"}
            or body.get("store") is not False
            or body.get("service_tier") != "default"
            or body.get("stream") is not False
            or not 16 <= body.get("max_output_tokens", 0) <= 8000
            or set(body)
            - {
                "model",
                "input",
                "reasoning",
                "store",
                "service_tier",
                "stream",
                "max_output_tokens",
                "temperature",
                "text",
            }
        ):
            raise Refused("WIRE_CONFIG_CHANGED")
        output_max = body["max_output_tokens"]
        self.ledger.reserve(
            self.batch,
            self.package,
            model_ticket,
            input_max=32000,
            output_max=output_max,
            fee_max=32000 + output_max,
        )
        self.ledger.reserve(
            self.batch, self.package, count_ticket, input_max=0, output_max=0, fee_max=0, seconds=10
        )
        try:
            self.ledger.mark_sent(self.batch, self.package, count_ticket)
            count_request = httpx.Request(
                "POST",
                request.url.copy_with(path=request.url.path + "/input_tokens"),
                headers=request.headers,
                content=request.content,
                extensions=request.extensions,
            )
            counter = await self.underlying.handle_async_request(count_request)
            count_status = counter.status_code
            raw_count = await self.read(counter)
            if count_status != 200:
                raise Refused("COUNT_UNAVAILABLE_NO_FALLBACK")
            counted = json.loads(raw_count)
            count = counted.get("input_tokens")
            if (
                counted.get("object") != "response.input_tokens"
                or type(count) is not int
                or not 0 < count <= 32000
            ):
                raise Refused("INPUT_BOUND_UNVERIFIED")
            self.ledger.settle(
                self.batch,
                count_ticket,
                outcome="complete",
                proof_sha256=hashlib.sha256(raw_count).hexdigest(),
                input_used=0,
                output_used=0,
                fee_used=0,
            )
            self.ledger.mark_sent(self.batch, self.package, model_ticket)
            self.sent = True
            response = await self.underlying.handle_async_request(request)
            status = response.status_code
            raw = await self.read(response)
            payload = json.loads(raw)
            usage = payload.get("usage")
            if status != 200 or payload.get("model") != "gpt-6-luna" or not isinstance(usage, dict):
                raise Refused("RESPONSE_CONTRACT_UNVERIFIED")
            inp = usage.get("input_tokens")
            out = usage.get("output_tokens")
            if (
                type(inp) is not int
                or type(out) is not int
                or inp != count
                or not 0 <= out <= output_max
            ):
                raise Refused("USAGE_BOUND_MISMATCH")
            self.proof = hashlib.sha256(raw).hexdigest()
            self.usage = (inp, out)
            self.model_id = payload["model"]
            # Reference fee only: rounded-up official Standard USD micros/token, NOT relay billing.
            self.ledger.settle(
                self.batch,
                model_ticket,
                outcome="complete",
                proof_sha256=self.proof,
                input_used=inp,
                output_used=out,
                fee_used=inp + out,
            )
            for name, content in [
                ("request.json", request.content),
                ("count.json", raw_count),
                ("response.json", raw),
            ]:
                (self.output / (identity + "-" + name)).write_bytes(content)
            (self.output / (identity + "-receipt.json")).write_text(
                json.dumps(
                    dict(
                        status=status,
                        input_tokens=inp,
                        output_tokens=out,
                        total_output_includes_reasoning=True,
                        request_sha256=hashlib.sha256(request.content).hexdigest(),
                        response_sha256=self.proof,
                        reference_fee_micros_usd_upper=inp + out,
                        actual_relay_fee=None,
                        invoice_verified=False,
                    ),
                    indent=2,
                )
                + "\n"
            )
            return httpx.Response(status, content=raw, request=request)
        except BaseException:
            # Unknown count/model outcome stops the whole batch. No implicit retry or fallback.
            self.ledger.halt(self.batch, "provider_contract_failure")
            for ticket in [count_ticket, model_ticket]:
                try:
                    self.ledger.settle(self.batch, ticket, outcome="unknown")
                except Refused:
                    pass
            raise


class DiagnosticAdapter:
    """Original Scheduler.Adapter interface, backed by counted actual Responses bytes."""

    def __init__(self, settings, guard, ledger, batch, package, output, transport_factory):
        self.settings = settings
        self.guard = guard
        self.ledger = ledger
        self.batch = batch
        self.package = package
        self.output = output
        self.transport_factory = transport_factory
        # Internal PG cost counters are conservative official-reference units, not an invoice cap.
        self.policy = SendPolicy(
            package_id=batch,
            requests=202,
            fee_micros=4272000,
            input_micros_per_token=1,
            output_micros_per_token=1,
            bounded_output_verified=True,
        )

    def input_upper_bound(self, _request):
        return 32000

    async def send(self, request, *, retry_safe):
        if retry_safe is not False:
            raise Refused("RETRY_FORBIDDEN")
        wire = CountedTransport(
            self.transport_factory(),
            self.ledger,
            self.batch,
            self.package,
            self.output,
            self.settings.api_key,
        )
        gateway = DiagnosticResponsesAdapter(
            self.settings, self.guard, transport=wire, reasoning_effort="none"
        )
        try:
            result = await gateway.generate_structured(request)
            if not wire.proof or not wire.usage or result.model_id != "gpt-6-luna":
                raise Refused("MISSING_EXACT_WIRE_PROOF")
            return Reply("complete_response", wire.proof, result.value, *wire.usage)
        except ProviderError:
            # HTTP complete but schema-invalid result is still charged and preserved for diagnosis.
            if wire.proof and wire.usage:
                return Reply("complete_response", wire.proof, {}, *wire.usage)
            return Reply("unknown", digest({"stopped": "unverified_transport"}))
        except Refused:
            return Reply("unknown", digest({"stopped": "unverified_transport"}))
