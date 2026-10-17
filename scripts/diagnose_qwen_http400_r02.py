"""Independent one-request HTTP diagnostic; never resume the stopped review run."""

# ruff: noqa: E402
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_qwen_review as old
import acceptance_support.qwen_review_attempt as impl
from acceptance_support.qwen_review_budget import Approval, FrozenBudget, sha

BASE = ROOT / "docs/acceptance/phase-1-qwen-http400-r02"
PRIVATE = ROOT / "local-materials/phase-1-qwen-http400-r02"
# Only known technical words / request Schema property names can leave memory.
WORDS = set(
    "invalid parameter parameters invalidparameter invalidparametererror invalid_request_error unsupported not supported support schema json_schema response_format strict additionalproperties required properties type object array string number integer boolean enum anyof oneof allof ref defs items minitems maxitems minlength maxlength pattern format minimum maximum exclusiveMinimum exclusiveMaximum const null false true must be contain contains include includes missing field fields value values error request format is are the a an of for in at to and or with without should set specified provided allowed only can cannot does do this model output max_completion_tokens max_tokens enable_thinking temperature depth nesting maximum limit exceeded too many nested level levels length size context tokens token input greater than less equal expected found got has have been failed validation validate property names keys all each every list default please use remove change definitions top level root schema additional property empty recursive recursion unsupportedparameter document enum values total count exceed".lower().split()
)
CODES = {
    "InvalidParameter",
    "InvalidParameterError",
    "InvalidRequest",
    "InvalidSchema",
    "invalid_request_error",
    "invalid_json_schema",
    "invalid_parameter",
    "UnsupportedOperation",
    "DataInspectionFailed",
    "AccessDenied",
    "ModelNotFound",
    "BadRequest",
}


def safe_error(raw, wire):
    """Return bounded technical tokens, never raw messages, unknown values or credentials."""
    try:
        body = json.loads(raw)
        error = body.get("error", body)
        if not isinstance(error, dict):
            return {"parse": "NO_ERROR_OBJECT"}
        request = json.loads(wire)
        names = set()

        def walk(value):
            if isinstance(value, dict):
                names.update(str(k).lower() for k in value.get("properties", {}))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(request.get("response_format", {}))
        allowed = WORDS | names
        message = error.get("message", "")
        if not isinstance(message, str):
            message = ""
        tokens = re.findall(
            r"[A-Za-z_$][A-Za-z0-9_$-]*|[0-9]+|[.:,;()\[\]/=<>]", message[:8192]
        )
        filtered = [
            t
            if t.lower() in allowed
            or t in ".:,;()[]/=<> "
            or (t.isdigit() and len(t) <= 4)
            else "[redacted]"
            for t in tokens
        ]
        code = error.get("code", error.get("type"))
        return {
            "parse": "ERROR_OBJECT",
            "code": code if code in CODES else "UNRECOGNIZED_REDACTED",
            "technical_message_tokens": filtered[:400],
            "message_truncated": len(message) > 8192,
        }
    except (ValueError, TypeError, AttributeError, RecursionError):
        return {"parse": "NON_JSON_OR_UNRECOGNIZED"}


class ErrorTransport(impl.ExactTransport):
    diagnosis = None

    async def handle_async_request(self, request):
        response = await super().handle_async_request(request)
        if response.status_code >= 400:
            data = bytearray()
            try:
                async for chunk in response.stream:
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise ValueError("bounded error")
                type(self).diagnosis = safe_error(bytes(data), self.wire)
            finally:
                await response.aclose()
            # The production adapter still receives the original HTTP status.
            return __import__("httpx").Response(
                response.status_code, content=b"", request=request
            )
        return response


def context():
    p, a, data = old.load(stop_only=True)
    frozen = json.loads((BASE / "freeze.json").read_text())
    assert frozen["approval"]["user_confirmation"] == "测试qwen为什么拒绝"
    assert frozen["old_proposal_sha256"] == old.stable(p)
    for name, digest in frozen["sources"].items():
        assert sha((ROOT / name).read_bytes()) == digest
    assert frozen["request_sha256"] == p["slots"][0]["wire_sha256"]
    assert __import__("time").strftime("%Y-%m-%d") == frozen["checked_on"]
    manifest = old.manifest(p, ROOT)
    manifest["run_id"] = "qwen-http400-r02"
    manifest["slots"] = manifest["slots"][:1]
    manifest["bounds"]["requests"] = 1
    manifest["bounds"]["cost_micro"] = p["slots"][0]["cost_micro_cny"]
    manifest["files"].update(frozen["sources"])
    manifest["files"]["docs/acceptance/phase-1-qwen-http400-r02/freeze.json"] = sha(
        (BASE / "freeze.json").read_bytes()
    )
    gate = FrozenBudget(
        manifest,
        PRIVATE / "budget.sqlite",
        root=ROOT,
        approval=Approval(
            old.stable(manifest),
            "diagnostic",
            1,
            manifest["bounds"]["cost_micro"],
            old.stable(frozen["approval"]),
            True,
        ),
    )
    return p, data, gate


async def main():
    p, data, gate = context()
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    assert not PRIVATE.is_symlink() and PRIVATE.stat().st_mode & 0o077 == 0
    snap = gate.snapshot()
    assert not snap["attempts"] and not snap["halted"], "already attempted/stopped"
    slot = p["slots"][0]["id"]
    case = data[slot]
    wire = bytes.fromhex(case["candidate_wire_hex"])
    tid = next(iter(gate.manifest["targets"]))
    number = gate.reserve(slot, "probe", tid, wire, resource="unit")
    impl.ExactTransport = ErrorTransport
    observation = None
    try:
        async with asyncio.timeout(60):
            credential_policy = dict(p)
            credential_policy["credential_file_metadata"] = json.loads(
                (BASE / "freeze.json").read_text()
            )["credential_file_metadata"]
            endpoint, key = old.credentials(ROOT, credential_policy)

            async def authorize(request):
                context()
                assert (
                    request.route.model_id == "qwen3.8-max-0902"
                    and request.purpose == "connection_test"
                )
                gate._authorize()

            outcome = await impl.perform(
                case,
                wire,
                endpoint=endpoint,
                key=key,
                database_url=old.database_url(),
                authorize=authorize,
            )
            observation = {
                "status": "COMPLETE_REVIEW_NOT_ADMITTED",
                "input_tokens": outcome["input_tokens"],
                "output_tokens": outcome["output_tokens"],
                "cleanup": outcome["cleanup"],
            }
            gate.finish(
                number,
                input_tokens=outcome["input_tokens"],
                output_tokens=outcome["output_tokens"],
            )
    except BaseException as exc:
        observation = (
            exc.observation
            if isinstance(exc, impl.AttemptFailure)
            else {
                "normalized_error": "TIMEOUT"
                if isinstance(exc, TimeoutError)
                else "INVALID_OUTPUT",
                "gate_code": getattr(exc, "code", None),
                "input_tokens": None,
                "output_tokens": None,
            }
        )
        gate.finish(
            number,
            error_code=observation["normalized_error"],
            input_tokens=observation.get("input_tokens"),
            output_tokens=observation.get("output_tokens"),
        )
    finally:
        gate.halt("ADMISSION_FAILED")
    result = {
        "version": "qwen-http400-diagnosis-v1",
        "old_run_resumed": False,
        "request_sha256": sha(wire),
        "observation": observation,
        "provider_error": ErrorTransport.diagnosis,
        "t040_passed": False,
    }
    old.private_write(PRIVATE / "result.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
