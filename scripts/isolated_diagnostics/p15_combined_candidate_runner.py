"""Proposed isolated two-stage runner; no permission to send is conferred by this file."""

import asyncio
import ipaddress
import json
import math
import re
import stat
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.provider_target import ApprovedTarget, is_public_address
from scripts.isolated_diagnostics import p15_combined_candidate_contract as c
from scripts.isolated_diagnostics import p15_minimal_probe as old
from scripts.isolated_diagnostics import p15_minimal_probe_contract as roles
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    Refused,
    private_write,
    sha,
)

FLAGS = (
    "combined_gate_change_accepted",
    "synthetic_transfer_accepted",
    "new_window_accepted",
    "fee_exception_accepted",
    "user_evaluation_accepted",
)


def check_grant(
    grant: dict[str, Any], package: str, *, now: float, current: bool = True
) -> None:
    if (
        grant.get("accepted") is not True
        or grant.get("scope") != c.SCOPE
        or grant.get("package_sha256") != package
        or grant.get("limits") != c.LIMITS
        or any(grant.get(k) is not True for k in FLAGS)
        or not grant.get("human_message")
        or not grant.get("evidence_ref")
    ):
        raise Refused("EXACT_COMBINED_APPROVAL_REQUIRED")
    start: Any = grant.get("window_started_epoch")
    end: Any = grant.get("deadline_epoch")
    if (
        any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
        or end - start != c.LIMITS["wall_seconds"]
        or not math.isfinite(now)
        or current
        and not start <= now < end
    ):
        raise Refused("COMBINED_WINDOW_INVALID")


