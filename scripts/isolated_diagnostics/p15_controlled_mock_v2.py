"""Offline Responses-shaped controller experiment; MockTransport is mandatory.

Not a live executor or an authorization. No DNS, credentials, or provider calls.
All reservations are retained, including unknown/failed/late attempts.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from typing import Any, Callable, TypeVar, cast

import httpx

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_bounded_json_v1 as bounded
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_pinned_transport_v1 as pinned
from scripts.isolated_diagnostics import p15_supervised_mock_v2 as supervised
from scripts.isolated_diagnostics import p15_synthetic_guard_v2 as synthetic_guard
from scripts.isolated_diagnostics import p15_synthetic_vault_v1 as synthetic_vault
from scripts.isolated_diagnostics import p15_teaching_pilot as teaching
from scripts.isolated_diagnostics import p15_teaching_revision as prompts
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics import p15_visible_worker_v2 as worker
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    SpecError,
    answer,
    build_example,
    canonical,
    digest,
    validate_spec,
)

VERSION = "controlled-mock-responses-batch-v5-offline"
MAX_RESPONSE = 2 * 1024 * 1024
HTTP_WALL_SECONDS = 60.0
T = TypeVar("T")


async def _daemon_call(function: Callable[..., T], *args: Any) -> T:
    """Do not let an unresponsive development callback hold asyncio.run open.

    The thread cannot dispatch or mutate the ledger; on stop its eventual
    result is discarded. Resource-intensive parsing is separately isolated in
    a monitored child process.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[T] = loop.create_future()

    def deliver(value: T | None, error: BaseException | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(cast(T, value))

    def invoke() -> None:
        try:
            value, error = function(*args), None
        except BaseException as exc:
            value, error = None, exc
        try:
            loop.call_soon_threadsafe(deliver, value, error)
        except RuntimeError:
            # The caller may have closed its loop after a recorded stop.
            pass

    threading.Thread(target=invoke, daemon=True).start()
    return await future


def read_anchor(path: Path, frozen: bytes) -> str | None:
    descriptor = os.open(Path(str(path) + ".anchor"), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as anchor_file:
        details = os.fstat(anchor_file.fileno())
        c.require(
            stat.S_ISREG(details.st_mode)
            and details.st_nlink == 1
            and details.st_size <= 1024 * 1024,
            "MOCK_LEDGER_ANCHOR",
        )
        data = anchor_file.read(1024 * 1024 + 1)
    c.require(data.endswith(b"\n"), "MOCK_LEDGER_ANCHOR")
    lines = data.splitlines()
    c.require(
        bool(lines) and lines[0] == hashlib.sha256(frozen).hexdigest().encode("ascii"),
        "MOCK_GRANT_BINDING",
    )
    c.require(
        all(re.fullmatch(rb"[0-9a-f]{64}", line) is not None for line in lines[1:]),
        "MOCK_LEDGER_ANCHOR",
    )
    return lines[-1].decode("ascii") if len(lines) > 1 else None


def ledger_state(db: sqlite3.Connection) -> dict[str, Any]:
    result: dict[str, Any] = {}
    ordering = {
        "batch": "rowid",
        "slots": "position",
        "attempts": "slot,arm,ordinal",
        "attestation": "slot,arm",
        "local_refusals": "slot,arm",
    }
    for table, order in ordering.items():
        projection = "rowid AS nonce_counter,*" if table == "attempts" else "*"
        cursor = db.execute(f"SELECT {projection} FROM {table} ORDER BY {order}")
        columns = [item[0] for item in cursor.description]
        rows = []
        for row in cursor:
            values = []
            for value in row:
                values.append(
                    {
                        "bytes_sha256": hashlib.sha256(value).hexdigest(),
                        "length": len(value),
                    }
                    if type(value) is bytes
                    else value
                )
            rows.append(dict(zip(columns, values)))
        result[table] = rows
    return result


def ledger_state_digest(db: sqlite3.Connection) -> str:
    return digest(ledger_state(db))


def open_package_ledger(
    path: Path, frozen: bytes
) -> tuple[sqlite3.Connection, bool, str | None]:
    """Create once, or reopen an anchored ledger without silently recreating it."""
    path = path.absolute()
    anchor = Path(str(path) + ".anchor")
    expected = hashlib.sha256(frozen).hexdigest().encode("ascii") + b"\n"
    created = False
    last_state = None
    try:
        anchor_fd = os.open(anchor, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        c.require(not os.path.lexists(path), "MOCK_LEDGER_UNANCHORED")
        anchor_fd = os.open(
            anchor, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(anchor_fd, "wb") as anchor_file:
            anchor_file.write(expected)
            anchor_file.flush()
            os.fsync(anchor_file.fileno())
        ledger_fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        os.close(ledger_fd)
        created = True
    else:
        os.close(anchor_fd)
        last_state = read_anchor(path, frozen)
        c.require(last_state is not None, "MOCK_LEDGER_ANCHOR_INCOMPLETE")
        c.require(os.path.lexists(path), "MOCK_LEDGER_LOST")
        details = os.lstat(path)
        c.require(
            stat.S_ISREG(details.st_mode)
            and details.st_nlink == 1
            and details.st_size > 0,
            "MOCK_LEDGER_LOST",
        )
    db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
    return db, created, last_state


def runtime_contract(transport: Any = None) -> dict[str, Any]:
    """Snapshot the exact role instructions, schemas and target identities."""
    stages = {}
    for stage in c.STAGES:
        instruction, version = budget.instruction(stage)
        stages[stage] = {
            "prompt_version": version,
            "instruction_sha256": hashlib.sha256(
                instruction.encode("utf-8")
            ).hexdigest(),
            "schema_sha256": hashlib.sha256(canonical(c.schema_for(stage))).hexdigest(),
        }
    routes = {
        role: {
            key: route[key]
            for key in ("url", "model", "reasoning", "credential_env")
        }
        for role, route in wire.ROUTES.items()
    }
    result = dict(
        version=VERSION,
        stages=stages,
        routes=routes,
        response_bytes=MAX_RESPONSE,
        output_tokens=8000,
        http_wall_seconds=HTTP_WALL_SECONDS,
        pinned_adapter_version=pinned.VERSION,
        supervised_adapter_version=supervised.VERSION,
        synthetic_guard_version=synthetic_guard.VERSION,
        synthetic_vault_version=synthetic_vault.VERSION,
    )
    if type(transport) is supervised.SupervisedMockTransport:
        result["supervisor_policy"] = transport.policy()
    return result


def normalized_package(path: Path, supplied: dict[str, Any], transport: Any = None) -> dict[str, Any]:
    """Bind every slot and the shared budgets to one designated ledger path."""
    limits = {"batch", "calls", "input", "output", "request_bytes", "deadline"}
    if set(supplied) == limits | {"slot", "arm", "spec", "ledger_path"}:
        package = {key: supplied[key] for key in limits}
        package["slots"] = [{key: supplied[key] for key in ("slot", "arm", "spec")}]
        package["ledger_path"] = supplied["ledger_path"]
    else:
        c.require(
            set(supplied)
            in (
                limits | {"slots", "ledger_path"},
                limits | {"slots", "ledger_path", "runtime_contract"},
            ),
            "MOCK_GRANT",
        )
        package = dict(supplied)
    c.require(
        type(package["batch"]) is str
        and re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", package["batch"]) is not None
        and package["ledger_path"] == str(path.absolute())
        and type(package["calls"]) is int
        and package["calls"] >= 0
        and all(
            type(package[k]) is int and package[k] > 0
            for k in ("input", "output", "request_bytes", "deadline")
        )
        and type(package["slots"]) is list
        and bool(package["slots"])
        and len(package["slots"]) <= 28,
        "MOCK_GRANT",
    )
    seen: set[tuple[str, str]] = set()
    pairs: dict[str, bytes] = {}
    maximum_calls = 0
    normalized_slots = []
    for supplied_row in package["slots"]:
        c.require(type(supplied_row) is dict, "MOCK_GRANT_SLOT")
        row = dict(supplied_row)
        if set(row) == {"slot", "arm", "spec"}:
            row.update(kind="supported", question=None)
        c.require(
            set(row) == {"slot", "arm", "spec", "kind", "question"}
            and type(row["slot"]) is str
            and re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", row["slot"]) is not None
            and row["arm"] in ("B", "C")
            and row["kind"] in ("supported", "refusal")
            and (row["question"] is None or type(row["question"]) is str)
            and (row["kind"] != "supported" or row["question"] is None),
            "MOCK_GRANT_SLOT",
        )
        key = (row["slot"], row["arm"])
        c.require(key not in seen, "MOCK_GRANT_SLOT")
        seen.add(key)
        comparable = bounded.encode(
            {name: row[name] for name in ("spec", "kind", "question")},
            c.MAX_PAYLOAD,
            "MOCK_GRANT_SLOT",
        )
        c.require(
            row["slot"] not in pairs or pairs[row["slot"]] == comparable,
            "MOCK_PAIRED_SLOT",
        )
        pairs[row["slot"]] = comparable
        bounded.encode(
            {"spec": row["spec"], "question": row["question"]},
            c.MAX_PAYLOAD,
            "MOCK_GRANT_SLOT",
        )
        if row["kind"] == "supported":
            c.identity(package["batch"], row["slot"], row["arm"], 0, row["spec"], None)
            maximum_calls += 4 if row["arm"] == "B" else 5
        normalized_slots.append(row)
    package["slots"] = normalized_slots
    for slot in pairs:
        positions = [
            (index, row["arm"])
            for index, row in enumerate(normalized_slots)
            if row["slot"] == slot
        ]
        if len(positions) == 2:
            c.require(
                positions[0][1] == "B" and positions[1] == (positions[0][0] + 1, "C"),
                "MOCK_PAIR_ORDER",
            )
    c.require(package["calls"] <= maximum_calls, "MOCK_GRANT")
    current_runtime = runtime_contract(transport)
    c.require(
        "runtime_contract" not in package
        or package["runtime_contract"] == current_runtime,
        "MOCK_RUNTIME_BINDING",
    )
    package["runtime_contract"] = current_runtime
    return package


def response_for_validation(body: bytes, raw: bytes, role: str) -> tuple[bytes, str]:
    """Private compatibility view; never modify the persisted original response."""
    c.require(len(raw) <= MAX_RESPONSE, "MOCK_RESPONSE_SIZE")
    request = wire.strict_json(body)
    original = wire.strict_json(raw)
    c.require(type(original) is dict, "MOCK_RESPONSE_ENVELOPE")
    text = original.get("text")
    schema_echo = "unknown"
    if text is not None:
        c.require(type(text) is dict, "MOCK_SCHEMA_ECHO")
        fmt = text.get("format")
        if fmt is not None:
            expected = request["text"]["format"]
            c.require(
                type(fmt) is dict
                and ("schema" not in fmt or fmt["schema"] == expected["schema"])
                and fmt.get("type", "json_schema") == "json_schema"
                and fmt.get("name", expected["name"]) == expected["name"]
                and fmt.get("strict", True) is True,
                "MOCK_SCHEMA_ECHO",
            )
            schema_echo = "matched" if "schema" in fmt else "unknown"
    c.require(len(raw) <= MAX_RESPONSE and "phase" not in original, "MOCK_PHASE")
    view = wire.strict_json(raw)
    for item in view.get("output", []):
        if type(item) is dict and "phase" in item:
            c.require(
                item.get("type") == "message" and item["phase"] == "final_answer",
                "MOCK_PHASE",
            )
            del item["phase"]
    if role == "review":
        for item in view.get("output", []):
            if (
                type(item) is dict
                and item.get("type") == "reasoning"
                and item.get("encrypted_content") not in (None, "")
            ):
                opaque = item["encrypted_content"]
                c.require(
                    type(opaque) is str and 1 <= len(opaque) <= 8192,
                    "MOCK_REASONING_BOUND",
                )
                item["encrypted_content"] = None
    return canonical(view), schema_echo


class Controller:
    """One shared package ledger and one owner for all authorized arm/slot pairs."""

    _encrypted_supervisor = False

    def __init__(
        self,
        path: Path,
        grant: dict[str, Any],
        transport: httpx.MockTransport | pinned.PinnedResponsesTransport | supervised.SupervisedMockTransport,
        *,
        selected: tuple[str, str] | None = None,
    ):
        c.require(
            type(transport) is httpx.MockTransport
            or (
                type(transport) is pinned.PinnedResponsesTransport
                and transport.offline_only is True
            )
            or type(transport) is supervised.SupervisedMockTransport,
            "MOCK_TRANSPORT_REQUIRED",
        )
        c.require(
            type(transport) is not supervised.SupervisedMockTransport or self._encrypted_supervisor,
            "ENCRYPTED_CONTROLLER_REQUIRED",
        )
        package = normalized_package(path, grant, transport)
        if type(transport) is supervised.SupervisedMockTransport:
            transport.bind_policy(package["runtime_contract"]["supervisor_policy"])
            transport.bind_deadline(package["deadline"])
        allowed = {(row["slot"], row["arm"]) for row in package["slots"]}
        c.require(
            selected in allowed if selected is not None else len(allowed) == 1,
            "MOCK_SELECTED_SLOT",
        )
        self._selected = selected if selected is not None else next(iter(allowed))
        # The isolated Mock implementation takes an exclusive process lock. It
        # must not be confused with a cross-process live dispatch mechanism.
        import fcntl

        lock_path = Path(str(path) + ".lock")
        self._lock_fd = os.open(
            lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self._lock_fd)
            raise c.ContractError("CONTROLLER_OWNER_BUSY") from None
        try:
            frozen = canonical(package)
            self._grant_bytes = frozen
            self._ledger_path = path.absolute()
            self.db, created, last_state = open_package_ledger(path, frozen)
            self.db.row_factory = sqlite3.Row
            if created:
                self.db.executescript("""
            CREATE TABLE IF NOT EXISTS batch (grant_json BLOB NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS slots (
                slot TEXT NOT NULL, arm TEXT NOT NULL, position INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL, PRIMARY KEY (slot,arm)
            );
            CREATE TABLE IF NOT EXISTS attempts (
                slot TEXT NOT NULL, arm TEXT NOT NULL, ordinal INTEGER NOT NULL,
                stage TEXT NOT NULL, request BLOB NOT NULL,
                request_sha TEXT NOT NULL, previous_receipt TEXT, input_reserved INTEGER NOT NULL,
                output_reserved INTEGER NOT NULL, state TEXT NOT NULL, response BLOB,
                http_status INTEGER, response_sha TEXT, input_used INTEGER, output_used INTEGER,
                PRIMARY KEY (slot,arm,ordinal)
            );
            CREATE TABLE IF NOT EXISTS attestation (
                slot TEXT NOT NULL, arm TEXT NOT NULL, value BLOB NOT NULL,
                PRIMARY KEY (slot,arm)
            );
            CREATE TABLE IF NOT EXISTS local_refusals (
                slot TEXT NOT NULL, arm TEXT NOT NULL, reason TEXT NOT NULL,
                spec_digest TEXT NOT NULL, question_digest TEXT NOT NULL,
                PRIMARY KEY (slot,arm)
            );
        """)
            else:
                tables = {
                    row[0]
                    for row in self.db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                c.require(
                    tables
                    == {"batch", "slots", "attempts", "attestation", "local_refusals"},
                    "MOCK_LEDGER_CORRUPT",
                )
            row = self.db.execute("SELECT * FROM batch").fetchone()
            if created:
                c.require(row is None, "MOCK_LEDGER_CORRUPT")
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute("INSERT INTO batch VALUES (?, 'active')", (frozen,))
                    self.db.executemany(
                        "INSERT INTO slots VALUES (?,?,?,'active')",
                        [
                            (row["slot"], row["arm"], i)
                            for i, row in enumerate(package["slots"])
                        ],
                    )
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
                self._last_seal = None
                self._seal()
            else:
                c.require(row is not None, "MOCK_LEDGER_CORRUPT")
                assert row is not None
                self._last_seal = last_state
                c.require(
                    last_state == ledger_state_digest(self.db), "MOCK_LEDGER_ROLLBACK"
                )
                c.require(bytes(row["grant_json"]) == frozen, "MOCK_GRANT_BINDING")
                actual = {
                    (item["slot"], item["arm"])
                    for item in self.db.execute("SELECT slot,arm FROM slots")
                }
                c.require(actual == allowed, "MOCK_GRANT_SLOT")
                ordered = [
                    (item["slot"], item["arm"])
                    for item in self.db.execute(
                        "SELECT slot,arm FROM slots ORDER BY position"
                    )
                ]
                c.require(
                    ordered
                    == [(item["slot"], item["arm"]) for item in package["slots"]],
                    "MOCK_GRANT_SLOT_ORDER",
                )
                # Reopen cannot advance if any earlier attempt is unresolved,
                # including a crash after recording unknown but before stop.
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    recovered = False
                    if self.db.execute(
                        "SELECT 1 FROM attempts WHERE state IN ('reserved','sent','unknown','cancelled','late')"
                    ).fetchone() or self.db.execute(
                        "SELECT 1 FROM slots WHERE status='started'"
                    ).fetchone():
                        c.require(
                            row["status"] != "complete", "MOCK_TERMINAL_INTEGRITY"
                        )
                        self.db.execute(
                            "UPDATE attempts SET state='unknown' WHERE state IN ('reserved','sent')"
                        )
                        self.db.execute(
                            "UPDATE batch SET status=? WHERE status='active'",
                            (
                                "stop_unconfirmed"
                                if type(transport) is supervised.SupervisedMockTransport
                                else "stopped",
                            ),
                        )
                        self.db.execute(
                            "UPDATE slots SET status='failed' WHERE status='started'"
                        )
                        recovered = True
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
                if recovered:
                    self._seal()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            os.close(self._lock_fd)
            raise
        self.transport = transport
        self._send_fence = pinned.DispatchFence()
        try:
            if type(self.transport) is pinned.PinnedResponsesTransport:
                self.transport.bind_stop_fence(self._send_fence)
        except BaseException:
            self.db.close()
            os.close(self._lock_fd)
            raise
        self._gate = asyncio.Lock()
        self._running = False
        self._abandoned = False
        self._stop_unconfirmed = self.batch_status() == "stop_unconfirmed"
        self._late_tasks: set[asyncio.Task[Any]] = set()
        self._execution_task: asyncio.Task[Any] | None = None
        self._verified_complete: set[tuple[str, str]] = set()
        self._ordinal = 0
        self._previous: str | None = None
        try:
            self._check_order()
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        import os

        c.require(not self._running and not self._late_tasks, "MOCK_PENDING_CLEANUP")
        self.db.close()
        os.close(self._lock_fd)

    def abandon_pending(self) -> None:
        """Close a stopped controller without waiting for an unresponsive daemon.

        Its sent reservations remain unknown; any later bytes are discarded.
        This cannot stop a remote provider or terminate an arbitrary Python thread.
        """
        c.require(
            not self._abandoned and self.batch_status() in ("stopped", "stop_unconfirmed"),
            "MOCK_NOT_STOPPED",
        )
        self._verify_seal()
        self._abandoned = True
        if self._execution_task is not None and not self._execution_task.done():
            self._execution_task.cancel()
        for task in self._late_tasks:
            task.cancel()
        self.db.close()
        os.close(self._lock_fd)

    async def drain_late(self, timeout: float) -> bool:
        """Wait at most timeout for retained late responses, without retrying."""
        c.require(type(timeout) in (float, int) and timeout >= 0, "MOCK_DRAIN_TIMEOUT")
        pending = set(self._late_tasks)
        if self._execution_task is not None and not self._execution_task.done():
            pending.add(self._execution_task)
        if pending:
            await asyncio.wait(pending, timeout=float(timeout))
        return not self._late_tasks and not self._running

    def _retain_late(
        self, task: asyncio.Task[tuple[int, bytes, bool]], scope: tuple[str, str, int]
    ) -> None:
        async def retain() -> None:
            try:
                status, raw, overflow = await task
            except BaseException:
                return
            if self._abandoned:
                return
            async with self._gate:
                if self._abandoned:
                    return
                self._verify_seal()
                row = self.db.execute(
                    "SELECT state FROM attempts WHERE slot=? AND arm=? AND ordinal=?",
                    scope,
                ).fetchone()
                c.require(
                    row is not None
                    and row["state"] == "unknown"
                    and self.batch_status() in ("stopped", "stop_unconfirmed")
                    and self._selected == scope[:2],
                    "MOCK_LATE_BINDING",
                )
                protected = self._protect_response(scope, raw, status)
                self.db.execute(
                    "UPDATE attempts SET state=?,response=?,http_status=?,response_sha=? "
                    "WHERE slot=? AND arm=? AND ordinal=?",
                    (
                        "unknown" if overflow else "late",
                        protected,
                        status,
                        hashlib.sha256(raw).hexdigest(),
                        *scope,
                    ),
                )
                self._seal()
                if not overflow:
                    try:
                        self._record_usage(scope[2], raw)
                    except Exception:
                        # Unknown usage retains the entire reservation.
                        pass

        background = asyncio.create_task(retain())
        self._late_tasks.add(background)

        def finished(done: asyncio.Task[Any]) -> None:
            self._late_tasks.discard(done)
            if not done.cancelled():
                # Retrieve any exception; the stopped ledger remains authoritative.
                done.exception()

        background.add_done_callback(finished)

    def _protect_response(self, scope: tuple[str, str, int], raw: bytes, http_status: int) -> bytes:
        return raw

    def _restore_response(self, row: sqlite3.Row) -> bytes:
        return bytes(row["response"])

    def _check_response_material(self, raw: bytes) -> None:
        return None

    def _seal(self) -> None:
        c.require(
            read_anchor(self._ledger_path, self._grant_bytes) == self._last_seal,
            "MOCK_LEDGER_ANCHOR",
        )
        state = ledger_state_digest(self.db)
        fd = os.open(
            Path(str(self._ledger_path) + ".anchor"),
            os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW,
        )
        with os.fdopen(fd, "ab") as anchor:
            details = os.fstat(anchor.fileno())
            c.require(
                stat.S_ISREG(details.st_mode)
                and details.st_nlink == 1
                and details.st_size + 65 <= 1024 * 1024,
                "MOCK_LEDGER_ANCHOR",
            )
            anchor.write(state.encode("ascii") + b"\n")
            anchor.flush()
            os.fsync(anchor.fileno())
        self._last_seal = state

    def _verify_seal(self) -> None:
        c.require(
            read_anchor(self._ledger_path, self._grant_bytes) == self._last_seal
            and ledger_state_digest(self.db) == self._last_seal,
            "MOCK_LEDGER_ROLLBACK",
        )

    def status(self) -> str:
        overall = self.batch_status()
        if overall in ("stopped", "stop_unconfirmed"):
            return overall
        row = self.db.execute(
            "SELECT status FROM slots WHERE slot=? AND arm=?", self._selected
        ).fetchone()
        c.require(row is not None, "MOCK_SELECTED_SLOT")
        return "active" if row[0] == "started" else str(row[0])

    def batch_status(self) -> str:
        return str(self.db.execute("SELECT status FROM batch").fetchone()[0])

    def _check_order(self) -> None:
        if self.batch_status() != "active" or self.status() == "complete":
            return
        first = self.db.execute(
            "SELECT slot,arm FROM slots WHERE status!='complete' ORDER BY position LIMIT 1"
        ).fetchone()
        c.require(
            first is not None and tuple(first) == self._selected, "MOCK_SLOT_ORDER"
        )

    def select_slot(self, slot: str, arm: str) -> None:
        c.require(
            not self._running and self.batch_status() != "stopped", "MOCK_SLOT_SWITCH"
        )
        candidate = (slot, arm)
        allowed = {(row["slot"], row["arm"]) for row in self.package["slots"]}
        c.require(candidate in allowed, "MOCK_SELECTED_SLOT")
        old_selection = self._selected
        self._selected = candidate
        try:
            self._check_order()
        except BaseException:
            self._selected = old_selection
            raise
        self._ordinal, self._previous = 0, None

    def _ensure_window(self) -> None:
        status = self.status()
        c.require(status in ("active", "complete"), "MOCK_STOPPED")
        if status == "active":
            c.require(time.time() < self.grant["deadline"], "MOCK_STOPPED_OR_EXPIRED")

    def _finish_slot(self) -> None:
        self._verify_seal()
        self._ensure_window()
        if self.status() == "complete":
            return
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "UPDATE slots SET status='complete' WHERE slot=? AND arm=?",
                self._selected,
            )
            if not self.db.execute(
                "SELECT 1 FROM slots WHERE status!='complete' LIMIT 1"
            ).fetchone():
                self.db.execute(
                    "UPDATE batch SET status='complete' WHERE status='active'"
                )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self._seal()

    @property
    def package(self) -> dict[str, Any]:
        row = self.db.execute("SELECT grant_json FROM batch").fetchone()
        c.require(
            row is not None and bytes(row[0]) == self._grant_bytes, "MOCK_GRANT_BINDING"
        )
        return dict(json.loads(self._grant_bytes))

    @property
    def grant(self) -> dict[str, Any]:
        package = self.package
        row = next(
            (
                item
                for item in package["slots"]
                if (item["slot"], item["arm"]) == self._selected
            ),
            None,
        )
        c.require(row is not None, "MOCK_SELECTED_SLOT")
        assert row is not None
        return {
            **{
                k: package[k]
                for k in (
                    "batch",
                    "calls",
                    "input",
                    "output",
                    "request_bytes",
                    "deadline",
                )
            },
            **row,
        }

    async def stop(self) -> None:
        if self._abandoned:
            return
        self._send_fence.stop()
        if type(self.transport) is supervised.SupervisedMockTransport:
            confirmed = await _daemon_call(self.transport.stop_and_confirm, supervised.STOP_GRACE)
            self._stop_unconfirmed |= not confirmed
        async with self._gate:
            if self._abandoned:
                return
            self._verify_seal()
            if self.batch_status() == "complete":
                return
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    "UPDATE batch SET status=? WHERE status IN ('active','stopped','stop_unconfirmed')",
                    ("stop_unconfirmed" if self._stop_unconfirmed else "stopped",),
                )
                self.db.execute(
                    "UPDATE attempts SET state='unknown' WHERE state='sent'"
                )
                self.db.execute(
                    "UPDATE attempts SET state='cancelled' WHERE state='reserved'"
                )
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self._seal()
        if self._stop_unconfirmed:
            raise c.ContractError("STOP_UNCONFIRMED")

    async def _mark_failed(self) -> None:
        """Record the attempted slot even when failure happened before dispatch."""
        if self._abandoned:
            return
        async with self._gate:
            if self._abandoned:
                return
            self._verify_seal()
            current = self.db.execute(
                "SELECT status FROM slots WHERE slot=? AND arm=?", self._selected
            ).fetchone()
            c.require(current is not None, "MOCK_SELECTED_SLOT")
            if current[0] in ("active", "started"):
                self.db.execute(
                    "UPDATE slots SET status='failed' WHERE slot=? AND arm=?",
                    self._selected,
                )
                self._seal()

    def fixed_denominator_summary(self) -> dict[str, Any]:
        """Summarize every frozen arm/slot; completion is not a quality pass."""
        self._verify_seal()
        rows = []
        for item in self.package["slots"]:
            pair = (item["slot"], item["arm"])
            state = self.db.execute(
                "SELECT status FROM slots WHERE slot=? AND arm=?", pair
            ).fetchone()[0]
            attempts = self.db.execute(
                "SELECT COUNT(*) FROM attempts WHERE slot=? AND arm=?", pair
            ).fetchone()[0]
            if state == "complete":
                outcome = (
                    "local_refused" if item["kind"] == "refusal" else "mechanical_complete"
                )
            elif state == "started" and self.batch_status() == "active":
                outcome = "in_progress"
            elif state in ("failed", "started") or attempts:
                outcome = "failed_or_unknown"
            else:
                outcome = "not_run"
            rows.append(
                dict(slot=pair[0], arm=pair[1], kind=item["kind"], outcome=outcome)
            )
        return dict(
            batch_status=self.batch_status(),
            denominator=len(rows),
            slots=rows,
            semantic_quality_evaluated=False,
        )

    async def _exchange(
        self, stage: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._verify_seal()
        self._ensure_window()
        policy = budget.DevelopmentPolicy(
            self.grant["request_bytes"], self.grant["input"], 8000
        )
        body, measurement = await _daemon_call(
            budget.build, stage, payload, policy
        )
        self._verify_seal()
        self._ensure_window()
        if type(self.transport) in (pinned.PinnedResponsesTransport, supervised.SupervisedMockTransport):
            safe_transport = cast(pinned.PinnedResponsesTransport | supervised.SupervisedMockTransport, self.transport)
            await _daemon_call(safe_transport.ensure_request_safe, body)
            self._verify_seal()
            self._ensure_window()
        runtime = self.package["runtime_contract"]
        c.require(runtime == runtime_contract(self.transport), "MOCK_RUNTIME_BINDING")
        role = "review" if stage.startswith("review_") else "generation"
        target_url = runtime["routes"][role]["url"]
        ordinal = self._ordinal
        slot, arm = self._selected
        scope = (slot, arm, ordinal)
        row = self.db.execute(
            "SELECT * FROM attempts WHERE slot=? AND arm=? AND ordinal=?", scope
        ).fetchone()
        if row is None:
            async with self._gate:
                self._verify_seal()
                c.require(
                    self.status() == "active" and time.time() < self.grant["deadline"],
                    "MOCK_STOPPED_OR_EXPIRED",
                )
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    stats = self.db.execute(
                        "SELECT COUNT(*), COALESCE(SUM(input_reserved),0), COALESCE(SUM(output_reserved),0) FROM attempts"
                    ).fetchone()
                    slot_calls = self.db.execute(
                        "SELECT COUNT(*) FROM attempts WHERE slot=? AND arm=?",
                        (slot, arm),
                    ).fetchone()[0]
                    c.require(
                        stats[0] < self.grant["calls"]
                        and slot_calls < (4 if arm == "B" else 5)
                        and stats[1] + measurement["local_input_reservation"]
                        <= self.grant["input"]
                        and stats[2] + 8000 <= self.grant["output"],
                        "MOCK_BUDGET",
                    )
                    self.db.execute(
                        "INSERT INTO attempts (slot,arm,ordinal,stage,request,request_sha,previous_receipt,input_reserved,output_reserved,state) VALUES (?,?,?,?,?,?,?,?,?,'reserved')",
                        (
                            slot,
                            arm,
                            ordinal,
                            stage,
                            body,
                            measurement["body_sha256"],
                            self._previous,
                            measurement["local_input_reservation"],
                            8000,
                        ),
                    )
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
                self._seal()
                self.db.execute(
                    "UPDATE attempts SET state='sent' WHERE slot=? AND arm=? AND ordinal=? AND state='reserved'",
                    scope,
                )
                self._seal()
                started = asyncio.Event()
                owner_loop = asyncio.get_running_loop()

                async def begin(request: httpx.Request) -> httpx.Response:
                    c.require(not self._send_fence.is_set(), "MOCK_STOPPED")
                    request.extensions["edumind_stage"] = stage
                    request.extensions["edumind_ordinal"] = ordinal
                    request.extensions["edumind_arm"] = arm
                    owner_loop.call_soon_threadsafe(started.set)
                    return await self.transport.handle_async_request(request)

                async def send() -> tuple[int, bytes, bool]:
                    async with httpx.AsyncClient(
                        transport=httpx.MockTransport(begin),
                        trust_env=False,
                        follow_redirects=False,
                    ) as client:
                        async with client.stream(
                            "POST",
                            target_url,
                            content=body,
                            headers={
                                "Accept-Encoding": "identity",
                                "Content-Type": "application/json",
                            },
                        ) as response:
                            chunks = bytearray()
                            c.require(
                                response.headers.get(
                                    "content-encoding", "identity"
                                ).lower()
                                == "identity",
                                "MOCK_CONTENT_ENCODING",
                            )
                            async for chunk in response.aiter_raw():
                                remaining = MAX_RESPONSE - len(chunks)
                                chunks.extend(chunk[:remaining])
                                if len(chunk) > remaining:
                                    return response.status_code, bytes(chunks), True
                            return response.status_code, bytes(chunks), False

                # Keep even a synchronous or cancellation-suppressing transport
                # off the caller's event loop and its default executor. The
                # daemon's late result is evidence only after the batch stops.
                task = asyncio.create_task(_daemon_call(lambda: asyncio.run(send())))
                waiter = asyncio.create_task(started.wait())
                request_started = time.monotonic()
                request_timeout = min(
                    HTTP_WALL_SECONDS,
                    max(0.0, self.grant["deadline"] - time.time()),
                )
                if type(self.transport) is supervised.SupervisedMockTransport:
                    request_timeout = max(0.0, request_timeout - supervised.STOP_GRACE)
                done, _ = await asyncio.wait(
                    (task, waiter),
                    timeout=request_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not started.is_set():
                    self._send_fence.stop()
                    waiter.cancel()
                    self.db.execute("BEGIN IMMEDIATE")
                    try:
                        self.db.execute(
                            "UPDATE attempts SET state='unknown' WHERE slot=? AND arm=? AND ordinal=?",
                            scope,
                        )
                        self.db.execute(
                            "UPDATE batch SET status=?",
                            (
                                "stop_unconfirmed"
                                if type(self.transport) is supervised.SupervisedMockTransport
                                else "stopped",
                            ),
                        )
                        self.db.execute("COMMIT")
                    except BaseException:
                        self.db.execute("ROLLBACK")
                        raise
                    self._seal()
                    if not task.done():
                        self._retain_late(task, scope)
                    elif not task.cancelled():
                        task.exception()
                    raise c.ContractError("MOCK_SEND_UNKNOWN")
                waiter.cancel()
            try:
                left = max(0.0, request_timeout - (time.monotonic() - request_started))
                done, _ = await asyncio.wait((task,), timeout=left)
                if not done:
                    await self.stop()
                    self._retain_late(task, scope)
                    raise c.ContractError("MOCK_HTTP_TIMEOUT")
                http_status, raw, overflow = task.result()
            except BaseException:
                await self.stop()
                if not task.done() and not self._late_tasks:
                    self._retain_late(task, scope)
                raise
            async with self._gate:
                self._verify_seal()
                state = self.status()
                expired = time.time() >= self.grant["deadline"]
                if expired:
                    state = "stopped"
                protected = self._protect_response(scope, raw, http_status)
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    if expired or overflow:
                        self.db.execute(
                            "UPDATE batch SET status='stopped' WHERE status='active'"
                        )
                    self.db.execute(
                        "UPDATE attempts SET state=?,response=?,http_status=?,response_sha=? WHERE slot=? AND arm=? AND ordinal=?",
                        (
                            "unknown"
                            if overflow
                            else "responded"
                            if state == "active"
                            else "late",
                            protected,
                            http_status,
                            hashlib.sha256(raw).hexdigest(),
                            *scope,
                        ),
                    )
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
                self._seal()
                if overflow:
                    raise c.ContractError("MOCK_RESPONSE_SIZE")
                if state != "active":
                    # Late bytes are kept, and never advance a stopped batch.
                    self._record_usage(ordinal, raw)
                    raise c.ContractError("MOCK_LATE_RESPONSE")
            row = self.db.execute(
                "SELECT * FROM attempts WHERE slot=? AND arm=? AND ordinal=?", scope
            ).fetchone()
        c.require(
            row is not None
            and row["state"] == "responded"
            and bytes(row["request"]) == body
            and row["stage"] == stage
            and row["previous_receipt"] == self._previous,
            "MOCK_REPLAY_BINDING",
        )
        raw = self._restore_response(row)
        c.require(
            hashlib.sha256(body).hexdigest() == row["request_sha"]
            and hashlib.sha256(raw).hexdigest() == row["response_sha"],
            "MOCK_RECEIPT_DIGEST",
        )
        try:
            await _daemon_call(self._check_response_material, raw)
            self._ensure_window()
            self._record_usage(ordinal, raw)
            row = self.db.execute(
                "SELECT * FROM attempts WHERE slot=? AND arm=? AND ordinal=?", scope
            ).fetchone()
            c.require(
                row["http_status"] == 200
                and row["input_used"] <= row["input_reserved"]
                and row["output_used"] <= row["output_reserved"],
                "MOCK_USAGE_OR_HTTP",
            )
            response_view, schema_echo = response_for_validation(
                body, raw, "review" if stage.startswith("review_") else "generation"
            )
            result, _ = wire.validate(
                json.loads(body),
                response_view,
                "review" if stage.startswith("review_") else "generation",
            )
        except Exception:
            await self.stop()
            raise
        core = dict(
            version=VERSION,
            package_digest=hashlib.sha256(self._grant_bytes).hexdigest(),
            batch=self.grant["batch"],
            slot=self.grant["slot"],
            arm=self.grant["arm"],
            ordinal=ordinal,
            stage=stage,
            target_url=target_url,
            prompt_version=measurement["prompt_version"],
            instruction_digest=hashlib.sha256(
                json.loads(body)["input"][0]["content"].encode("utf-8")
            ).hexdigest(),
            schema_echo=schema_echo,
            previous_receipt_digest=self._previous,
            request_digest=row["request_sha"],
            response_digest=row["response_sha"],
        )
        receipt = dict(core, receipt_digest=digest(core))
        self._previous = receipt["receipt_digest"]
        self._ordinal += 1
        return dict(result.value), receipt

    def _record_usage(self, ordinal: int, raw: bytes) -> None:
        self._verify_seal()
        value = wire.strict_json(raw)
        usage = value.get("usage") if type(value) is dict else None
        c.require(type(usage) is dict, "MOCK_USAGE_UNKNOWN")
        assert isinstance(usage, dict)
        counts = [
            usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")
        ]
        c.require(all(type(n) is int and n >= 0 for n in counts), "MOCK_USAGE_UNKNOWN")
        count_in, count_out, total = cast(list[int], counts)
        c.require(count_in + count_out == total, "MOCK_USAGE_UNKNOWN")
        current = self.db.execute(
            "SELECT input_used,output_used FROM attempts WHERE slot=? AND arm=? AND ordinal=?",
            (*self._selected, ordinal),
        ).fetchone()
        if current[0] is not None or current[1] is not None:
            c.require(
                current[0] == count_in and current[1] == count_out, "MOCK_USAGE_BINDING"
            )
        else:
            c.require(self.status() != "complete", "MOCK_USAGE_BINDING")
            self.db.execute(
                "UPDATE attempts SET input_used=?, output_used=? WHERE slot=? AND arm=? AND ordinal=?",
                (count_in, count_out, *self._selected, ordinal),
            )
            self._seal()

    async def run(
        self,
        attest: Callable[
            [dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]
        ]
        | None = None,
    ) -> dict[str, Any]:
        if self._running:
            await self.stop()
            raise c.ContractError("MOCK_CONCURRENT_RUN")
        self._running = True

        async def execute() -> dict[str, Any]:
            try:
                self._verify_seal()
                c.require(self.status() in ("active", "complete"), "MOCK_NOT_ACTIVE")
                if self.status() == "active":
                    self.db.execute(
                        "UPDATE slots SET status='started' WHERE slot=? AND arm=? AND status='active'",
                        self._selected,
                    )
                    self._seal()
                if self.status() == "complete":
                    self._ordinal, self._previous = 0, None
                await self._verify_completed_prefix()
                result = await self._run(attest)
                self._verified_complete.add(self._selected)
                return result
            except BaseException:
                await self._mark_failed()
                await self.stop()
                raise
            finally:
                self._running = False

        task = asyncio.create_task(execute())
        self._execution_task = task

        def consume(done: asyncio.Task[Any]) -> None:
            if not done.cancelled():
                done.exception()

        try:
            timeout = (
                max(0.0, self.grant["deadline"] - time.time())
                if self.status() != "complete"
                else 120.0
            )
            if type(self.transport) is supervised.SupervisedMockTransport:
                timeout = max(0.0, timeout - supervised.STOP_GRACE)
            done, _ = await asyncio.wait((task,), timeout=timeout)
            if done:
                return task.result()
            await self._mark_failed()
            await self.stop()
            task.add_done_callback(consume)
            raise c.ContractError("MOCK_DEADLINE_TIMEOUT")
        except asyncio.CancelledError:
            await self._mark_failed()
            await self.stop()
            task.add_done_callback(consume)
            raise

    async def _verify_completed_prefix(self) -> None:
        original, ordinal, previous = self._selected, self._ordinal, self._previous
        ordered = [(row["slot"], row["arm"]) for row in self.package["slots"]]
        try:
            for pair in ordered[: ordered.index(original)]:
                if pair in self._verified_complete:
                    continue
                self._selected = pair
                self._ordinal, self._previous = 0, None
                c.require(self.status() == "complete", "MOCK_SLOT_ORDER")
                await self._run(None)
                self._verified_complete.add(pair)
        finally:
            self._selected, self._ordinal, self._previous = original, ordinal, previous

    async def _run(
        self,
        attest: Callable[
            [dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]
        ]
        | None = None,
    ) -> dict[str, Any]:
        """Reconstruct every stage from persisted actual Mock request/response bytes."""
        c.require(
            self._ordinal == 0 and self.status() in ("active", "complete"),
            "MOCK_NOT_ACTIVE",
        )
        arm, spec, slot = self.grant["arm"], self.grant["spec"], self.grant["slot"]
        self._ensure_window()
        self._check_order()
        if self.grant["kind"] == "refusal":
            try:
                admitted = validate_spec(spec)
                if self.grant["question"] is not None:
                    answer(build_example(admitted), self.grant["question"])
            except SpecError as exc:
                reason = str(exc)
                expected_refusal = (
                    reason,
                    digest(spec),
                    digest(self.grant["question"]),
                )
                old_refusal = self.db.execute(
                    "SELECT reason,spec_digest,question_digest FROM local_refusals WHERE slot=? AND arm=?",
                    self._selected,
                ).fetchone()
                if old_refusal is None:
                    self.db.execute(
                        "INSERT INTO local_refusals VALUES (?,?,?,?,?)",
                        (*self._selected, *expected_refusal),
                    )
                    self._seal()
                else:
                    c.require(
                        tuple(old_refusal) == expected_refusal, "MOCK_REFUSAL_BINDING"
                    )
                self._finish_slot()
                return dict(
                    status="local_refused",
                    reason=reason,
                    real_provider_calls=0,
                    independent_evaluation=False,
                )
            raise c.ContractError("MOCK_EXPECTED_REFUSAL_NOT_REJECTED")
        catalog = c.make_catalog(spec)
        common = old.baseline_input(spec)
        plan_digest = None
        if arm == "C":
            plan, plan_receipt = await self._exchange(
                "C_plan", teaching.plan_input(spec, catalog)
            )
            c.validate("C_plan", plan, catalog=catalog)
            plan_digest = plan_receipt["receipt_digest"]
            initial = teaching.content_input(common, catalog, plan)
        else:
            initial = common
        versions, reviews = [], []
        prior = previous_review = None
        current = initial
        for revision in range(2):
            stage = arm + (
                "_repair" if revision else ("_content" if arm == "C" else "_generate")
            )
            value, receipt = await self._exchange(stage, current)
            c.validate(stage, value, catalog=catalog if arm == "C" else None)
            ident = c.identity(
                self.grant["batch"],
                slot,
                arm,
                revision,
                spec,
                prior["artifact_digest"] if prior else None,
            )
            raw_request = self.db.execute(
                "SELECT request FROM attempts WHERE slot=? AND arm=? AND ordinal=?",
                (*self._selected, self._ordinal - 1),
            ).fetchone()[0]
            instruction = json.loads(bytes(raw_request))["input"][0]["content"]
            ident.update(
                prompt_version=prompts.PROMPT_VERSION,
                binding_version=teaching.VERSION,
                stage=stage,
                instruction_digest=hashlib.sha256(
                    instruction.encode("utf-8")
                ).hexdigest(),
                request_digest=receipt["request_digest"],
                response_digest=receipt["response_digest"],
                receipt_digest=receipt["receipt_digest"],
                plan_receipt_digest=plan_digest,
                parent_review_receipt_digest=previous_review["receipt_digest"]
                if previous_review
                else None,
            )
            expanded = await _daemon_call(worker.expand, value, ident, catalog)
            self._ensure_window()
            candidate, view, binding = (
                expanded["artifact"],
                expanded["view"],
                expanded["binding"],
            )
            opinion, review_receipt = await self._exchange("review_" + arm, view)
            sent = self.db.execute(
                "SELECT request FROM attempts WHERE slot=? AND arm=? AND ordinal=?",
                (*self._selected, self._ordinal - 1),
            ).fetchone()[0]
            sent_view = json.loads(bytes(sent))["input"][1]["content"].encode("utf-8")
            await _daemon_call(
                worker.validate_review, opinion, sent_view, candidate, catalog, binding
            )
            self._ensure_window()
            versions.append(candidate)
            reviews.append(opinion)
            outcome = c.review_disposition(opinion)
            if outcome == "advisory_pass":
                self._finish_slot()
                return dict(
                    versions=versions,
                    opinions=reviews,
                    status="mock_advisory_pass",
                    real_provider_calls=0,
                )
            c.require(
                revision == 0 and outcome == "ordinary_revise", "MOCK_REVIEW_STOP"
            )
            if arm == "B":
                expected = dict(
                    candidate_digest=candidate["artifact_digest"],
                    review_receipt_digest=review_receipt["receipt_digest"],
                    issues_digest=digest(opinion["issues"]),
                )
                saved = self.db.execute(
                    "SELECT value FROM attestation WHERE slot=? AND arm=?",
                    self._selected,
                ).fetchone()
                record = (
                    json.loads(bytes(saved[0]))
                    if saved
                    else (
                        await _daemon_call(
                            attest, candidate, opinion, review_receipt
                        )
                        if attest
                        else None
                    )
                )
                self._ensure_window()
                c.require(
                    type(record) is dict
                    and set(record) == set(expected) | {"reviewer", "approved"}
                    and all(record[k] == v for k, v in expected.items())
                    and type(record["reviewer"]) is str
                    and bool(record["reviewer"])
                    and record["approved"] is True,
                    "MOCK_B_FEEDBACK_ATTESTATION",
                )
                await _daemon_call(self._check_response_material, canonical(record))
                self._ensure_window()
                if saved is None:
                    self.db.execute(
                        "INSERT INTO attestation VALUES (?,?,?)",
                        (*self._selected, canonical(record)),
                    )
                    self._seal()
            current = teaching.repair_input(initial, candidate, opinion)
            prior, previous_review = candidate, review_receipt
        raise c.ContractError("MOCK_UNREACHABLE")
