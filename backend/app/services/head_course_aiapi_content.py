"""Bindings and response checks for one AIAPI content-only development batch."""

from copy import deepcopy
from datetime import timedelta
from hashlib import sha256

from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import head_course_archived_import as archive
from app.services import head_course_generation as generation
from app.services import head_course_materials as materials
from app.services import head_course_reuse as reuse
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from scripts.isolated_diagnostics import p15_pilot_wire as wire

BATCH = "head-fixed-aiapi-content-r01"
VERSION = "head-aiapi-content-responses-v1"
DATABASE = "edumind_catalog_p15_t108_aiapi_content"
ENDPOINT = "https://aiapi.world/v1/responses"
WINDOW_SECONDS = 1800
REQUEST_SHA = "4df87d4a2ab296d1deb4e1ae67ebe35bda0eceb02f3a548ab69cc172184409b5"
PACKAGE = archive.ACCEPTANCE / "phase-1.5-head-aiapi-content-r01"
ECHO_FIELDS = ("model", "store", "temperature", "max_output_tokens", "reasoning", "instructions")
OPTIONAL_DEFAULTS = {
    "tools": [],
    "background": False,
    "previous_response_id": None,
    "stream": False,
}
USAGE_COUNTS = ("input_tokens", "output_tokens", "total_tokens")
USAGE_DETAILS = ("input_tokens_details", "output_tokens_details")
DETAIL_FIELDS = {
    "audio_tokens",
    "image_tokens",
    "text_tokens",
    "cached_tokens",
    "cached_creation_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
}


def sha(raw):
    return sha256(raw).hexdigest()


def source():
    raw_request = (PACKAGE / "request.json").read_bytes()
    payload = archive.original_payload()
    request = dict(
        materials.body(payload), model=archive.REQUESTED_MODEL, reasoning={"effort": "low"}
    )
    if sha(raw_request) != REQUEST_SHA or raw_request != canonical(request):
        raise SnapshotError("HEAD_AIAPI_REQUEST_BINDING")
    return payload, request


def require_database(db):
    bind = db.bind.engine if isinstance(db.bind, AsyncConnection) else db.bind
    if bind is None or bind.url.database != DATABASE:
        raise SnapshotError("HEAD_AIAPI_DATABASE")
    generation.require_development_database(bind.url.render_as_string(hide_password=False))


def operation_window(op):
    if op.config_snapshot.get(
        "policy_version"
    ) != BATCH or op.deadline_at - op.created_at != timedelta(seconds=WINDOW_SECONDS):
        raise SnapshotError("HEAD_AIAPI_WINDOW_BINDING")
    return dict(starts_at=op.created_at.isoformat(), expires_at=op.deadline_at.isoformat())


def bound_payload(inputs, plan, old):
    ids = ("course_id", "operation_id", "request_id")
    if (
        any(inputs[key] == old["source_binding"][key] for key in ids)
        or plan != old["plan"]
        or inputs["original_goal"] != old["original_goal"]
        or inputs["head_support"] != materials.support_for_goal(old["original_goal"])
        or inputs["teaching_language"] != "zh-CN"
        or inputs["code_language"] != "C"
        or inputs["profile_id"] is not None
        or inputs["profile_version"] is not None
        or inputs["learner_evidence"]
        or inputs["request_sources"]
        != {
            "request_1": dict(request_id=inputs["request_id"], version=1, text=old["original_goal"])
        }
    ):
        raise SnapshotError("HEAD_AIAPI_PLAN_BINDING")
    new = materials.content_payload(inputs, plan)
    if new != {**old, "source_binding": {key: inputs[key] for key in ids}}:
        raise SnapshotError("HEAD_AIAPI_MATERIALS_BINDING")
    return new


async def outline(repo, cid):
    if (await repo.get_course(cid))["head_version"] != 1:
        raise SnapshotError("HEAD_OUTLINE_REQUIRED")
    version = await repo.get_version(cid, 1)
    return dict(plan_id=version["plan_id"], scene_id=version["scenes"][0]["scene_id"])


