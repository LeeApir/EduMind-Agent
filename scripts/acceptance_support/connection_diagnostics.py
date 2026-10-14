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

    def summary(self):
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
            obj = strict_json(bytes(self.payload))
        except Exception:
            return result
        if not isinstance(obj, dict):
            return result
        result["json_object"] = True
        result["has_error"] = "error" in obj
        choices = obj.get("choices")
        result["choices_count"] = len(choices) if isinstance(choices, list) else None
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
