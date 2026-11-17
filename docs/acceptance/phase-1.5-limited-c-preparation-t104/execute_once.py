"""One foreground HTTP request. No supervisor, subprocess, retry or automatic next call.

Proposed only. Real use requires separate explicit user authorization of this package.
"""

import argparse
import getpass
import hashlib
import json
import ipaddress
import os
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
# Absolute repository paths, never the caller's working directory or PYTHONPATH.
sys.path[:0] = [str(HERE), str(ROOT / "backend"), str(ROOT)]
import httpx  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from app.core.provider_target import TargetPolicy, approve_target  # noqa: E402
from prepare import VERSION, artifact, body, canonical, generate, manifest, render, wire  # noqa: E402


class IncompleteEvidence(ValueError):
    pass


def exclusive(path, raw):
    with path.open("xb") as f:
        os.chmod(path, 0o600)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def collect(response, target, cipher, maximum=2097152):
    """Encrypt each received body chunk before any JSON parsing; preserve partials."""
    raw = bytearray()
    complete = False
    with target.open("xb") as out:
        os.chmod(target, 0o600)
        try:
            for chunk in response.iter_raw():
                remaining = maximum - len(raw)
                piece = chunk[:remaining]
                token = cipher.encrypt(piece)
                out.write(struct.pack(">I", len(token)) + token)
                out.flush()
                os.fsync(out.fileno())
                raw.extend(piece)
                if len(chunk) > remaining:
                    raise IncompleteEvidence("RESPONSE_LIMIT_PARTIAL")
            complete = True
        finally:
            out.flush()
            os.fsync(out.fileno())
    if not complete:
        raise IncompleteEvidence("BODY_INCOMPLETE")
    return bytes(raw)


def decrypt(path, cipher):
    raw = bytearray()
    with path.open("rb") as f:
        while header := f.read(4):
            if len(header) != 4:
                raise IncompleteEvidence("TRUNCATED_FRAME")
            n = struct.unpack(">I", header)[0]
            token = f.read(n)
            if len(token) != n:
                raise IncompleteEvidence("TRUNCATED_FRAME")
            raw.extend(cipher.decrypt(token))
    return bytes(raw)


PHASE_ADAPTER_VERSION = "limited-c-message-phase-v1"


def observe_generation(request, raw):
    """Only this batch accepts an absent/final_answer message phase.

    The encrypted original is never rewritten. All other envelope checks remain
    with the unchanged shared wire validator, including unknown-field rejection.
    """
    if len(raw) > 2097152:
        raise wire.PilotError("WIRE_RESPONSE_SIZE_OR_ROLE")
    view = wire.strict_json(raw)
    observed = []
    if type(view) is dict and type(view.get("output")) is list:
        for item in view["output"]:
            if type(item) is dict and item.get("type") == "message":
                if "phase" in item:
                    if (
                        type(item["phase"]) is not str
                        or item["phase"] != "final_answer"
                    ):
                        raise wire.PilotError("WIRE_MESSAGE_PHASE")
                    observed.append(item.pop("phase"))
                else:
                    observed.append("absent")
    result, observation = wire.validate(request, canonical(view), "generation")
    return result, {
        **observation,
        "phase_adapter_version": PHASE_ADAPTER_VERSION,
        "message_phase": observed[0],
    }


