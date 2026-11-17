"""Read-only reconciliation of this authorized batch; never sends or alters originals."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
VAULT = Path("/Users/apir/.local/share/edumind/limited-c-r01")
entry = ROOT / "docs/acceptance/phase-1.5-limited-c-preparation-t104/execute_once.py"
spec = importlib.util.spec_from_file_location("limited_c_approved_entry", entry)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def main():
    package = e.verify_package()
    assert package == "b686eedd986990806f01160750507f77d0a822f049c6060c4356c90f85fd284d"
    cipher = e.Fernet((VAULT / "raw.key").read_bytes())
    rows = []
    for slot in ["C01", "C02"]:
        for phase in ["generate", "repair"]:
            prefix = f"{slot}-{phase}"
            attempt = VAULT / f"{prefix}.attempt.json"
            if not attempt.exists():
                rows.append(dict(slot=slot, phase=phase, status="not_run"))
                continue
            request = json.loads((VAULT / f"{prefix}.request.json").read_text())
            row = dict(
                slot=slot,
                phase=phase,
                status="unknown",
                request_sha256=hashlib.sha256(e.canonical(request)).hexdigest(),
            )
            try:
                raw = e.decrypt(VAULT / f"{prefix}.raw.enc", cipher)
                row.update(
                    raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw)
                )
                receipt = json.loads((VAULT / f"{prefix}.body.json").read_text())
                assert (
                    receipt["raw_sha256"] == row["raw_sha256"]
                    and receipt["raw_bytes"] == len(raw)
                    and receipt["body_complete"] is True
                )
                row["http_status"] = receipt["http_status"]
                assert receipt["http_status"] == 200, "HTTP_FAILED"
                _, observation = e.observe_generation(request, raw)
                row["observation"] = observation
                candidate = e.verify_saved(VAULT, prefix, cipher)
                row.update(
                    status="complete_candidate_awaiting_independent_evaluation",
                    candidate_digest=candidate["artifact_digest"],
                )
                decision_path = OUT / (
                    f"{slot}-final-evaluation.json"
                    if phase == "repair"
                    else f"{slot}-evaluation.json"
                )
                if decision_path.exists():
                    decision = json.loads(decision_path.read_text())
                    assert decision["candidate_digest"] == candidate["artifact_digest"]
                    assert (
                        decision["course_sha256"]
                        == hashlib.sha256(
                            (VAULT / f"{prefix}.course.html").read_bytes()
                        ).hexdigest()
                    )
                    row["teaching_verdict"] = decision["verdict"]
                    row["evaluation_file"] = decision_path.name
                    row["status"] = "complete_candidate_independently_evaluated"
                # Exact copies only; do not add, edit or replace teaching content.
                for suffix in [
                    "candidate.json",
                    "course.html",
                    "request.json",
                    "body.json",
                    "result.json",
                    "attempt.json",
                ]:
                    source = VAULT / f"{prefix}.{suffix}"
                    (OUT / f"{prefix}.{suffix}").write_bytes(source.read_bytes())
            except Exception as exc:
                row["error_type"] = type(exc).__name__
                if isinstance(exc, e.wire.PilotError):
                    row["protocol_code"] = str(exc)
            rows.append(row)
    inventory = []
    for file in sorted(VAULT.iterdir()):
        if file.name == "raw.key":
            continue
        if file.is_file():
            inventory.append(
                dict(
                    name=file.name,
                    bytes=file.stat().st_size,
                    sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                )
            )
    summary = dict(
        package_sha256=package,
        originals_private_path=str(VAULT),
        new_http_attempts=len(list(VAULT.glob("*.attempt.json"))),
        stopped=(VAULT / "STOP").exists(),
        active_or_unconfirmed=(VAULT / "ACTIVE").exists(),
        rows=rows,
        private_inventory=inventory,
        actual_invoice="unknown; no billing endpoint called",
    )
    (OUT / "evidence-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: summary[k]
                for k in [
                    "new_http_attempts",
                    "stopped",
                    "active_or_unconfirmed",
                    "rows",
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if any(row["status"] == "unknown" for row in rows):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
