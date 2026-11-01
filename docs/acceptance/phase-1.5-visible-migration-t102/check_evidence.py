"""Recheck local synthetic evidence. This never calls a Provider."""

import hashlib
import json
from pathlib import Path

from scripts.isolated_diagnostics import p15_controlled_mock_v1 as control
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.isolated_diagnostics import p15_visible_worker_v1 as worker
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_bytes())


def check_targets(arm):
    report = read(f"{arm.lower()}-target-report.json")
    source = read(f"{arm.lower()}-target-sources.json")
    assert report["report_digest"] == digest(
        {k: v for k, v in report.items() if k != "report_digest"}
    )
    binding, view = source["visible_binding"], source["visible_view"]
    assert binding["view_digest"] == digest(view)
    assert binding["binding_digest"] == digest(
        {k: v for k, v in binding.items() if k != "binding_digest"}
    )
    assert report["candidate_digest"] == binding["candidate_digest"]
    old, cells = source["old_targets"], {cell["id"]: cell for cell in view["cells"]}
    assert set(old) == {row["old_id"] for row in report["targets"]}
    for row in report["targets"]:
        assert row["old_path"] == old[row["old_id"]]["path"]
        assert row["visible_ids"] or row["program_checks"]
        assert all(
            target in cells and target in binding["paths"]
            for target in row["visible_ids"]
        )
        assert all(check in report["checks"] for check in row["program_checks"])
    assert report["checks"]["RECEIPT_AND_PARENT_CHAIN"] == "pending_controlled_http"
    return len(old)


def check_flow(arm):
    data = read(f"{arm.lower()}-mock-flow.json")
    package = data["package"]
    package_sha = hashlib.sha256(canonical(package)).hexdigest()
    assert data["anchor_lines"][0] == package_sha
    assert data["anchor_lines"][-1] == digest(data["ledger_state"])
    assert (
        data["real_provider_calls"] == 0 and not data["independent_semantic_evaluation"]
    )
    assert data["batch_status"] == "complete" and data["batch_attempts"] == 9
    assert len(data["attempts"]) == (4 if arm == "B" else 5)
    catalog = c.make_catalog(data["grant"]["spec"])
    versions, opinions = data["result"]["versions"], data["result"]["opinions"]
    prior, reviewed = None, []
    for index, attempt in enumerate(data["attempts"]):
        request, response = attempt["request"].encode(), attempt["response"].encode()
        assert hashlib.sha256(request).hexdigest() == attempt["request_sha"]
        assert hashlib.sha256(response).hexdigest() == attempt["response_sha"]
        assert attempt["previous_receipt"] == prior and attempt["ordinal"] == index
        body, stage = json.loads(request), attempt["stage"]
        role = "review" if stage.startswith("review_") else "generation"
        private, echo = control.response_for_validation(request, response, role)
        result, _ = control.wire.validate(body, private, role)
        usage = json.loads(response)["usage"]
        assert (
            usage["input_tokens"] == attempt["input_used"] <= attempt["input_reserved"]
        )
        assert (
            usage["output_tokens"]
            == attempt["output_used"]
            <= attempt["output_reserved"]
        )
        runtime = package["runtime_contract"]["stages"][stage]
        system_sha = hashlib.sha256(body["input"][0]["content"].encode()).hexdigest()
        assert runtime["instruction_sha256"] == system_sha
        core = dict(
            version=control.VERSION,
            package_digest=package_sha,
            batch=package["batch"],
            slot=attempt["slot"],
            arm=arm,
            ordinal=index,
            stage=stage,
            target_url=package["runtime_contract"]["routes"][role]["url"],
            prompt_version=runtime["prompt_version"],
            instruction_digest=system_sha,
            schema_echo=echo,
            previous_receipt_digest=prior,
            request_digest=attempt["request_sha"],
            response_digest=attempt["response_sha"],
        )
        prior = digest(core)
        if stage in (arm + "_generate", arm + "_content", arm + "_repair"):
            revision = 1 if stage.endswith("repair") else 0
            candidate = versions[revision]
            assert result.value == candidate["raw_output"]
            assert candidate["identity"]["receipt_digest"] == prior
            if revision:
                assert (
                    candidate["identity"]["parent_digest"]
                    == versions[0]["artifact_digest"]
                )
                assert (
                    candidate["identity"]["parent_review_receipt_digest"] == reviewed[0]
                )
        elif stage == "review_" + arm:
            revision = len(reviewed)
            assert result.value == opinions[revision]
            view, binding = visible.build(versions[revision], catalog)
            sent = body["input"][1]["content"].encode()
            assert sent == canonical(view)
            worker.validate_review(
                opinions[revision], sent, versions[revision], catalog, binding
            )
            reviewed.append(prior)
    assert (
        len(reviewed) == 2
        and opinions[0]["verdict"] == "revise"
        and opinions[0]["issues"]
    )
    assert opinions[1]["verdict"] == "pass"
    if arm == "B":
        attestation = data["feedback_attestation"]
        assert attestation["review_receipt_digest"] == reviewed[0]
        assert attestation["candidate_digest"] == versions[0]["artifact_digest"]
        assert attestation["issues_digest"] == digest(opinions[0]["issues"])
    return len(data["attempts"]), package_sha


def main():
    assert check_targets("B") == 206 and check_targets("C") == 160
    b_count, b_package = check_flow("B")
    c_count, c_package = check_flow("C")
    assert b_package == c_package and (b_count, c_count) == (4, 5)
    capacity = read("capacity-evidence.json")
    assert capacity["real_provider_calls"] == 0
    assert capacity["scenarios"]["dense_B"]["stages"][1]["body_bytes"] > 4 * 1024 * 1024
    distinct = capacity["scenarios"]["distinct_refs_B"]
    assert distinct["reference_occurrences"] == distinct["distinct_definitions"] == 9693
    assert distinct["stages"][1]["body_bytes"] == 7680483
    assert distinct["worker_result_bytes"] < 32 * 1024 * 1024
    assert capacity["scenarios"]["max_actions_B"]["visible_states"] == 64
    assert capacity["scenarios"]["max_actions_B"]["visible_actions"] == 180
    print(
        "206/160 old targets; 9 Mock requests, parent/review/usage/anchor bindings; capacity samples; Provider 0"
    )


if __name__ == "__main__":
    main()