def verify_saved(vault, prefix, cipher):
    request = json.loads((vault / f"{prefix}.request.json").read_text())
    raw = decrypt(vault / f"{prefix}.raw.enc", cipher)
    receipt = json.loads((vault / f"{prefix}.body.json").read_text())
    assert receipt == dict(
        http_status=200,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_bytes=len(raw),
        body_complete=True,
    ), "EVIDENCE_INCOMPLETE"
    candidate = json.loads((vault / f"{prefix}.candidate.json").read_text())
    slot, phase = prefix.split("-")
    assert candidate["slot"] == slot
    if phase == "generate":
        assert candidate["parent_digest"] is None and request == body(slot), (
            "REQUEST_PARENT_CHANGED"
        )
    else:
        parent = verify_saved(vault, f"{slot}-generate", cipher)
        supplied = json.loads(request["input"][1]["content"])
        assert candidate["parent_digest"] == parent["artifact_digest"]
        assert request == body(slot, parent, supplied["issues"]), (
            "REPAIR_REQUEST_CHANGED"
        )
    attempt = json.loads((vault / f"{prefix}.attempt.json").read_text())
    assert attempt["slot"] == slot and attempt["phase"] == phase
    assert attempt["request_sha256"] == hashlib.sha256(canonical(request)).hexdigest()
    value, _ = observe_generation(request, raw)
    assert candidate == artifact(slot, dict(value.value), candidate["parent_digest"]), (
        "CANDIDATE_CHANGED"
    )
    result = json.loads((vault / f"{prefix}.result.json").read_text())
    assert result["candidate_digest"] == candidate["artifact_digest"]
    assert (vault / f"{prefix}.course.html").read_text() == render(
        slot, dict(value.value)
    )
    return candidate


def verify_package():
    outputs = generate()
    assert (HERE / "manifest.json").read_bytes() == manifest(outputs), "PACKAGE_CHANGED"
    for name, raw in outputs.items():
        assert (HERE / name).read_bytes() == raw, "GENERATED_CHANGED"
    return hashlib.sha256((HERE / "manifest.json").read_bytes()).hexdigest()


