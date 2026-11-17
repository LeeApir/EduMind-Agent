"""One foreground Responses exchange with the existing encrypted collector."""

import ipaddress
from pathlib import Path

import httpx

from app.core.provider_target import TargetPolicy, approve_target
from app.services.free_course_snapshots import canonical
from scripts import head_course_deepseek_wire as direct


def resolve_target(transport):
    options = (
        {"resolver": lambda _host, _port: ["93.184.216.34"]}
        if isinstance(transport, httpx.MockTransport)
        else {}
    )
    return approve_target(direct.ENDPOINT, policy=TargetPolicy(), **options)


def send_and_seal(
    target,
    key: str,
    request: bytes,
    archive: Path,
    cipher,
    *,
    transport,
    headers_path=None,
):
    # Import lazily so historical entry points can continue exporting the original collector.
    from scripts.head_course_goal import raw_io

    ip = ipaddress.ip_address(target.connect_ip)
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    with (
        httpx.Client(
            transport=transport,
            timeout=direct.IO_TIMEOUT,
            trust_env=False,
            follow_redirects=False,
        ) as client,
        client.stream(
            "POST",
            f"https://{host}:443/responses",
            content=request,
            extensions={"sni_hostname": target.hostname},
            headers={
                "Host": target.hostname,
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        ) as response,
    ):
        status = response.status_code
        encoding = response.headers.get("content-encoding", "identity")
        if headers_path is not None:
            raw_io.exclusive(
                headers_path, canonical(dict(http_status=status, encoding=encoding))
            )
        raw = raw_io.collect(response, archive, cipher)
    return status, encoding, raw
