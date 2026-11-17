"""T069 proposed durable execution primitive. No credentials are loaded here.

A pending proposal is not execution authority; the CLI checks the exact grant first.
"""

import asyncio
from contextlib import contextmanager
from collections.abc import Iterator
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, cast
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.provider_target import TargetPolicy, approve_target
from app.services.provider_gateway import (
    ProviderGateway,
    StructuredRequest,
    StructuredResult,
)
from scripts.isolated_diagnostics import p15_agent_pilot as c
from scripts.isolated_diagnostics import p15_pilot_baseline as b
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_pilot_batch import (
    BatchState,
    initial_batch,
    reduce_batch,
)
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest


class Journal:
    def __init__(self, output: Path, *, clock: Callable[[], float] = time.time):
        self.output, self.clock = output.absolute(), clock
        if (
            any(p.is_symlink() for p in (self.output, *self.output.parents))
            or not (self.output / "ledger.sqlite").is_file()
            or (self.output / "ledger.sqlite").is_symlink()
        ):
            raise c.PilotError("JOURNAL_PATH")
        self.db = sqlite3.connect(
            self.output / "ledger.sqlite", isolation_level=None, timeout=1
        )
        self.db.row_factory = sqlite3.Row

    @classmethod
    def start(
        cls,
        output: Path,
        package: str,
        grant: dict[str, Any],
        inputs: dict[str, Any],
        *,
        clock: Callable[[], float] = time.time,
    ) -> "Journal":
        if not (grant["window_started_epoch"] <= clock() < grant["deadline_epoch"]):
            raise c.PilotError("EXPIRED_NEW_WINDOW")
        output = output.absolute()
        if any(p.is_symlink() for p in (output, *output.parents)):
            raise c.PilotError("OUTPUT_SYMLINK")
        os.mkdir(output, 0o700)
        fd = os.open(
            output / "ledger.sqlite",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        os.close(fd)
        j = cls(output, clock=clock)
        j.db.executescript("""CREATE TABLE batch (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT);
        CREATE TABLE calls (ticket TEXT PRIMARY KEY, slot TEXT, arm TEXT, stage TEXT,
          state TEXT, request_sha TEXT, response_sha TEXT, usage TEXT);
        CREATE TABLE events (seq INTEGER PRIMARY KEY, kind TEXT, payload TEXT,
          previous TEXT, digest TEXT, epoch REAL);""")
        value = initial_batch(grant, inputs, package)
        j.db.execute("INSERT INTO batch VALUES(1,?)", (canonical(value).decode(),))
        j.write("grant.json", grant)
        j.write("inputs.json", inputs)
        j.record("started", value)
        return j

    @contextmanager
    def lock(self) -> Iterator[None]:
        descriptor = os.open(
            self.output / "executor.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise c.PilotError("CONCURRENT_EXECUTOR") from exc
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def batch(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            json.loads(
                self.db.execute("SELECT value FROM batch WHERE id=1").fetchone()[0]
            ),
        )

    def update(self, **values: Any) -> None:
        current = self.batch()
        current.update(values)
        self.db.execute(
            "UPDATE batch SET value=? WHERE id=1", (canonical(current).decode(),)
        )

    def protocol(self) -> BatchState:
        grant = self._protocol_file("grant.json")
        inputs = self._protocol_file("inputs.json")
        initial = initial_batch(grant, inputs, self.batch()["package_sha256"])
        events = []
        parent = None
        for index, row in enumerate(
            self.db.execute("SELECT * FROM events ORDER BY seq")
        ):
            payload = wire.strict_json(row["payload"])
            expected_digest = digest(
                dict(
                    seq=index,
                    kind=row["kind"],
                    payload=payload,
                    previous=parent,
                    epoch=row["epoch"],
                )
            )
            if (
                row["seq"] != index
                or row["previous"] != parent
                or row["digest"] != expected_digest
            ):
                raise c.PilotError("RECEIPT_CHAIN")
            events.append(dict(kind=row["kind"], payload=payload, epoch=row["epoch"]))
            parent = row["digest"]
        state = reduce_batch(initial, events)
        if state.batch != self.batch():
            raise c.PilotError("BATCH_PROJECTION_MISMATCH")
        expected = [
            dict(
                row,
                usage=canonical(row["usage"]).decode()
                if row["usage"] is not None
                else None,
            )
            for row in state.calls.values()
        ]
        actual = [
            dict(r) for r in self.db.execute("SELECT * FROM calls ORDER BY rowid")
        ]
        if expected != actual:
            raise c.PilotError("CALL_PROJECTION_MISMATCH")
        return state

    def _protocol_file(self, name: str) -> dict[str, Any]:
        path = self.output / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4000000:
            raise c.PilotError("PROTOCOL_FILE")
        return cast(dict[str, Any], wire.strict_json(path.read_bytes()))

    def record(self, kind: str, value: dict[str, Any]) -> None:
        own_transaction = not self.db.in_transaction
        if own_transaction:
            self.db.execute("BEGIN IMMEDIATE")
        try:
            state = self.protocol()
            previous = self.db.execute(
                "SELECT seq,digest FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            seq, parent = (previous[0] + 1, previous[1]) if previous else (0, None)
            epoch = float(self.clock())
            state.apply(dict(kind=kind, payload=value, epoch=epoch))
            sha = digest(
                dict(seq=seq, kind=kind, payload=value, previous=parent, epoch=epoch)
            )
            self.db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (seq, kind, canonical(value).decode(), parent, sha, epoch),
            )
            self.db.execute(
                "UPDATE batch SET value=? WHERE id=1",
                (canonical(state.batch).decode(),),
            )
            for row in state.calls.values():
                self.db.execute(
                    "INSERT INTO calls VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket) "
                    "DO UPDATE SET state=excluded.state,response_sha=excluded.response_sha,usage=excluded.usage",
                    (
                        row["ticket"],
                        row["slot"],
                        row["arm"],
                        row["stage"],
                        row["state"],
                        row["request_sha"],
                        row["response_sha"],
                        canonical(row["usage"]).decode()
                        if row["usage"] is not None
                        else None,
                    ),
                )
            if own_transaction:
                self.db.execute("COMMIT")
        except BaseException:
            if own_transaction:
                self.db.execute("ROLLBACK")
            raise

    def write(self, name: str, value: Any, *, raw: bool = False) -> str:
        if "/" in name or not name or name in (".", ".."):
            raise c.PilotError("EVIDENCE_NAME")
        content = value if raw else canonical(value)
        descriptor = os.open(
            self.output / name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        return hashlib.sha256(content).hexdigest()

    def guard(
        self, *, package: str | None = None, grant: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        row = self.protocol().batch
        if row["status"] != "active":
            raise c.PilotError("BATCH_NOT_ACTIVE")
        if self.clock() >= row["deadline_epoch"] or self.clock() < row["started_epoch"]:
            raise c.PilotError("BATCH_WINDOW")
        if package is not None and row["package_sha256"] != package:
            raise c.PilotError("PACKAGE_CHANGED")
        if grant is not None and row["grant_sha256"] != digest(grant):
            raise c.PilotError("GRANT_CHANGED")
        if self.db.execute("SELECT 1 FROM calls WHERE state!='complete'").fetchone():
            raise c.PilotError("PENDING_OR_UNKNOWN_NO_RESEND")
        return row

    def reserve(self, slot: str, arm: str, stage: str, body: dict[str, Any]) -> str:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.guard()
            if {
                k: row["order"][row["position"]][k] for k in ("slot_id", "arm")
            } != dict(slot_id=slot, arm=arm):
                raise c.PilotError("SLOT_ORDER")
            if row["order"][row["position"]]["kind"] == "refusal":
                raise c.PilotError("REFUSAL_SLOT_NO_HTTP")
            total = self.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
            own = self.db.execute(
                "SELECT stage FROM calls WHERE slot=? AND arm=? ORDER BY rowid",
                (slot, arm),
            ).fetchall()
            expected = (
                [
                    "pilot_baseline",
                    "pilot_review",
                    "pilot_baseline_repair",
                    "pilot_review",
                ]
                if arm == "B"
                else [
                    "pilot_plan",
                    "pilot_content",
                    "pilot_review",
                    "pilot_repair",
                    "pilot_review",
                ]
            )
            if total >= 90 or len(own) >= len(expected) or stage != expected[len(own)]:
                raise c.PilotError("REQUEST_OR_STAGE_LIMIT")
            ticket = f"call-{total:03d}"
            request_sha = digest(body)
            self.record(
                "reserved",
                dict(
                    ticket=ticket,
                    slot_id=slot,
                    arm=arm,
                    stage=stage,
                    request_sha256=request_sha,
                ),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.write(ticket + "-request.json", body)
        return ticket

    def sent(self, ticket: str) -> None:
        row = self.batch()
        if (
            row["status"] != "active"
            or not row["started_epoch"] <= self.clock() < row["deadline_epoch"]
        ):
            raise c.PilotError("DISPATCH_WINDOW_OR_STATE")
        if (
            self.db.execute(
                "SELECT state FROM calls WHERE ticket=?", (ticket,)
            ).fetchone()[0]
            != "reserved"
        ):
            raise c.PilotError("DUPLICATE_SEND")
        self.record("sent", dict(ticket=ticket))

    def settle(
        self, ticket: str, response_sha: str, observation: dict[str, Any]
    ) -> None:
        row = self.batch()
        if row["status"] != "active" or self.clock() >= row["deadline_epoch"]:
            self.stop("LATE_REPLY")
            raise c.PilotError("LATE_REPLY")
        self.record(
            "settled",
            dict(ticket=ticket, response_sha256=response_sha, observation=observation),
        )

    def stop(self, reason: str) -> None:
        self.record("stopped", dict(reason=reason))

    def finish(self, result: dict[str, Any]) -> str:
        state = self.protocol()
        row = state.batch
        item = row["order"][row["position"]]
        name = f"slot-{row['position']:02d}-{item['arm']}-result.json"
        sha = self.write(name, result)
        epoch = self.clock()
        timely = (
            row["started_epoch"] <= epoch < row["deadline_epoch"]
            and epoch >= state.last_epoch
        )
        late = (
            result["state"] in ("model_advisory_pending_assistant", "refused")
            and not timely
        )
        if late:
            self.stop("LATE_SLOT_RESULT")
        self.record(
            "late_slot_result" if late else "slot_result",
            dict(**item, name=name, result_sha256=sha, state=result["state"]),
        )
        if result["state"] not in ("model_advisory_pending_assistant", "refused"):
            self.stop(result.get("reason", "WORKFLOW_STOPPED"))
        return sha

    def accept_report(self, report: dict[str, Any]) -> None:
        row = self.batch()
        if (
            row["status"] != "awaiting_assistant"
            or self.clock() >= row["deadline_epoch"]
        ):
            raise c.PilotError("ASSISTANT_CHECKPOINT_STATE_OR_TIME")
        result_raw = (self.output / row["pending"]["name"]).read_bytes()
        if hashlib.sha256(result_raw).hexdigest() != row["pending"]["result_sha256"]:
            raise c.PilotError("PENDING_RESULT_CHANGED")
        validate_assistant_report(
            report, row["package_sha256"], row["pending"], wire.strict_json(result_raw)
        )
        self.write(f"assistant-{row['position']:02d}.json", report)
        self.record("assistant_review", report)
        if report["decision"] == "stop":
            self.stop("INDEPENDENT_ASSISTANT_STOP")


def validate_assistant_report(
    report: dict[str, Any],
    package: str,
    pending: dict[str, Any],
    result: dict[str, Any],
) -> None:
    required = {
        "version",
        "reviewer",
        "reviewer_type",
        "package_sha256",
        "slot_id",
        "arm",
        "result_sha256",
        "decision",
        "checks",
        "issues",
        "version_reviews",
        "evidence_ref",
    }
    check_names = {"facts", "answers", "code", "actions", "teaching"}
    if (
        set(report) != required
        or report["version"] != "pilot-slot-review-v1"
        or report["reviewer"] != "pilot_independent_evaluator"
        or report["reviewer_type"] != "assistant"
        or type(report["evidence_ref"]) is not str
        or not report["evidence_ref"].strip()
        or report["package_sha256"] != package
        or any(report[k] != pending[k] for k in ("slot_id", "arm", "result_sha256"))
        or report["decision"] not in ("accept", "stop")
        or type(report["checks"]) is not dict
        or set(report["checks"]) != check_names
        or any(type(v) is not bool for v in report["checks"].values())
        or type(report["issues"]) is not list
    ):
        raise c.PilotError("INDEPENDENT_ASSISTANT_REPORT")
    if report["decision"] == "accept" and (
        not all(report["checks"].values()) or report["issues"]
    ):
        raise c.PilotError("ASSISTANT_FALSE_ACCEPT")
    versions = report["version_reviews"]
    if (
        type(versions) is not list
        or not versions
        or len(versions) != len(result["versions"])
    ):
        raise c.PilotError("ALL_VERSIONS_REQUIRED")
    fatal = False
    for index, version in enumerate(versions):
        if (
            set(version) != {"revision", "checks", "issues"}
            or version["revision"] != index
            or type(version["checks"]) is not dict
            or set(version["checks"]) != check_names
            or any(type(v) is not bool for v in version["checks"].values())
            or type(version["issues"]) is not list
        ):
            raise c.PilotError("VERSION_REVIEW_INVALID")
        for issue in version["issues"]:
            if (
                set(issue)
                != {"severity", "area", "source_pointer", "evidence_value", "reason"}
                or issue["severity"] not in ("minor", "major", "severe")
                or issue["area"]
                not in ("fact", "difficulty", "misconception", "code_safety")
                or type(issue["reason"]) is not str
                or not issue["reason"].strip()
                or type(issue["source_pointer"]) is not str
                or not issue["source_pointer"].startswith(f"/versions/{index}/")
            ):
                raise c.PilotError("INDEPENDENT_ISSUE_INVALID")
            if canonical(c.pointer(result, issue["source_pointer"])) != canonical(
                issue["evidence_value"]
            ):
                raise c.PilotError("INDEPENDENT_ISSUE_EVIDENCE")
            fatal |= issue["severity"] == "severe" or issue["area"] in (
                "fact",
                "code_safety",
            )
        mapping = dict(
            facts={"fact"},
            answers={"fact"},
            code={"fact", "code_safety"},
            actions={"fact", "code_safety", "difficulty", "misconception"},
            teaching={"difficulty", "misconception"},
        )
        for key, checked in version["checks"].items():
            if not checked and not any(
                i["area"] in mapping[key] for i in version["issues"]
            ):
                raise c.PilotError("FAILED_CHECK_WITHOUT_EVIDENCE")
        fatal |= not all(version["checks"][key] for key in ("facts", "answers", "code"))
    if (
        versions[-1]["checks"] != report["checks"]
        or versions[-1]["issues"] != report["issues"]
    ):
        raise c.PilotError("FINAL_REVIEW_MISMATCH")
    if fatal and report["decision"] != "stop":
        raise c.PilotError("INITIAL_SEVERE_ERROR_CANNOT_BE_REPAIRED_AWAY")


class RecordedAdapter:
    def __init__(
        self,
        journal: Journal,
        *,
        role: str,
        slot: str,
        arm: str,
        keys: dict[str, str],
        transport_factory: Callable[[], httpx.AsyncBaseTransport],
        resolver: Callable[..., Any],
    ):
        self.journal, self.role, self.slot, self.arm = journal, role, slot, arm
        self._keys, self.transport_factory, self.resolver = (
            keys,
            transport_factory,
            resolver,
        )

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        body = wire.request_body(request, self.role)
        ticket = self.journal.reserve(self.slot, self.arm, request.stage or "", body)
        try:
            route = wire.ROUTES[self.role]
            target = approve_target(
                route["url"], policy=TargetPolicy(), resolver=self.resolver
            )
            self.journal.record(
                "target_pinned",
                dict(
                    ticket=ticket,
                    hostname=target.hostname,
                    addresses=list(target.addresses),
                ),
            )
            parsed = urlsplit(target.url)
            ip = ipaddress.ip_address(target.connect_ip)
            host = f"[{ip}]" if ip.version == 6 else str(ip)
            pinned = urlunsplit(("https", f"{host}:443", parsed.path, "", ""))
            remaining = min(
                120.0, self.journal.batch()["deadline_epoch"] - self.journal.clock()
            )
            if remaining <= 0:
                raise c.PilotError("BATCH_WINDOW")
            transport = self.transport_factory()
            self.journal.record(
                "transport_kind",
                dict(
                    ticket=ticket,
                    kind="mock"
                    if isinstance(transport, httpx.MockTransport)
                    else "real",
                ),
            )
            async with httpx.AsyncClient(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                timeout=remaining,
            ) as client:
                req = client.build_request(
                    "POST",
                    pinned,
                    content=canonical(body),
                    headers={
                        "Host": target.hostname,
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + self._keys[self.role],
                    },
                )
                req.extensions["sni_hostname"] = target.hostname
                self.journal.sent(ticket)
                remaining = min(
                    120.0, self.journal.batch()["deadline_epoch"] - self.journal.clock()
                )
                if remaining <= 0:
                    raise c.PilotError("BATCH_WINDOW")
                async with asyncio.timeout(remaining):
                    response = await client.send(
                        req, stream=True, follow_redirects=False
                    )
                    status_sha = self.journal.write(
                        ticket + "-status.json", dict(http_status=response.status_code)
                    )
                    data = bytearray()
                    try:
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 2097152:
                                raise c.PilotError("RESPONSE_TOO_LARGE")
                    finally:
                        await response.aclose()
            raw = bytes(data)
            if any(key.encode() in raw for key in self._keys.values()):
                raise c.PilotError("SECRET_ECHO_REFUSED")
            sha = self.journal.write(ticket + "-response.json", raw, raw=True)
            self.journal.record(
                "wire_observed",
                dict(ticket=ticket, response_sha256=sha, status_sha256=status_sha),
            )
            if response.status_code != 200:
                raise c.PilotError("HTTP_STATUS")
            result, observation = wire.validate(body, raw, self.role)
            self.journal.settle(ticket, sha, observation)
            return result
        except BaseException:
            self.journal.stop("WIRE_UNKNOWN_OR_FAILURE")
            raise


class ExecutionGateway:
    def __init__(self, adapter: RecordedAdapter):
        self.gateway = ProviderGateway(adapter)  # type: ignore[arg-type]

    async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
        return await self.gateway.generate_structured(request, retry_safe=False)


def _initialize(
    flow: c.Pilot,
    generation: ExecutionGateway,
    review: ExecutionGateway,
    journal: Journal,
    *,
    maximum: int,
) -> None:
    """Separate live constructor; never relabels a real transport as MockTransport."""
    journal.guard()
    flow.generation, flow.review = generation, review  # type: ignore[assignment]
    flow.max_calls, flow.clock = maximum, journal.clock
    flow.deadline = journal.batch()["deadline_epoch"]
    flow.started, flow.calls, flow._events = False, 0, []


class ExecutionC(c.Pilot):
    def __init__(
        self, generation: ExecutionGateway, review: ExecutionGateway, journal: Journal
    ):
        _initialize(self, generation, review, journal, maximum=5)

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        result = await super().run(**kwargs)
        if result["state"] == "mock_advisory_pass":
            result["state"] = "model_advisory_pending_assistant"
        return result


class ExecutionB(b.Baseline):
    def __init__(
        self, generation: ExecutionGateway, review: ExecutionGateway, journal: Journal
    ):
        _initialize(self, generation, review, journal, maximum=4)

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        result = await super().run(**kwargs)
        if result["state"] == "mock_advisory_pass":
            result["state"] = "model_advisory_pending_assistant"
        return result
