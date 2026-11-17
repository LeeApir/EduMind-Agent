"""Isolated p02: known final-answer phase metadata. Original p01 source remains unchanged."""

import asyncio
from copy import deepcopy
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.provider_target import ApprovedTarget, TargetPolicy, approve_target
from scripts.isolated_diagnostics import p15_pilot_wire as wire

URL = "https://api.deepseek.com/responses"
KEY_NAME = "EDUMIND_DEEPSEEK_COMPAT_API_KEY"
ENVELOPE_POLICY = "synthetic-final-phase-v1"
LIMITS = dict(requests=2, input_reservation=8192, output_reservation=64,
              fee_cap=None, wall_seconds=90, per_request_seconds=25,
              dns_seconds=9, max_output_tokens=32, request_bytes=1024, response_bytes=65536)
EXPECTED = {"kind": "show_state"}
MISSING_TYPE_ERROR = "one of `type`, `anyOf`, `$ref` field is required"


class Refused(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def request_pair() -> dict[str, dict[str, Any]]:
    typed: dict[str, Any] = dict(
        model="deepseek-flash", reasoning={"effort": "none"}, temperature=0.2,
        stream=False, store=False, max_output_tokens=32,
        input=[dict(role="system", content="Synthetic compatibility check. No tools, files, "
                    "network, learner facts, or course content."),
               dict(role="user", content='Return exactly {"kind":"show_state"}.')],
        text={"format": dict(type="json_schema", name="edumind_schema_pair", strict=True,
              schema=dict(type="object", properties={"kind": dict(type="string", enum=[
                  "show_state", "highlight_code", "advance_step"])},
                  required=["kind"], additionalProperties=False))},
    )
    untyped = deepcopy(typed)
    del untyped["text"]["format"]["schema"]["properties"]["kind"]["type"]
    return {"S1": typed, "S2": untyped}


def check_grant(grant: dict[str, Any], package: str, *, now: float,
                require_current: bool = True) -> None:
    if (grant.get("accepted") is not True or grant.get("scope") != "PHASE-1.5-T076"
            or grant.get("package_sha256") != package or grant.get("limits") != LIMITS
            or not grant.get("human_message") or not grant.get("evidence_ref")
            or any(grant.get(k) is not True for k in (
                "synthetic_only_accepted", "conditional_second_request_accepted",
                "new_window_accepted", "unverified_limits_and_fee_waiver_accepted"))):
        raise Refused("EXACT_NEW_APPROVAL_REQUIRED")
    start: Any = grant.get("window_started_epoch")
    end: Any = grant.get("deadline_epoch")
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
            or end - start != 90 or not math.isfinite(now)
            or require_current and not start <= now < end):
        raise Refused("WINDOW_INVALID_OR_EXPIRED")


