"""Exercise both large synthetic arms through the same offline Mock controller."""

import asyncio
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

import httpx

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as control
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.generate_p15_visible_capacity_evidence import payload
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_controlled_mock_v1 import attest, package_grant
from scripts.tests.test_p15_pilot_wire_execution import response

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = (
    ROOT / "docs/acceptance/phase-1.5-visible-migration-t102/stress-mock-flow.json.gz"
)


def synthetic_transport(arm: str, seen: list[dict]) -> httpx.MockTransport:
    reviews = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal reviews
        body = json.loads(request.content)
        message = json.loads(body["input"][1]["content"])
        if "cells" in message:
            reviews += 1
            paragraph = next(
                item for item in message["cells"] if item["kind"] == "paragraph"
            )
            result = dict(
                candidate_id=message["candidate_id"],
                verdict="revise" if reviews == 1 else "pass",
                uncertainty="",
                issues=[],
            )
            if reviews == 1:
                result["issues"] = [
                    dict(
                        severity="minor",
                        area="difficulty",
                        target_id=paragraph["id"],
                        evidence_quote="[](",
                        reason="需要补充解释。",
                    )
                ]
            stage = "review_" + arm
        elif "original" in message:
            result = deepcopy(message["original"])
            for paragraph in result["paragraphs"]:
                paragraph["text"] += "修订"
            for question in result["questions"].values():
                question["stem"] += "修订"
                question["explanation"] += "修订"
            stage = arm + "_repair"
        elif body["text"]["format"]["schema"] == c.schema_for("C_plan"):
            result = dict(spec_id=message["spec_id"], objective_ids=list(c.GOALS))
            stage = "C_plan"
        else:
            result = payload(arm, "distinct_refs")
            stage = "B_generate" if arm == "B" else "C_content"
        role = "review" if stage.startswith("review_") else "generation"
        assert str(request.url) == control.wire.ROUTES[role]["url"]
        assert (
            request.method == "POST"
            and request.headers["content-type"] == "application/json"
        )
        assert (
            request.headers["accept-encoding"] == "identity"
            and "authorization" not in request.headers
        )
        seen.append(
            dict(
                stage=stage,
                method=request.method,
                url=str(request.url),
                content_type=request.headers["content-type"],
                accept_encoding=request.headers["accept-encoding"],
                authorization_present="authorization" in request.headers,
                body_sha256=hashlib.sha256(request.content).hexdigest(),
            )
        )
        raw = canonical(response(body, result))
        return httpx.Response(200, stream=httpx.ByteStream(raw))

    return httpx.MockTransport(handle)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "stress-package.db"
        grant = package_grant(path)
        grant.update(input=30_000_000, request_bytes=12_000_000)
        seen: list[dict] = []
        executor = control.Controller(
            path, grant, synthetic_transport("B", seen), selected=("slot", "B")
        )
        try:
            results = {"B": asyncio.run(executor.run(attest))}
            print("B complete", flush=True)
            executor.select_slot("slot", "C")
            executor.transport = synthetic_transport("C", seen)
            results["C"] = asyncio.run(executor.run(attest))
            attempts = []
            for row in executor.db.execute(
                "SELECT * FROM attempts ORDER BY CASE arm WHEN 'B' THEN 0 ELSE 1 END, ordinal"
            ):
                record = dict(row)
                record["request"] = bytes(record["request"]).decode("utf-8")
                record["response"] = bytes(record["response"]).decode("utf-8")
                attempts.append(record)
            evidence = dict(
                scope="synthetic stress fixture; B output is fixture-generated, not model output or independent truth",
                real_provider_calls=0,
                independent_semantic_evaluation=False,
                package=executor.package,
                batch_status=executor.batch_status(),
                observed_stages=[item["stage"] for item in seen],
                observed_requests=seen,
                attempts=attempts,
                results=results,
                ledger_state=control.ledger_state(executor.db),
                anchor_lines=Path(str(path) + ".anchor").read_text().splitlines(),
                feedback_attestations=[
                    dict(
                        slot=row["slot"],
                        arm=row["arm"],
                        value=json.loads(bytes(row["value"])),
                    )
                    for row in executor.db.execute(
                        "SELECT * FROM attestation ORDER BY slot,arm"
                    )
                ],
            )
            OUTPUT.write_bytes(
                gzip.compress(canonical(evidence), compresslevel=9, mtime=0)
            )
            print(
                "C complete;",
                len(attempts),
                "Mock requests;",
                OUTPUT.stat().st_size,
                "compressed bytes",
                flush=True,
            )
        finally:
            executor.close()


if __name__ == "__main__":
    main()
