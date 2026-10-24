"""Single synthetic count/generation discovery probe; two exact approvals required."""

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from acceptance_support.p15_diagnostic_ledger import Ledger, Limits, Refused, digest  # noqa: E402
from acceptance_support.p15_diagnostic_transport import CountedTransport, redact_check  # noqa: E402
from acceptance_support.p15_guarded_transport import GuardedWireTransport  # noqa: E402

BASE = ROOT / "docs/acceptance/phase-1.5-compatibility-probe-p01"
OUTPUT = Path("/tmp/edumind-p15-compatibility-probe-p01")
BATCH = "p15-compatibility-probe-p01"
LIMITS = Limits(2, 32000, 16, None, 40)
PURPOSE = "one_synthetic_compatibility_probe_no_course_admission"


def load_package(base=BASE, root=ROOT):
    raw = (base / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    for name, expected in manifest["sha256"].items():
        path = root / name
        if (
            not path.resolve().is_relative_to(root.resolve())
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise Refused("FROZEN_PACKAGE_CHANGED")
    if (
        manifest["batch_id"] != BATCH
        or manifest.get("purpose") != PURPOSE
        or manifest["limits"] != asdict(LIMITS)
    ):
        raise Refused("PROBE_SCOPE_CHANGED")
    return manifest, hashlib.sha256(raw).hexdigest()


def gate(base=BASE, root=ROOT):
    manifest, package = load_package(base, root)
    grants = []
    for kind in ("contract", "execution"):
        path = base / (kind + "-approval.json")
        if not path.is_file():
            raise Refused("EXACT_PROBE_APPROVALS_REQUIRED")
        grant = json.loads(path.read_text())
        if (
            grant.get("kind") != kind
            or grant.get("scope") != "PHASE-1.5-T038"
            or grant.get("purpose") != PURPOSE
            or grant.get("batch_id") != BATCH
            or grant.get("package_sha256") != package
            or grant.get("limits") != asdict(LIMITS)
            or not all(
                isinstance(grant.get(k), str) and grant[k].strip()
                for k in ("human_message", "reviewer", "received_at", "evidence_ref")
            )
        ):
            raise Refused("EXACT_PROBE_APPROVALS_REQUIRED")
        grants.append(grant)
    if grants[0].get("decisions") != ["A", "B", "C"]:
        raise Refused("ACCURATE_ADR0029_APPROVAL_REQUIRED")
    if any(
        grants[1].get(k) is not True
        for k in (
            "fee_cap_waiver",
            "unverified_upstream_bounds_risk_accepted",
            "no_course_admission",
        )
    ):
        raise Refused("ACCURATE_DISCOVERY_RISK_APPROVAL_REQUIRED")
    return manifest, package, grants


class DiscoveryObservationTransport(GuardedWireTransport):
    """Separate discovery exception; unchanged T052 rejects live production transport.

    The inherited observer rejects all detected contradictions before settlement. Its
    echoes do not establish an independent preflight bound. No general live factory
    is provided; this runner's exact approvals authorize only the fixed request.
    """

    def __init__(self, underlying, output, key, permit):
        if (
            permit.get("purpose") != PURPOSE
            or permit.get("unverified_upstream_bounds_risk_accepted") is not True
        ):
            raise Refused("DISCOVERY_PERMIT_REQUIRED")
        self.underlying = underlying
        self.output = Path(output)
        self.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.key = key
        self.count, self.body, self.model_sent = None, None, False

    async def handle_async_request(self, request):
        seconds = 9 if request.url.path.endswith("/input_tokens") else 29
        return await asyncio.wait_for(
            super().handle_async_request(request), timeout=seconds
        )

    def check_response(self, request, response):
        issues = super().check_response(request, response)
        try:
            output = response["output"]
            if len(output) != 1 or output[0]["type"] != "message":
                raise ValueError("unexpected output")
            content = output[0]["content"]
            if len(content) != 1 or content[0]["type"] != "output_text":
                raise ValueError("unexpected content")
            if json.loads(content[0]["text"]) != {"result": "OK"}:
                raise ValueError("unexpected result")
        except (AssertionError, KeyError, ValueError, TypeError):
            issues.append("OUTPUT_SCHEMA_UNVERIFIED")
        return issues


async def run(base, output, manifest, package, grants, settings, target, underlying):
    # Exclusive directory is a durable one-shot barrier, including interrupted runs.
    raw_body = (base / "request.json").read_bytes()
    redact_check(raw_body, settings.api_key)
    pinned = [v for k, v in manifest["sha256"].items() if k.endswith("/request.json")]
    if pinned != [hashlib.sha256(raw_body).hexdigest()]:
        raise Refused("FROZEN_REQUEST_CHANGED")
    output.mkdir(mode=0o700, exist_ok=False)
    (output / "request.json").write_bytes(raw_body)
    ledger = Ledger(output / "ledger.sqlite")
    try:
        ledger.start(
            BATCH, package, LIMITS, grants[1], pinned_approval_sha256=digest(grants[1])
        )
        ledger.record(BATCH, "contract_approval", {"sha256": digest(grants[0])})
        observation = DiscoveryObservationTransport(
            underlying, output / "audit", settings.api_key, grants[1]
        )
        transport = CountedTransport(
            observation, ledger, BATCH, package, output / "wire", settings.api_key
        )
        from app.services.deepseek_responses import _wire_target
        import httpx

        url, host = _wire_target(target)
        request = httpx.Request(
            "POST",
            url,
            content=raw_body,
            headers={
                "Host": host,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": "Bearer " + settings.api_key,
            },
            extensions={"sni_hostname": target.hostname},
        )
        verdict = "not_observed"
        try:
            response = await asyncio.wait_for(
                transport.handle_async_request(request), timeout=39
            )
            await response.aclose()
            verdict = "no_observed_contract_violation_not_admitted"
        except Exception:
            # Parent transport already preserves specific safe observer reasons and holds.
            ledger.halt(BATCH, "provider_contract_failure")
            verdict = "contract_failure_or_unknown_not_admitted"
        finally:
            await transport.aclose()
        reported = None
        for sent_path in (output / "audit").glob("*-send.json"):
            if json.loads(sent_path.read_text())["path"] != "/v1/responses":
                continue
            body_path = sent_path.with_name(
                sent_path.name.replace("-send.json", "-body.json")
            )
            try:
                usage = json.loads(body_path.read_bytes()).get("usage", {})
                reported = {
                    k: usage.get(k) if type(usage.get(k)) is int else None
                    for k in ("input_tokens", "output_tokens", "total_tokens")
                }
            except (OSError, ValueError, AttributeError):
                pass
        sent = ledger.db.execute(
            "SELECT attempt FROM receipts WHERE kind='sent'"
        ).fetchall()
        summary = dict(
            batch_id=BATCH,
            package_sha256=package,
            verdict=verdict,
            usage=ledger.usage(BATCH),
            provider_reported_usage=reported,
            verified_protocol_usage=transport.usage,
            http_dispatch_markers=len(sent),
            model_dispatch_markers=sum(row[0].endswith("-model") for row in sent),
            dispatch_markers_are_not_server_receipt_proof=True,
            course_admitted=False,
            T038_completed=False,
            actual_relay_fee=None,
            upstream_hard_bounds_independently_verified=False,
            automatic_retry=False,
        )
        ledger.record(BATCH, "probe_finished", summary)
        # A clean observation is terminal too; it never grants another call or course.
        ledger.halt(BATCH, "human_pause")
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.check:
        load_package()
        print("Probe package verified; no execution, credentials or network")
        return
    manifest, package, grants = gate()
    # Gate precedes .env, provider target DNS, transport, output and persistent budget.
    from run_p15_strict_diagnostic import settings_after_approval
    from app.core.provider_target import ProviderTargetGuard, TargetPolicy
    import httpx

    if OUTPUT.exists():
        raise Refused("PROBE_ALREADY_STARTED_NO_RETRY")
    settings = settings_after_approval()
    target = ProviderTargetGuard(settings.base_url, TargetPolicy()).approve_base()
    transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
    result = asyncio.run(
        run(BASE, OUTPUT, manifest, package, grants, settings, target, transport)
    )
    print(json.dumps({"verdict": result["verdict"], "course_admitted": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "REFUSED_OR_STOPPED: inspect protected evidence; no retry."
        ) from None
