"""New diagnostic transport; historical HTTP error readers remain immutable."""

import httpx
from acceptance_support.provider_error_decode import read_error
from acceptance_support.qwen_review_attempt import ExactTransport


class QwenCompatibilityTransport(ExactTransport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_diagnosis = None

    async def handle_async_request(self, request):
        request.headers["accept-encoding"] = "gzip, deflate"
        response = await super().handle_async_request(request)
        if response.status_code >= 400:
            self.error_diagnosis = await read_error(response, self.wire)
            # Preserve actual status so production normalization still runs.
            return httpx.Response(response.status_code, content=b"", request=request)
        return response
