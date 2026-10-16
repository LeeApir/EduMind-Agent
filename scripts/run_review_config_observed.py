"""Future isolated comparison executor with safe failure evidence; not a prepared run."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.om_diagnostic import MODEL, stable

BASE = "docs/acceptance/phase-1-review-config-r02"
PRIVATE = "local-materials/phase-1-review-config-r02"
from acceptance_support.phase1_budget import (
    Approval,
    FrozenBudget,
    GateFailure,
    canonical,
    sha,
)
from acceptance_support.failure_observation import CompletionStream, observe_failure
from run_deepseek_connection import Audit
from app.agents.hybrid_resource_review import route_review
from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.provider_gateway import (
    ChatMessage,
    StructuredRequest,
    TextRequest,
)
from app.services.provider_protocol import strict_json


def require(condition, code):
    if not condition:
        raise GateFailure(code)


def reflected(value, key):
    """Check decoded strings as well as raw bytes (JSON can escape ASCII letters)."""
    if isinstance(value, str):
        return key in value or re.search(r"sk-[A-Za-z0-9_-]{16,}", value) is not None
    if isinstance(value, dict):
        return any(reflected(k, key) or reflected(v, key) for k, v in value.items())
    if isinstance(value, list):
        return any(reflected(v, key) for v in value)
    return False


def read(path):
    require(not path.is_symlink() and path.is_file(), "NOT_AUTHORIZED")
    return strict_json(path.read_bytes())


def private_write(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


def load(root=ROOT):
    p = read(root / BASE / "proposal.json")
    # Approval is absent by default and cannot be minted by a CLI flag or model result.
    a = read(root / BASE / "run-approval.json")
    require(
        set(a)
        == {
            "version",
            "proposal_sha256",
            "requests",
            "cost_micro_cny",
            "labels_sha256",
            "confirmed_by",
            "user_confirmation",
            "source_message_id",
            "terms_verified_on",
        }
        and a["version"] == "om-admission-human-approval-v1"
        and a["proposal_sha256"] == stable(p)
        and type(a["requests"]) is int
        and a["requests"] == p["requests"] == 14
        and type(a["cost_micro_cny"]) is int
        and a["cost_micro_cny"] == p["cost_micro_cny"]
        and a["labels_sha256"] == p["labels_sha256"]
        and a["confirmed_by"] == "Lee"
        and all(
            isinstance(a[k], str) and a[k].strip()
            for k in ("user_confirmation", "source_message_id")
        )
        and a["terms_verified_on"] == time.strftime("%Y-%m-%d")
        and time.time() < datetime.fromisoformat(p["expiry_local"]).timestamp(),
        "NOT_AUTHORIZED",
    )
    require(p["execution_root"] == str(root.resolve()), "TARGET_CHANGED")
    for name, expected in p["sources"].items():
        path = root / name
        require(
            not path.is_symlink()
            and path.resolve().is_relative_to(root.resolve())
            and sha(path.read_bytes()) == expected,
            "FREEZE_CHANGED",
        )
    data = read(root / BASE / "cases.json")
    require(
        stable(data) == p["cases_sha256"]
        and stable(read(root / BASE / "proposed-labels.json")) == p["labels_sha256"]
        and stable(read(root / BASE / "token-cost-proof.json")) == p["proof_sha256"],
        "FREEZE_CHANGED",
    )
    labels = read(root / BASE / "labels-human.json")
    require(
        labels.get("proposal_sha256") == stable(p)
        and labels.get("labels_sha256") == p["labels_sha256"]
        and labels.get("case_digests")
        == {name: stable(c["material"]) for name, c in data.items()}
        and labels.get("decision") == "accept_calibration_labels"
        and labels.get("reviewer") == "Lee"
        and isinstance(labels.get("source_message_id"), str)
        and bool(labels["source_message_id"].strip()),
        "LABEL_REVIEW_REQUIRED",
    )
    require(
        tuple(data) == tuple(s["id"] for s in p["slots"])
        and len(data) == 14
        and (root / BASE / "human-review.md").read_text()
        == __import__("prepare_review_config_comparison").review_document(data)
        and read(root / BASE / "token-cost-proof.json")["checked_on"]
        == time.strftime("%Y-%m-%d"),
        "FREEZE_CHANGED",
    )
    return p, a, data


def manifest(p, root):
    target = {
        "provider_type": "openai-compatible",
        "model_id": MODEL,
        "adapter_sha256": p["sources"]["backend/app/services/deepseek_responses.py"],
        "capability_sha256": p["proof_sha256"],
        "model_revision": "DeepSeek-V4.1-Flash",
        "currency": "CNY",
        "input_price_micro_per_million": 2000000,
        "output_price_micro_per_million": 8000000,
        "input_overhead_tokens": 1048576,
        "max_wire_bytes": max(s["wire_bytes"] for s in p["slots"]),
        "max_total_output_tokens": 2048,
        "total_output_limit_verified": True,
        # This inherited kernel flag denotes a PROVEN BOUND, not byte/token equality.
        "token_byte_bound_verified": True,
        "output_limit_path": ["max_output_tokens"],
    }
    target_id = stable(target)
    files = {
        **p["sources"],
        **{
            str(Path(BASE) / k): sha((root / BASE / k).read_bytes())
            for k in (
                "proposal.json",
                "cases.json",
                "proposed-labels.json",
                "token-cost-proof.json",
            )
        },
    }
    files[str(Path(BASE) / "labels-human.json")] = sha(
        (root / BASE / "labels-human.json").read_bytes()
    )
    return {
        "version": "phase1-run-v1",
        "run_id": "review-config-r02",
        "state": "FROZEN_RUN_READY",
        "phase": "diagnostic",
        "files": files,
        "targets": {target_id: target},
        "slots": [
            {
                "id": s["id"],
                "input_sha256": s["wire_sha256"],
                "attempts": 1,
                "stages": ["probe"],
                "targets": [target_id],
                "resources": ["unit"],
            }
            for s in p["slots"]
        ],
        "bounds": {
            "requests": 14,
            "cost_micro": p["cost_micro_cny"],
            "max_active_attempts": 1,
            "timeout_seconds": 60,
            "corrections_per_resource": 2,
        },
        "required_evidence": ["adr", "connection"],
        "evidence": {
            "adr": files["docs/ADR/0015-approval-20261015.json"],
            "connection": files[
                "docs/acceptance/phase-1-deepseek-connection-v1/results/r01.json"
            ],
        },
    }


def credentials(root):
    path = root / ".env"
    require(not path.is_symlink(), "SAFETY_FAILURE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        st = os.fstat(stream.fileno())
        import stat

        require(
            stat.S_ISREG(st.st_mode)
            and st.st_mode & 0o077 == 0
            and st.st_uid == os.geteuid(),
            "SAFETY_FAILURE",
        )
        expected = read(root / BASE / "proposal.json")["credential_file_metadata"]
        require(all(getattr(st, k) == v for k, v in expected.items()), "TARGET_CHANGED")
        wanted = {
            "EDUMIND_PROVIDER_API_KEY",
            "EDUMIND_PROVIDER_BASE_URL",
            "EDUMIND_PROVIDER_MODEL",
            "EDUMIND_PROVIDER_STRUCTURED_TRANSPORT",
        }
        values = {}
        for line in stream:
            k, sep, v = line.partition("=")
            if sep and k.strip() in wanted:
                require(k.strip() not in values, "TARGET_CHANGED")
                values[k.strip()] = v.strip().strip('"').strip("'")
        current = os.fstat(stream.fileno())
        require(
            all(
                getattr(current, k) == getattr(st, k)
                for k in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            ),
            "SAFETY_FAILURE",
        )
    require(
        set(values) == wanted
        and values["EDUMIND_PROVIDER_BASE_URL"] == "https://api.deepseek.com"
        and values["EDUMIND_PROVIDER_MODEL"] == MODEL
        and values["EDUMIND_PROVIDER_STRUCTURED_TRANSPORT"] == "responses_json_schema",
        "TARGET_CHANGED",
    )
    key = values["EDUMIND_PROVIDER_API_KEY"]
    require(bool(key) and all(32 < ord(c) < 127 for c in key), "SAFETY_FAILURE")
    return ProviderSettings("https://api.deepseek.com", key, MODEL)


class ExactAudit(Audit):
    def __init__(self, wire, inner=None):
        super().__init__(strict_json(wire))
        self.wire = wire
        self.capture_complete = False
        if inner is not None:
            self.inner = inner

    async def handle_async_request(self, request):
        require(request.content == self.wire, "FREEZE_CHANGED")
        response = await super().handle_async_request(request)
        response.stream = CompletionStream(response.stream, self)
        return response


class PinnedGuard:
    """DNS was already bounded by the same attempt deadline; avoid a second lookup."""

    def __init__(self, approved):
        self.approved = approved

    def approve_base(self):
        return self.approved


async def assess(case, value, slot, root=ROOT):
    """Structural signals only. Human must verify the exact counterexample and gap."""
    route = route_review(value, scope="unit", catalog=case["anchors"])
    kind = case["comparison_kind"]
    if kind == "positive":
        ok = route["verdict"] == "pass"
    elif kind == "pure_gap":
        ok = (
            route["verdict"] == "needs_human"
            and not value["findings"]
            and bool(value["unresolved"])
        )
    else:
        category = "fact" if kind == "fact" else "code_safety"
        ok = route["verdict"] == "reject" and any(
            f["category"] == category and f["severity"] in {"major", "severe"}
            for f in value["findings"]
        )
    # A baseline regression is an experimental observation, never a calibration pass.
    # Candidate failure stops, with no retry or reuse of the reservation.
    if case["arm"] == "candidate":
        require(ok, "CANDIDATE_CRITERION_FAILED")
    return {
        "route": route,
        "arm": case["arm"],
        "criterion_signal": ok,
        "semantic_detection_confirmed": False,
        "human_concrete_detection_check_required": True,
        "note": "Category/route matching alone is not semantic success. Inspect actual "
        "anchors, omissions, contradictions and severity before continuation.",
    }


async def step(root=ROOT, *, transport=None, resolver=None):
    p, a, data = load(root)  # No credential/DNS/ledger access before this gate.
    private = root / PRIVATE
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(
        not private.is_symlink()
        and private.resolve().is_relative_to(root.resolve())
        and private.stat().st_mode & 0o077 == 0,
        "SAFETY_FAILURE",
    )
    fd = os.open(
        private / "execution.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = manifest(p, root)
        gate = FrozenBudget(
            m,
            private / "budget.sqlite",
            root=root,
            approval=Approval(
                stable(m), "diagnostic", 14, p["cost_micro_cny"], stable(a), True
            ),
        )
        registration = private / "enrollment.json"
        if registration.exists():
            require(
                read(registration) == {"proposal_sha256": stable(p)}
                and gate.ledger.is_file(),
                "LEDGER_MISSING",
            )
        else:
            require(not gate.ledger.exists(), "LEDGER_MISMATCH")
            private_write(registration, {"proposal_sha256": stable(p)})
        snapshot = gate.snapshot()
        require(snapshot["halted"] is None, "RUN_HALTED")
        require(
            all(r[6] == "complete" for r in snapshot["attempts"]),
            "SEND_STATE_UNCERTAIN",
        )
        require(bool(snapshot["unattempted_slots"]), "BUDGET_EXHAUSTED")
        slot = snapshot["unattempted_slots"][0]
        for row in snapshot["attempts"]:
            receipt = read(private / (row[1] + ".json"))
            human = read(private / (row[1] + "-human.json"))
            require(
                human.get("proposal_sha256") == stable(p)
                and human.get("receipt_sha256") == stable(receipt)
                and human.get("decision") == "continue"
                and human.get("reviewer") == "Lee"
                and isinstance(human.get("source_message_id"), str)
                and bool(human["source_message_id"].strip()),
                "HUMAN_CHECK_REQUIRED",
            )
        case = data[slot]
        wire = bytes.fromhex(case["wire_hex"])
        planned = next(s for s in p["slots"] if s["id"] == slot)
        require(sha(wire) == planned["wire_sha256"], "FREEZE_CHANGED")
        number = gate.reserve(
            slot, "probe", next(iter(m["targets"])), wire, resource="unit"
        )
        usage, audit = None, None
        stage = "credentials"
        try:
            async with asyncio.timeout(60):
                # Reservation precedes key/DNS; config cannot fall back to another provider.
                settings = credentials(root)
                audit = ExactAudit(wire, transport)
                kwargs = {} if resolver is None else {"resolver": resolver}
                stage = "target_resolution"
                approved = await asyncio.to_thread(
                    ProviderTargetGuard(
                        settings.base_url, TargetPolicy(), **kwargs
                    ).approve_base
                )
                body = strict_json(wire)
                adapter = DeepSeekResponsesAdapter(
                    settings,
                    PinnedGuard(approved),
                    transport=audit,
                    reasoning_effort=body["reasoning"]["effort"],
                )
                stage = "provider"
                result = await adapter.generate_structured(
                    StructuredRequest(
                        TextRequest(
                            tuple(
                                ChatMessage(m["role"], m["content"])
                                for m in body["input"]
                            ),
                            max_output_tokens=2048,
                        ),
                        body["text"]["format"]["schema"],
                    )
                )
                stage = "response_checks"
                usage = result.usage
                raw = audit.decoded()
                require(
                    settings.api_key.encode() not in raw
                    and not re.search(rb"sk-[A-Za-z0-9_-]{16,}", raw)
                    and not reflected(dict(result.value), settings.api_key),
                    "SAFETY_FAILURE",
                )
                require(
                    result.model_id == MODEL
                    and result.transport_audit is not None
                    and result.transport_audit.request_digest == sha(wire),
                    "TARGET_CHANGED",
                )
                require(
                    result.output_text_counts is not None
                    and result.output_text_counts.messages == 1
                    and result.output_text_counts.blocks == 1,
                    "INVALID_OUTPUT",
                )
                usage = result.usage
                require(
                    usage is not None
                    and type(usage.input_tokens) is int
                    and type(usage.output_tokens) is int,
                    "USAGE_UNKNOWN",
                )
                require(
                    0 <= usage.input_tokens <= 1048576 + len(wire)
                    and 0 <= usage.output_tokens <= 2048,
                    "USAGE_BOUND_EXCEEDED",
                )
                receipt = {
                    "proposal_sha256": stable(p),
                    "slot": slot,
                    "request_sha256": sha(wire),
                    "response_sha256": result.transport_audit.response_digest,
                    "value": dict(result.value),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "local_assessment": None,
                    "human_confirmed": False,
                    "t040_passed": False,
                }
                stage = "review_assessment"
                try:
                    receipt["local_assessment"] = await assess(
                        case, dict(result.value), slot, root
                    )
                except Exception:
                    receipt["local_assessment"] = {"status": "ADMISSION_FAILED"}
                    private_write(private / (slot + "-failed.json"), receipt)
                    raise
                stage = "receipt_write"
                private_write(private / (slot + ".json"), receipt)
                stage = "ledger_finish"
                gate.finish(
                    number,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
        except BaseException as exc:
            observation = observe_failure(exc, audit=audit, usage=usage, stage=stage)
            # Finalize failure and halt BEFORE evidence I/O; a disk error must not permit retry.
            try:
                gate.finish(
                    number,
                    error_code=observation["normalized_error"],
                    input_tokens=observation["input_tokens"],
                    output_tokens=observation["output_tokens_including_reasoning"],
                )
            finally:
                gate.halt("ADMISSION_FAILED")
            private_write(
                private / (slot + "-failure-observation.json"),
                {
                    "proposal_sha256": stable(p),
                    "slot": slot,
                    "attempt_number": number,
                    "reserved_wire_sha256": sha(wire),
                    "observation": observation,
                    "t040_passed": False,
                },
            )
            raise GateFailure("ADMISSION_STOPPED") from None
        return {
            "slot": slot,
            "status": "HUMAN_CHECK_REQUIRED",
            "t040_passed": False,
            "requests_sent_this_step": audit.sent,
            "receipt_sha256": stable(receipt),
        }
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-one", action="store_true", required=True)
    parser.parse_args()
    try:
        print(json.dumps(asyncio.run(step())))
    except (GateFailure, OSError, ValueError):
        print(json.dumps({"status": "STOPPED_OR_NOT_AUTHORIZED", "t040_passed": False}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