def private_write(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(raw)
        file.flush()
        os.fsync(file.fileno())


def final_phase_validation_view(raw: bytes) -> tuple[bytes, str | None]:
    """Never alter stored raw bytes; only recognize the observed final-answer metadata value."""
    if len(raw) > 65536:
        raise Refused("RESPONSE_TOO_LARGE")
    value = wire.strict_json(raw)
    phase = None
    if isinstance(value, dict):
        if "phase" in value:
            raise Refused("PHASE_LOCATION")
        items = value.get("output")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and "phase" in item:
                    if item.get("type") != "message" or item["phase"] != "final_answer":
                        raise Refused("GENERATION_PHASE_UNRECOGNIZED")
                    phase = item.pop("phase")
    return (canonical(value) if phase is not None else raw), phase


def success_observation(body: dict[str, Any], raw: bytes) -> dict[str, Any]:
    view, phase = final_phase_validation_view(raw)
    result, observation = wire.validate(body, view, "generation")
    observation.update(envelope_policy=ENVELOPE_POLICY, generation_phase=phase,
                       original_response_preserved=True, phase_identity_verified=False)
    if result.value != EXPECTED:
        raise Refused("EXPECTED_SYNTHETIC_JSON_MISSING")
    if observation["reported_input_tokens"] > 4096:
        raise Refused("REPORTED_INPUT_OVER_RESERVATION")
    if observation["reported_total_output_tokens"] > 32:
        raise Refused("REPORTED_OUTPUT_OVER_REQUEST")
    return observation


def matching_schema_error(raw: bytes) -> bool:
    value = wire.strict_json(raw)
    if type(value) is not dict or set(value) != {"error"}:
        return False
    error = value["error"]
    return bool(type(error) is dict and error.get("type") == "invalid_request_error"
                and error.get("code") == "invalid_request_error"
                and type(error.get("message")) is str and len(error["message"]) <= 1024
                and MISSING_TYPE_ERROR in error["message"])


async def bounded_target(timeout: float, resolver: Callable[..., Any] | None) -> ApprovedTarget:
    if resolver is not None:  # Injected offline resolver only; the live CLI never supplies one.
        return approve_target(URL, policy=TargetPolicy(), resolver=resolver)
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-I", "-c",
        "import json,socket; print(json.dumps(sorted({x[4][0] for x in "
        "socket.getaddrinfo('api.deepseek.com',443,type=socket.SOCK_STREAM)})))",
        env={}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
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
            if (type(addresses) is not list or not addresses
                    or not all(type(x) is str for x in addresses)):
                raise Refused("DNS_RESPONSE_INVALID")
            return approve_target(URL, policy=TargetPolicy(), resolver=lambda *args: addresses)
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


def replay(events: list[dict[str, Any]], package: str, grant: dict[str, Any],
           bodies: dict[str, bytes]) -> dict[str, Any]:
    """Verify order/checkpoint/window; independently revalidate bodies in verify_results."""
    stage, current, previous, last_wall, last_elapsed = "new", None, None, None, -1.0
    reserved: list[str] = []
    sent: list[str] = []
    observed: list[str] = []
    transports: list[str] = []
    control = False
    observed_status: dict[str, int] = {}
    pinned_addresses: Any = None
    for index, row in enumerate(events):
        core = {k: v for k, v in row.items() if k != "digest"}
        if (type(row.get("seq")) is not int or row.get("seq") != index or row.get("previous") != previous
                or row.get("digest") != sha(canonical(core)) or stage == "terminal"):
            raise Refused("RECEIPT_CHAIN_OR_POST_STOP")
        previous = row["digest"]
        kind, data = row["kind"], row["data"]
        wall, elapsed = row["epoch"], row["elapsed"]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (wall, elapsed)):
            raise Refused("RECEIPT_CLOCK")
        productive_terminal = kind == "terminal" and str(data.get("outcome", "")).startswith("minimal_enum_")
        if (kind != "terminal" or productive_terminal) and (
            not grant["window_started_epoch"] <= wall < grant["deadline_epoch"]
            or not 0 <= elapsed < 90 or elapsed < last_elapsed
            or last_wall is not None and wall < last_wall
        ):
            raise Refused("RECEIPT_WINDOW_OR_CLOCK_ROLLBACK")
        last_wall, last_elapsed = wall, elapsed
        if kind == "started":
            if stage != "new" or data != dict(package_sha256=package, grant_sha256=sha(canonical(grant))):
                raise Refused("START_BINDING")
            stage = "ready"
        elif kind == "reserved":
            expected = "S1" if not reserved else "S2"
            if (stage != "ready" or len(reserved) >= 2 or reserved and not control
                    or data != dict(name=expected, request_sha256=sha(bodies[expected]))):
                raise Refused("RESERVE_ORDER_OR_CONTROL")
            current, stage = expected, "reserved"
            reserved.append(expected)
        elif kind == "target_pinned":
            if stage != "reserved" or data.get("name") != current:
                raise Refused("PIN_ORDER")
            if data.get("hostname") != "api.deepseek.com" or not data.get("addresses"):
                raise Refused("TARGET_CHANGED")
            from app.core.provider_target import is_public_address
            if not all(is_public_address(ipaddress.ip_address(ip)) for ip in data["addresses"]):
                raise Refused("NONPUBLIC_TARGET")
            if pinned_addresses is not None and data["addresses"] != pinned_addresses:
                raise Refused("PAIR_TARGET_IP_CHANGED")
            pinned_addresses = data["addresses"]
            stage = "pinned"
        elif kind == "sent":
            if (stage != "pinned" or set(data) != {"name", "transport_kind"}
                    or data["name"] != current or data["transport_kind"] not in ("real", "mock")
                    or current in sent):
                raise Refused("SEND_ORDER_OR_DUPLICATE")
            sent.append(str(current))
            transports.append(data["transport_kind"])
            stage = "sent"
        elif kind == "observed":
            if (stage != "sent" or data.get("name") != current
                    or type(data.get("status")) is not int or not 100 <= data["status"] <= 599):
                raise Refused("OBSERVE_ORDER")
            observed.append(str(current))
            observed_status[str(current)] = data["status"]
            stage = "observed"
        elif kind == "control_validated":
            if (stage != "observed" or current != "S1" or data.get("name") != "S1"
                    or observed_status.get("S1") != 200):
                raise Refused("CONTROL_ORDER")
            control, stage = True, "ready"
        elif kind == "terminal":
            if stage == "new" or data.get("outcome") not in {
                "inconclusive_stopped", "minimal_enum_rejection_observed",
                "minimal_enum_rejection_not_reproduced",
            }:
                raise Refused("TERMINAL_ORDER")
            stage = "terminal"
        else:
            raise Refused("UNKNOWN_RECEIPT")
    return dict(stage=stage, reserved=reserved, sent=sent, observed=observed,
                control_validated=control, transports=transports)