def replay(
    events: list[dict[str, Any]], output: Path, package: str, grant: dict[str, Any]
) -> tuple[dict[str, Any], c.Workflow]:
    wf = c.Workflow()
    phase, current_name, current_role = "new", None, None
    previous, last_wall, last_elapsed = None, None, -1.0
    reserved: list[str] = []
    sent: list[str] = []
    observed: list[str] = []
    validated: list[str] = []
    kinds: list[str] = []
    pinned: dict[str, list[str]] = {}
    status = None
    reserved_clock: tuple[float, float] | None = None
    sent_clock: tuple[float, float] | None = None
    for index, event in enumerate(events):
        core = {k: v for k, v in event.items() if k != "digest"}
        if (
            set(event)
            != {"seq", "previous", "kind", "data", "epoch", "elapsed", "digest"}
            or type(event["seq"]) is not int
            or event["seq"] != index
            or event["previous"] != previous
            or event["digest"] != sha(canonical(core))
            or phase == "terminal"
        ):
            raise Refused("COMBINED_EVENT_CHAIN")
        previous = event["digest"]
        kind, data, wall, elapsed = (
            event["kind"],
            event["data"],
            event["epoch"],
            event["elapsed"],
        )
        if any(
            type(v) not in (int, float) or not math.isfinite(v) for v in (wall, elapsed)
        ):
            raise Refused("COMBINED_CLOCK")
        if elapsed < last_elapsed or last_wall is not None and wall < last_wall:
            raise Refused("COMBINED_CLOCK_ROLLBACK")
        if (
            kind != "terminal" or data.get("outcome") == "pending_user_review"
        ) and not (
            grant["window_started_epoch"] <= wall < grant["deadline_epoch"]
            and 0 <= elapsed < c.LIMITS["wall_seconds"]
        ):
            raise Refused("COMBINED_WINDOW")
        last_wall, last_elapsed = wall, elapsed
        if kind == "started":
            if phase != "new" or data != dict(
                package_sha256=package, grant_sha256=sha(canonical(grant))
            ):
                raise Refused("COMBINED_START")
            phase = "ready"
        elif kind == "reserved":
            expected = wf.next_request()
            if (
                phase != "ready"
                or expected is None
                or len(reserved) >= c.LIMITS["requests"]
            ):
                raise Refused("COMBINED_RESERVE_ORDER")
            name, role, request = expected
            if (
                data != dict(name=name, role=role, request_sha256=sha(request))
                or (output / f"{name}-request.json").read_bytes() != request
            ):
                raise Refused("COMBINED_REQUEST_BINDING")
            current_name, current_role, phase = name, role, "reserved"
            reserved.append(name)
            reserved_clock = (wall, elapsed)
        elif kind == "pinned":
            if (
                phase != "reserved"
                or data.get("name") != current_name
                or set(data) != {"name", "hostname", "addresses", "connect_ip"}
            ):
                raise Refused("COMBINED_PIN_ORDER")
            if (
                reserved_clock is None
                or wall - reserved_clock[0] > c.LIMITS["dns_seconds"]
                or elapsed - reserved_clock[1] > c.LIMITS["dns_seconds"]
            ):
                raise Refused("COMBINED_DNS_TIMEOUT")
            host = urlsplit(wire.ROUTES[str(current_role)]["url"]).hostname
            addresses = data.get("addresses")
            if (
                data.get("hostname") != host
                or type(addresses) is not list
                or not addresses
                or data.get("connect_ip") not in addresses
                or not all(
                    is_public_address(ipaddress.ip_address(a)) for a in addresses
                )
                or current_role in pinned
                and pinned[str(current_role)] != addresses
            ):
                raise Refused("COMBINED_PIN_BINDING")
            pinned[str(current_role)], phase = addresses, "pinned"
        elif kind == "sent":
            if (
                phase != "pinned"
                or set(data) != {"name", "transport_kind"}
                or data["name"] != current_name
                or data["name"] in sent
                or data["transport_kind"] not in ("real", "mock")
            ):
                raise Refused("COMBINED_SEND_ORDER")
            sent.append(str(current_name))
            kinds.append(data["transport_kind"])
            phase = "sent"
            sent_clock = (wall, elapsed)
        elif kind == "observed":
            if (
                phase != "sent"
                or set(data) != {"name", "status", "response_sha256"}
                or data["name"] != current_name
                or type(data["status"]) is not int
                or not 100 <= data["status"] <= 599
            ):
                raise Refused("COMBINED_OBSERVE_ORDER")
            if (
                sent_clock is None
                or wall - sent_clock[0] > c.LIMITS["per_request_seconds"]
                or elapsed - sent_clock[1] > c.LIMITS["per_request_seconds"]
            ):
                raise Refused("COMBINED_HTTP_TIMEOUT")
            raw = (output / f"{current_name}-response.bin").read_bytes()
            if (
                len(raw) > c.LIMITS["response_bytes"]
                or sha(raw) != data["response_sha256"]
                or wire.strict_json(
                    (output / f"{current_name}-status.json").read_bytes()
                )
                != {"http_status": data["status"]}
            ):
                raise Refused("COMBINED_RESPONSE_BINDING")
            status = data["status"]
            observed.append(str(current_name))
            phase = "observed"
        elif kind == "validated":
            if phase != "observed" or status != 200 or data.get("name") != current_name:
                raise Refused("COMBINED_VALIDATE_ORDER")
            raw = (output / f"{current_name}-response.bin").read_bytes()
            request = (output / f"{current_name}-request.json").read_bytes()
            observation = wf.accept(str(current_name), request, raw)
            if data != dict(name=current_name, observation=observation):
                raise Refused("COMBINED_VALIDATION_BINDING")
            validated.append(str(current_name))
            phase = "ready"
        elif kind == "terminal":
            if (
                phase == "new"
                or set(data) != {"outcome", "reason"}
                or data["outcome"] not in ("stopped", "pending_user_review")
            ):
                raise Refused("COMBINED_TERMINAL")
            if data["outcome"] == "pending_user_review" and (
                phase != "ready"
                or wf.stage != "pending_user_review"
                or data["reason"] is not None
            ):
                raise Refused("COMBINED_PREMATURE_SUCCESS")
            phase = "terminal"
        else:
            raise Refused("COMBINED_UNKNOWN_EVENT")
    return dict(
        phase=phase,
        reserved=reserved,
        sent=sent,
        observed=observed,
        validated=validated,
        transport_kinds=kinds,
    ), wf


