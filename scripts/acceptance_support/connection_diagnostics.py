"""Content-free diagnostics; record decoded bytes only in memory, never serialize them."""

from contextlib import asynccontextmanager

from app.services.provider_protocol import strict_json

LIMIT = 2 * 1024 * 1024


class RecordingResponse:
    def __init__(self, response, recorder):
        self.response, self.recorder = response, recorder

    def __getattr__(self, name):
        return getattr(self.response, name)

    async def aiter_bytes(self):
        async for chunk in self.response.aiter_bytes():
            if len(self.recorder.payload) + len(chunk) > LIMIT:
                raise ValueError("RESPONSE_TOO_LARGE")
            self.recorder.payload.extend(chunk)
            yield chunk


class RecordingOperation:
    """Delegate all actual authority/network sends; observe the parser's decoded input."""

    def __init__(self, operation):
        self.operation = operation
        self.payload = bytearray()
        self.content_encoding = None

    def __getattr__(self, name):
        return getattr(self.operation, name)

    @asynccontextmanager
    async def send(self, body, *, stream=False):
        async with self.operation.send(body, stream=stream) as response:
            encoding = response.headers.get("content-encoding", "identity").lower()
            self.content_encoding = (
                encoding if encoding in {"gzip", "deflate", "br", "identity"} else "other"
            )
            yield RecordingResponse(response, self)

    def objects(self, streaming=False):
        if not streaming:
            return [strict_json(bytes(self.payload))]
        objects = []
        fields = []
        for line in bytes(self.payload).replace(b"\r\n", b"\n").split(b"\n"):
            if not line:
                if fields:
                    data = b"\n".join(fields)
                    if data != b"[DONE]":
                        objects.append(strict_json(data))
                    fields = []
            elif line.startswith(b"data:"):
                fields.append(line[5:].removeprefix(b" "))
        return objects

    def summary(self, streaming=False):
        result = {
            "decoded_bytes": len(self.payload),
            "content_encoding": self.content_encoding,
            "json_object": False,
            "has_error": False,
            "choices_count": None,
            "input_tokens": None,
            "output_tokens": None,
        }
        try:
            objects = self.objects(streaming)
        except Exception:
            return result
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            result["json_object"] = True
            result["has_error"] |= "error" in obj
            choices = obj.get("choices")
            if isinstance(choices, list):
                result["choices_count"] = len(choices)
            usage = obj.get("usage")
            if isinstance(usage, dict):
                for source, target in [
                    ("prompt_tokens", "input_tokens"),
                    ("completion_tokens", "output_tokens"),
                ]:
                    value = usage.get(source)
                    if type(value) is int and value >= 0:
                        result[target] = value
        return result


class ProbeFailure(ValueError):
    """Local assertion errors have their own safe category, never vendor outage."""

    def __init__(self, check):
        super().__init__("PROBE_VALIDATION_FAILED")
        self.check = check


def classify_failure(error):
    from app.core.credential_crypto import CredentialFailure
    from app.services.provider_gateway import ProviderError

    if isinstance(error, ProbeFailure):
        return "INVALID_OUTPUT", "probe_validation"
    if isinstance(error, TimeoutError):
        return "TIMEOUT", "deadline"
    if isinstance(error, ProviderError):
        code = error.code.value
        if code in {
            "AUTHENTICATION_FAILED",
            "RATE_LIMITED",
            "CAPABILITY_UNAVAILABLE",
            "TIMEOUT",
            "INVALID_OUTPUT",
            "TEMPORARILY_UNAVAILABLE",
        }:
            return code, "provider_protocol"
        return "TARGET_CHANGED", "target_policy"
    if isinstance(error, CredentialFailure):
        return "SAFETY_FAILURE", "credential_policy"
    return "SAFETY_FAILURE", "local_unexpected"