def usage_counts(usage, cap):
    if type(usage) is not dict or usage.keys() - set((*USAGE_COUNTS, *USAGE_DETAILS)):
        raise SnapshotError("HEAD_AIAPI_USAGE")
    counts = {key: usage.get(key) for key in USAGE_COUNTS}
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise SnapshotError("HEAD_AIAPI_USAGE")
    incoming, outgoing, total = (counts[key] for key in USAGE_COUNTS)
    if incoming + outgoing != total or incoming > 139264 or outgoing > cap:
        raise SnapshotError("HEAD_AIAPI_USAGE")
    for field in USAGE_DETAILS:
        details = usage.get(field, {})
        if (
            type(details) is not dict
            or details.keys() - DETAIL_FIELDS
            or any(type(value) is not int or value < 0 for value in details.values())
            or details.get("audio_tokens", 0)
            or details.get("image_tokens", 0)
            or details.get("reasoning_tokens", 0) > outgoing
        ):
            raise SnapshotError("HEAD_AIAPI_USAGE")
    return {
        **counts,
        "reasoning_tokens": usage.get("output_tokens_details", {}).get("reasoning_tokens"),
    }


def assistant_text(output):
    if type(output) is not list:
        raise SnapshotError("HEAD_AIAPI_OUTPUT")
    for message in output:
        if type(message) is not dict:
            continue
        if message.get("type") == "refusal":
            raise SnapshotError("HEAD_AIAPI_REFUSAL")
        parts = message.get("content")
        if type(parts) is list and any(
            type(part) is dict and part.get("type") == "refusal" for part in parts
        ):
            raise SnapshotError("HEAD_AIAPI_REFUSAL")
    if len(output) != 1 or type(output[0]) is not dict:
        raise SnapshotError("HEAD_AIAPI_OUTPUT")
    message = output[0]
    if (
        message.keys() - {"id", "type", "role", "status", "phase", "content"}
        or (message.get("type"), message.get("role"), message.get("status"))
        != ("message", "assistant", "completed")
        or message.get("phase", "final_answer") != "final_answer"
    ):
        raise SnapshotError("HEAD_AIAPI_OUTPUT")
    check_id(message)
    parts = message.get("content")
    if type(parts) is not list or len(parts) != 1 or type(parts[0]) is not dict:
        raise SnapshotError("HEAD_AIAPI_OUTPUT")
    part = parts[0]
    text = part.get("text")
    if (
        part.keys() - {"type", "text", "annotations", "logprobs"}
        or part.get("type") != "output_text"
        or any(part.get(key, []) != [] for key in ("annotations", "logprobs"))
        or type(text) is not str
        or not text.strip()
    ):
        raise SnapshotError("HEAD_AIAPI_OUTPUT")
    return text


def check_id(obj):
    if "id" in obj and (type(obj["id"]) is not str or not obj["id"]):
        raise SnapshotError("HEAD_AIAPI_METADATA")


