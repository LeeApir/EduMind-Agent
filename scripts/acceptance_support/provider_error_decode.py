"""Bound raw and decoded HTTP error bodies independently; serialize only safe metadata."""

import hashlib
import json
import re
import zlib

WORDS = set(
    "invalid parameter parameters invalidparameter invalidparametererror "
    "invalid_request_error unsupported not supported support schema json_schema "
    "response_format strict additionalproperties required properties type object "
    "array string number integer boolean enum anyof oneof allof ref defs items "
    "minitems maxitems minlength maxlength pattern format minimum maximum "
    "exclusiveMinimum exclusiveMaximum const null false true must be contain contains "
    "include includes missing field fields value values error request format is are "
    "the a an of for in at to and or with without should set specified provided "
    "allowed only can cannot does do this model output max_completion_tokens "
    "max_tokens enable_thinking temperature depth nesting maximum limit exceeded too "
    "many nested level levels length size context tokens token input greater than "
    "less equal expected found got has have been failed validation validate property "
    "names keys all each every list default please use remove change definitions top "
    "level root schema additional property empty recursive recursion "
    "unsupportedparameter document enum values total count exceed".lower().split()
)
CODES = {
    "InvalidParameter",
    "InvalidParameterError",
    "InvalidRequest",
    "InvalidSchema",
    "invalid_request_error",
    "invalid_json_schema",
    "invalid_parameter",
    "UnsupportedOperation",
    "DataInspectionFailed",
    "AccessDenied",
    "ModelNotFound",
    "BadRequest",
}

RAW_LIMIT = 65536
DECODED_LIMIT = 131072
WORDS = WORDS | {
    "uniqueitems",
    "contains",
    "mincontains",
    "maxcontains",
    "multipleof",
    "patternproperties",
    "propertynames",
    "additionalitems",
}
MEDIA = {
    "application/json",
    "application/problem+json",
    "text/plain",
    "text/html",
    "application/octet-stream",
}
ENCODINGS = {"identity", "gzip", "deflate", "br"}
FIELDS = {"error", "code", "type", "message", "param", "Code", "Message"}


class DecodeLimit(ValueError):
    pass


def header_metadata(headers):
    media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    encoding = headers.get("content-encoding", "identity").strip().lower()
    return {
        "media_type": media if media in MEDIA else "other",
        "content_encoding": encoding if encoding in ENCODINGS else "other",
    }, encoding


def safe_fields(decoded, wire):
    try:
        body = json.loads(decoded)
    except (ValueError, UnicodeError, RecursionError):
        return {"parse": "NON_JSON"}
    if not isinstance(body, dict):
        return {"parse": "JSON_NON_OBJECT"}
    error = body.get("error", body)
    if not isinstance(error, dict):
        return {"parse": "JSON_NON_OBJECT_ERROR", "error_type": type(error).__name__}
    code = error.get("code", error.get("Code", error.get("type")))
    message = error.get("message", error.get("Message", ""))
    names = set()

    def walk(value):
        if isinstance(value, dict):
            names.update(str(k).lower() for k in value.get("properties", {}))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(json.loads(wire).get("response_format", {}))
    tokens = re.findall(
        r"[A-Za-z_$][A-Za-z0-9_$-]*|[0-9]+|[.:,;()\[\]/=<>]",
        message[:8192] if isinstance(message, str) else "",
    )
    safe = [
        token
        if token.lower() in WORDS | names
        or token in ".:,;()[]/=<>"
        or (token.isdigit() and len(token) <= 4)
        else "[redacted]"
        for token in tokens
    ]
    return {
        "parse": "JSON_ERROR_OBJECT",
        "code": code if isinstance(code, str) and code in CODES else "UNRECOGNIZED_REDACTED",
        "fields": {k: type(v).__name__ for k, v in error.items() if k in FIELDS},
        "unknown_field_count": len(set(error) - FIELDS),
        "technical_message_tokens": safe[:400],
    }


async def read_error(response, wire):
    """Read raw stream (not aiter_bytes); never trust Content-Length or auto decoding."""
    metadata, encoding = header_metadata(response.headers)
    observation = {**metadata, "raw_bytes": 0, "decoded_bytes": 0, "raw_complete": False}
    digest = hashlib.sha256()
    decoded = bytearray()
    decompressor = None
    try:
        if encoding not in {"identity", "gzip", "deflate"}:
            observation["parse"] = "UNSUPPORTED_ENCODING"
            return observation
        if encoding != "identity":
            decompressor = zlib.decompressobj(31 if encoding == "gzip" else 15)
        async for chunk in response.stream:
            observation["raw_bytes"] += len(chunk)
            if observation["raw_bytes"] > RAW_LIMIT:
                raise DecodeLimit("RAW_LIMIT")
            digest.update(chunk)
            remaining = DECODED_LIMIT - len(decoded)
            output = decompressor.decompress(chunk, remaining + 1) if decompressor else chunk
            if len(output) > remaining:
                raise DecodeLimit("DECODED_LIMIT")
            decoded.extend(output)
            observation["decoded_bytes"] = len(decoded)
            if decompressor and (decompressor.unconsumed_tail or decompressor.unused_data):
                raise DecodeLimit("TRAILING_OR_EXCESS_DATA")
        observation["raw_complete"] = True
        if decompressor and not decompressor.eof:
            observation["parse"] = "TRUNCATED_COMPRESSION"
        else:
            observation.update(safe_fields(bytes(decoded), wire))
    except DecodeLimit as exc:
        observation["parse"] = str(exc)
    except zlib.error:
        observation["parse"] = "INVALID_COMPRESSION"
    finally:
        observation["raw_sha256"] = digest.hexdigest()
        await response.aclose()
    return observation
