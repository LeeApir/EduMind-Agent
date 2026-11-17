"""Exec-isolated, watchdog-supervised synthetic Responses transport.

All dispatch in this module is MockTransport with synthetic DNS and keys.
It is not a real Provider authorization or a general-purpose code sandbox.
"""

import asyncio
import base64
from collections.abc import AsyncIterable
import hashlib
import json
import os
from pathlib import Path
import select
import ssl
import subprocess
import sys
import threading
import time
from typing import Any, AsyncIterator, cast
from urllib.parse import urlsplit, urlunsplit

import httpx
import httpcore

from app.core.provider_target import TargetPolicy, approve_target
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_synthetic_guard_v1 as guard
from scripts.isolated_diagnostics import p15_synthetic_fixtures_v1 as fixtures
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

ROOT = Path(__file__).resolve().parents[2]
VERSION = "supervised-synthetic-responses-v1"
MAX_REQUEST = 12_000_000
MAX_JOB = 17_000_000
MAX_RESULT = 3_000_000
STOP_GRACE = 1.0
_SCENARIOS = frozenset({
    "chain", "delayed_dns", "delayed_dispatch", "slow_stream", "encoded_key",
    "deep_encoded_key", "http_error", "redirect", "oversize", "invalid_json",
})


def _env() -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join((str(ROOT / "backend"), str(ROOT))),
        "LANG": "C.UTF-8",
    }