def observe(request, raw):
    if len(raw) > 2097152:
        raise SnapshotError("HEAD_AIAPI_RESPONSE_SIZE")
    body = wire.strict_json(raw)
    if type(body) is not dict:
        raise SnapshotError("HEAD_AIAPI_ENVELOPE")
    incomplete = body.get("incomplete_details")
    if body.get("status") == "incomplete" or incomplete is not None:
        code = (
            "HEAD_AIAPI_TRUNCATED"
            if (
                type(incomplete) is dict
                and incomplete.get("reason") in ("max_output_tokens", "length")
            )
            else "HEAD_AIAPI_INCOMPLETE"
        )
        raise SnapshotError(code)
    if body.get("error") is not None or body.get("status") in ("failed", "cancelled"):
        raise SnapshotError("HEAD_AIAPI_SERVICE_ERROR")
    if (
        body.keys()
        - set(ECHO_FIELDS)
        - OPTIONAL_DEFAULTS.keys()
        - {
            "id",
            "created_at",
            "completed_at",
            "object",
            "status",
            "error",
            "incomplete_details",
            "text",
            "output",
            "output_text",
            "usage",
        }
        or body.get("object") != "response"
        or body.get("status") != "completed"
        or any(
            canonical(body[key]) != canonical(value)
            for key, value in OPTIONAL_DEFAULTS.items()
            if key in body
        )
    ):
        raise SnapshotError("HEAD_AIAPI_ENVELOPE")
    check_id(body)
    for key in ("created_at", "completed_at"):
        if key in body and (type(body[key]) is not int or body[key] < 0):
            raise SnapshotError("HEAD_AIAPI_METADATA")
    for key in ECHO_FIELDS[:4]:
        if key not in body or (key == "max_output_tokens" and body[key] is None):
            continue
        value, expected = body[key], request[key]
        if value != expected or type(value) is not type(expected):
            raise SnapshotError("HEAD_AIAPI_PARAMETER_CONFLICT")
    if "reasoning" in body:
        reasoning = body["reasoning"]
        known = {
            "effort": request["reasoning"]["effort"],
            "context": "all_turns",
            "mode": "standard",
            "summary": None,
        }
        if (
            type(reasoning) is not dict
            or reasoning.get("effort") != known["effort"]
            or any(key not in known or value != known[key] for key, value in reasoning.items())
        ):
            raise SnapshotError("HEAD_AIAPI_REASONING_CONFLICT")
    if body.get("instructions") not in (None, request["input"][0]["content"]):
        raise SnapshotError("HEAD_AIAPI_INSTRUCTIONS")

    original_text = request["text"]
    allowed_echo = deepcopy(original_text)
    del allowed_echo["format"]["schema"]["properties"]["paragraphs"]["items"]["properties"][
        "fact_ids"
    ]["uniqueItems"]
    schema_echo = canonical(body.get("text"))
    if schema_echo not in (canonical(original_text), canonical(allowed_echo)):
        raise SnapshotError("HEAD_AIAPI_SCHEMA_ECHO")
    text = assistant_text(body.get("output"))
    if "output_text" in body and body["output_text"] != text:
        raise SnapshotError("HEAD_AIAPI_OUTPUT")
    usage = usage_counts(body.get("usage"), request["max_output_tokens"])
    output = wire.strict_json(text)
    wire.check_schema(output, original_text["format"]["schema"])
    if usage["output_tokens"] == request["max_output_tokens"]:
        raise SnapshotError("HEAD_AIAPI_OUTPUT_CAP_SUSPECTED")
    observation = dict(
        response_rule=VERSION,
        requested={key: request[key] for key in ECHO_FIELDS if key in request}
        | {"instructions": request["input"][0]["content"]},
        reported={key: body[key] for key in ECHO_FIELDS if key in body},
        schema_echo="exact"
        if schema_echo == canonical(original_text)
        else "fact_ids_unique_items_omitted",
    )
    return output, usage, observation


def record(payload, request, raw, evidence_kind):
    if evidence_kind not in ("offline_fixture", "actual_provider_response"):
        raise SnapshotError("HEAD_AIAPI_EVIDENCE_KIND")
    output, usage, observation = observe(request, raw)
    return dict(
        protocol_version=VERSION,
        request=request,
        raw_response=raw.decode(),
        raw_sha256=sha(raw),
        candidate=reuse.candidate(payload, output, allow_terminal_lf=True),
        model=request["model"],
        evidence_kind=evidence_kind,
        usage=usage,
        observation=observation,
    )


def review_binding(context, rec):
    return dict(
        operation_digest=digest(VERSION, context=context),
        request_sha256=REQUEST_SHA,
        raw_response_sha256=rec["raw_sha256"],
        plan_digest=archive.PLAN,
        materials_digest=rec["candidate"]["payload"]["materials"]["materials_digest"],
    )


def validate_chain(chain, inputs, plan):
    old, request = source()
    payload = bound_payload(inputs, plan, old)
    context = chain["context"]
    if context["planning_inputs"] != inputs or len(chain["records"]) != 1:
        raise SnapshotError("HEAD_AIAPI_CHAIN_BINDING")
    (rec,) = chain["records"]
    if rec != record(payload, request, rec["raw_response"].encode(), rec["evidence_kind"]):
        raise SnapshotError("HEAD_AIAPI_RECORD_BINDING")
    review = chain["final_review"]
    if review.get("aiapi_binding") != review_binding(context, rec):
        raise SnapshotError("HEAD_AIAPI_REVIEW_BINDING")
    return reuse.require_full_review(review, rec["candidate"], allow_terminal_lf=True)