class Runner:
    def __init__(self, output: Path, package: str, grant: dict[str, Any], bodies: dict[str, bytes],
                 key: str, *, clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.output, self.package, self.grant, self.bodies, self.key = output, package, grant, bodies, key
        self.clock, self.monotonic, self.origin_mono = clock, monotonic, monotonic()
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, data: dict[str, Any]) -> None:
        wall, elapsed = self.clock(), self.monotonic() - self.origin_mono
        if kind == "terminal" and (not math.isfinite(wall) or not math.isfinite(elapsed)):
            wall, elapsed = self.events[-1]["epoch"], self.events[-1]["elapsed"]
            data = {**data, "outcome": "inconclusive_stopped", "reason": "CLOCK_INVALID",
                    "clock_source": "last_valid_receipt_no_success_credit"}
        core = dict(seq=len(self.events), previous=self.events[-1]["digest"] if self.events else None,
                    kind=kind, data=data, epoch=wall, elapsed=elapsed)
        row = {**core, "digest": sha(canonical(core))}
        replay([*self.events, row], self.package, self.grant, self.bodies)
        # Exclusive per-event files preserve a durable, hash-bound trace without a resume API.
        private_write(self.output / f"event-{len(self.events):03}.json", canonical(row))
        self.events.append(row)

    def remaining(self) -> float:
        wall, mono = self.clock(), self.monotonic() - self.origin_mono
        replay(self.events, self.package, self.grant, self.bodies)
        if (not math.isfinite(wall) or not math.isfinite(mono) or mono < 0
                or self.events and (wall < self.events[-1]["epoch"] or mono < self.events[-1]["elapsed"])):
            raise Refused("CLOCK_ROLLBACK")
        remaining = min(self.grant["deadline_epoch"] - wall, 90 - mono)
        if remaining <= 0:
            raise Refused("WINDOW_EXHAUSTED")
        return float(remaining)

    async def run(self, *, transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
                  resolver: Callable[..., Any] | None = None) -> dict[str, Any]:
        check_grant(self.grant, self.package, now=self.clock())
        if set(self.bodies) != {"S1", "S2"}:
            raise Refused("PAIR_REQUIRED")
        for name, body in request_pair().items():
            if self.bodies[name] != canonical(body) or len(self.bodies[name]) > 1024:
                raise Refused("REQUEST_PAIR_DRIFT")
        self.output.mkdir(mode=0o700, exist_ok=False)
        private_write(self.output / "grant.json", canonical(self.grant))
        self.record("started", dict(package_sha256=self.package, grant_sha256=sha(canonical(self.grant))))
        outcome = "inconclusive_stopped"
        reason = None
        target = None
        try:
            for name in ("S1", "S2"):
                self.remaining()
                raw = self.bodies[name]
                private_write(self.output / f"{name}-request.json", raw)
                self.record("reserved", dict(name=name, request_sha256=sha(raw)))
                if target is None:
                    target = await bounded_target(min(9.0, self.remaining()), resolver)
                self.record("target_pinned", dict(name=name, hostname=target.hostname,
                            addresses=list(target.addresses)))
                ip = ipaddress.ip_address(target.connect_ip)
                host = f"[{ip}]" if ip.version == 6 else str(ip)
                pinned = urlunsplit(("https", f"{host}:443", urlsplit(target.url).path, "", ""))
                transport = transport_factory() if transport_factory else httpx.AsyncHTTPTransport(retries=0)
                if not isinstance(transport, (httpx.MockTransport, httpx.AsyncHTTPTransport)):
                    raise Refused("TRANSPORT_UNCLASSIFIED")
                transport_kind = "mock" if isinstance(transport, httpx.MockTransport) else "real"
                async with httpx.AsyncClient(transport=transport, trust_env=False,
                                             follow_redirects=False, timeout=min(25.0, self.remaining())) as client:
                    request = client.build_request("POST", pinned, content=raw, headers={
                        "Host": target.hostname, "Content-Type": "application/json",
                        "Authorization": "Bearer " + self.key})
                    request.extensions["sni_hostname"] = target.hostname
                    self.record("sent", dict(name=name, transport_kind=transport_kind))
                    async with asyncio.timeout(min(25.0, self.remaining())):
                        response = await client.send(request, stream=True, follow_redirects=False)
                        try:
                            status = response.status_code
                            private_write(self.output / f"{name}-status.json", canonical({"http_status": status}))
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > 65536:
                                    raise Refused("RESPONSE_TOO_LARGE")
                        finally:
                            await response.aclose()
                response_raw = bytes(content)
                if self.key.encode() in response_raw:
                    raise Refused("SECRET_ECHO_REFUSED")
                private_write(self.output / f"{name}-response.bin", response_raw)
                self.record("observed", dict(name=name, status=status, response_sha256=sha(response_raw)))
                if status == 200:
                    obs = success_observation(wire.strict_json(raw), response_raw)
                    if name == "S1":
                        self.record("control_validated", dict(name=name, observation=obs))
                    else:
                        outcome = "minimal_enum_rejection_not_reproduced"
                elif name == "S2" and status == 400 and matching_schema_error(response_raw):
                    outcome = "minimal_enum_rejection_observed"
                else:
                    raise Refused("HTTP_OR_UNEXPECTED_SCHEMA_ERROR")
        except Exception as error:
            reason = str(error) if isinstance(error, Refused) else "PROTOCOL_TRANSPORT_TIMEOUT_OR_LOCAL_FAILURE"
            outcome = "inconclusive_stopped"
        try:
            self.record("terminal", dict(outcome=outcome, reason=reason))
        except Refused:
            self.record("terminal", dict(outcome="inconclusive_stopped", reason="LATE_TERMINAL_OR_CLOCK"))
        result = verify_results(self.output, self.package, self.grant, self.bodies,
                                require_real=transport_factory is None)
        private_write(self.output / "summary.json", canonical(result))
        return result


