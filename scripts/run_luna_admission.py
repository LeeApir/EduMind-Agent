"""Run one exactly frozen Luna review only after count, labels and prior-result approvals."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import hashlib
import ipaddress
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_admission_gate import (
    BASE,
    PRIVATE,
    Ledger,
    approved,
    env_metadata,
    prior_human_checks,
    private_write,
    read,
    require,
    verify_freeze,
)
from acceptance_support.luna_review_routing import CONFIG, ExplicitRouter
from acceptance_support.provider_error_decode import read_error
from acceptance_support.qwen_review_budget import canonical, sha
from app.agents.hybrid_resource_review import review_once
from app.agents.shared_learning_plan import CallWindow
from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from prepare_luna_admission import candidates


class BoundedRaw(httpx.AsyncByteStream):
    def __init__(self, inner, owner):
        self.inner, self.owner = inner, owner

    async def __aiter__(self):
        async for part in self.inner:
            self.owner.raw_bytes += len(part)
            require(self.owner.raw_bytes <= 4 * 1024 * 1024, "RESPONSE_LIMIT")
            self.owner.raw_hash.update(part)
            yield part
        self.owner.raw_complete = True

    async def aclose(self):
        await self.inner.aclose()


class ExactTransport(httpx.AsyncBaseTransport):
    def __init__(self, wire, target, authorize, inner=None):
        self.wire, self.target, self.authorize = wire, target, authorize
        self.inner = inner if inner is not None else httpx.AsyncHTTPTransport(retries=0)
        self.sent = 0
        self.status = None
        self.raw_bytes = 0
        self.raw_complete = False
        self.raw_hash = hashlib.sha256()
        self.error_metadata = None

    async def handle_async_request(self, request):
        base = urlsplit(CONFIG.review_base)
        require(
            self.sent == 0
            and request.method == "POST"
            and request.content == self.wire,
            "EXACT_WIRE_MISMATCH",
        )
        require(
            request.headers.get("host") == base.netloc
            and request.extensions.get("sni_hostname") == base.hostname
            and request.url.path == base.path + "/responses"
            and request.url.scheme == "https"
            and request.url.host in self.target.addresses
            and ipaddress.ip_address(request.url.host).is_global
            and (request.url.port or 443) == 443,
            "TARGET_CHANGED",
        )
        self.authorize()
        self.sent += 1
        response = await self.inner.handle_async_request(request)
        self.status = response.status_code
        response.stream = BoundedRaw(response.stream, self)
        if response.status_code >= 400:
            self.error_metadata = await read_error(response, self.wire)
            return httpx.Response(response.status_code, content=b"", request=request)
        return response

    async def aclose(self):
        await self.inner.aclose()


def credential(root, manifest):
    require(env_metadata(root / ".env") == manifest["env_metadata"], "ENV_CHANGED")
    values = {}
    fd = os.open(root / ".env", os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        require(
            {k: getattr(os.fstat(f.fileno()), k) for k in manifest["env_metadata"]}
            == manifest["env_metadata"],
            "ENV_CHANGED",
        )
        for line in f:
            if line.lstrip().startswith("#"):
                continue
            k, sep, v = line.strip().partition("=")
            if sep and k in {
                "EDUMIND_PROVIDER_BASE_URL",
                "EDUMIND_PROVIDER_MODEL",
                "EDUMIND_PROVIDER_API_KEY",
                "EDUMIND_PROVIDER_REVIEW_REASONING_EFFORT",
                "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
            }:
                require(k not in values, "DUPLICATE_ENV_FIELD")
                values[k] = v.strip().strip('"').strip("'")
        require(
            {k: getattr(os.fstat(f.fileno()), k) for k in manifest["env_metadata"]}
            == manifest["env_metadata"],
            "ENV_CHANGED",
        )
    require(
        values.get("EDUMIND_PROVIDER_BASE_URL") == CONFIG.review_base
        and values.get("EDUMIND_PROVIDER_MODEL") == CONFIG.review_model
        and values.get("EDUMIND_PROVIDER_REVIEW_REASONING_EFFORT")
        == CONFIG.review_reasoning
        and values.get("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT")
        == "responses_json_schema",
        "CONFIG_CHANGED",
    )
    key = values.get("EDUMIND_PROVIDER_API_KEY", "")
    require(key and all(32 < ord(c) < 127 for c in key), "KEY_UNAVAILABLE")
    return key


def safe_failure(exc):
    code = getattr(getattr(exc, "code", None), "value", getattr(exc, "code", None))
    allowed = {
        "AUTHENTICATION_FAILED",
        "RATE_LIMITED",
        "CAPABILITY_UNAVAILABLE",
        "TIMEOUT",
        "INVALID_OUTPUT",
        "TEMPORARILY_UNAVAILABLE",
        "INVALID_TARGET",
        "RESPONSE_MODEL_CHANGED",
        "USAGE_MISSING_OR_EXCEEDED",
        "EXACT_WIRE_MISMATCH",
        "TARGET_CHANGED",
        "AUDIT_MISMATCH",
        "SECRET_REFLECTION",
        "RESPONSE_LIMIT",
        "GENERATION_FORBIDDEN",
        "CONFIG_CHANGED",
        "KEY_UNAVAILABLE",
        "ENV_CHANGED",
    }
    if type(exc) is ValueError and str(exc) in allowed:
        code = str(exc)
    return (
        "TIMEOUT"
        if isinstance(exc, (TimeoutError, asyncio.CancelledError))
        else code
        if code in allowed
        else "DIAGNOSTIC_FAILURE"
    )


class LunaAttemptFailure(Exception):
    def __init__(self, code, details):
        self.code, self.details = code, details
        super().__init__(code)


async def attempt(root, manifest, case, wire, authorize):
    key = credential(root, manifest)
    guard = ProviderTargetGuard(CONFIG.review_base, TargetPolicy())
    target = await asyncio.to_thread(guard.approve_base)
    audit = ExactTransport(wire, target, authorize)
    # The selected target is pinned once; the adapter cannot resolve a different IP later.
    pinned = SimpleNamespace(approve_base=lambda: target)
    adapter = DeepSeekResponsesAdapter(
        ProviderSettings(CONFIG.review_base, key, CONFIG.review_model),
        pinned,
        transport=audit,
        reasoning_effort=CONFIG.review_reasoning,
    )

    class DenyGeneration:
        async def generate_structured(self, request):
            raise ValueError("GENERATION_FORBIDDEN")

    router = ExplicitRouter(DenyGeneration(), adapter)
    m = case["material"]
    started = __import__("time").monotonic()
    try:
        record = await review_once(
            router,
            CallWindow(),
            binding=m["binding"],
            target_digest=m["unit_digest"],
            payload={"unit": m, "reference_context": m["reference_context"]},
            candidates=candidates(case),
            scope="unit",
            input_snapshot=case["input_snapshot"],
        )
        require(
            audit.sent == 1
            and audit.raw_complete
            and record["request_digest"] == sha(wire),
            "AUDIT_MISMATCH",
        )
        require(key not in canonical(record).decode(), "SECRET_REFLECTION")
        return {
            "record": record,
            "http_status": audit.status,
            "sent": audit.sent,
            "raw_response_sha256": audit.raw_hash.hexdigest(),
            "raw_bytes": audit.raw_bytes,
            "raw_complete": audit.raw_complete,
            "actual_model": CONFIG.review_model,
            "duration_ms": round((__import__("time").monotonic() - started) * 1000),
            "input_tokens": router.last_usage.input_tokens,
            "output_tokens": router.last_usage.output_tokens,
            "response_integrity": "completed/schema/local_routing checked; semantic and citations pending human",
        }
    except BaseException as exc:
        usage = getattr(exc, "usage", None) or router.last_usage
        raise LunaAttemptFailure(
            safe_failure(exc),
            {
                "http_status": audit.status,
                "sent": audit.sent,
                "raw_bytes": audit.raw_bytes,
                "raw_response_sha256": audit.raw_hash.hexdigest(),
                "raw_complete": audit.raw_complete,
                "provider_error": audit.error_metadata,
                "output_failure_reason": getattr(
                    getattr(exc, "output_failure_reason", None), "value", None
                ),
                "schema_keyword": getattr(exc, "schema_keyword", None),
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            },
        ) from None
    finally:
        async with asyncio.timeout(5):
            await audit.aclose()


async def step(root=ROOT, perform=attempt):
    manifest, h = approved(
        root
    )  # Must precede private dirs, credential reads, DNS and HTTP.
    private = root / PRIVATE
    require(
        not private.is_symlink()
        and private.parent.resolve().is_relative_to(root.resolve()),
        "UNSAFE_PRIVATE_PATH",
    )
    private.mkdir(parents=True, mode=0o700, exist_ok=True)
    require(private.stat().st_mode & 0o077 == 0, "UNSAFE_PRIVATE_MODE")
    fd = os.open(
        private / "execution.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger = Ledger(private / "requests.sqlite", h)
        prior_human_checks(root, h, ledger)
        requests = read(root / BASE / "requests.json")
        cases = read(root / BASE / "cases.json")
        order = [s["id"] for s in read(root / BASE / "budget.json")["slots"]]
        require(
            len(order) == len(set(order)) == 12 and set(order) == set(requests),
            "SLOT_ORDER_INVALID",
        )
        require(
            order[0] == "screen-complete"
            and all(s.startswith("screen-") for s in order[:8])
            and all(s.startswith("holdout-") for s in order[8:]),
            "SLOT_ORDER_INVALID",
        )
        _, slot = ledger.reserve(order)
        n = ledger.snapshot()[2][-1][0]
        wire = bytes.fromhex(requests[slot]["wire_hex"])

        def authorize():
            approved(root)
            start, halt, rows = ledger.snapshot()
            require(
                not halt
                and __import__("time").time() - start < 1800
                and rows[-1][:3] == (n, slot, "reserved"),
                "RUN_STOPPED",
            )

        try:
            async with asyncio.timeout(60):
                outcome = await perform(root, manifest, cases[slot], wire, authorize)
            receipt = {
                "manifest_sha256": h,
                "slot": slot,
                "outcome": outcome,
                "semantic_accepted": False,
            }
            private_write(private / (slot + ".json"), receipt)
            ledger.finish(n, sha(canonical(receipt)))
            expected = next(
                x
                for x in read(root / BASE / "proposed-labels.json")["labels"]
                if x["id"] == slot
            )
            if (
                outcome["record"]["local_routing"]["verdict"]
                != expected["expected_local_verdict"]
            ):
                ledger.stop("VERDICT_CRITERION_FAILED")
                return {
                    "state": "HALTED",
                    "slot": slot,
                    "reason": "VERDICT_CRITERION_FAILED",
                }
            return {
                "state": "HUMAN_CHECK_REQUIRED",
                "slot": slot,
                "receipt_sha256": sha(canonical(receipt)),
            }
        except BaseException as exc:
            code = safe_failure(exc)
            ledger.stop(code)
            failure = {
                "manifest_sha256": h,
                "slot": slot,
                "error": code,
                "semantic_accepted": False,
                "usage": "unknown unless receipt retained",
                "details": exc.details if isinstance(exc, LunaAttemptFailure) else None,
            }
            if not (private / (slot + ".json")).exists():
                private_write(private / (slot + ".json"), failure)
            return {"state": "HALTED", "slot": slot, "reason": code}
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(__doc__)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--run-one", action="store_true")
    group.add_argument("--check-complete", action="store_true")
    a = p.parse_args()
    if a.check_complete:
        _, h = approved(ROOT)
        path = ROOT / PRIVATE / "requests.sqlite"
        require(path.is_file() and not path.is_symlink(), "RUN_NOT_STARTED")
        ledger = Ledger(path, h)
        prior_human_checks(ROOT, h, ledger)
        require(len(ledger.snapshot()[2]) == 12, "DIAGNOSTIC_INCOMPLETE")
        print(
            json.dumps(
                {
                    "state": "DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION",
                    "T040_pass": False,
                }
            )
        )
        return
    if a.run_one:
        result = asyncio.run(step())
        print(json.dumps(result))
        raise SystemExit(0 if result["state"] == "HUMAN_CHECK_REQUIRED" else 2)
    _, h = verify_freeze(ROOT)
    print(
        json.dumps(
            {
                "freeze_sha256": h,
                "real_calls": 0,
                "request_count_approval": "pending",
                "not_T040_pass": True,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No arbitrary exception message, provider payload or key in terminal.
        print(json.dumps({"state": "BLOCKED", "exception_type": type(exc).__name__}))
        raise SystemExit(2)
