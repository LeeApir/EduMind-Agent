"""Acceptance-only wire clock, multi-paragraph evidence and independent qualification."""

import asyncio
import codecs
import hashlib
import json
import re
import time
from contextlib import suppress


class ParagraphClock:
    """Candidate timing is mechanical; semantic acceptance is never inferred here."""

    def __init__(self):
        self.pending = ""
        self.fence = None
        self.lines = []
        self.first_ns = None
        self.candidates = []
        self.ended = False

    def feed(self, delta, now_ns):
        if self.ended:
            raise ValueError("TEMPORARY_STREAM_ALREADY_ENDED")
        # Track each character's delivery time, including fragments before line completion.
        for char in delta:
            self.pending += char
            if self.first_ns is None and char.isalnum():
                self.first_ns = now_ns
            if char == "\n":
                self.line(self.pending, now_ns)
                self.pending = ""

    def line(self, line, now_ns):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if self.fence is None:
                self.fence = marker
            elif self.fence == marker:
                self.fence = None
            if not self.lines:
                self.first_ns = None
        elif self.fence:
            if not self.lines:
                self.first_ns = None
        elif not stripped:
            self.complete(now_ns, "blank_line")
        elif re.match(r"^#{1,6}\s", stripped):
            if not self.lines:
                self.first_ns = None
        else:
            self.lines.append(line.rstrip("\r\n"))

    def complete(self, now_ns, boundary):
        text = "\n".join(self.lines).strip()
        if text:
            self.candidates.append(
                {
                    "id": len(self.candidates) + 1,
                    "text": text,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "first_token_ns": self.first_ns,
                    "completed_ns": now_ns,
                    "boundary": boundary,
                    "sentence_terminated": bool(re.search(r"[。！？.!?]", text)),
                    "qualification": "unconfirmed",
                }
            )
        self.lines = []
        self.first_ns = None

    def finish(self, now_ns):
        if self.ended:
            return
        if self.pending:
            self.line(self.pending, now_ns)
            self.pending = ""
        if self.fence is None:
            self.complete(now_ns, "temporary_stream_end")
        self.ended = True


def qualify(candidates, decisions):
    """All prior candidates must be reviewed before selecting earliest teaching content.

    Decisions bind candidate hash, acceptance and a nonempty human rationale.
    Missing decisions remain unconfirmed, never silently filtered to a passing sample.
    """
    accepted = None
    unresolved = False
    results = []
    for candidate in candidates:
        decision = decisions.get(str(candidate["id"]))
        valid = (
            decision is not None
            and decision.get("sha256") == candidate["sha256"]
            and decision.get("verdict") in {"teaching", "intro", "unconfirmed"}
            and bool(decision.get("reason", "").strip())
        )
        verdict = decision["verdict"] if valid else "unconfirmed"
        if verdict == "teaching" and not candidate["sentence_terminated"]:
            verdict = "unconfirmed"
        results.append({"id": candidate["id"], "verdict": verdict})
        if accepted is None:
            if verdict == "unconfirmed":
                unresolved = True
            if verdict == "teaching" and not unresolved:
                accepted = candidate
    return {
        "first_teaching_candidate": accepted,
        "decisions": results,
        "milestone_confirmed": accepted is not None,
    }


class SSEClock:
    def __init__(self, started_ns):
        self.started_ns = started_ns
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.pending = ""
        self.event = ""
        self.data = []
        self.paragraphs = ParagraphClock()
        self.milestones_ns = {}
        self.status = "incomplete"
        self.errors = []
        self.validated_ns = None
        self.operation_id = None  # In-memory recovery only; never exported in timing evidence.

    def feed(self, chunk, now_ns):
        self.pending += self.decoder.decode(chunk)
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            line = line.rstrip("\r")
            if line.startswith("event:"):
                self.event = line[6:].strip()
            elif line.startswith("data:"):
                self.data.append(line[5:].strip())
            elif not line and self.data:
                payload = json.loads("\n".join(self.data))
                self.data = []
                if isinstance(payload.get("operation_id"), str):
                    self.operation_id = payload["operation_id"]
                if self.event == "agent_start":
                    self.milestones_ns.setdefault("sse_status", now_ns)
                elif self.event == "token" and payload.get("temporary") is True:
                    delta = payload["delta"]
                    if delta.strip():
                        self.milestones_ns.setdefault("any_nonempty_token", now_ns)
                    self.paragraphs.feed(delta, now_ns)
                elif self.event == "stage_changed" and payload.get("stage") == "reviewing":
                    self.paragraphs.finish(now_ns)
                elif self.event == "scene_ready":
                    self.milestones_ns.setdefault("published", now_ns)
                elif self.event == "error":
                    self.errors.append(payload.get("code", "SSE_ERROR"))
                elif self.event == "done":
                    self.status = payload.get("status", "failed")

    def evidence(self, public_benchmark=False):
        # Content is exportable only for the fixed public benchmark, never arbitrary user input.
        candidates = []
        for candidate in self.paragraphs.candidates:
            item = {k: v for k, v in candidate.items() if k != "text"}
            item["characters"] = len(candidate["text"])
            if public_benchmark:
                item["public_text"] = candidate["text"]
            candidates.append(item)
        return {
            "started_ns": self.started_ns,
            "validated_ns": self.validated_ns,
            "milestones_ns": self.milestones_ns,
            "candidates": candidates,
            "temporary_stream_ended": self.paragraphs.ended,
            "status": self.status,
            "errors": self.errors,
        }


