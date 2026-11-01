"""Recheck large synthetic Responses-shaped Mock evidence; no Provider calls."""

import gzip
import hashlib
import json
from pathlib import Path

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as control
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics import p15_teaching_pilot as teaching
from scripts.isolated_diagnostics import p15_visible_worker_v1 as worker
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

ROOT = Path(__file__).resolve().parent


def main() -> None:
    data = json.loads(gzip.decompress((ROOT / "stress-mock-flow.json.gz").read_bytes()))
    package = data["package"]
    package_sha = hashlib.sha256(canonical(package)).hexdigest()
    assert data["anchor_lines"][0] == package_sha
    assert data["anchor_lines"][-1] == digest(data["ledger_state"])
    assert data["batch_status"] == "complete" and data["real_provider_calls"] == 0
    assert not data["independent_semantic_evaluation"] and len(data["attempts"]) == 9
    assert data["observed_stages"] == [
        "B_generate",
        "review_B",
        "B_repair",
        "review_B",
        "C_plan",
        "C_content",
        "review_C",
        "C_repair",
        "review_C",
    ]
    assert sum(row["input_reserved"] for row in data["attempts"]) == 26954741
    assert sum(row["output_reserved"] for row in data["attempts"]) == 72000
    assert sum(row["input_reserved"] for row in data["attempts"]) <= package["input"]
    assert sum(row["output_reserved"] for row in data["attempts"]) <= package["output"]
    catalog = c.make_catalog(package["slots"][0]["spec"])
    spec = package["slots"][0]["spec"]
    assert canonical(package["slots"][1]["spec"]) == canonical(spec)
    common = old.baseline_input(spec)
    initial = {"B": common, "C": None}
    plan = None
    snapshot_rows = []
    previous = {"B": None, "C": None}
    reviewed = {"B": [], "C": []}
    assert len(data["observed_requests"]) == len(data["attempts"])
    for row, observed in zip(data["attempts"], data["observed_requests"]):
        arm, stage = row["arm"], row["stage"]
        request, raw = row["request"].encode(), row["response"].encode()
        assert hashlib.sha256(request).hexdigest() == row["request_sha"]
        assert hashlib.sha256(raw).hexdigest() == row["response_sha"]
        assert row["previous_receipt"] == previous[arm] and row["state"] == "responded"
        body = json.loads(request)
        assert row["input_reserved"] == len(request) + 8192
        assert row["output_reserved"] == body["max_output_tokens"] == 8000
        snapshot = dict(row)
        for field, value in (("request", request), ("response", raw)):
            snapshot[field] = {
                "bytes_sha256": hashlib.sha256(value).hexdigest(),
                "length": len(value),
            }
        snapshot_rows.append(snapshot)
        role = "review" if stage.startswith("review_") else "generation"
        assert observed == dict(
            stage=stage,
            method="POST",
            url=package["runtime_contract"]["routes"][role]["url"],
            content_type="application/json",
            accept_encoding="identity",
            authorization_present=False,
            body_sha256=row["request_sha"],
        )
        private, echo = control.response_for_validation(request, raw, role)
        result, _ = control.wire.validate(body, private, role)
        usage = json.loads(raw)["usage"]
        assert usage["input_tokens"] == row["input_used"] <= row["input_reserved"]
        assert usage["output_tokens"] == row["output_used"] <= row["output_reserved"]
        assert (usage["input_tokens"], usage["output_tokens"]) == (10, 20)
        runtime = package["runtime_contract"]["stages"][stage]
        instruction_sha = hashlib.sha256(
            body["input"][0]["content"].encode()
        ).hexdigest()
        assert instruction_sha == runtime["instruction_sha256"]
        assert (
            hashlib.sha256(canonical(body["text"]["format"]["schema"])).hexdigest()
            == runtime["schema_sha256"]
        )
        receipt = dict(
            version=control.VERSION,
            package_digest=package_sha,
            batch=package["batch"],
            slot=row["slot"],
            arm=arm,
            ordinal=row["ordinal"],
            stage=stage,
            target_url=package["runtime_contract"]["routes"][role]["url"],
            prompt_version=runtime["prompt_version"],
            instruction_digest=instruction_sha,
            schema_echo=echo,
            previous_receipt_digest=previous[arm],
            request_digest=row["request_sha"],
            response_digest=row["response_sha"],
        )
        current = digest(receipt)
        versions, opinions = (
            data["results"][arm]["versions"],
            data["results"][arm]["opinions"],
        )
        if stage == "B_generate":
            assert body["input"][1]["content"].encode() == canonical(common)
        elif stage == "C_plan":
            assert body["input"][1]["content"].encode() == canonical(
                teaching.plan_input(spec, catalog)
            )
            c.validate("C_plan", result.value, catalog=catalog)
            plan = dict(result.value)
        elif stage == "C_content":
            assert plan is not None
            initial["C"] = teaching.content_input(common, catalog, plan)
            assert body["input"][1]["content"].encode() == canonical(initial["C"])
        elif stage.endswith("_repair"):
            assert initial[arm] is not None
            expected_repair = teaching.repair_input(
                initial[arm], versions[0], opinions[0]
            )
            assert body["input"][1]["content"].encode() == canonical(expected_repair)
        if stage in (arm + "_generate", arm + "_content", arm + "_repair"):
            revision = 1 if stage.endswith("repair") else 0
            candidate = versions[revision]
            assert result.value == candidate["raw_output"]
            c.validate(stage, result.value, catalog=catalog if arm == "C" else None)
            assert candidate["identity"]["receipt_digest"] == current
            if revision:
                assert (
                    candidate["identity"]["parent_digest"]
                    == versions[0]["artifact_digest"]
                )
                assert (
                    candidate["identity"]["parent_review_receipt_digest"]
                    == reviewed[arm][0]
                )
        elif stage == "review_" + arm:
            revision = len(reviewed[arm])
            candidate = versions[revision]
            assert result.value == opinions[revision]
            expanded = worker.expand(
                candidate["raw_output"], candidate["identity"], catalog
            )
            assert expanded["artifact"] == candidate
            sent = body["input"][1]["content"].encode()
            assert sent == canonical(expanded["view"])
            worker.validate_review(
                opinions[revision], sent, candidate, catalog, expanded["binding"]
            )
            reviewed[arm].append(current)
        previous[arm] = current
    assert snapshot_rows == data["ledger_state"]["attempts"]
    for arm in ("B", "C"):
        opinions = data["results"][arm]["opinions"]
        assert len(reviewed[arm]) == 2 and opinions[0]["verdict"] == "revise"
        assert opinions[0]["issues"] and opinions[1]["verdict"] == "pass"
    attestation = data["feedback_attestations"][0]["value"]
    assert attestation["review_receipt_digest"] == reviewed["B"][0]
    assert (
        attestation["candidate_digest"]
        == data["results"]["B"]["versions"][0]["artifact_digest"]
    )
    assert attestation["issues_digest"] == digest(
        data["results"]["B"]["opinions"][0]["issues"]
    )
    attestation_bytes = canonical(attestation)
    assert data["ledger_state"]["attestation"] == [
        dict(
            slot="slot",
            arm="B",
            value=dict(
                bytes_sha256=hashlib.sha256(attestation_bytes).hexdigest(),
                length=len(attestation_bytes),
            ),
        )
    ]
    print(
        "9 large Mock requests, actual view/quote/parent/usage/anchor replayed; Provider 0"
    )


if __name__ == "__main__":
    main()
