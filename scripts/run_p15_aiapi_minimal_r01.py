"""One-shot synthetic AIAPI observation; never unlocks product or old acceptance."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-aiapi-minimal-r01"
OUTPUT = Path("/tmp/edumind-p15-aiapi-minimal-r01")


def read(path):
    return json.loads(path.read_text())


def package():
    manifest = read(BASE / "manifest.json")
    for name, sha in manifest["sha256"].items():
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    plan = read(BASE / "plan.json")
    assert plan["url"] == "https://aiapi.world/v1/responses"
    assert plan["model"] == "gpt-6.1-sol"
    assert sum(map(Decimal, plan["limits"]["local_slot_holds_usd"])) == Decimal("0.05")
    assert Decimal("0.04032") <= Decimal("0.05")
    for name, cap, streaming in [("S1", 128, False), ("S2", 512, True)]:
        body = read(BASE / f"{name}.json")
        assert body["model"] == plan["model"] and body["max_output_tokens"] == cap
        assert body["stream"] is streaming and body["store"] is False
        assert len(json.dumps(body).encode()) < 65536
        Draft202012Validator.check_schema(body["text"]["format"]["schema"])
    return plan


def observe(body, reply, slot):
    usage = reply.get("usage") or {}
    ins = reply.get("instructions")
    expected = body.get("instructions")
    if expected is None:
        expected = "\n\n".join(
            m["content"] for m in body["input"] if m["role"] == "system"
        )
    text = "".join(
        b.get("text", "")
        for item in reply.get("output", [])
        if item.get("type") == "message" and item.get("role") == "assistant"
        for b in item.get("content", [])
        if b.get("type") == "output_text"
    )
    counts = [usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")]
    valid_usage = all(type(n) is int and n >= 0 for n in counts)
    checks = {
        "completed": reply.get("status") == "completed" and reply.get("error") is None,
        "model": reply.get("model") == body["model"],
        "instructions_exact": ins == expected,
        "output_cap_observed": reply.get("max_output_tokens")
        == body["max_output_tokens"],
        "storage": reply.get("store") is False,
        "usage": valid_usage and counts[0] + counts[1] == counts[2],
        "reported_within_reservation": valid_usage
        and counts[0] <= [4096, 8192][slot]
        and counts[1] <= body["max_output_tokens"],
    }
    try:
        value = json.loads(text)
        Draft202012Validator(body["text"]["format"]["schema"]).validate(value)
        checks["schema"] = True
    except Exception as exc:
        # Record a boolean, never forward provider text through exception messages.
        checks["schema"] = False
        value = None
        del exc
    if slot == 0:
        checks["role_marker"] = (
            isinstance(value, dict) and value.get("role_marker") == "EDUMIND_TUTOR_R01"
        )
    return {"checks": checks, "text": text, "all_passed": all(checks.values())}


def scrub(value):
    if isinstance(value, dict):
        return {
            k: "<omitted>"
            if k in {"encrypted_content", "safety_identifier", "prompt_cache_key"}
            else scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def execute(plan):
    # Exclusive directory and reservation persist before dispatch; cannot resume/retry.
    OUTPUT.mkdir(mode=0o700)
    state = {
        "batch_id": plan["batch_id"],
        "status": "started",
        "requests": [],
        "actual_invoice_usd": None,
    }

    def save():
        (OUTPUT / "results.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        )

    save()
    cfg = dotenv_values(ROOT / ".env")
    assert cfg.get("EDUMIND_PROVIDER_BASE_URL", "").rstrip("/") in {
        "https://aiapi.world",
        "https://aiapi.world/v1",
    }
    key = cfg.get("EDUMIND_PROVIDER_API_KEY")
    assert key and key.isascii() and not any(ch.isspace() for ch in key)
    started = time.monotonic()
    for slot, name in enumerate(["S1", "S2"]):
        body = read(BASE / f"{name}.json")
        remaining = 89 - (time.monotonic() - started)
        if remaining < 40:
            state["status"] = "stopped_time_budget"
            break
        row = {
            "case": name,
            "local_hold_usd": plan["limits"]["local_slot_holds_usd"][slot],
            "settlement": "unknown",
            "dispatch_attempted": False,
        }
        state["requests"].append(row)
        save()
        with tempfile.TemporaryDirectory(prefix="aiapi-r01-") as td:
            p = Path(td)
            (p / "headers").write_text(
                "Authorization: Bearer " + key + "\nContent-Type: application/json\n"
            )
            os.chmod(p / "headers", 0o600)
            (p / "body").write_bytes((BASE / f"{name}.json").read_bytes())
            row["dispatch_attempted"] = True
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
                        "@" + str(p / "body"),
                        "--dump-header",
                        str(p / "response-headers"),
                        "--output",
                        str(p / "response"),
                        "--write-out",
                        "%{http_code}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=42,
                )
                row["transport_exit"] = proc.returncode
                row["http_status"] = int(proc.stdout.strip() or "0")
                raw = (p / "response").read_text() if (p / "response").exists() else ""
                assert key not in raw
                row["response_raw_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
                headers = (
                    (p / "response-headers").read_text()
                    if (p / "response-headers").exists()
                    else ""
                )
                row["response_headers"] = [
                    ln
                    for ln in headers.splitlines()
                    if ln.lower().startswith(
                        ("content-type:", "x-request-id:", "x-oneapi-request-id:")
                    )
                ]
                if proc.returncode != 0 or row["http_status"] != 200:
                    row["observation"] = {
                        "all_passed": False,
                        "reason": "TRANSPORT_OR_HTTP",
                    }
                elif slot == 0:
                    reply = json.loads(raw)
                    row["response"] = scrub(reply)
                    row["observation"] = observe(body, reply, slot)
                else:
                    events = [
                        json.loads(ln[6:])
                        for ln in raw.splitlines()
                        if ln.startswith("data: ") and ln[6:] != "[DONE]"
                    ]
                    row["events"] = scrub(events)
                    finals = [
                        e["response"]
                        for e in events
                        if e.get("type") == "response.completed"
                    ]
                    row["observation"] = (
                        observe(body, finals[-1], slot)
                        if len(finals) == 1
                        else {"all_passed": False, "reason": "STREAM_NOT_COMPLETE"}
                    )
            except Exception as exc:
                row["observation"] = {"all_passed": False, "reason": type(exc).__name__}
        # Actual billed amount remains unknown even when usage/schema pass.
        save()
        if not row["observation"]["all_passed"]:
            state["status"] = "stopped_observation_unproven_or_failed"
            break
    else:
        state["status"] = "minimal_observation_pass_not_course_admission"
    state["not_run"] = [
        n for n in ["S1", "S2"] if n not in [r["case"] for r in state["requests"]]
    ]
    state["seconds"] = round(time.monotonic() - started, 3)
    save()
    print(
        json.dumps(
            {
                "status": state["status"],
                "requests": len(state["requests"]),
                "not_run": state["not_run"],
                "output": str(OUTPUT),
            },
            ensure_ascii=False,
        )
    )
    return 0 if state["status"].startswith("minimal_observation_pass") else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = package()
    raise SystemExit(execute(plan) if args.execute else 0)
