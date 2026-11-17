"""One final T111 sample of the exact request rejected in continuation r02."""

import argparse
import getpass
import ipaddress
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
import httpx  # noqa: E402

from app.core.provider_target import TargetPolicy, approve_target  # noqa: E402
from app.services.free_course_snapshots import SnapshotError, canonical  # noqa: E402
from scripts import head_course_fixed_continuation as prior  # noqa: E402

BATCH = "head-fixed-repeat-r03"
VAULT = Path.home() / ".local/share/edumind/head-fixed-repeat-r03"
APPROVAL = ROOT / "docs/acceptance/phase-1.5-head-fixed-repeat-r03/approval.json"
REQUEST_SHA = "fccba92a41527dbcd9da34ceefca77ca1ee1edaa33c83a49e1ffbc3940e1c92d"
REJECTED_SHA = "6881f3b3a95142249494adf1ffe3bee40a1a0bdc8eb13eab23e97af83794f1c7"
read, raw_io, sha = prior.read, prior.raw_io, prior.sha


def inputs():
    payload = prior.source_payload()
    vault = prior.VAULT
    request = prior.materials.body(payload)
    body = canonical(request)
    attempt = read(vault / "draft.attempt.json")
    raw = raw_io.decrypt(vault / "draft.raw.enc", prior.cipher(vault))
    if (
        not (vault / "STOP").is_file()
        or sorted(p.name for p in vault.glob("*.attempt.json"))
        != ["draft.attempt.json"]
        or attempt["evidence_kind"] != "actual_provider_response"
        or attempt["batch"] != prior.BATCH
        or attempt["approval_sha256"] != sha(prior.APPROVAL.read_bytes())
        or read(prior.APPROVAL)["runner_sha256"]
        != sha(Path(prior.__file__).read_bytes())
        or (vault / "draft.request.json").read_bytes() != body
        or attempt["request_sha256"] != sha(body)
        or sha(body) != REQUEST_SHA
        or sha(raw) != REJECTED_SHA
        or read(vault / "draft.body.json")
        != dict(
            http_status=200,
            raw_bytes=len(raw),
            raw_sha256=REJECTED_SHA,
            body_complete=True,
        )
        or read(vault / "draft.failure.json")["code"] != "HEAD_FACT_REFERENCE"
    ):
        raise SnapshotError("REPEAT_REJECTED_SOURCE_BINDING")
    return payload, request, body


def gate(vault):
    approved = read(APPROVAL)
    if (
        approved["batch"] != BATCH
        or approved["explicit_user_authorization"] is not True
        or approved["historical_http"] != 2
        or approved["additional_http_limit"] != 1
        or approved["request_sha256"] != REQUEST_SHA
        or approved["rejected_response_sha256"] != REJECTED_SHA
        or approved["runner_sha256"] != sha(Path(__file__).read_bytes())
    ):
        raise SnapshotError("REPEAT_APPROVAL")
    if (
        vault.is_symlink()
        or not vault.is_dir()
        or vault.stat().st_mode & 0o077
        or (vault / "STOP").exists()
        or list(vault.glob("*.attempt.json"))
    ):
        raise SnapshotError("REPEAT_STOPPED_OR_UNSAFE")
    return sha(APPROVAL.read_bytes())


def send(vault, *, transport=None, key=None):
    payload, request, body = inputs()
    approved = gate(vault)
    lock = vault / "ACTIVE"
    raw_io.exclusive(lock, b"single foreground request; unresolved means stop\n")
    try:
        encryption = prior.cipher(vault)
        target = approve_target(
            "https://api.deepseek.com/responses",
            policy=TargetPolicy(),
            **(
                {"resolver": lambda h, p: ["93.184.216.34"]}
                if transport is not None
                else {}
            ),
        )
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        if key is None:
            if not sys.stdin.isatty():
                raise SnapshotError("REPEAT_TTY_REQUIRED")
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise SnapshotError("REPEAT_KEY_INVALID")
        if gate(vault) != approved or inputs()[2] != body:
            raise SnapshotError("REPEAT_APPROVAL_OR_INPUT_CHANGED")
        raw_io.exclusive(vault / "repeat.request.json", body)
        kind = (
            "offline_fixture" if transport is not None else "actual_provider_response"
        )
        raw_io.exclusive(
            vault / "repeat.attempt.json",
            canonical(
                dict(
                    batch=BATCH,
                    stage="independent_repeat_after_rejection",
                    evidence_kind=kind,
                    approval_sha256=approved,
                    request_sha256=REQUEST_SHA,
                    source_plan_digest=prior.SOURCE_PLAN,
                    rejected_response_sha256=REJECTED_SHA,
                )
            ),
        )
        with httpx.Client(
            transport=transport, timeout=90, trust_env=False, follow_redirects=False
        ) as client:
            with client.stream(
                "POST",
                f"https://{host}:443/responses",
                content=body,
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
                raw = raw_io.collect(response, vault / "repeat.raw.enc", encryption)
        raw_io.exclusive(
            vault / "repeat.body.json",
            canonical(
                dict(
                    http_status=status,
                    raw_bytes=len(raw),
                    raw_sha256=sha(raw),
                    body_complete=True,
                )
            ),
        )
        if (
            status != 200
            or encoding != "identity"
            or key in raw.decode(errors="replace")
            or raw_io.decrypt(vault / "repeat.raw.enc", encryption) != raw
            or (vault / "STOP").exists()
            or sha(APPROVAL.read_bytes()) != approved
        ):
            raise SnapshotError("REPEAT_HTTP_EVIDENCE_OR_STOP")
        record = prior.reuse.record(payload, request, raw, raw_io, evidence_kind=kind)
        raw_io.exclusive(vault / "repeat.record.json", canonical(record))
        raw_io.exclusive(vault / "STOP", b"final authorized attempt completed\n")
        lock.unlink()
        return record
    except BaseException as error:
        raw_io.exclusive(
            vault / "repeat.failure.json",
            canonical(
                dict(
                    error_type=type(error).__name__,
                    code=getattr(
                        error,
                        "code",
                        str(error)
                        if isinstance(error, raw_io.wire.PilotError)
                        else None,
                    ),
                )
            ),
        )
        if not (vault / "STOP").exists():
            raw_io.exclusive(
                vault / "STOP", b"final attempt failed or unknown; preserve originals\n"
            )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "send"))
    args = parser.parse_args()
    if args.action == "inspect":
        print(canonical(dict(batch=BATCH, request_sha256=sha(inputs()[2]))).decode())
        return
    if any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "DEEPSEEK", "OPENAI"))
        for k in os.environ
    ):
        parser.error("Use a clean terminal environment")
    try:
        send(VAULT)
    except BaseException:
        print(
            "STOPPED or refused. Preserve originals and report this status.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print("Final attempt complete. Preserve originals.")


if __name__ == "__main__":
    main()
