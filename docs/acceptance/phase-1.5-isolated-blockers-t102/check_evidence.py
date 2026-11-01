"""Recheck archived synthetic evidence without its intentionally unexported AES key."""

import base64
import gzip
import hashlib
import json
from pathlib import Path

from scripts.isolated_diagnostics import p15_controlled_mock_v2 as control
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics import p15_teaching_pilot as teaching
from scripts.isolated_diagnostics import p15_visible_worker_v2 as worker
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

ROOT = Path(__file__).resolve().parent


def main() -> None:
    data = json.loads(gzip.decompress((ROOT / "offline-evidence.json.gz").read_bytes()))
    package = data["package"]
    package_sha = hashlib.sha256(canonical(package)).hexdigest()
    assert data["anchor_lines"][0] == package_sha
    assert data["anchor_lines"][-1] == digest(data["ledger_state"])
    assert data["real_provider_calls"] == 0 and not data["synthetic_aes_key_exported"]
    assert data["summary"]["batch_status"] == "complete" and data["summary"]["denominator"] == 2
    attempts = data["attempts"]
    assert [row["stage"] for row in attempts] == [
        "B_generate", "review_B", "B_repair", "review_B",
        "C_plan", "C_content", "review_C", "C_repair", "review_C",
    ]
    assert [row["counter"] for row in attempts] == list(range(1, 10))
    assert len({row["reference"]["transport_proof"]["pid"] for row in attempts}) == 9
    assert sum(row["input_reserved"] for row in attempts) <= package["input"]
    assert sum(row["output_reserved"] for row in attempts) == 72000 <= package["output"]
    spec = package["slots"][0]["spec"]
    assert canonical(package["slots"][1]["spec"]) == canonical(spec)
    catalog = c.make_catalog(spec)
    common = old.baseline_input(spec)
    initial = {"B": common, "C": None}
    previous = {"B": None, "C": None}
    reviews = {"B": [], "C": []}
    snapshots = []
    plan = None
    for row in attempts:
        arm, stage = row["arm"], row["stage"]
        role = "review" if stage.startswith("review_") else "generation"
        request, raw = row["request"].encode(), row["raw_response"].encode()
        reference = row["reference"]
        proof = reference["transport_proof"]
        cipher = base64.b64decode(row["ciphertext_b64"], validate=True)
        assert hashlib.sha256(request).hexdigest() == row["request_sha256"]
        assert hashlib.sha256(raw).hexdigest() == row["response_sha256"] == reference["raw_sha256"]
        assert hashlib.sha256(cipher).hexdigest() == reference["ciphertext_sha256"]
        assert len(raw) == reference["raw_bytes"] and len(cipher) == len(raw) + 16
        assert row["state"] == "responded" and row["http_status"] == 200
        assert row["previous_receipt_digest"] == previous[arm]
        assert row["input_reserved"] == len(request) + 8192 and row["output_reserved"] == 8000
        assert proof["request_sha256"] == row["request_sha256"] and proof["ordinal"] == row["ordinal"]
        assert proof["role"] == role and proof["stage"] == stage and proof["credential_roles"] == [role]
        assert proof["target"] == package["runtime_contract"]["routes"][role]["url"]
        assert proof["ip"] == "1.1.1.1" and proof["host"] == proof["sni"]
        assert proof["transport_kind"] == "httpx-async-http-transport-core-intercepted"
        assert proof["tls_verification_configured"] and proof["retries"] == 0
        assert proof["provider_env_present"] is False
        aad = dict(
            version="supervised-encrypted-controller-v2-offline", package_sha256=package_sha,
            batch=package["batch"], slot=row["slot"], arm=arm, ordinal=row["ordinal"],
            stage=stage, http_status=200, request_sha256=row["request_sha256"],
            previous_receipt_digest=previous[arm], counter=row["counter"], transport_proof=proof,
        )
        assert row["aad"] == aad and reference["aad_sha256"] == hashlib.sha256(canonical(aad)).hexdigest()
        body = json.loads(request)
        private, echo = control.response_for_validation(request, raw, role)
        result, _ = control.wire.validate(body, private, role)
        usage = json.loads(raw)["usage"]
        assert (usage["input_tokens"], usage["output_tokens"]) == (row["input_used"], row["output_used"]) == (10, 20)
        runtime = package["runtime_contract"]["stages"][stage]
        instruction_sha = hashlib.sha256(body["input"][0]["content"].encode()).hexdigest()
        assert instruction_sha == runtime["instruction_sha256"]
        assert hashlib.sha256(canonical(body["text"]["format"]["schema"])).hexdigest() == runtime["schema_sha256"]
        receipt = dict(
            version=package["runtime_contract"]["version"], package_digest=package_sha,
            batch=package["batch"], slot=row["slot"], arm=arm, ordinal=row["ordinal"], stage=stage,
            target_url=package["runtime_contract"]["routes"][role]["url"], prompt_version=runtime["prompt_version"],
            instruction_digest=instruction_sha, schema_echo=echo, previous_receipt_digest=previous[arm],
            request_digest=row["request_sha256"], response_digest=row["response_sha256"],
        )
        receipt_digest = digest(receipt)
        versions, opinions = data["results"][arm]["versions"], data["results"][arm]["opinions"]
        if stage == "B_generate":
            assert body["input"][1]["content"].encode() == canonical(common)
        elif stage == "C_plan":
            assert body["input"][1]["content"].encode() == canonical(teaching.plan_input(spec, catalog))
            c.validate("C_plan", result.value, catalog=catalog)
            plan = dict(result.value)
        elif stage == "C_content":
            assert plan is not None
            initial["C"] = teaching.content_input(common, catalog, plan)
            assert body["input"][1]["content"].encode() == canonical(initial["C"])
        elif stage.endswith("_repair"):
            assert initial[arm] is not None
            assert body["input"][1]["content"].encode() == canonical(teaching.repair_input(initial[arm], versions[0], opinions[0]))
        if stage in (arm + "_generate", arm + "_content", arm + "_repair"):
            revision = 1 if stage.endswith("repair") else 0
            candidate = versions[revision]
            assert result.value == candidate["raw_output"] and candidate["identity"]["receipt_digest"] == receipt_digest
            c.validate(stage, result.value, catalog=catalog if arm == "C" else None)
            if revision:
                assert candidate["identity"]["parent_digest"] == versions[0]["artifact_digest"]
                assert candidate["identity"]["parent_review_receipt_digest"] == reviews[arm][0]
        elif stage == "review_" + arm:
            revision = len(reviews[arm])
            candidate = versions[revision]
            assert result.value == opinions[revision]
            expanded = worker.expand(candidate["raw_output"], candidate["identity"], catalog)
            sent = body["input"][1]["content"].encode()
            assert expanded["artifact"] == candidate and sent == canonical(expanded["view"])
            worker.validate_review(opinions[revision], sent, candidate, catalog, expanded["binding"])
            reviews[arm].append(receipt_digest)
        reference_bytes = canonical(reference)
        snapshots.append(dict(
            nonce_counter=row["counter"], slot=row["slot"], arm=arm, ordinal=row["ordinal"], stage=stage,
            request={"bytes_sha256": row["request_sha256"], "length": len(request)}, request_sha=row["request_sha256"],
            previous_receipt=row["previous_receipt_digest"], input_reserved=row["input_reserved"], output_reserved=row["output_reserved"],
            state=row["state"], response={"bytes_sha256": hashlib.sha256(reference_bytes).hexdigest(), "length": len(reference_bytes)},
            http_status=row["http_status"], response_sha=row["response_sha256"], input_used=row["input_used"], output_used=row["output_used"],
        ))
        previous[arm] = receipt_digest
    assert snapshots == data["ledger_state"]["attempts"]
    for arm in ("B", "C"):
        opinions = data["results"][arm]["opinions"]
        assert len(reviews[arm]) == 2 and opinions[0]["issues"] and opinions[0]["verdict"] == "revise"
        assert opinions[1]["verdict"] == "pass"
    attestation = data["feedback_attestation"]
    assert attestation["review_receipt_digest"] == reviews["B"][0]
    assert attestation["candidate_digest"] == data["results"]["B"]["versions"][0]["artifact_digest"]
    assert attestation["issues_digest"] == digest(data["results"]["B"]["opinions"][0]["issues"])
    print("9 supervised synthetic requests: schema, visible quotes, parent/receipt/AAD and ledger replayed; Provider 0")
    print("Archived ciphertext integrity checked by digest; original AES key intentionally not exported.")


if __name__ == "__main__":
    main()
