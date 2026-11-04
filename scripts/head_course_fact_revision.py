"""Single foreground fact-revision wrapper; reuse existing sealed collector/phase adapter."""

import argparse
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services import head_course_fact_revision as f  # noqa: E402
from app.services.free_course_snapshots import canonical, SnapshotError  # noqa: E402
from scripts import head_course_goal as old  # noqa: E402

PACKAGE = ROOT / "docs/acceptance/phase-1.5-head-fact-revision-r01"
VAULT = Path("/Users/apir/.local/share/edumind/head-goal-fact-r01")


def package_digest():
    data = (PACKAGE / "manifest.json").read_bytes()
    for name, h in json.loads(data)["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != h:
            raise SnapshotError("FACT_PACKAGE_CHANGED")
    if old.read(PACKAGE / "request.json") != f.body():
        raise SnapshotError("FACT_REQUEST_CHANGED")
    return hashlib.sha256(data).hexdigest()


def gate(vault, approval):
    sha = package_digest()
    if (
        approval.get("manifest_sha256") != sha
        or approval.get("parent_digest") != f.PARENT
        or approval.get("explicit_user_authorization") is not True
        or approval.get("accept_fact_revision_and_batch_C2") is not True
        or type(approval.get("max_http_requests")) is not int
        or approval.get("max_http_requests") != 1
        or type(approval.get("starts_epoch")) is not int
        or type(approval.get("expires_epoch")) is not int
        or approval["expires_epoch"] - approval["starts_epoch"] != 600
        or not approval["starts_epoch"] <= time.time() < approval["expires_epoch"]
        or vault.resolve() != VAULT
        or vault.is_symlink()
        or vault.stat().st_mode & 0o077
        or (vault / "STOP").exists()
    ):
        raise SnapshotError("FACT_AUTHORIZATION_OR_STOP")
    return sha


def send(vault, approval, *, transport=None, key=None):
    import httpx
    from cryptography.fernet import Fernet
    from app.core.provider_target import TargetPolicy, approve_target

    sha = gate(vault, approval)
    old.raw_io.exclusive(
        vault / "ACTIVE", b"one foreground fact revision; stale means unknown\n"
    )
    try:
        if list(vault.glob("*.attempt.json")):
            raise SnapshotError("FACT_ONE_REQUEST_LIMIT")
        rawkey = vault / "raw.key"
        if rawkey.is_symlink() or rawkey.stat().st_mode & 0o077:
            raise SnapshotError("FACT_RAW_KEY")
        cipher = Fernet(rawkey.read_bytes())
        request = f.body()
        body = canonical(request)
        if len(body) > 131072:
            raise SnapshotError("FACT_REQUEST_SIZE")
        target = approve_target(
            "https://api.deepseek.com/responses",
            policy=TargetPolicy(),
            **(
                {"resolver": lambda h, p: ["93.184.216.34"]}
                if isinstance(transport, httpx.MockTransport)
                else {}
            ),
        )
        ip = ipaddress.ip_address(target.connect_ip)
        host = f"[{ip}]" if ip.version == 6 else str(ip)
        if key is None:
            key = getpass.getpass("Current DeepSeek API key (not saved): ")
        if not key or "\n" in key or "\r" in key:
            raise SnapshotError("FACT_KEY")
        gate(vault, approval)
        old.raw_io.exclusive(vault / "revision.request.json", body)
        old.raw_io.exclusive(
            vault / "revision.attempt.json",
            canonical(
                dict(
                    stage="fact_revision",
                    manifest_sha256=sha,
                    parent_digest=f.PARENT,
                    request_sha256=hashlib.sha256(body).hexdigest(),
                    evidence_kind="offline_fixture"
                    if transport is not None
                    else "actual_provider_response",
                    state="attempted_unknown",
                    input_reservation=139264,
                    output_reservation=4000,
                )
            ),
        )
        # Same accepted best-effort pause/late-send risk as prior foreground entry, not a T102 fix.
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
                raw = old.raw_io.collect(response, vault / "revision.raw.enc", cipher)
        if old.raw_io.decrypt(vault / "revision.raw.enc", cipher) != raw:
            raise SnapshotError("FACT_RAW_MISMATCH")
        old.raw_io.exclusive(
            vault / "revision.body.json",
            canonical(
                dict(
                    http_status=status,
                    raw_bytes=len(raw),
                    raw_sha256=hashlib.sha256(raw).hexdigest(),
                    body_complete=True,
                )
            ),
        )
        gate(vault, approval)
        if status != 200 or encoding != "identity":
            raise SnapshotError("FACT_HTTP_OR_ENCODING")
        result, obs = old.raw_io.observe_generation(request, raw)
        if (
            obs["reported_input_tokens"] > 139264
            or result.usage.output_tokens > 4000
            or key in raw.decode(errors="replace")
        ):
            raise SnapshotError("FACT_USAGE_OR_KEY_ECHO")
        replacements = dict(result.value)
        old.raw_io.exclusive(vault / "revision.output.json", canonical(replacements))
        parent = f.inputs()["parent_candidate"]
        candidate = f.merge(parent, replacements)
        differences = []
        for key, path in f.PATHS.items():
            before = parent["raw_output"]
            for part in path:
                before = before[part]
            differences.append(
                dict(
                    path=list(path),
                    before=before,
                    after=replacements[key],
                    changed=before != replacements[key],
                )
            )
        old.raw_io.exclusive(vault / "revision.diff.json", canonical(differences))
        old.raw_io.exclusive(vault / "revision.candidate.json", canonical(candidate))
        old.raw_io.exclusive(
            vault / "revision.assembled.private.json", canonical(f.assemble(candidate))
        )
        old.raw_io.exclusive(vault / "revision.observation.json", canonical(obs))
        old.raw_io.exclusive(vault / "STOP", b"one request consumed; no next request\n")
        (vault / "ACTIVE").unlink()
    except BaseException as error:
        if not (vault / "revision.failure.json").exists():
            old.raw_io.exclusive(
                vault / "revision.failure.json",
                canonical(
                    dict(
                        error_type=type(error).__name__,
                        code=getattr(
                            error,
                            "code",
                            str(error)
                            if isinstance(error, old.raw_io.wire.PilotError)
                            else None,
                        ),
                        state="failed_or_unknown",
                    )
                ),
            )
        if not (vault / "STOP").exists():
            old.raw_io.exclusive(vault / "STOP", b"failure/unknown; no retry\n")
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--send", action="store_true")
    a = p.parse_args()
    if a.inspect:
        print(
            json.dumps(
                dict(
                    manifest_sha256=package_digest(), provider_calls=0, authorized=False
                )
            )
        )
    elif a.send:
        if any(
            k.startswith(
                ("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "DEEPSEEK", "OPENAI")
            )
            for k in os.environ
        ):
            p.error(
                "Clean environment required; never read .env or use credential environment"
            )
        try:
            send(VAULT, old.read(VAULT / "approval.json"))
        except BaseException:
            print("STOPPED: preserve originals and failures; no next request.")
            sys.exit(2)
    else:
        p.error("Choose --inspect or --send")