class SupervisedMockTransport(httpx.AsyncBaseTransport):
    """One active synthetic child; a separate watcher owns and reaps it."""

    def __init__(
        self,
        credentials: dict[str, str],
        *,
        scenario: str = "chain",
        marker_dir: Path | None = None,
        wall_seconds: float = 59.0,
    ) -> None:
        c.require(
            set(credentials) == {row["credential_env"] for row in wire.ROUTES.values()}
            and all(type(value) is str and value.startswith("synthetic-") for value in credentials.values())
            and scenario in _SCENARIOS
            and 0 < wall_seconds <= 59.0,
            "SUPERVISOR_SYNTHETIC_ONLY",
        )
        self._keys = dict(credentials)
        self._routes = json.loads(json.dumps(wire.ROUTES))
        self._policy_bytes = canonical(
            {"scenario": scenario, "marker_dir": str(marker_dir.absolute()) if marker_dir else None,
             "wall_seconds": float(wall_seconds), "stop_grace": STOP_GRACE}
        )
        self._bound_policy: bytes | None = None
        self._condition = threading.Condition()
        self._stopped = False
        self._spawning = False
        self._process: subprocess.Popen[bytes] | None = None
        self._live_fd: int | None = None
        self._ack_fd: int | None = None
        self._stop_fd: int | None = None
        self._exit_confirmed = False
        self._exit_unconfirmed = False
        self.audit: list[dict[str, Any]] = []
        self.offline_only = True

    def policy(self) -> dict[str, Any]:
        return dict(json.loads(self._policy_bytes))

    def bind_policy(self, policy: dict[str, Any]) -> None:
        c.require(self._bound_policy is None and canonical(policy) == self._policy_bytes, "SUPERVISOR_POLICY")
        self._bound_policy = self._policy_bytes

    def _verify_policy(self) -> None:
        c.require(self._bound_policy is not None and self._policy_bytes == self._bound_policy, "SUPERVISOR_POLICY")

    @property
    def scenario(self) -> str:
        return str(self.policy()["scenario"])

    @property
    def marker_dir(self) -> Path | None:
        value = self.policy()["marker_dir"]
        return Path(value) if value is not None else None

    @property
    def wall_seconds(self) -> float:
        return float(self.policy()["wall_seconds"])

    def ensure_request_safe(self, body: bytes) -> None:
        guard.check(body, list(self._keys.values()))

    def check_response_safe(self, raw: bytes) -> None:
        guard.check(raw, list(self._keys.values()))

    def _confirm_exit(self, process: subprocess.Popen[bytes]) -> bool:
        """A dead watcher is insufficient: require its post-reap acknowledgement."""
        with self._condition:
            if self._exit_confirmed:
                return True
            if self._exit_unconfirmed or self._ack_fd is None:
                return False
            readable, _, _ = select.select([self._ack_fd], [], [], 0)
            if readable and os.read(self._ack_fd, 1) == b"A":
                self._exit_confirmed = True
                return True
            self._exit_unconfirmed = True
        # The watcher may already be reaped and its PID reused. Do not signal
        # a stale process group; preserve the unconfirmed outcome instead.
        return False

    def stop_and_confirm(self, timeout: float = STOP_GRACE) -> bool:
        """Stop watchdog, which kills and reaps its child before exiting."""
        deadline = time.monotonic() + timeout
        with self._condition:
            self._stopped = True
            while self._spawning:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._condition.wait(left)
            process = self._process
        if process is None:
            return not self._exit_unconfirmed
        if process.poll() is None:
            try:
                with self._condition:
                    if self._stop_fd is not None:
                        os.set_blocking(self._stop_fd, False)
                        os.write(self._stop_fd, b"S")
            except OSError:
                pass
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                # No signal to a possibly reaped/reused PID. Preserve unknown.
                with self._condition:
                    self._exit_unconfirmed = True
                return False
        return self._confirm_exit(process)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self._send(request)
        except c.ContractError:
            raise
        except Exception:
            raise c.ContractError("SUPERVISOR_UNKNOWN") from None

    def _send(self, request: httpx.Request) -> httpx.Response:
        self._verify_policy()
        routes = self._routes
        roles = [role for role, route in routes.items() if str(request.url) == route["url"]]
        c.require(
            routes == wire.ROUTES
            and request.method == "POST"
            and len(roles) == 1
            and "authorization" not in request.headers
            and len(request.content) <= MAX_REQUEST,
            "SUPERVISOR_TARGET",
        )
        role = roles[0]
        stage = request.extensions.get("edumind_stage")
        ordinal = request.extensions.get("edumind_ordinal")
        arm = request.extensions.get("edumind_arm")
        c.require(type(stage) is str and type(ordinal) is int and arm in ("B", "C"), "SUPERVISOR_STAGE")
        job = canonical(
            dict(
                role=role,
                role_key=self._keys[routes[role]["credential_env"]],
                target=routes[role]["url"],
                arm=arm,
                stage=stage,
                ordinal=ordinal,
                request_b64=base64.b64encode(request.content).decode("ascii"),
                scenario=self.scenario,
                marker_dir=str(self.marker_dir) if self.marker_dir is not None else None,
            )
        )
        c.require(len(job) <= MAX_JOB, "SUPERVISOR_REQUEST")
        with self._condition:
            c.require(not self._stopped and self._process is None, "SUPERVISOR_STOPPED")
            self._spawning = True
            self._exit_confirmed = False
            self._exit_unconfirmed = False
        permit_r = permit_w = live_r = live_w = ready_r = ready_w = ack_r = ack_w = stop_r = stop_w = -1
        process: subprocess.Popen[bytes] | None = None
        try:
            permit_r, permit_w = os.pipe()
            live_r, live_w = os.pipe()
            ready_r, ready_w = os.pipe()
            ack_r, ack_w = os.pipe()
            stop_r, stop_w = os.pipe()
            process = subprocess.Popen(
                [
                    sys.executable, "-m", "scripts.isolated_diagnostics.p15_supervised_mock_v1",
                    "--watchdog", str(permit_r), str(live_r), str(ready_w), str(ack_w), str(stop_r),
                    str(time.monotonic() + self.wall_seconds),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=ROOT,
                env=_env(),
                close_fds=True,
                pass_fds=(permit_r, live_r, ready_w, ack_w, stop_r),
                start_new_session=True,
            )
            with self._condition:
                self._process = process
                self._live_fd = live_w
                self._ack_fd = ack_r
                self._stop_fd = stop_w
                self._spawning = False
                self._condition.notify_all()
            os.close(permit_r)
            permit_r = -1
            os.close(live_r)
            live_r = -1
            os.close(ready_w)
            ready_w = -1
            os.close(ack_w)
            ack_w = -1
            os.close(stop_r)
            stop_r = -1
            available, _, _ = select.select([ready_r], [], [], self.wall_seconds)
            c.require(bool(available) and os.read(ready_r, 1) == b"R", "SUPERVISOR_NOT_READY")
            with self._condition:
                self._verify_policy()
                c.require(self._routes == wire.ROUTES, "SUPERVISOR_TARGET")
                c.require(not self._stopped, "SUPERVISOR_STOPPED")
                # One byte fits in an empty nonblocking pipe and is issued only
                # under the same lock as stop; before this there is no dispatch.
                os.set_blocking(permit_w, False)
                c.require(os.write(permit_w, b"G") == 1, "SUPERVISOR_PERMIT")
            os.close(permit_w)
            permit_w = -1
            try:
                output, _ = process.communicate(input=job, timeout=self.wall_seconds)
            except subprocess.TimeoutExpired:
                confirmed = self.stop_and_confirm(STOP_GRACE)
                raise c.ContractError("SUPERVISOR_TIMEOUT" if confirmed else "STOP_UNCONFIRMED") from None
            c.require(
                self._confirm_exit(process) and process.returncode == 0 and len(output) <= MAX_RESULT,
                "SUPERVISOR_UNKNOWN",
            )
            result = json.loads(output)
            c.require(type(result) is dict and set(result) == {"status", "body_b64", "proof"}, "SUPERVISOR_RESULT")
            status = result["status"]
            body = base64.b64decode(result["body_b64"], validate=True)
            proof = result["proof"]
            c.require(
                type(status) is int and 100 <= status <= 599 and len(body) <= 2 * 1024 * 1024
                and type(proof) is dict
                and set(proof) == {"pid", "role", "stage", "ordinal", "target", "ip", "host", "sni", "request_sha256", "credential_roles", "provider_env_present", "transport_kind", "tls_verification_configured", "retries"}
                and type(proof["pid"]) is int and proof["pid"] > 0
                and proof["role"] == role and proof["stage"] == stage and proof["ordinal"] == ordinal
                and proof["target"] == routes[role]["url"] and proof["ip"] == "1.1.1.1"
                and proof["host"] == proof["sni"] == urlsplit(routes[role]["url"]).hostname
                and proof["request_sha256"] == hashlib.sha256(request.content).hexdigest()
                and proof["credential_roles"] == [role] and proof["provider_env_present"] is False
                and proof["transport_kind"] == "httpx-async-http-transport-core-intercepted"
                and proof["tls_verification_configured"] is True and proof["retries"] == 0,
                "SUPERVISOR_RESULT",
            )
            self.audit.append(dict(proof))
            return httpx.Response(status, stream=httpx.ByteStream(body))
        finally:
            if process is not None and process.poll() is not None:
                self._confirm_exit(process)
            with self._condition:
                self._spawning = False
                self._condition.notify_all()
                if process is not None and process.poll() is not None and self._process is process:
                    self._process = None
                    self._live_fd = None
                    self._ack_fd = None
                    self._stop_fd = None
            for fd in (permit_r, permit_w, live_r, live_w, ready_r, ready_w, ack_r, ack_w, stop_r, stop_w):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    async def aclose(self) -> None:
        return None


def _watchdog(permit_fd: int, live_fd: int, ready_fd: int, ack_fd: int, stop_fd: int, deadline: float) -> None:
    import signal as sig

    stopping = [False]
    sig.signal(sig.SIGTERM, lambda *_args: stopping.__setitem__(0, True))
    worker = subprocess.Popen(
        [sys.executable, "-m", "scripts.isolated_diagnostics.p15_supervised_mock_v1", "--worker", str(permit_fd)],
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=subprocess.DEVNULL,
        env=_env(),
        cwd=ROOT,
        close_fds=True,
        pass_fds=(permit_fd,),
    )
    os.close(permit_fd)
    os.write(ready_fd, b"R")
    os.close(ready_fd)
    try:
        while worker.poll() is None:
            if stopping[0] or time.monotonic() >= deadline:
                worker.kill()
                worker.wait()
                raise SystemExit(2)
            readable, _, _ = select.select([live_fd, stop_fd], [], [], 0.05)
            if (live_fd in readable and os.read(live_fd, 1) == b"") or (
                stop_fd in readable and os.read(stop_fd, 1) in (b"S", b"")
            ):
                worker.kill()
                worker.wait()
                raise SystemExit(2)
        worker.wait()
        raise SystemExit(worker.returncode)
    finally:
        os.close(live_fd)
        os.close(stop_fd)
        if worker.poll() is None:
            worker.kill()
            worker.wait()
        os.write(ack_fd, b"A")
        os.close(ack_fd)


async def _synthetic_response(job: dict[str, Any], body: bytes) -> tuple[int, bytes, dict[str, Any]]:
    route = wire.ROUTES[job["role"]]
    request_body = wire.strict_json(body)
    c.require(
        type(request_body) is dict
        and request_body.get("model") == route["model"]
        and job["target"] == route["url"]
        and job["role_key"].startswith("synthetic-"),
        "SYNTHETIC_TARGET",
    )
    payload = json.loads(request_body["input"][1]["content"])
    scenario = job["scenario"]
    if job["marker_dir"] is not None:
        (Path(job["marker_dir"]) / "worker-pid").write_text(str(os.getpid()))
    if scenario == "delayed_dns":
        await asyncio.sleep(10)
    if scenario == "delayed_dispatch":
        if job["marker_dir"] is not None:
            (Path(job["marker_dir"]) / "before-dispatch").write_text("ready")
        await asyncio.sleep(10)
    target = approve_target(route["url"], policy=TargetPolicy(), resolver=lambda _host, _port: ("1.1.1.1",))
    parts = urlsplit(route["url"])
    pinned_url = urlunsplit(("https", f"{target.connect_ip}:443", parts.path, "", ""))

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"partial"
            await asyncio.sleep(10)
            yield b"late"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        c.require(
            request.url.host == target.connect_ip
            and request.headers["host"] == target.hostname
            and request.extensions["sni_hostname"] == target.hostname
            and request.headers["authorization"] == "Bearer " + job["role_key"]
            and request.content == body,
            "SYNTHETIC_BINDING",
        )
        if job["marker_dir"] is not None:
            (Path(job["marker_dir"]) / "dispatched").write_text("mock")
            with (Path(job["marker_dir"]) / "dispatch-count").open("a") as evidence:
                evidence.write("1\n")
        if scenario == "slow_stream":
            return httpx.Response(200, stream=SlowStream())
        if scenario == "http_error":
            return httpx.Response(503, stream=httpx.ByteStream(b'{"error":"synthetic"}'))
        if scenario == "redirect":
            return httpx.Response(
                302, headers={"Location": "https://invalid.example/elsewhere"},
                stream=httpx.ByteStream(b'{"error":"redirect"}'),
            )
        if scenario == "oversize":
            return httpx.Response(200, stream=httpx.ByteStream(b"x" * (2 * 1024 * 1024 + 1)))
        if scenario == "invalid_json":
            return httpx.Response(200, stream=httpx.ByteStream(b"synthetic-invalid-json"))
        if scenario == "encoded_key":
            encoded = "".join("\\\\u%04x" % ord(char) for char in job["role_key"])
            reply = canonical({"output": [{"content": [{"text": "echo " + encoded}]}]})
            return httpx.Response(200, stream=httpx.ByteStream(reply))
        if scenario == "deep_encoded_key":
            encoded = "".join("\\u%04x" % ord(char) for char in job["role_key"])
            for _ in range(4):
                encoded = encoded.replace("\\", "\\u005c")
            reply = canonical({"output": [{"content": [{"text": "echo " + encoded}]}]})
            return httpx.Response(200, stream=httpx.ByteStream(reply))
        if "cells" in payload:
            first = job["ordinal"] == (1 if job["arm"] == "B" else 2)
            paragraph = next(cell for cell in payload["cells"] if cell["kind"] == "paragraph")
            value: dict[str, Any] = dict(
                candidate_id=payload["candidate_id"], verdict="revise" if first else "pass", uncertainty="", issues=[]
            )
            if first:
                value["issues"] = [dict(
                    severity="minor", area="difficulty", target_id=paragraph["id"],
                    evidence_quote=paragraph["text"][:4], reason="需要补充解释。"
                )]
        elif "original" in payload:
            value = payload["original"]
            value["paragraphs"][0]["text"] += " 补充解释。"
        elif job["stage"] == "C_plan":
            value = dict(spec_id=payload["spec_id"], objective_ids=list(c.GOALS))
        else:
            value = fixtures.content() if job["arm"] == "C" else fixtures.baseline(payload["spec"])
        return httpx.Response(200, stream=httpx.ByteStream(canonical(fixtures.envelope(request_body, value))))

    class OfflineCorePool:
        async def __aenter__(self) -> "OfflineCorePool":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            await self.aclose()

        async def handle_async_request(self, request: httpcore.Request) -> httpcore.Response:
            c.require(
                request.url.scheme == b"https"
                and request.url.host == target.connect_ip.encode("ascii")
                and request.url.target == parts.path.encode("ascii"),
                "SYNTHETIC_BINDING",
            )
            received = bytearray()
            async for chunk in cast(AsyncIterable[bytes], request.stream):
                c.require(len(received) + len(chunk) <= MAX_REQUEST, "SYNTHETIC_REQUEST_SIZE")
                received.extend(chunk)
            converted = httpx.Request(
                request.method.decode("ascii"), pinned_url, content=bytes(received),
                headers=request.headers, extensions=request.extensions,
            )
            reply = mock_handler(converted)
            return httpcore.Response(reply.status_code, headers=reply.headers.raw, content=reply.stream)

        async def aclose(self) -> None:
            return None

    actual_httpx = httpx.AsyncHTTPTransport(retries=0, trust_env=False, verify=True)
    pool = actual_httpx._pool
    context = pool._ssl_context
    c.require(context is not None, "SYNTHETIC_TRANSPORT_CONFIG")
    assert context is not None
    c.require(
        pool._retries == 0 and context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname,
        "SYNTHETIC_TRANSPORT_CONFIG",
    )
    await actual_httpx.aclose()
    # Exercise the actual HTTPX adapter while replacing its lower-level pool;
    # no DNS or socket operation is permitted in this synthetic child.
    setattr(actual_httpx, "_pool", OfflineCorePool())
    async with httpx.AsyncClient(
        transport=actual_httpx, trust_env=False, follow_redirects=False
    ) as client:
        outgoing = client.build_request(
            "POST", pinned_url, content=body,
            headers={"Host": target.hostname, "Authorization": "Bearer " + job["role_key"], "Accept-Encoding": "identity"},
        )
        outgoing.extensions["sni_hostname"] = target.hostname
        incoming = await client.send(outgoing, stream=True, follow_redirects=False)
        chunks = bytearray()
        try:
            async for chunk in incoming.aiter_raw():
                c.require(len(chunks) + len(chunk) <= 2 * 1024 * 1024, "SYNTHETIC_RESPONSE_SIZE")
                chunks.extend(chunk)
            return incoming.status_code, bytes(chunks), dict(
                pid=os.getpid(), role=job["role"], stage=job["stage"], ordinal=job["ordinal"],
                target=route["url"], ip=target.connect_ip, host=target.hostname, sni=target.hostname,
                request_sha256=hashlib.sha256(body).hexdigest(), credential_roles=[job["role"]],
                provider_env_present=any(name in os.environ for name in (r["credential_env"] for r in wire.ROUTES.values())),
                transport_kind="httpx-async-http-transport-core-intercepted", tls_verification_configured=True, retries=0,
            )
        finally:
            await incoming.aclose()


def _worker(permit_fd: int) -> None:
    import socket

    def deny(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("synthetic transport forbids network")

    socket.getaddrinfo = deny
    setattr(socket.socket, "connect", deny)
    if os.read(permit_fd, 1) != b"G":
        raise SystemExit(2)
    os.close(permit_fd)
    raw = sys.stdin.buffer.read(MAX_JOB + 1)
    c.require(len(raw) <= MAX_JOB, "SYNTHETIC_JOB")
    job = json.loads(raw)
    c.require(type(job) is dict and job.get("scenario") in _SCENARIOS, "SYNTHETIC_JOB")
    body = base64.b64decode(job["request_b64"], validate=True)
    status, result, proof = asyncio.run(_synthetic_response(job, body))
    output = canonical({"status": status, "body_b64": base64.b64encode(result).decode("ascii"), "proof": proof})
    c.require(len(output) <= MAX_RESULT, "SYNTHETIC_RESPONSE_SIZE")
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    if len(sys.argv) == 8 and sys.argv[1] == "--watchdog":
        _watchdog(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), float(sys.argv[7]))
    elif len(sys.argv) == 3 and sys.argv[1] == "--worker":
        _worker(int(sys.argv[2]))
    else:
        raise SystemExit(2)
