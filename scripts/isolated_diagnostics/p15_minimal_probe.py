"""Seven sequential exact schema-only echoes. No teaching workflow, publishing, or restart API."""

import asyncio
import ipaddress
import math
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.provider_target import (
    ApprovedTarget,
    TargetPolicy,
    approve_target,
    is_public_address,
)
from scripts.isolated_diagnostics import p15_agent_pilot as pilot
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_minimal_probe_contract as contract
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    Refused,
    canonical,
    final_phase_validation_view,
    private_write,
    sha,
)

FLAGS = (
    "minimal_contract_A_D_accepted",
    "synthetic_two_provider_transfer_accepted",
    "bounded_metadata_accepted",
    "new_window_accepted",
    "unverified_limits_and_fee_waiver_accepted",
)


def check_grant(
    grant: dict[str, Any], package: str, *, now: float, current: bool = True
) -> None:
    if (
        grant.get("accepted") is not True
        or grant.get("scope") != "PHASE-1.5-T085"
        or grant.get("package_sha256") != package
        or grant.get("limits") != contract.LIMITS
        or not grant.get("human_message")
        or not grant.get("evidence_ref")
        or any(grant.get(k) is not True for k in FLAGS)
        or grant.get("fee_exception_human_message") != "接受本批费用例外并执行"
    ):
        raise Refused("EXACT_NEW_ROLE_APPROVAL_REQUIRED")
    start: Any = grant.get("window_started_epoch")
    end: Any = grant.get("deadline_epoch")
    if (
        any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
        or end - start != 900
        or not math.isfinite(now)
        or current
        and not start <= now < end
    ):
        raise Refused("ROLE_WINDOW_INVALID_OR_EXPIRED")


async def bounded_target(
    url: str, timeout: float, resolver: Callable[..., Any] | None
) -> ApprovedTarget:
    if url not in {r["url"] for r in wire.ROUTES.values()}:
        raise Refused("ROLE_TARGET_CHANGED")
    if resolver is not None:  # Offline tests only; the live CLI supplies no resolver.
        return approve_target(url, policy=TargetPolicy(), resolver=resolver)
    hostname = urlsplit(url).hostname
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-c",
        "import json,socket,sys; print(json.dumps(sorted({x[4][0] for x in "
        "socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)})))",
        str(hostname),
        env={},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(timeout):
            if process.stdout is None:
                raise Refused("DNS_PIPE_MISSING")
            raw = bytearray()
            while True:
                chunk = await process.stdout.read(16385 - len(raw))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > 16384:
                    raise Refused("DNS_RESPONSE_TOO_LARGE")
            if await process.wait() != 0:
                raise Refused("DNS_PROCESS_FAILURE")
            addresses = wire.strict_json(bytes(raw))
            if (
                type(addresses) is not list
                or not addresses
                or not all(type(a) is str for a in addresses)
            ):
                raise Refused("DNS_RESPONSE_INVALID")
            return approve_target(
                url, policy=TargetPolicy(), resolver=lambda *args: addresses
            )
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


