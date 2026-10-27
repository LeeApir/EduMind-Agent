"""One-shot official DeepSeek synthetic observation. Default/--check is offline."""

import argparse
import asyncio
import hashlib
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.p15_candidate_compatibility import (  # noqa: E402
    ProbeFailure,
    evidence,
    parse,
    redact_check,
)
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from run_p15_candidate_compatibility import bounded_resolver  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-deepseek-flash-r01"
OUTPUT = Path("/tmp/edumind-p15-deepseek-flash-r01")
BATCH = "p15-deepseek-flash-r01"
URL = "https://api.deepseek.com/responses"
KEY_NAME = "EDUMIND_DEEPSEEK_COMPAT_API_KEY"
LIMITS = Limits(2, 8192, 640, 10000, 90)


def load_package(base=BASE, root=ROOT):
    raw = (base / "manifest.json").read_bytes()
    manifest = parse(raw)
    if (manifest.get("batch_id"), manifest.get("url"), manifest.get("limits")) != (
        BATCH,
        URL,
        asdict(LIMITS),
    ):
        raise Refused("PACKAGE_SCOPE_CHANGED")
    pins = manifest.get("sha256")
    required = {
        "scripts/run_p15_deepseek_flash_r01.py",
        "scripts/tests/test_p15_deepseek_flash_r01.py",
        "scripts/acceptance_support/p15_candidate_compatibility.py",
        "scripts/acceptance_support/p15_diagnostic_ledger.py",
        "scripts/run_p15_candidate_compatibility.py",
        "backend/app/core/provider_target.py",
        "backend/app/services/deepseek_responses.py",
        "docs/ADR/0032-deepseek-synthetic-observation.md",
    }
    required |= {
        str((base / n).relative_to(root))
        for n in ("README.md", "plan.json", "pricing.json", "S1.json", "S2.json")
    }
    required |= {str(p.relative_to(root)) for p in (root / "backend/app").rglob("*.py")}
    required |= {
        str(p.relative_to(root))
        for p in (root / "scripts/acceptance_support").glob("*.py")
    }
    required |= {"backend/pyproject.toml", "backend/uv.lock"}
    if not isinstance(pins, dict) or set(pins) != required:
        raise Refused("PACKAGE_PINS_CHANGED")
    for name, sha in pins.items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise Refused("FROZEN_PACKAGE_CHANGED")
    plan = parse((base / "plan.json").read_bytes())
    if (
        plan["url"] != URL
        or plan["model"] != "deepseek-flash"
        or plan["limits"] != asdict(LIMITS)
    ):
        raise Refused("PLAN_CHANGED")
    for name, cap, streaming in (("S1", 128, False), ("S2", 512, True)):
        body = parse((base / f"{name}.json").read_bytes())
        if (
            body["model"] != "deepseek-flash"
            or body["stream"] is not streaming
            or body["max_output_tokens"] != cap
            or body["reasoning"] != {"effort": "none"}
            or set(body)
            != {
                "model",
                "instructions",
                "input",
                "reasoning",
                "stream",
                "max_output_tokens",
                "text",
            }
            or len((base / f"{name}.json").read_bytes()) > 4096
        ):
            raise Refused("REQUEST_SCOPE_CHANGED")
        Draft202012Validator.check_schema(body["text"]["format"]["schema"])
        Draft202012Validator(body["text"]["format"]["schema"]).validate(
            plan["expected"][name]
        )
    return manifest, hashlib.sha256(raw).hexdigest(), plan


def gate(base=BASE, root=ROOT, *, now=None):
    manifest, package, plan = load_package(base, root)
    rate = parse((base / "pricing.json").read_bytes())
    stamp = now or datetime.now(timezone.utc)
    if not (
        datetime.fromisoformat(rate["checked_at"]) <= stamp
        and stamp + timedelta(seconds=90) <= datetime.fromisoformat(rate["expires_at"])
    ):
        raise Refused("PRICE_WINDOW_EXPIRED")
    path = base / "execution-authorization.json"
    if not path.is_file():
        raise Refused("DIRECT_EXECUTION_AUTHORITY_REQUIRED")
    grant = parse(path.read_bytes())
    if (
        grant.get("package_sha256") != package
        or grant.get("batch_id") != BATCH
        or grant.get("scope") != "PHASE-1.5-T038"
        or grant.get("limits") != asdict(LIMITS)
        or grant.get("authorization_basis")
        != "latest_explicit_direct_execution_instruction"
        or grant.get("new_manifest_independently_human_reviewed") is not False
        or grant.get("human_message") != "直接执行，不用批准"
        or not grant.get("evidence_ref")
        or grant.get("no_course_or_review_calls") is not True
    ):
        raise Refused("AUTHORITY_BINDING_CHANGED")
    return manifest, package, plan, grant


