"""Independent, one-shot synthetic compatibility runner. No teaching integration."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
from acceptance_support.p15_diagnostic_ledger import Ledger, Refused, digest
from jsonschema import Draft202012Validator, ValidationError


class ProbeFailure(ValueError):
    """Fixed safe code only; never put arbitrary provider text in exception messages."""


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProbeFailure("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def constant(_):
        raise ProbeFailure("NONFINITE_JSON")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ProbeFailure):
            raise
        raise ProbeFailure("INVALID_JSON") from None


def redact_check(raw, key):
    text = raw.decode("utf-8")
    try:
        decoded = json.dumps(json.loads(text), ensure_ascii=False)
    except ValueError:
        decoded = text
    if key and (key in text or key in decoded):
        raise Refused("CREDENTIAL_ECHO")


def evidence(path, value):
    raw = (
        value
        if isinstance(value, bytes)
        else json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def response_value(body, payload, count, expected, candidate):
    if not isinstance(payload, dict) or payload.get("object") != "response":
        raise ProbeFailure("RESPONSE_OBJECT_UNVERIFIED")
    if payload.get("model") not in candidate["response_model_ids"]:
        raise ProbeFailure("MODEL_MAPPING_UNVERIFIED")
    if payload.get("status") != "completed" or payload.get("error") is not None:
        raise ProbeFailure("RESPONSE_NOT_COMPLETE")
    if payload.get("service_tier") != "default":
        raise ProbeFailure("SERVICE_TIER_UNVERIFIED")
    if payload.get("store") is not False or payload.get("tools") not in (None, []):
        raise ProbeFailure("STORAGE_OR_TOOLS_CHANGED")
    reason = payload.get("reasoning")
    if reason is not None and (
        not isinstance(reason, dict) or reason.get("effort") not in (None, "none")
    ):
        raise ProbeFailure("REASONING_CHANGED")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise ProbeFailure("USAGE_MISSING")
    inp, out, total = [usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")]
    if any(type(n) is not int or n < 0 for n in (inp, out, total)):
        raise ProbeFailure("USAGE_TYPE_UNVERIFIED")
    if inp != count or total != inp + out:
        raise ProbeFailure("USAGE_MISMATCH")
    if out > body["max_output_tokens"]:
        raise ProbeFailure("OUTPUT_OVERFLOW")
    for field, name, upper in (
        ("input_tokens_details", "cached_tokens", inp),
        ("output_tokens_details", "reasoning_tokens", out),
    ):
        details = usage.get(field)
        if details is not None and (
            not isinstance(details, dict)
            or (
                name in details
                and (type(details[name]) is not int or not 0 <= details[name] <= upper)
            )
        ):
            raise ProbeFailure("USAGE_DETAILS_UNVERIFIED")
    ins = payload.get("instructions")
    systems = [m for m in body["input"] if m["role"] == "system"]
    if "instructions" in body:
        if ins != body["instructions"]:
            raise ProbeFailure("TOP_LEVEL_INSTRUCTIONS_UNVERIFIED")
    elif ins is not None and ins != systems and ins != "\n\n".join(m["content"] for m in systems):
        raise ProbeFailure("UNREQUESTED_INSTRUCTIONS")
    if payload.get("max_output_tokens") != body["max_output_tokens"]:
        raise ProbeFailure("OUTPUT_LIMIT_UNRESOLVED")
    text = payload.get("text")
    fmt = text.get("format") if isinstance(text, dict) else None
    if (
        not isinstance(fmt, dict)
        or fmt.get("strict") is not True
        or any(fmt.get(k) != body["text"]["format"].get(k) for k in ("type", "name", "schema"))
    ):
        raise ProbeFailure("SCHEMA_ECHO_UNVERIFIED")
    output = payload.get("output")
    if not isinstance(output, list):
        raise ProbeFailure("OUTPUT_MISSING")
    chunks = []
    for item in output:
        if not isinstance(item, dict):
            raise ProbeFailure("OUTPUT_TYPE_UNVERIFIED")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise ProbeFailure("UNREQUESTED_OUTPUT_TYPE")
        if item.get("status") not in (None, "completed") or not isinstance(
            item.get("content"), list
        ):
            raise ProbeFailure("MESSAGE_NOT_COMPLETE")
        for block in item["content"]:
            if (
                not isinstance(block, dict)
                or block.get("type") != "output_text"
                or not isinstance(block.get("text"), str)
            ):
                raise ProbeFailure("OUTPUT_BLOCK_UNVERIFIED")
            chunks.append(block["text"])
    value = parse("".join(chunks))
    try:
        Draft202012Validator(body["text"]["format"]["schema"]).validate(value)
    except ValidationError:
        raise ProbeFailure("LOCAL_SCHEMA_REJECTED") from None
    if value != expected:
        raise ProbeFailure("FIXED_OBJECT_MISMATCH")
    return inp, out


class Runner:
    def __init__(
        self, base, output, manifest, package, approval, limits, key, *, contract, clock=None
    ):
        self.base, self.output = Path(base), Path(output)
        self.manifest, self.package, self.approval = manifest, package, approval
        self.batch = manifest["batch_id"]
        self.key, self.clock, self.limits = key, clock, limits
        self.contract = contract
        self.ledger = None
        self.http_markers, self.model_markers = 0, 0
        self.completed = []
        self.reported = {}

    async def exchange(self, client, url, headers, target, raw, case, kind):
        stem = self.output / (case + "-" + kind)
        evidence(
            Path(str(stem) + "-dispatch.json"),
            dict(
                method="POST",
                public_origin=self.manifest["candidate"]["base_url"],
                path="/responses" + ("/input_tokens" if kind == "count" else ""),
                body_sha256=hashlib.sha256(raw).hexdigest(),
                body_bytes=len(raw),
            ),
        )
        self.http_markers += 1
        self.model_markers += int(kind == "model")
        request = client.build_request("POST", url, headers=headers, content=raw)
        request.extensions["sni_hostname"] = target.hostname
        timeout = 10 if kind == "count" else 30
        async with asyncio.timeout(timeout):
            response = await client.send(request, stream=True, follow_redirects=False)
            try:
                evidence(Path(str(stem) + "-status.json"), {"http_status": response.status_code})
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    data.extend(chunk)
                    if len(data) > 2097152:
                        raise ProbeFailure("RESPONSE_TOO_LARGE")
            finally:
                await response.aclose()
        raw_response = bytes(data)
        redact_check(raw_response, self.key)
        evidence(Path(str(stem) + "-response.json"), raw_response)
        if response.status_code != 200:
            raise ProbeFailure("HTTP_STATUS_UNVERIFIED")
        result = parse(raw_response)
        if not isinstance(result, dict):
            raise ProbeFailure("RESPONSE_OBJECT_UNVERIFIED")
        if kind == "model" and isinstance(result.get("usage"), dict):
            self.reported[case] = {
                k: result["usage"].get(k) if type(result["usage"].get(k)) is int else None
                for k in ("input_tokens", "output_tokens", "total_tokens")
            }
        return result, hashlib.sha256(raw_response).hexdigest()

    async def pair(self, client, target, case):
        from app.services.deepseek_responses import _wire_target

        case_id = case["id"]
        raw = (self.base / case["body"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != case["body_sha256"]:
            raise ProbeFailure("CASE_BYTES_CHANGED")
        body = parse(raw)
        model_ticket, count_ticket = case_id + "-model", case_id + "-count"
        # Combined model hold includes a full conservative counting-fee allowance.
        self.ledger.reserve(
            self.batch,
            self.package,
            model_ticket,
            input_max=4096,
            output_max=case["output_max"],
            fee_max=8192 + case["output_max"],
            seconds=90,
        )
        self.ledger.reserve(
            self.batch, self.package, count_ticket, input_max=0, output_max=0, fee_max=0, seconds=10
        )
        url, host = _wire_target(target)
        headers = {
            "Host": host,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + self.key,
        }
        self.ledger.mark_sent(self.batch, self.package, count_ticket)
        count_response, proof = await self.exchange(
            client, url + "/input_tokens", headers, target, raw, case_id, "count"
        )
        count = count_response.get("input_tokens")
        if (
            count_response.get("object") != "response.input_tokens"
            or type(count) is not int
            or not 1 <= count <= 4096
        ):
            raise ProbeFailure("COUNT_BOUND_UNVERIFIED")
        self.ledger.settle(
            self.batch,
            count_ticket,
            outcome="complete",
            proof_sha256=proof,
            input_used=0,
            output_used=0,
            fee_used=0,
        )
        self.ledger.mark_sent(self.batch, self.package, model_ticket)
        response, proof = await self.exchange(client, url, headers, target, raw, case_id, "model")
        inp, out = response_value(
            body, response, count, case["expected"], self.manifest["candidate"]
        )
        # USD micros: $1/MTok envelope + $0.004096 retained counter allowance.
        self.ledger.settle(
            self.batch,
            model_ticket,
            outcome="complete",
            proof_sha256=proof,
            input_used=inp,
            output_used=out,
            fee_used=4096 + inp + out,
        )
        with self.ledger.transaction():
            self.ledger.guard(self.batch, self.package)
        self.completed.append(case_id)
        self.ledger.record(self.batch, "case_verified", {"case": case_id, "response_sha256": proof})

    async def execute(self, target_factory, transport_factory):
        for case in self.manifest["cases"]:
            redact_check((self.base / case["body"]).read_bytes(), self.key)
        self.output.mkdir(mode=0o700, exist_ok=False)
        self.ledger = Ledger(self.output / "ledger.sqlite", clock=self.clock)
        reason, status = None, "blocked"
        try:
            self.ledger.start(
                self.batch,
                self.package,
                self.limits,
                self.approval,
                pinned_approval_sha256=digest(self.approval),
            )
            self.ledger.record(self.batch, "contract_approval", {"sha256": digest(self.contract)})
            try:
                async with asyncio.timeout(89):
                    target = await asyncio.to_thread(target_factory)
                    if target.url != self.manifest["candidate"]["base_url"]:
                        raise ProbeFailure("TARGET_CHANGED")
                    async with httpx.AsyncClient(
                        transport=transport_factory(),
                        trust_env=False,
                        follow_redirects=False,
                        timeout=30,
                    ) as client:
                        for case in self.manifest["cases"]:
                            await self.pair(client, target, case)
                    with self.ledger.transaction():
                        self.ledger.guard(self.batch, self.package)
                    status = "minimal_compatibility_observed_pass"
            except BaseException as exc:
                if isinstance(exc, ProbeFailure):
                    reason = str(exc)
                elif isinstance(exc, Refused):
                    reason = "BUDGET_CLOCK_OR_CREDENTIAL_REFUSAL"
                elif isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                    reason = "TIMEOUT_UNKNOWN"
                else:
                    reason = "TRANSPORT_OR_EVIDENCE_FAILURE"
                self.ledger.halt(self.batch, "provider_contract_failure")
                rows = self.ledger.db.execute(
                    "SELECT id,state FROM attempts WHERE batch=?", (self.batch,)
                ).fetchall()
                for row in rows:
                    if row["state"] not in ("complete", "not_executed"):
                        self.ledger.settle(self.batch, row["id"], outcome="unknown")
            summary = dict(
                status=status,
                safe_failure_code=reason,
                verified_cases=self.completed,
                case_states={
                    c["id"]: (
                        "verified"
                        if c["id"] in self.completed
                        else "failed_or_unknown"
                        if (self.output / (c["id"] + "-count-dispatch.json")).exists()
                        else "unrun"
                    )
                    for c in self.manifest["cases"]
                },
                provider_reported_usage=self.reported,
                local_accounting=self.ledger.usage(self.batch),
                http_dispatch_markers=self.http_markers,
                model_dispatch_markers=self.model_markers,
                dispatch_markers_are_not_server_receipt_proof=True,
                actual_invoice_usd=None,
                fee_units_are_conservative_not_invoice=True,
                local_requests_count_reservations_not_server_calls=True,
                package_sha256=self.package,
                course_generation_authorized=False,
                T038_completed=False,
            )
            self.ledger.record(self.batch, "terminal_result", summary)
            self.ledger.halt(self.batch, "human_pause")
            evidence(self.output / "summary.json", summary)
            return summary
        finally:
            self.ledger.close()