def observe(name: str, body: dict[str, Any], raw: bytes) -> dict[str, Any]:
    view, phase = final_phase_validation_view(raw)
    reply = wire.strict_json(raw)
    text = reply.get("text") if isinstance(reply, dict) else None
    if text is not None and not isinstance(text, dict):
        raise Refused("ROLE_SCHEMA_ECHO_SHAPE")
    echo = text.get("format") if isinstance(text, dict) else None
    if echo is not None and not isinstance(echo, dict):
        raise Refused("ROLE_SCHEMA_ECHO_SHAPE")
    schema_echo = "unavailable"
    if isinstance(echo, dict):
        if (
            "name" in echo
            and echo["name"] != body["text"]["format"]["name"]
            or "type" in echo
            and echo["type"] != "json_schema"
            or "strict" in echo
            and echo["strict"] is not True
        ):
            raise Refused("ROLE_SCHEMA_ECHO_MISMATCH")
        if "schema" in echo:
            if canonical(echo["schema"]) != canonical(body["text"]["format"]["schema"]):
                raise Refused("ROLE_SCHEMA_ECHO_MISMATCH")
            schema_echo = "recognized"
    if schema_echo != "recognized":
        raise Refused("MINIMAL_SCHEMA_ECHO_UNAVAILABLE")
    result, observation = wire.validate(body, view, contract.ROLES[name])
    pilot.check_schema(result.value, contract.original_schemas()[name])
    contract.validate_local(name, dict(result.value), body)
    if canonical(result.value) != canonical(contract.FIXTURES[name]):
        raise Refused("SYNTHETIC_FIXTURE_MISMATCH")
    if (
        observation["reported_input_tokens"] > contract.CAPS[name][0]
        or observation["reported_total_output_tokens"] > contract.CAPS[name][1]
    ):
        raise Refused("ROLE_REPORTED_TOKEN_BUDGET")
    return {
        **observation,
        "role_schema_policy": contract.VERSION,
        "message_phase": phase,
        "phase_identity_verified": False,
        "original_response_preserved": True,
        "original_local_schema_verified": True,
        "schema_echo": schema_echo,
        "provider_schema_enforcement_verified": False,
        "teaching_evaluated": False,
    }


def replay(
    events: list[dict[str, Any]],
    package: str,
    grant: dict[str, Any],
    bodies: dict[str, bytes],
) -> dict[str, Any]:
    phase, name, previous, last_wall, last_elapsed = "new", None, None, None, -1.0
    reserved: list[str] = []
    sent: list[str] = []
    observed: list[str] = []
    validated: list[str] = []
    kinds: list[str] = []
    addresses: dict[str, Any] = {}
    status = None
    for index, row in enumerate(events):
        core = {k: v for k, v in row.items() if k != "digest"}
        if (
            type(row.get("seq")) is not int
            or row["seq"] != index
            or row.get("previous") != previous
            or row.get("digest") != sha(canonical(core))
            or phase == "terminal"
        ):
            raise Refused("ROLE_RECEIPT_CHAIN_OR_POST_STOP")
        previous = row["digest"]
        kind, data, wall, elapsed = (
            row["kind"],
            row["data"],
            row["epoch"],
            row["elapsed"],
        )
        if any(
            type(v) not in (int, float) or not math.isfinite(v) for v in (wall, elapsed)
        ):
            raise Refused("ROLE_RECEIPT_CLOCK")
        if (
            kind != "terminal" or data.get("outcome") == "roles_protocol_admitted"
        ) and (
            not grant["window_started_epoch"] <= wall < grant["deadline_epoch"]
            or not 0 <= elapsed < 900
            or elapsed < last_elapsed
            or last_wall is not None
            and wall < last_wall
        ):
            raise Refused("ROLE_RECEIPT_WINDOW_OR_ROLLBACK")
        last_wall, last_elapsed = wall, elapsed
        if kind == "started":
            if phase != "new" or data != dict(
                package_sha256=package, grant_sha256=sha(canonical(grant))
            ):
                raise Refused("ROLE_START_BINDING")
            phase = "ready"
        elif kind == "reserved":
            if (
                phase != "ready"
                or len(reserved) >= 7
                or len(validated) != len(reserved)
            ):
                raise Refused("ROLE_RESERVE_ORDER_OR_CHECKPOINT")
            expected = contract.ORDER[len(reserved)]
            if data != dict(name=expected, request_sha256=sha(bodies[expected])):
                raise Refused("ROLE_REQUEST_BINDING")
            name, phase = expected, "reserved"
            reserved.append(expected)
        elif kind == "target_pinned":
            if phase != "reserved" or data.get("name") != name:
                raise Refused("ROLE_PIN_ORDER")
            role = contract.ROLES[str(name)]
            if (
                data.get("hostname") != urlsplit(wire.ROUTES[role]["url"]).hostname
                or not data.get("addresses")
                or not all(
                    is_public_address(ipaddress.ip_address(a))
                    for a in data["addresses"]
                )
            ):
                raise Refused("ROLE_TARGET_CHANGED")
            if role in addresses and addresses[role] != data["addresses"]:
                raise Refused("ROLE_PIN_CHANGED")
            addresses[role] = data["addresses"]
            phase = "pinned"
        elif kind == "sent":
            if (
                phase != "pinned"
                or set(data) != {"name", "transport_kind"}
                or data["name"] != name
                or name in sent
                or data["transport_kind"] not in ("real", "mock")
            ):
                raise Refused("ROLE_SEND_ORDER_OR_DUPLICATE")
            sent.append(str(name))
            kinds.append(data["transport_kind"])
            phase = "sent"
        elif kind == "observed":
            if (
                phase != "sent"
                or data.get("name") != name
                or type(data.get("status")) is not int
                or not 100 <= data["status"] <= 599
            ):
                raise Refused("ROLE_OBSERVE_ORDER")
            observed.append(str(name))
            status, phase = data["status"], "observed"
        elif kind == "validated":
            if phase != "observed" or status != 200 or data.get("name") != name:
                raise Refused("ROLE_VALIDATE_ORDER")
            validated.append(str(name))
            phase = "ready"
        elif kind == "terminal":
            outcome = data.get("outcome")
            if phase == "new" or outcome not in (
                "roles_protocol_admitted",
                "inconclusive_stopped",
            ):
                raise Refused("ROLE_TERMINAL_OUTCOME")
            if outcome == "roles_protocol_admitted" and validated != list(
                contract.ORDER
            ):
                raise Refused("ALL_ROLES_REQUIRED")
            phase = "terminal"
        else:
            raise Refused("UNKNOWN_ROLE_EVENT")
    return dict(
        phase=phase,
        reserved=reserved,
        sent=sent,
        observed=observed,
        validated=validated,
        transport_kinds=kinds,
    )