def credential(root=ROOT):
    # Only the explicitly dedicated key. No generic/OpenRouter/AIAPI credential fallback.
    key = os.environ.get(KEY_NAME)
    if key is None:
        key = dotenv_values(root / ".env", interpolate=False).get(KEY_NAME)
    if (
        not isinstance(key, str)
        or len(key) < 16
        or not key.isascii()
        or any(c.isspace() for c in key)
    ):
        raise Refused("DEDICATED_DEEPSEEK_CREDENTIAL_REQUIRED")
    return key


def output_text(reply):
    items = reply.get("output")
    if not isinstance(items, list) or not items:
        raise ProbeFailure("OUTPUT_MISSING")
    parts = []
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("type") != "message"
            or item.get("role") != "assistant"
        ):
            raise ProbeFailure("UNREQUESTED_OUTPUT_TYPE")
        if item.get("status") not in (None, "completed") or not isinstance(
            item.get("content"), list
        ):
            raise ProbeFailure("MESSAGE_INVALID")
        for block in item["content"]:
            if (
                not isinstance(block, dict)
                or block.get("type") != "output_text"
                or not isinstance(block.get("text"), str)
            ):
                raise ProbeFailure("OUTPUT_BLOCK_INVALID")
            parts.append(block["text"])
    return "".join(parts)


