"""Static proposal checks only. No Provider/credentials/live-run entry or JSON repair."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as local
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def load(name: str) -> Any:
    return json.loads((BASE / name).read_bytes())


def request(name: str) -> dict[str, Any]:
    return dict(load(name + ".request.json"))


def user(name: str) -> dict[str, Any]:
    return dict(json.loads(request(name)["input"][1]["content"]))


def differences(left: Any, right: Any, path: str = "") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        changes = []
        for key in sorted(set(left) | set(right)):
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in left or key not in right:
                changes.append(pointer)
            else:
                changes.extend(differences(left[key], right[key], pointer))
        return changes
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        return [
            p
            for i, (a, b) in enumerate(zip(left, right))
            for p in differences(a, b, path + "/" + str(i))
        ]
    return [] if left == right else [path]


def patch_once(value: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    parts = patch["path"].split("/")[1:]
    current = result
    for part in parts[:-1]:
        current = current[part]
    key = parts[-1]
    assert (patch["op"] == "add" and key not in current) or (
        patch["op"] == "replace" and key in current
    )
    current[key] = deepcopy(patch["value"])
    return result


def protocol_value_outcome(case: str, value: dict[str, Any]) -> str:
    assert case != "R0"
    local.validate("B_repair", value)
    return (
        "exact_echo"
        if canonical(value) == canonical(user(case)["expected_output"])
        else "reject_wrong_echo"
    )


def repair_mechanical_outcome(value: dict[str, Any]) -> str:
    """Mechanical gate cannot certify new natural-language truth or pedagogical quality."""
    local.validate("B_repair", value)
    paths = differences(user("R0")["original"], value)
    if not paths:
        return "reject_no_repair"
    if paths != ["/paragraphs/0/text"]:
        return "reject_unauthorized_delta"
    return "pending_independent_semantic_review"


def main() -> None:
    matrix = load("matrix.json")
    assert matrix["actual_provider_calls_authorized"] == 0
    assert matrix["order"] == ["P0", "W0", "W1", "W2", "W3", "W4", "R0"]
    old = json.loads(
        (ROOT / "docs/acceptance/phase-1.5-minimal-live-r01/S5.json").read_bytes()
    )
    settings = {k: v for k, v in old.items() if k != "input"}
    for row in matrix["rows"]:
        body = request(row["id"])
        assert {k: v for k, v in body.items() if k != "input"} == settings
        raw = (BASE / row["request_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["request_sha256"]
        assert len(raw) == row["request_bytes"] <= 65536
        assert body["text"]["format"]["strict"] is True
        if row["parent"]:
            assert len(row["user_payload_patch"]) == 1
            assert patch_once(
                user(row["parent"]), row["user_payload_patch"][0]
            ) == user(row["id"])
            assert differences(user(row["parent"]), user(row["id"])) == [
                row["user_payload_patch"][0]["path"]
            ]
            assert request(row["parent"])["input"][0] == body["input"][0]
        if row["id"] != "R0":
            assert body["input"][0] == request("P0")["input"][0]
            assert user(row["id"])["expected_output"] == user("P0")["expected_output"]
            assert (
                protocol_value_outcome(row["id"], user("P0")["expected_output"])
                == "exact_echo"
            )
    assert set(user("P0")) == {"expected_output"}

    def keys(node: Any) -> list[str]:
        if isinstance(node, dict):
            return [*node, *(k for v in node.values() for k in keys(v))]
        return [k for v in node for k in keys(v)] if isinstance(node, list) else []

    assert "expected_output" not in keys(user("R0"))
    assert request("R0")["input"][0] != request("P0")["input"][0]
    context = load("repair-context.json")
    local.verify_artifact(context["original_artifact"])
    local.verify_binding(context["binding"])
    assert (
        user("R0")["previous_candidate_digest"]
        == context["original_artifact"]["artifact_digest"]
    )
    assert user("R0")["original"] == context["original_artifact"]["raw_output"]
    for issue in user("R0")["issues"]:
        assert issue["area"] == "difficulty" and issue["severity"] == "minor"
        assert (
            issue["evidence_quote"]
            in context["binding"]["targets"][issue["target_id"]]["text"]
        )
    output_examples = load("repair-output-examples.json")["examples"]
    for example in output_examples:
        assert (
            repair_mechanical_outcome(example["value"])
            == example["mechanical_expected"]
        )
    provenance = load("fixtures/provenance.json")
    raw = (BASE / provenance["message_text_file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == provenance["message_text_sha256"]
    assert len(raw.decode()) == provenance["message_chars"] == 3306
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        assert exc.msg == "Extra data" and exc.pos == 3287
    else:
        raise AssertionError("Original malformed JSON must not be accepted")
    assert matrix["proposed_later_max_http"] == len(matrix["rows"]) == 7
    assert matrix["proposed_later_input_reservation"] == 7 * 8192
    assert (
        matrix["proposed_later_output_reservation"]
        == sum(request(r["id"])["max_output_tokens"] for r in matrix["rows"])
        == 28672
    )
    old_manifest_path = (
        ROOT / "docs/acceptance/phase-1.5-minimal-live-r01/manifest.json"
    )
    assert (
        hashlib.sha256(old_manifest_path.read_bytes()).hexdigest()
        == "0312764b635f62310f36513683c9fdd98653186224471e024601fcff5658df79"
    )
    old_manifest = json.loads(old_manifest_path.read_bytes())
    for entry in old_manifest["files"]:
        assert (
            hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
            == entry["sha256"]
        ), entry["path"]
    results = ROOT / "docs/acceptance/phase-1.5-minimal-live-r01/results"
    result_manifest_path = results / "result-manifest.json"
    assert (
        hashlib.sha256(result_manifest_path.read_bytes()).hexdigest()
        == "5cc6a2af01e38ca7183080b47eb10827f8afe70a5f11fb61faf02a020f5b2820"
    )
    old_result = json.loads(result_manifest_path.read_bytes())
    for entry in old_result["files"]:
        assert (
            hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
            == entry["sha256"]
        )
    assert (
        hashlib.sha256((ROOT / old_result["grant_path"]).read_bytes()).hexdigest()
        == old_result["grant_sha256"]
    )
    evidence = json.loads((results / "evidence-manifest.json").read_bytes())
    assert (
        next(e["sha256"] for e in evidence["files"] if e["name"] == "S5-response.bin")
        == provenance["raw_response_sha256"]
    )
    manifest = load("manifest.json")
    for entry in [*manifest["files"], *manifest["source_pins"]]:
        assert (
            hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
            == entry["sha256"]
        ), entry["path"]
    checked_links = 0
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                assert (path.parent / target.split("#")[0]).exists(), target
                checked_links += 1
    print(
        json.dumps(
            dict(
                result="offline_design_passed",
                exact_inputs=7,
                pure_echo=1,
                wrapper_cases=5,
                real_repair_proposal=1,
                single_patch_pairs=5,
                repair_output_examples=len(output_examples),
                raw_failure_chars=3306,
                source_pins=len(manifest["source_pins"]),
                original_execution_files_verified=len(old_manifest["files"]),
                files=len(manifest["files"]),
                provider_calls=0,
                relative_links=checked_links,
                semantics_independently_rated=False,
                new_validation_package_approved=False,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
