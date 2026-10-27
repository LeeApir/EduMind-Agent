"""One fixed synthetic review probe; gold is local and never sent to provider."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from jsonschema import Draft202012Validator

from run_p15_aiapi_minimal_r01 import scrub

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-aiapi-review-probe-r01"
OUT = Path("/tmp/edumind-p15-aiapi-review-probe-r01")


def read(name):
    return json.loads((BASE / name).read_text())


def score(text, cases, gold, schema):
    result = {
        "total": len(cases),
        "error_cases": sum(g["has_error"] for g in gold),
        "correct_cases": sum(not g["has_error"] for g in gold),
        "evaluated": 0,
        "unknown": len(cases),
        "tp": 0,
        "fn": 0,
        "fp": 0,
        "tn": 0,
        "uncertain": 0,
        "rows": [],
        "format_valid": False,
    }
    try:
        value = json.loads(text)
        Draft202012Validator(schema).validate(value)
        rows = value["reviews"]
        assert len({r["case_id"] for r in rows}) == len(cases)
        assert {r["case_id"] for r in rows} == {c["case_id"] for c in cases}
    except Exception as exc:
        result["format_failure"] = type(exc).__name__
        return result
    result["format_valid"] = True
    texts = {c["case_id"]: c["text"] for c in cases}
    expected = {g["case_id"]: g for g in gold}
    for row in rows:
        e = expected[row["case_id"]]["has_error"]
        evidence_valid = (
            row["verdict"] != "error"
            or bool(row["evidence"].strip())
            and row["evidence"] in texts[row["case_id"]]
        )
        label = (
            ("tp" if e else "fp")
            if row["verdict"] == "error"
            else ("fn" if e else "tn")
            if row["verdict"] == "no_error"
            else "uncertain"
        )
        if not evidence_valid or not row["reason"].strip():
            label = "unknown"
        if label != "unknown":
            result[label] += 1
            result["evaluated"] += 1
            result["unknown"] -= 1
        result["rows"].append(
            {
                **row,
                "expected_error": e,
                "classification": label,
                "exact_evidence_valid": evidence_valid,
            }
        )
    result["detection_fraction_all_errors"] = [result["tp"], result["error_cases"]]
    result["false_positive_fraction_all_correct"] = [
        result["fp"],
        result["correct_cases"],
    ]
    result["scope"] = (
        "single-batch synthetic smoke, no statistical reliability or teaching acceptance"
    )
    return result


def check():
    manifest = read("manifest.json")
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    body = read("request.json")
    Draft202012Validator.check_schema(body["text"]["format"]["schema"])
    assert body["model"] == "gpt-6.1-sol" and body["stream"] is False
    assert body["max_output_tokens"] == 1536 and body["store"] is False
    assert json.loads(body["input"][0]["content"]) == {"cases": read("cases.json")}
    assert (
        len(read("cases.json")) == 12
        and sum(x["has_error"] for x in read("gold.json")) == 6
    )
    assert "label_source" not in json.dumps(body)
    return body


def execute(body):
    OUT.mkdir(mode=0o700)
    r = {
        "batch_id": "p15-aiapi-review-probe-r01",
        "local_hold_usd": "0.05",
        "actual_invoice_usd": None,
        "settlement": "unknown",
        "dispatch_attempted": False,
    }

    def save():
        (OUT / "results.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2) + "\n"
        )

    save()
    cfg = dotenv_values(ROOT / ".env")
    assert cfg.get("EDUMIND_PROVIDER_BASE_URL", "").rstrip("/") in {
        "https://aiapi.world",
        "https://aiapi.world/v1",
    }
    key = cfg["EDUMIND_PROVIDER_API_KEY"]
    assert key and key.isascii() and not any(c.isspace() for c in key)
    with tempfile.TemporaryDirectory(prefix="review-probe-") as td:
        p = Path(td)
        (p / "headers").write_text(
            "Authorization: Bearer " + key + "\nContent-Type: application/json\n"
        )
        os.chmod(p / "headers", 0o600)
        r["dispatch_attempted"] = True
        save()
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--request",
                    "POST",
                    "https://aiapi.world/v1/responses",
                    "--connect-timeout",
                    "10",
                    "--max-time",
                    "60",
                    "--max-filesize",
                    "1048576",
                    "--header",
                    "@" + str(p / "headers"),
                    "--data-binary",
                    "@" + str(BASE / "request.json"),
                    "--output",
                    str(p / "reply"),
                    "--write-out",
                    "%{http_code}",
                ],
                capture_output=True,
                text=True,
                timeout=62,
            )
            r.update(
                http_status=int(proc.stdout.strip() or "0"),
                transport_exit=proc.returncode,
            )
            raw = (p / "reply").read_text() if (p / "reply").exists() else ""
            assert key not in raw
            r["raw_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            reply = json.loads(raw)
            r["response"] = scrub(reply)
            text = "".join(
                b.get("text", "")
                for i in reply.get("output", [])
                if i.get("type") == "message"
                for b in i.get("content", [])
                if b.get("type") == "output_text"
            )
            r["text"] = text
            if (
                proc.returncode == 0
                and r["http_status"] == 200
                and reply.get("status") == "completed"
            ):
                r["score"] = score(
                    text,
                    read("cases.json"),
                    read("gold.json"),
                    body["text"]["format"]["schema"],
                )
            else:
                r["failure"] = "TRANSPORT_HTTP_OR_INCOMPLETE"
            r["output_cap_echo"] = reply.get("max_output_tokens")
            r["instructions_exact_echo"] = (
                reply.get("instructions") == body["instructions"]
            )
        except Exception as exc:
            r["failure"] = type(exc).__name__
    r["status"] = "observed_once_not_acceptance"
    save()
    print(
        json.dumps(
            {
                "http": r.get("http_status"),
                "failure": r.get("failure"),
                "score": {k: v for k, v in r.get("score", {}).items() if k != "rows"},
                "output": str(OUT),
            },
            ensure_ascii=False,
        )
    )
    return 0 if r.get("score", {}).get("format_valid") else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    body = check()
    raise SystemExit(execute(body) if args.execute else 0)
