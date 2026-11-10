"""Shared request transport preserves the precise wire body and encrypted originals."""

import httpx
import pytest
from cryptography.fernet import Fernet

from scripts import course_trial_transport as transport
from scripts.head_course_goal import raw_io


@pytest.mark.parametrize("keep_headers", [False, True])
def test_shared_responses_transport(tmp_path, keep_headers):
    archive = tmp_path / "response.raw.enc"
    headers = tmp_path / "headers.json"
    body = b'{"model":"deepseek-flash","input":"fixture"}'
    response = b'{"response":"unchanged"}'
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://93.184.216.34/responses"
        assert request.method == "POST" and request.content == body
        assert request.headers["host"] == request.extensions["sni_hostname"] == "api.deepseek.com"
        assert request.headers["authorization"] == "Bearer fixture"
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(429, stream=httpx.ByteStream(response))

    mock = httpx.MockTransport(handle)
    cipher = Fernet(Fernet.generate_key())
    target = transport.resolve_target(mock)
    observed = transport.send_and_seal(
        target,
        "fixture",
        body,
        archive,
        cipher,
        transport=mock,
        headers_path=headers if keep_headers else None,
    )
    assert len(calls) == 1 and observed == (429, "identity", response)
    assert response not in archive.read_bytes()
    assert raw_io.decrypt(archive, cipher) == response
    if keep_headers:
        assert headers.read_bytes() == b'{"encoding":"identity","http_status":429}'
    else:
        assert not headers.exists()