class Runner:
    def __init__(
        self,
        output: Path,
        package: str,
        grant: dict[str, Any],
        keys: dict[str, str],
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.output, self.package, self.grant, self.keys = output, package, grant, keys
        self.clock, self.monotonic, self.origin_mono = clock, monotonic, monotonic()
        self.bodies = contract.bodies()
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, data: dict[str, Any]) -> None:
        wall, elapsed = self.clock(), self.monotonic() - self.origin_mono
        if kind == "terminal" and (
            not math.isfinite(wall) or not math.isfinite(elapsed)
        ):
            wall, elapsed = self.events[-1]["epoch"], self.events[-1]["elapsed"]
            data = dict(
                outcome="inconclusive_stopped",
                reason="CLOCK_INVALID",
                clock_source="last_valid_receipt_no_success_credit",
            )
        core = dict(
            seq=len(self.events),
            previous=self.events[-1]["digest"] if self.events else None,
            kind=kind,
            data=data,
            epoch=wall,
            elapsed=elapsed,
        )
        row = {**core, "digest": sha(canonical(core))}
        replay([*self.events, row], self.package, self.grant, self.bodies)
        private_write(self.output / f"event-{len(self.events):03}.json", canonical(row))
        self.events.append(row)

    def remaining(self) -> float:
        wall, elapsed = self.clock(), self.monotonic() - self.origin_mono
        replay(self.events, self.package, self.grant, self.bodies)
        if (
            not math.isfinite(wall)
            or not math.isfinite(elapsed)
            or elapsed < 0
            or self.events
            and (
                wall < self.events[-1]["epoch"] or elapsed < self.events[-1]["elapsed"]
            )
        ):
            raise Refused("ROLE_CLOCK_ROLLBACK")
        seconds = min(self.grant["deadline_epoch"] - wall, 900 - elapsed)
        if seconds <= 0:
            raise Refused("ROLE_WINDOW_EXHAUSTED")
        return float(seconds)

    async def run(
        self,
        *,
        transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
        resolver: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        check_grant(self.grant, self.package, now=self.clock())
        if set(self.keys) != set(wire.ROUTES) or any(
            type(k) is not str
            or len(k) < 16
            or not k.isascii()
            or any(c.isspace() for c in k)
            for k in self.keys.values()
        ):
            raise Refused("ROLE_EXACT_KEYS_REQUIRED")
        if any(path.is_symlink() for path in (self.output, *self.output.parents)):
            raise Refused("MINIMAL_OUTPUT_SYMLINK")
        self.output.mkdir(mode=0o700, exist_ok=False)
        private_write(self.output / "grant.json", canonical(self.grant))
        self.record(
            "started",
            dict(package_sha256=self.package, grant_sha256=sha(canonical(self.grant))),
        )
        targets: dict[str, ApprovedTarget] = {}
        outcome, reason = "inconclusive_stopped", None
        try:
            for name in contract.ORDER:
                self.remaining()
                role, raw = contract.ROLES[name], self.bodies[name]
                private_write(self.output / f"{name}-request.json", raw)
                self.record("reserved", dict(name=name, request_sha256=sha(raw)))
                if role not in targets:
                    targets[role] = await bounded_target(
                        wire.ROUTES[role]["url"], min(9.0, self.remaining()), resolver
                    )
                target = targets[role]
                self.record(
                    "target_pinned",
                    dict(
                        name=name,
                        hostname=target.hostname,
                        addresses=list(target.addresses),
                    ),
                )
                ip = ipaddress.ip_address(target.connect_ip)
                host = f"[{ip}]" if ip.version == 6 else str(ip)
                pinned = urlunsplit(
                    ("https", f"{host}:443", urlsplit(target.url).path, "", "")
                )
                transport = (
                    transport_factory()
                    if transport_factory
                    else httpx.AsyncHTTPTransport(retries=0)
                )
                if not isinstance(
                    transport, (httpx.MockTransport, httpx.AsyncHTTPTransport)
                ):
                    raise Refused("ROLE_TRANSPORT_UNCLASSIFIED")
                transport_kind = (
                    "mock" if isinstance(transport, httpx.MockTransport) else "real"
                )
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=min(60.0, self.remaining()),
                ) as client:
                    request = client.build_request(
                        "POST",
                        pinned,
                        content=raw,
                        headers={
                            "Host": target.hostname,
                            "Content-Type": "application/json",
                            "Authorization": "Bearer " + self.keys[role],
                        },
                    )
                    request.extensions["sni_hostname"] = target.hostname
                    self.record("sent", dict(name=name, transport_kind=transport_kind))
                    async with asyncio.timeout(min(60.0, self.remaining())):
                        response = await client.send(
                            request, stream=True, follow_redirects=False
                        )
                        try:
                            status = response.status_code
                            private_write(
                                self.output / f"{name}-status.json",
                                canonical({"http_status": status}),
                            )
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > 262144:
                                    raise Refused("ROLE_RESPONSE_BYTES")
                        finally:
                            await response.aclose()
                received = bytes(content)
                if any(key.encode() in received for key in self.keys.values()):
                    raise Refused("ROLE_SECRET_ECHO_REFUSED")
                private_write(self.output / f"{name}-response.bin", received)
                self.record(
                    "observed",
                    dict(name=name, status=status, response_sha256=sha(received)),
                )
                if status != 200:
                    raise Refused("ROLE_HTTP_STATUS")
                observation = observe(name, wire.strict_json(raw), received)
                self.record("validated", dict(name=name, observation=observation))
            outcome = "roles_protocol_admitted"
        except Exception as error:
            reason = (
                str(error)
                if isinstance(error, (Refused, pilot.PilotError))
                else "ROLE_LOCAL_PROTOCOL_OR_TRANSPORT"
            )
        try:
            self.record("terminal", dict(outcome=outcome, reason=reason))
        except Refused:
            self.record(
                "terminal",
                dict(
                    outcome="inconclusive_stopped", reason="ROLE_LATE_TERMINAL_OR_CLOCK"
                ),
            )
        result = verify_results(
            self.output,
            self.package,
            self.grant,
            require_real=transport_factory is None,
        )
        private_write(self.output / "summary.json", canonical(result))
        return result