def run(slot, vault, approval, transport=None, key=None):
    package = verify_package()
    assert approval["package_sha256"] == package and approval["version"] == VERSION
    assert (
        approval["explicit_user_authorization"] is True
        and approval["accept_contract_A_D_and_batch_C2"] is True
    )
    assert (
        time.time() < approval["expires_epoch"]
        and approval["expires_epoch"] - approval["starts_epoch"] == 1800
    )
    assert approval["starts_epoch"] <= time.time()
    assert (
        vault.is_dir() and not vault.is_symlink() and vault.stat().st_mode & 0o077 == 0
    )
    # This is a local guard, not an independent witness or anti-rollback mechanism.
    assert not (vault / "STOP").exists(), "BATCH_STOPPED"
    lock = vault / "ACTIVE"
    exclusive(lock, b"foreground request active; stale lock means stop/unknown\n")
    try:
        cipher = Fernet((vault / "raw.key").read_bytes())
        assert (
            not (vault / "raw.key").is_symlink()
            and (vault / "raw.key").stat().st_mode & 0o077 == 0
        )
        assert not (vault / f"{slot}-repair.attempt.json").exists(), "SAMPLE_EXHAUSTED"
        is_repair = (vault / f"{slot}-generate.attempt.json").exists()
        request = body(slot)
        parent = None
        if is_repair:
            parent = verify_saved(vault, f"{slot}-generate", cipher)
            decision = json.loads((vault / f"{slot}-evaluation.json").read_text())
            assert decision["candidate_digest"] == parent["artifact_digest"]
            assert (
                decision["verdict"] == "ordinary_wording_repair"
                and decision["independent_evaluator"]
            )
            assert 1 <= len(decision["issues"]) <= 8
            assert all(
                i["severity"] == "minor"
                and i["area"] in ("difficulty", "misconception")
                and i["quote"]
                for i in decision["issues"]
            )
            for issue in decision["issues"]:
                target = parent["raw_output"]
                assert 1 <= len(issue["path"]) <= 4
                for part in issue["path"]:
                    target = target[part]
                assert isinstance(target, str) and issue["quote"] in target, (
                    "ISSUE_TARGET"
                )

            request = body(slot, parent, decision["issues"])
        elif slot == "C02":
            decision = json.loads((vault / "C01-evaluation.json").read_text())
            assert decision["verdict"] == "pass" and decision["independent_evaluator"]
            previous = json.loads((vault / "C01-final.candidate.json").read_text())
            final_phase = (
                "repair" if (vault / "C01-repair.attempt.json").exists() else "generate"
            )
            assert previous == verify_saved(vault, f"C01-{final_phase}", cipher)
            assert decision["candidate_digest"] == previous["artifact_digest"]
        phase = "repair" if is_repair else "generate"
        prefix = f"{slot}-{phase}"
        raw_request = canonical(request)
        assert len(raw_request) <= 131072
        attempts = list(vault.glob("*.attempt.json"))
        assert len(attempts) < 4
        target = approve_target(
            wire.ROUTES["generation"]["url"],
            policy=TargetPolicy(),
            **(
                {"resolver": lambda host, port: ["93.184.216.34"]}
                if isinstance(transport, httpx.MockTransport)
                else {}
            ),
        )
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        pinned_url = f"https://{host}:443/responses"
        # Key is prompted only after all local guards. No credential in argv, env or request evidence.
        if key is None:
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        assert key and "\n" not in key and "\r" not in key
        assert not (vault / "STOP").exists() and time.time() < approval["expires_epoch"]
        exclusive(
            vault / f"{prefix}.attempt.json",
            canonical(
                dict(
                    slot=slot,
                    phase=phase,
                    package=package,
                    request_sha256=hashlib.sha256(raw_request).hexdigest(),
                    parent_digest=None if parent is None else parent["artifact_digest"],
                    input_reservation=139264,
                    output_reservation=8000,
                    state="attempted_result_unknown",
                )
            ),
        )
        exclusive(vault / f"{prefix}.request.json", raw_request)
        # Known limitation: pause here can lead to send after expiry/STOP. No stronger claim.
        with httpx.Client(
            transport=transport, timeout=90, trust_env=False, follow_redirects=False
        ) as client:
            with client.stream(
                "POST",
                pinned_url,
                content=raw_request,
                extensions={"sni_hostname": target.hostname},
                headers={
                    "Host": target.hostname,
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as response:
                status = response.status_code
                encoding = response.headers.get("content-encoding", "identity")
                raw = collect(response, vault / f"{prefix}.raw.enc", cipher)
        assert decrypt(vault / f"{prefix}.raw.enc", cipher) == raw
        # Receipt proves observed complete body here, not anti-rollback or independent custody.
        exclusive(
            vault / f"{prefix}.body.json",
            canonical(
                dict(
                    http_status=status,
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                    raw_bytes=len(raw),
                    body_complete=True,
                )
            ),
        )
        if time.time() >= approval["expires_epoch"] or (vault / "STOP").exists():
            raise IncompleteEvidence("LATE_BODY_PRESERVED_STOP")
        assert status == 200, "HTTP_FAILED"
        assert encoding == "identity", "UNEXPECTED_ENCODING_RAW_PRESERVED"
        result, observation = observe_generation(request, raw)
        assert observation["reported_input_tokens"] <= 139264, (
            "INPUT_RESERVATION_EXCEEDED"
        )
        value = dict(result.value)
        assert key not in canonical(value).decode(), "CREDENTIAL_ECHO_STOP"
        candidate = artifact(
            slot, value, None if parent is None else parent["artifact_digest"]
        )
        exclusive(vault / f"{prefix}.candidate.json", canonical(candidate))
        exclusive(vault / f"{prefix}.course.html", render(slot, value).encode())
        exclusive(
            vault / f"{prefix}.result.json",
            canonical(
                dict(
                    state="awaiting_independent_teaching_evaluation",
                    candidate_digest=candidate["artifact_digest"],
                    observation=observation,
                )
            ),
        )
        lock.unlink()
        return candidate
    except BaseException:
        if not (vault / "STOP").exists():
            exclusive(
                vault / "STOP",
                b"stopped_unknown_or_failed; never retry/resume this batch\n",
            )
        # Keep ACTIVE and attempted slots occupied. Never print raw exception or response.
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--send", choices=["C01", "C02"])
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    package = verify_package()
    if not args.send:
        print(
            json.dumps(
                dict(
                    status="proposed_not_authorized",
                    package_sha256=package,
                    live_calls=0,
                )
            )
        )
        return
    if not args.vault or not args.approval:
        parser.error(
            "--send requires separately authorized approval record and private vault"
        )
    approval = json.loads(args.approval.read_text())
    try:
        run(args.send, args.vault, approval)
    except BaseException:
        print(
            "STOPPED: failed/unknown. Preserve vault; no retry, no next request.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(
        "Body preserved; complete course awaits independent teaching evaluation. No next call scheduled."
    )


if __name__ == "__main__":
    main()