def assessed_metrics(evidence, decisions):
    reviewed = qualify(evidence["candidates"], decisions)
    chosen = reviewed["first_teaching_candidate"]
    milestones = dict(evidence["milestones_ns"])
    if chosen:
        milestones["teaching_token"] = chosen["first_token_ns"]
        milestones["teaching_paragraph"] = chosen["completed_ns"]
    metrics = {}
    for label, origin in (
        ("client_ms", evidence["started_ns"]),
        ("validated_ms", evidence.get("validated_ns")),
    ):
        metrics[label] = {
            key: (value - origin) / 1e6
            for key, value in milestones.items()
            if value is not None and origin is not None
        }
    return {
        **metrics,
        "milestone_confirmed": reviewed["milestone_confirmed"],
        "outcome_success": evidence["status"] == "published" and not evidence["errors"],
        "review": reviewed["decisions"],
    }


async def raw_learning_post(*, port, cookie, csrf, key, goal, timeout=180):
    """Restricted loopback HTTP/1.1 wire: timestamp first received header byte.

    HTTPX's response context measures completed headers, not the first wire byte.
    This path sends secrets only in memory and never exports request headers/body.
    """
    result = SSEClock(time.monotonic_ns())
    writer = None
    try:
        async with asyncio.timeout(timeout):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            body = json.dumps({"goal": goal, "preferred_language": "c"}).encode()
            if any("\r" in v or "\n" in v for v in (cookie, csrf, key)):
                raise ValueError("INVALID_HEADER")
            headers = (
                f"POST /api/learning-sessions HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                f"Origin: http://127.0.0.1:{port}\r\nCookie: edumind_session={cookie}\r\n"
                f"X-CSRF-Token: {csrf}\r\nIdempotency-Key: {key}\r\n"
                f"Content-Type: application/json\r\nAccept: text/event-stream\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            ).encode()
            writer.write(headers + body)
            await writer.drain()
            first = await reader.readexactly(1)
            result.milestones_ns["http_first_byte"] = time.monotonic_ns()
            header_block = first + await reader.readuntil(b"\r\n\r\n")
            result.milestones_ns["http_headers_complete"] = time.monotonic_ns()
            lines = header_block.decode("latin1").split("\r\n")
            status = int(lines[0].split()[1])
            if status != 200:
                result.errors.append(f"HTTP_{status}")
                return result
            fields = dict(line.lower().split(":", 1) for line in lines[1:] if ":" in line)
            if "x-acceptance-validated-at-ns" in fields:
                result.validated_ns = int(fields["x-acceptance-validated-at-ns"])
                if (
                    not result.started_ns
                    <= result.validated_ns
                    <= result.milestones_ns["http_headers_complete"]
                ):
                    raise ValueError("CLOCK_INVALID")
            if "chunked" not in fields.get("transfer-encoding", ""):
                raise ValueError("EXPECTED_CHUNKED_SSE")
            while True:
                size = int((await reader.readuntil(b"\r\n")).split(b";", 1)[0], 16)
                if size == 0:
                    break
                remaining = size
                while remaining:
                    chunk = await reader.read(min(remaining, 65536))
                    if not chunk:
                        raise asyncio.IncompleteReadError(b"", remaining)
                    remaining -= len(chunk)
                    result.feed(chunk, time.monotonic_ns())
                if await reader.readexactly(2) != b"\r\n":
                    raise ValueError("INVALID_CHUNK")
    except TimeoutError:
        result.errors.append("TOTAL_TIMEOUT")
    except (OSError, asyncio.IncompleteReadError):
        result.errors.append("INTERRUPTED")
    except (ValueError, KeyError):
        result.errors.append("PROTOCOL_ERROR")
    finally:
        if writer:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 1)
    return result