def verify_results(
    output: Path, package: str, grant: dict[str, Any], *, require_real: bool = True
) -> dict[str, Any]:
    check_grant(grant, package, now=0.0, current=False)
    if (
        not output.is_dir()
        or any(p.is_symlink() for p in (output, *output.parents))
        or stat.S_IMODE(output.stat().st_mode) != 0o700
    ):
        raise Refused("ROLE_RESULT_DIRECTORY")
    for file in output.iterdir():
        if (
            not re.fullmatch(
                r"grant\.json|summary\.json|event-[0-9]{3}\.json|"
                r"S[1-7]-(?:request\.json|status\.json|response\.bin)",
                file.name,
            )
            or file.is_symlink()
            or not file.is_file()
            or file.stat().st_size > 262144
            or stat.S_IMODE(file.stat().st_mode) != 0o600
        ):
            raise Refused("ROLE_RESULT_FILE")
    if (output / "grant.json").read_bytes() != canonical(grant):
        raise Refused("ROLE_RESULT_GRANT_DRIFT")
    paths = sorted(output.glob("event-*.json"))
    if len(paths) > 50 or [p.name for p in paths] != [
        f"event-{i:03}.json" for i in range(len(paths))
    ]:
        raise Refused("ROLE_RECEIPT_GAP")
    events = [wire.strict_json(p.read_bytes()) for p in paths]
    bodies = contract.bodies()
    state = replay(events, package, grant, bodies)
    if require_real and any(k != "real" for k in state["transport_kinds"]):
        raise Refused("ROLE_MOCK_NOT_REAL")
    observations = {}
    for name in state["reserved"]:
        if (output / f"{name}-request.json").read_bytes() != bodies[name]:
            raise Refused("ROLE_RESULT_REQUEST_DRIFT")
    for event in events:
        data = event["data"]
        if event["kind"] == "observed":
            raw = (output / f"{data['name']}-response.bin").read_bytes()
            status = wire.strict_json(
                (output / f"{data['name']}-status.json").read_bytes()
            )
            if sha(raw) != data["response_sha256"] or status != {
                "http_status": data["status"]
            }:
                raise Refused("ROLE_RESULT_RESPONSE_DRIFT")
        elif event["kind"] == "validated":
            name = data["name"]
            raw = (output / f"{name}-response.bin").read_bytes()
            observation = observe(name, wire.strict_json(bodies[name]), raw)
            if data != dict(name=name, observation=observation):
                raise Refused("ROLE_RESULT_VALIDATION_DRIFT")
            observations[name] = observation
    outcome = (
        events[-1]["data"]["outcome"]
        if state["phase"] == "terminal"
        else "incomplete_no_restart"
    )
    result = dict(
        package_sha256=package,
        state=state["phase"],
        outcome=outcome,
        protocol_admission_complete=outcome == "roles_protocol_admitted",
        evidence_verified=True,
        recorded_window_verified=True,
        planned_roles=7,
        admitted_roles=len(observations),
        observations=observations,
        requests_reserved=len(state["reserved"]),
        dispatch_markers=len(state["sent"]),
        http_responses_recorded=len(state["observed"]),
        transport_kinds={
            k: state["transport_kinds"].count(k)
            for k in sorted(set(state["transport_kinds"]))
        },
        unknown_protocol_or_usage=len(state["sent"]) - len(observations),
        unrun_roles=7 - len(state["sent"]),
        unattempted_roles=7 - len(state["reserved"]),
        actual_invoice=None,
        actual_currency=None,
        actual_input_upper_bound_verified=False,
        clock_source_independently_attested=False,
        teaching_evaluated=False,
        course_requests_authorized=False,
        T038_completed=False,
        restart_authorized=False,
    )
    if (output / "summary.json").exists() and (
        output / "summary.json"
    ).read_bytes() != canonical(result):
        raise Refused("ROLE_RESULT_SUMMARY_DRIFT")
    return result