def secret_visible(raw: bytes, keys: dict[str, str]) -> bool:
    """Detect literal and common JSON-escaped full credentials before any raw persistence."""
    if b"\x00" in raw:
        return True
    if any(key.encode() in raw for key in keys.values()):
        return True
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return True
    for _ in range(3):
        text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
        if any(key in text for key in keys.values()):
            return True
    try:
        root = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return False

    def walk(value: Any, depth: int) -> bool:
        if depth > 16:
            return False
        if isinstance(value, str):
            if any(key in value for key in keys.values()):
                return True
            if depth < 16 and value[:1] in ("{", "[", '"'):
                try:
                    nested = json.loads(value)
                except (ValueError, RecursionError):
                    return False
                return walk(nested, depth + 1)
            return False
        if isinstance(value, dict):
            return any(
                walk(k, depth + 1) or walk(v, depth + 1) for k, v in value.items()
            )
        if isinstance(value, list):
            return any(walk(v, depth + 1) for v in value)
        return False

    return walk(root, 0)


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
        self.clock, self.monotonic, self.origin = clock, monotonic, monotonic()
        self.events: list[dict[str, Any]] = []

    def record(self, kind: str, data: dict[str, Any]) -> None:
        wall, elapsed = self.clock(), self.monotonic() - self.origin
        if (
            kind == "terminal"
            and self.events
            and (
                not math.isfinite(wall)
                or not math.isfinite(elapsed)
                or wall < self.events[-1]["epoch"]
                or elapsed < self.events[-1]["elapsed"]
            )
        ):
            wall, elapsed = self.events[-1]["epoch"], self.events[-1]["elapsed"]
            data = dict(outcome="stopped", reason="CLOCK_INVALID")
        core = dict(
            seq=len(self.events),
            previous=self.events[-1]["digest"] if self.events else None,
            kind=kind,
            data=data,
            epoch=wall,
            elapsed=elapsed,
        )
        row = {**core, "digest": sha(canonical(core))}
        replay([*self.events, row], self.output, self.package, self.grant)
        private_write(self.output / f"event-{len(self.events):03}.json", canonical(row))
        self.events.append(row)

    def remaining(self) -> float:
        replay(self.events, self.output, self.package, self.grant)
        wall, elapsed = self.clock(), self.monotonic() - self.origin
        if (
            not math.isfinite(wall)
            or not math.isfinite(elapsed)
            or elapsed < 0
            or self.events
            and (
                wall < self.events[-1]["epoch"] or elapsed < self.events[-1]["elapsed"]
            )
        ):
            raise Refused("COMBINED_CLOCK_ROLLBACK")
        value = min(
            self.grant["deadline_epoch"] - wall, c.LIMITS["wall_seconds"] - elapsed
        )
        if value <= 0:
            raise Refused("COMBINED_WINDOW_EXHAUSTED")
        return float(value)

    async def run(
        self,
        *,
        transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
        resolver: Callable[..., Any] | None = None,
    ) -> dict[str, Any]:
        check_grant(self.grant, self.package, now=self.clock())
        if transport_factory is None and resolver is not None:
            raise Refused("COMBINED_REAL_RESOLVER_FORBIDDEN")
        if set(self.keys) != set(wire.ROUTES) or any(
            type(k) is not str
            or len(k) < 16
            or not k.isascii()
            or any(ch.isspace() for ch in k)
            for k in self.keys.values()
        ):
            raise Refused("COMBINED_KEYS_REQUIRED")
        if any(path.is_symlink() for path in (self.output, *self.output.parents)):
            raise Refused("COMBINED_OUTPUT_SYMLINK")
        self.output.mkdir(mode=0o700, exist_ok=False)
        private_write(self.output / "grant.json", canonical(self.grant))
        self.record(
            "started",
            dict(package_sha256=self.package, grant_sha256=sha(canonical(self.grant))),
        )
        targets: dict[str, ApprovedTarget] = {}
        outcome, reason = "stopped", None
        try:
            while True:
                self.remaining()
                _, wf = replay(self.events, self.output, self.package, self.grant)
                target_request = wf.next_request()
                if target_request is None:
                    if wf.stage == "pending_user_review":
                        outcome = "pending_user_review"
                    else:
                        reason = wf.stop_reason or "WORKFLOW_STOPPED"
                    break
                name, role, raw = target_request
                private_write(self.output / f"{name}-request.json", raw)
                self.record(
                    "reserved", dict(name=name, role=role, request_sha256=sha(raw))
                )
                if role not in targets:
                    targets[role] = await old.bounded_target(
                        wire.ROUTES[role]["url"], min(9.0, self.remaining()), resolver
                    )
                target = targets[role]
                self.record(
                    "pinned",
                    dict(
                        name=name,
                        hostname=target.hostname,
                        addresses=list(target.addresses),
                        connect_ip=target.connect_ip,
                    ),
                )
                ip = ipaddress.ip_address(target.connect_ip)
                host = f"[{ip}]" if ip.version == 6 else str(ip)
                pinned = urlunsplit(
                    ("https", f"{host}:443", urlsplit(target.url).path, "", "")
                )
                if transport_factory is None:
                    transport: httpx.AsyncBaseTransport = httpx.AsyncHTTPTransport(
                        retries=0
                    )
                    if type(transport) is not httpx.AsyncHTTPTransport:
                        raise Refused("COMBINED_REAL_TRANSPORT")
                    transport_kind = "real"
                else:
                    transport = transport_factory()
                    if type(transport) is not httpx.MockTransport:
                        raise Refused("COMBINED_MOCK_TRANSPORT_REQUIRED")
                    transport_kind = "mock"
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
                                if len(content) > c.LIMITS["response_bytes"]:
                                    raise Refused("COMBINED_RESPONSE_TOO_LARGE")
                        finally:
                            await response.aclose()
                received = bytes(content)
                if secret_visible(received, self.keys):
                    raise Refused("COMBINED_SECRET_OR_NON_UTF8")
                private_write(self.output / f"{name}-response.bin", received)
                self.record(
                    "observed",
                    dict(name=name, status=status, response_sha256=sha(received)),
                )
                if status != 200:
                    raise Refused("COMBINED_HTTP_STATUS")
                _, fresh = replay(self.events, self.output, self.package, self.grant)
                observation = fresh.accept(name, raw, received)
                self.record("validated", dict(name=name, observation=observation))
        except Exception as exc:
            reason = (
                str(exc)
                if isinstance(exc, Refused)
                and re.fullmatch(r"[A-Z0-9_]{1,80}", str(exc))
                else "COMBINED_PROTOCOL_OR_TRANSPORT_FAILURE"
            )
        try:
            self.record("terminal", dict(outcome=outcome, reason=reason))
        except Refused:
            self.record(
                "terminal", dict(outcome="stopped", reason="COMBINED_LATE_OR_CLOCK")
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
        raise Refused("COMBINED_RESULT_DIRECTORY")
    names = set(roles.ORDER) | set(c.COURSE_ORDER)
    for file in output.iterdir():
        allowed = (
            file.name in {"grant.json", "summary.json"}
            or re.fullmatch(r"event-[0-9]{3}\.json", file.name)
            or any(
                file.name == f"{name}-{suffix}"
                for name in names
                for suffix in ("request.json", "status.json", "response.bin")
            )
        )
        if (
            not allowed
            or file.is_symlink()
            or not file.is_file()
            or file.stat().st_size > c.LIMITS["response_bytes"]
            or stat.S_IMODE(file.stat().st_mode) != 0o600
        ):
            raise Refused("COMBINED_RESULT_FILE")
    if (output / "grant.json").read_bytes() != canonical(grant):
        raise Refused("COMBINED_GRANT_DRIFT")
    paths = sorted(output.glob("event-*.json"))
    if len(paths) > 80 or [p.name for p in paths] != [
        f"event-{i:03}.json" for i in range(len(paths))
    ]:
        raise Refused("COMBINED_EVENT_GAP")
    events = [wire.strict_json(p.read_bytes()) for p in paths]
    state, wf = replay(events, output, package, grant)
    if require_real and any(kind != "real" for kind in state["transport_kinds"]):
        raise Refused("COMBINED_MOCK_NOT_REAL")
    outcome = (
        events[-1]["data"]["outcome"]
        if state["phase"] == "terminal"
        else "incomplete_no_restart"
    )
    file_sets = {
        suffix: sorted(name for name in names if (output / f"{name}-{suffix}").exists())
        for suffix in ("request.json", "status.json", "response.bin")
    }
    request_names = set(file_sets["request.json"])
    allowed_requests = set(state["reserved"])
    next_request = wf.next_request()
    if outcome != "pending_user_review" and next_request is not None:
        allowed_requests.add(next_request[0])
    if (
        not set(state["reserved"]).issubset(request_names)
        or not request_names.issubset(allowed_requests)
        or not set(file_sets["status.json"]).issubset(state["sent"])
        or not set(file_sets["response.bin"]).issubset(state["sent"])
    ):
        raise Refused("COMBINED_UNBOUND_FILES")
    if outcome == "pending_user_review" and (
        request_names != set(state["reserved"])
        or set(file_sets["status.json"]) != set(state["observed"])
        or set(file_sets["response.bin"]) != set(state["observed"])
    ):
        raise Refused("COMBINED_SUCCESS_FILE_SET")
    result = dict(
        package_sha256=package,
        state=state["phase"],
        outcome=outcome,
        protocol_admission_complete=all(n in state["validated"] for n in roles.ORDER),
        user_evaluation_pending=outcome == "pending_user_review",
        repair_success=False,
        real_course_quality_pass=False,
        formal_pilot_pass=False,
        T038_completed=False,
        reserved=state["reserved"],
        sent=state["sent"],
        observed=state["observed"],
        validated=state["validated"],
        transport_kinds=state["transport_kinds"],
        unknown_sent=len(state["sent"]) - len(state["validated"]),
        files_recorded=file_sets,
        versions=wf.versions,
        opinions=wf.opinions,
        plan=wf.plan,
        actual_invoice=None,
        actual_currency=None,
        upstream_limits_verified=False,
        independent_time_attested=False,
        restart_authorized=False,
    )
    if (output / "summary.json").exists() and (
        output / "summary.json"
    ).read_bytes() != canonical(result):
        raise Refused("COMBINED_SUMMARY_DRIFT")
    return result