def verify_results(output: Path, package: str, grant: dict[str, Any],
                   bodies: dict[str, bytes], *, require_real: bool = False) -> dict[str, Any]:
    check_grant(grant, package, now=0.0, require_current=False)
    if (not output.is_dir() or any(p.is_symlink() for p in (output, *output.parents))
            or stat.S_IMODE(output.stat().st_mode) != 0o700):
        raise Refused("RESULT_DIRECTORY_PERMISSIONS")
    for file in output.iterdir():
        if (not re.fullmatch(r"grant\.json|summary\.json|event-[0-9]{3}\.json|"
                             r"S[12]-(?:request\.json|status\.json|response\.bin)", file.name)
                or file.is_symlink() or not file.is_file() or file.stat().st_size > 65536
                or stat.S_IMODE(file.stat().st_mode) != 0o600):
            raise Refused("RESULT_FILE_PERMISSIONS_OR_SCOPE")
    if (output / "grant.json").read_bytes() != canonical(grant):
        raise Refused("RESULT_GRANT_DRIFT")
    paths = sorted(output.glob("event-*.json"))
    if len(paths) > 12 or [p.name for p in paths] != [f"event-{i:03}.json" for i in range(len(paths))]:
        raise Refused("RECEIPT_FILE_GAP")
    events = [wire.strict_json(p.read_bytes()) for p in paths]
    state = replay(events, package, grant, bodies)
    if require_real and any(kind != "real" for kind in state["transports"]):
        raise Refused("MOCK_NOT_REAL_EVIDENCE")
    observations = {}
    for name in state["reserved"]:
        if (output / f"{name}-request.json").read_bytes() != bodies[name]:
            raise Refused("RESULT_REQUEST_DRIFT")
    for event in events:
        if event["kind"] == "observed":
            data = event["data"]
            name = data["name"]
            raw = (output / f"{name}-response.bin").read_bytes()
            if (sha(raw) != data["response_sha256"] or wire.strict_json(
                    (output / f"{name}-status.json").read_bytes()) != {"http_status": data["status"]}):
                raise Refused("RESULT_RESPONSE_DRIFT")
        if event["kind"] == "control_validated":
            raw = (output / "S1-response.bin").read_bytes()
            obs = success_observation(wire.strict_json(bodies["S1"]), raw)
            if event["data"] != dict(name="S1", observation=obs):
                raise Refused("CONTROL_EVIDENCE_DRIFT")
            observations["S1"] = obs
    outcome = events[-1]["data"]["outcome"] if state["stage"] == "terminal" else "incomplete_no_restart"
    if outcome.startswith("minimal_enum_"):
        if (state["sent"] != ["S1", "S2"] or state["observed"] != ["S1", "S2"]
                or not state["control_validated"]):
            raise Refused("COMPLETE_PAIR_REQUIRED")
        status = wire.strict_json((output / "S2-status.json").read_bytes())["http_status"]
        raw = (output / "S2-response.bin").read_bytes()
        if outcome == "minimal_enum_rejection_observed":
            if status != 400 or not matching_schema_error(raw):
                raise Refused("SCHEMA_REJECTION_EVIDENCE_MISMATCH")
        elif outcome == "minimal_enum_rejection_not_reproduced":
            if status != 200:
                raise Refused("SECOND_SUCCESS_STATUS")
            observations["S2"] = success_observation(wire.strict_json(bodies["S2"]), raw)
        else:
            raise Refused("UNKNOWN_TERMINAL_OUTCOME")
    result = dict(package_sha256=package, state="terminal" if state["stage"] == "terminal" else "incomplete",
                outcome=outcome, evidence_verified=True, recorded_window_verified=True,
                requests_reserved=len(state["reserved"]), dispatch_markers=len(state["sent"]),
                http_responses_recorded=len(state["observed"]), observations=observations,
                transport_kinds={k: state["transports"].count(k) for k in sorted(set(state["transports"]))},
                unknown_protocol_or_usage=len(state["sent"]) - len(observations),
                unused_requests_not_inherited=2 - len(state["reserved"]),
                actual_input_upper_bound_verified=False, actual_invoice=None, actual_currency=None,
                full_original_schema_compatibility_verified=False, course_feasibility_authorized=False,
                T038_completed=False, restart_authorized=False)
    summary = output / "summary.json"
    if summary.exists() and summary.read_bytes() != canonical(result):
        raise Refused("RESULT_SUMMARY_DRIFT")
    return result
