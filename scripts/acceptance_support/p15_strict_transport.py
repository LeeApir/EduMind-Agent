"""r03-only counted Responses adapter; never changes or resumes frozen r02 code."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from acceptance_support.p15_diagnostic_ledger import Refused, digest
from acceptance_support.p15_diagnostic_transport import (
    CountedTransport,
    DiagnosticAdapter,
    DiagnosticResponsesAdapter,
)
from acceptance_support.p15_strict_schema import VERSION, guidance, project, validate_wire
from jsonschema import Draft202012Validator, ValidationError

from app.agents.free_course_planning import SCHEMA as PLAN_SCHEMA
from app.agents.free_scene_generation import SCHEMA as SCENE_SCHEMA
from app.agents.review_schema import review_output_schema
from app.services.free_course_scheduler import Reply
from app.services.provider_gateway import (
    ChatMessage,
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
)

SCHEMAS = {
    "free_course_plan_generation": PLAN_SCHEMA,
    "free_scene_generation": SCENE_SCHEMA,
    "development_review_probe": dict(review_output_schema()),
}


class StrictResponsesAdapter(DiagnosticResponsesAdapter):
    async def _response(self, body):
        body["text"]["format"]["strict"] = True
        validate_wire(body["text"]["format"]["schema"])
        return await super()._response(body)

    async def generate_structured(self, request):
        original = deepcopy(dict(request.json_schema))
        wire, _ = project(original)
        messages = request.prompt.messages
        # Trusted schema guidance precedes all untrusted learner inputs, never label answers.
        amended = replace(
            request.prompt,
            messages=(messages[0], ChatMessage("system", guidance(original)), *messages[1:]),
        )
        result = await super().generate_structured(
            replace(request, prompt=amended, json_schema=wire)
        )
        try:
            Draft202012Validator(original).validate(result.value)
        except ValidationError:
            raise ProviderError(
                ProviderErrorCode.INVALID_OUTPUT,
                output_failure_reason=OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH,
                schema_keyword="other",
                usage=result.usage,
                output_text_counts=result.output_text_counts,
            ) from None
        return result


class StrictDiagnosticAdapter(DiagnosticAdapter):
    async def send(self, request, *, retry_safe):
        if retry_safe is not False:
            raise Refused("RETRY_FORBIDDEN")
        if request.stage not in SCHEMAS or digest(dict(request.json_schema)) != digest(
            SCHEMAS[request.stage]
        ):
            raise Refused("UNFROZEN_DOMAIN_SCHEMA")
        wire_schema, changes = project(dict(request.json_schema))
        wire = CountedTransport(
            self.transport_factory(),
            self.ledger,
            self.batch,
            self.package,
            self.output,
            self.settings.api_key,
        )
        audit = dict(
            version=VERSION,
            stage=request.stage,
            local_schema_sha256=digest(dict(request.json_schema)),
            wire_schema_sha256=digest(wire_schema),
            guidance_sha256=hashlib.sha256(
                guidance(dict(request.json_schema)).encode()
            ).hexdigest(),
            changes=changes,
        )
        (Path(self.output) / (uuid4().hex + "-projection.json")).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
        )
        gateway = StrictResponsesAdapter(
            self.settings, self.guard, transport=wire, reasoning_effort="none"
        )
        try:
            result = await gateway.generate_structured(request)
            if not wire.proof or not wire.usage or result.model_id != "gpt-6-luna":
                raise Refused("MISSING_EXACT_WIRE_PROOF")
            return Reply("complete_response", wire.proof, result.value, *wire.usage)
        except ProviderError:
            if wire.proof and wire.usage:
                return Reply("complete_response", wire.proof, {}, *wire.usage)
            return Reply("unknown", digest({"stopped": "unverified_transport"}))
        except Refused:
            return Reply("unknown", digest({"stopped": "unverified_transport"}))
