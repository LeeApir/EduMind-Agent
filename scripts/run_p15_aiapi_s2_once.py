"""Explicitly authorized S2-only dispatch; frozen r01 and its stop state stay intact."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values

from run_p15_aiapi_minimal_r01 import BASE, ROOT, observe, package, read, scrub

BASE2 = ROOT / "docs/acceptance/phase-1.5-aiapi-s2-once"
OUT = Path("/tmp/edumind-p15-aiapi-s2-once")


def check():
    plan = package()
    auth = read(BASE2 / "execution-authorization.json")
    assert auth["quote"] == "执行S2"
    assert (
        auth["request_sha256"]
        == hashlib.sha256((BASE / "S2.json").read_bytes()).hexdigest()
    )
    assert (
        auth["runner_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )
    return plan


def execute(plan):
    OUT.mkdir(mode=0o700)
    result = {
        "batch_id": "p15-aiapi-s2-once",
        "status": "reserved",
        "local_hold_usd": "0.035",
        "settlement": "unknown",
        "actual_invoice_usd": None,
        "dispatch_attempted": False,
    }

    def save():
        (OUT / "results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )

    save()
    cfg = dotenv_values(ROOT / ".env")
    assert cfg.get("EDUMIND_PROVIDER_BASE_URL", "").rstrip("/") in {
        "https://aiapi.world",
        "https://aiapi.world/v1",
    }
    key = cfg["EDUMIND_PROVIDER_API_KEY"]
    assert key and key.isascii() and not any(c.isspace() for c in key)
    with tempfile.TemporaryDirectory(prefix="aiapi-s2-") as td:
        p = Path(td)
        (p / "headers").write_text(
            "Authorization: Bearer " + key + "\nContent-Type: application/json\n"
        )
        os.chmod(p / "headers", 0o600)
        result["dispatch_attempted"] = True
        save()
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--request",
                    "POST",
                    plan["url"],
                    "--connect-timeout",
                    "10",
                    "--max-time",
                    "40",
                    "--max-filesize",
                    "1048576",
                    "--header",
                    "@" + str(p / "headers"),
                    "--data-binary",
                    "@" + str(BASE / "S2.json"),
                    "--output",
                    str(p / "response"),
                    "--write-out",
                    "%{http_code}",
                ],
                capture_output=True,
                text=True,
                timeout=42,
            )
            result.update(
                transport_exit=proc.returncode,
                http_status=int(proc.stdout.strip() or "0"),
            )
            raw = (p / "response").read_text() if (p / "response").exists() else ""
            assert key not in raw
            result["response_raw_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            events = [
                json.loads(line[6:])
                for line in raw.splitlines()
                if line.startswith("data: ") and line[6:] != "[DONE]"
            ]
            result["events"] = scrub(events)
            finals = [
                e["response"] for e in events if e.get("type") == "response.completed"
            ]
            result["assembled_text"] = "".join(
                e.get("delta", "")
                for e in events
                if e.get("type") == "response.output_text.delta"
            )
            result["stream_completed_count"] = len(finals)
            if (
                proc.returncode == 0
                and result["http_status"] == 200
                and len(finals) == 1
            ):
                result["observation"] = observe(read(BASE / "S2.json"), finals[0], 1)
            else:
                result["observation"] = {
                    "all_passed": False,
                    "reason": "HTTP_TRANSPORT_OR_STREAM_INCOMPLETE",
                }
        except Exception as exc:
            result["observation"] = {"all_passed": False, "reason": type(exc).__name__}
    result["status"] = (
        "observed_pass_not_course_acceptance"
        if result["observation"]["all_passed"]
        else "stopped_failed_or_unproven"
    )
    save()
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"events", "assembled_text"}},
            ensure_ascii=False,
        )
    )
    return 0 if result["observation"]["all_passed"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = check()
    raise SystemExit(execute(plan) if args.execute else 0)