def observe(body, reply, expected):
    if not isinstance(reply, dict) or reply.get("object") != "response":
        raise ProbeFailure("RESPONSE_INVALID")
    if reply.get("status") != "completed" or reply.get("error") is not None:
        raise ProbeFailure("RESPONSE_NOT_COMPLETE")
    if reply.get("model") != "deepseek-flash":
        raise ProbeFailure("MODEL_MAPPING_CHANGED")
    if reply.get("store") is not False or reply.get("tools") not in (None, []):
        raise ProbeFailure("STORAGE_OR_TOOLS_CHANGED")
    unknown = [
        "independent_input_count_unavailable",
        "upstream_snapshot_unverified",
        "invoice_unverified",
    ]
    for field, expected_echo in (
        ("instructions", body["instructions"]),
        ("max_output_tokens", body["max_output_tokens"]),
        ("text", body["text"]),
    ):
        echo = reply.get(field)
        if echo is None:
            unknown.append(field + "_echo_missing")
        elif field == "text":
            fmt = echo.get("format") if isinstance(echo, dict) else None
            if not isinstance(fmt, dict) or any(
                fmt.get(k) != v for k, v in expected_echo["format"].items()
            ):
                raise ProbeFailure("SCHEMA_ECHO_CHANGED")
        elif echo != expected_echo:
            raise ProbeFailure("INSTRUCTIONS_OR_CAP_CHANGED")
    usage = reply.get("usage")
    if not isinstance(usage, dict):
        raise ProbeFailure("USAGE_MISSING")
    numbers = [usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")]
    if (
        not all(type(n) is int and n >= 0 for n in numbers)
        or numbers[0] + numbers[1] != numbers[2]
    ):
        raise ProbeFailure("USAGE_INVALID")
    if numbers[0] > 4096 or numbers[1] > body["max_output_tokens"]:
        raise ProbeFailure("REPORTED_USAGE_OVERFLOW")
    cached = usage.get("input_tokens_details")
    if cached is not None and (
        not isinstance(cached, dict)
        or (
            "cached_tokens" in cached
            and (
                type(cached["cached_tokens"]) is not int
                or not 0 <= cached["cached_tokens"] <= numbers[0]
            )
        )
    ):
        raise ProbeFailure("CACHE_USAGE_INVALID")
    details = usage.get("output_tokens_details")
    if details is not None and (
        not isinstance(details, dict)
        or type(details.get("reasoning_tokens", 0)) is not int
        or details.get("reasoning_tokens", 0) != 0
    ):
        raise ProbeFailure("UNEXPECTED_REASONING")
    text = output_text(reply)
    value = parse(text)
    try:
        Draft202012Validator(body["text"]["format"]["schema"]).validate(value)
    except ValidationError:
        raise ProbeFailure("LOCAL_FULL_SCHEMA_REJECTED") from None
    if value != expected:
        raise ProbeFailure("EXPECTED_OBJECT_MISMATCH")
    return {
        "protocol_observed": True,
        "unknown": unknown,
        "provider_reported_usage": dict(
            zip(("input_tokens", "output_tokens", "total_tokens"), numbers)
        ),
        "value": value,
    }


def parse_stream(raw):
    try:
        blocks = raw.decode("utf-8").replace("\r\n", "\n").split("\n\n")
    except UnicodeError:
        raise ProbeFailure("SSE_ENCODING_INVALID") from None
    events, deltas = [], []
    terminal = None
    last_seq = -1
    for block in blocks:
        if not block.strip():
            continue
        data = "\n".join(
            line[5:].lstrip(" ")
            for line in block.splitlines()
            if line.startswith("data:")
        )
        if not data:
            continue
        event = parse(data)
        if not isinstance(event, dict) or terminal is not None:
            raise ProbeFailure("SSE_AFTER_TERMINAL_OR_INVALID")
        kind, seq = event.get("type"), event.get("sequence_number")
        if not isinstance(kind, str) or type(seq) is not int or seq <= last_seq:
            raise ProbeFailure("SSE_SEQUENCE_INVALID")
        last_seq = seq
        header = [
            line[6:].strip() for line in block.splitlines() if line.startswith("event:")
        ]
        if len(header) > 1 or (header and header[0] != kind):
            raise ProbeFailure("SSE_TYPE_MISMATCH")
        if (
            "tool" in kind
            or "reasoning" in kind
            or kind in ("response.failed", "response.incomplete")
        ):
            raise ProbeFailure("SSE_UNREQUESTED_OR_FAILED")
        if "item" in event and (
            not isinstance(event["item"], dict)
            or event["item"].get("type") != "message"
        ):
            raise ProbeFailure("SSE_UNREQUESTED_ITEM")
        if "part" in event and (
            not isinstance(event["part"], dict)
            or event["part"].get("type") != "output_text"
        ):
            raise ProbeFailure("SSE_UNREQUESTED_PART")
        allowed = {
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.output_item.done",
            "response.content_part.added",
            "response.content_part.done",
            "response.output_text.delta",
            "response.output_text.done",
            "response.completed",
        }
        if kind not in allowed:
            raise ProbeFailure("SSE_EVENT_UNKNOWN")
        events.append(kind)
        if kind == "response.output_text.delta":
            if not isinstance(event.get("delta"), str):
                raise ProbeFailure("SSE_DELTA_INVALID")
            deltas.append(event["delta"])
        if kind == "response.completed":
            terminal = event.get("response")
            if not isinstance(terminal, dict):
                raise ProbeFailure("SSE_TERMINAL_INVALID")
    if (
        not isinstance(terminal, dict)
        or not deltas
        or events.count("response.completed") != 1
        or events[0] != "response.created"
    ):
        raise ProbeFailure("SSE_INCOMPLETE")
    if "".join(deltas) != output_text(terminal):
        raise ProbeFailure("SSE_DELTA_FINAL_MISMATCH")
    return terminal, events


class Runner:
    def __init__(self, base, output, package, plan, grant, key, *, clock=None):
        self.base, self.output, self.package = Path(base), Path(output), package
        self.plan, self.grant, self.key, self.clock = plan, grant, key, clock
        self.ledger = None
        self.attempted, self.observations = [], {}
        self.reported = {}

    async def execute(self, target_factory, transport_factory):
        bodies = {n: (self.base / f"{n}.json").read_bytes() for n in ("S1", "S2")}
        for raw in bodies.values():
            redact_check(raw, self.key)
        self.output.mkdir(mode=0o700, exist_ok=False)
        self.ledger = Ledger(self.output / "ledger.sqlite", clock=self.clock)
        reason, state = None, "blocked"
        try:
            self.ledger.start(
                BATCH,
                self.package,
                LIMITS,
                self.grant,
                pinned_approval_sha256=digest(self.grant),
            )
            # Reserve both slots before DNS; never release unused local holds as invoice refunds.
            for name, cap in (("S1", 128), ("S2", 512)):
                self.ledger.reserve(
                    BATCH,
                    self.package,
                    name,
                    input_max=4096,
                    output_max=cap,
                    fee_max=5000,
                    seconds=90,
                )
            try:
                async with asyncio.timeout(89):
                    target = await asyncio.to_thread(target_factory)
                    if (
                        target.url != "https://api.deepseek.com"
                        or target.hostname != "api.deepseek.com"
                    ):
                        raise ProbeFailure("TARGET_CHANGED")
                    from app.services.deepseek_responses import _wire_target

                    url, host = _wire_target(target)
                    async with httpx.AsyncClient(
                        transport=transport_factory(),
                        trust_env=False,
                        follow_redirects=False,
                        timeout=35,
                    ) as client:
                        for name, raw in bodies.items():
                            body = parse(raw)
                            with self.ledger.transaction():
                                self.ledger.guard(BATCH, self.package)
                            self.ledger.mark_sent(BATCH, self.package, name)
                            evidence(
                                self.output / f"{name}-dispatch.json",
                                {
                                    "url": URL,
                                    "body_sha256": hashlib.sha256(raw).hexdigest(),
                                    "request_bytes": len(raw),
                                },
                            )
                            self.attempted.append(name)
                            request = client.build_request(
                                "POST",
                                url,
                                headers={
                                    "Host": host,
                                    "Content-Type": "application/json",
                                    "Accept": "text/event-stream"
                                    if body["stream"]
                                    else "application/json",
                                    "Authorization": "Bearer " + self.key,
                                },
                                content=raw,
                            )
                            request.extensions["sni_hostname"] = target.hostname
                            async with asyncio.timeout(40):
                                response = await client.send(
                                    request, stream=True, follow_redirects=False
                                )
                                try:
                                    evidence(
                                        self.output / f"{name}-status.json",
                                        {"http_status": response.status_code},
                                    )
                                    content = bytearray()
                                    async for chunk in response.aiter_bytes(
                                        chunk_size=65536
                                    ):
                                        content.extend(chunk)
                                        if len(content) > 1048576:
                                            raise ProbeFailure("RESPONSE_TOO_LARGE")
                                finally:
                                    await response.aclose()
                            response_raw = bytes(content)
                            redact_check(response_raw, self.key)
                            evidence(self.output / f"{name}-response.bin", response_raw)
                            if response.status_code != 200:
                                raise ProbeFailure("HTTP_NOT_200")
                            events = None
                            if body["stream"]:
                                if "text/event-stream" not in response.headers.get(
                                    "content-type", ""
                                ):
                                    raise ProbeFailure("SSE_CONTENT_TYPE_INVALID")
                                reply, events = parse_stream(response_raw)
                            else:
                                reply = parse(response_raw)
                            if isinstance(reply, dict) and isinstance(
                                reply.get("usage"), dict
                            ):
                                self.reported[name] = {
                                    k: reply["usage"].get(k)
                                    if type(reply["usage"].get(k)) is int
                                    else None
                                    for k in (
                                        "input_tokens",
                                        "output_tokens",
                                        "total_tokens",
                                    )
                                }
                            obs = observe(body, reply, self.plan["expected"][name])
                            obs["events"] = events
                            self.ledger.record(
                                BATCH,
                                "synthetic_protocol_observed_cost_unsettled",
                                obs,
                                name,
                            )
                            with self.ledger.transaction():
                                self.ledger.guard(BATCH, self.package)
                            self.observations[name] = obs
                    state = "two_synthetic_observations_only_unsettled"
            except BaseException as exc:
                reason = (
                    str(exc)
                    if isinstance(exc, ProbeFailure)
                    else "TIMEOUT_BUDGET_TRANSPORT_OR_EVIDENCE_FAILURE"
                )
                state = "blocked"
            self.ledger.halt(
                BATCH, "provider_contract_failure" if reason else "human_pause"
            )
            for name in ("S1", "S2"):
                self.ledger.settle(BATCH, name, outcome="unknown")
            summary = {
                "batch_id": BATCH,
                "state": state,
                "safe_failure_code": reason,
                "package_sha256": self.package,
                "dispatch_markers": self.attempted,
                "dispatch_is_not_proof_of_server_execution": True,
                "observations": self.observations,
                "local_accounting": self.ledger.usage(BATCH),
                "provider_reported_usage_including_failures": self.reported,
                "unknown_holds_include_unsent_reserved_slots": True,
                "actual_invoice_usd": None,
                "T038_completed": False,
                "course_generation_authorized": False,
                "review_calls": 0,
            }
            self.ledger.record(BATCH, "terminal_result", summary)
            evidence(self.output / "summary.json", summary)
            return summary
        finally:
            self.ledger.close()


def execute():
    _, package, plan, grant = gate()
    if OUTPUT.exists():
        raise Refused("ALREADY_STARTED_NO_RESTART")
    key = credential()
    from app.core.provider_target import ProviderTargetGuard, TargetPolicy

    runner = Runner(BASE, OUTPUT, package, plan, grant, key)
    return asyncio.run(
        runner.execute(
            lambda: ProviderTargetGuard(
                "https://api.deepseek.com", TargetPolicy(), resolver=bounded_resolver
            ).approve_base(),
            lambda: httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        result = execute()
        print(result["state"])
        return (
            0 if result["state"] == "two_synthetic_observations_only_unsettled" else 2
        )
    print("PACKAGE_VERIFIED_NO_CALLS " + load_package()[1])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Refused, ProbeFailure) as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit("REFUSED_OR_STOPPED_NO_RESTART") from None
