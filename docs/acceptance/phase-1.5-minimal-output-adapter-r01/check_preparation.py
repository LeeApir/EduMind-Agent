"""Read-only isolated implementation/request/Mock evidence check. No live mode."""

import hashlib
import json
from pathlib import Path
import re
import stat

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as p
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def load(path):
    return json.loads(path.read_text())


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    manifest = load(BASE / "manifest.json")
    for item in [*manifest["files"], *manifest["source_pins"]]:
        check(
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            == item["sha256"],
            "SOURCE_CHANGED_" + item["path"],
        )
    approval = load(ROOT / "docs/ADR/0047-approval-20261029.json")
    check(
        approval["status"] == "accepted_for_isolated_implementation",
        "IMPLEMENTATION_APPROVAL",
    )
    check(approval["sections"] == ["A", "B", "C", "D"], "ADR_SCOPE")
    check(
        approval["real_compatibility_scope_approved"]
        and approval["real_http_scope_limit"] == 7,
        "SEVEN_SCOPE",
    )
    check(
        approval["review_handoff_required"] and not approval["fee_waiver_approved"],
        "NO_FEE_EXCEPTION",
    )
    design_manifest = ROOT / approval["manifest_path"]
    check(
        hashlib.sha256(design_manifest.read_bytes()).hexdigest()
        == approval["manifest_sha256"],
        "APPROVAL_MANIFEST",
    )
    for item in approval["attachments"]:
        check(
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest()
            == item["sha256"],
            "APPROVED_ATTACHMENT",
        )
    candidate = load(BASE / "compatibility-candidate.json")
    check(
        candidate["actual_real_http"] == 0
        and not candidate["live_entry_available"]
        and not candidate["fee_cap_verified"],
        "OFFLINE_ONLY",
    )
    plan = load(c.DESIGN / "compatibility-plan.json")
    check(candidate["limits"] == plan["limits"], "LIMIT_DRIFT")
    check(
        sum(slot["max_output_tokens"] for slot in candidate["slots"]) == 16896,
        "OUTPUT_TOTAL",
    )
    check(
        sum(slot["input_reservation"] for slot in candidate["slots"]) == 57344,
        "INPUT_TOTAL",
    )
    bodies = p.protocol_bodies()
    check(len(bodies) == len(candidate["slots"]) == 7, "REQUEST_COUNT")
    for slot in candidate["slots"]:
        expected_config = next(r for r in plan["requests"] if r["slot"] == slot["slot"])
        check(
            all(slot[k] == v for k, v in expected_config.items()),
            "ROUTE_OR_PARAMETER_DRIFT",
        )
        raw = (ROOT / slot["request_path"]).read_bytes()
        check(
            raw == bodies[slot["slot"]]
            and hashlib.sha256(raw).hexdigest() == slot["request_sha256"],
            "REQUEST_BYTES",
        )
        check(len(raw) == slot["request_bytes"] <= 65536, "REQUEST_SIZE")
    check(
        load(BASE / "prompt-snapshot.json")
        == dict(version=p.PROMPT_VERSION, instructions=p.INSTRUCTIONS),
        "PROMPT_CHANGED",
    )
    evidence = load(BASE / "mock-evidence.json")
    directory = Path(evidence["private_directory"])
    check(
        directory.is_dir()
        and not directory.is_symlink()
        and stat.S_IMODE(directory.stat().st_mode) == 0o700,
        "PRIVATE_DIR",
    )
    total_mock_calls = 0
    for row in evidence["cases"]:
        check(
            re.fullmatch(r"[BC]-[a-z_]+\.json", row["file"]) is not None,
            "EVIDENCE_NAME",
        )
        path = directory / row["file"]
        check(
            not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600,
            "PRIVATE_FILE",
        )
        raw = path.read_bytes()
        check(
            hashlib.sha256(raw).hexdigest() == row["sha256"]
            and len(raw) == row["bytes"],
            "MOCK_ORIGINAL_HASH",
        )
        case = json.loads(raw)
        result, wire = case["result"], case["mock_wire"]
        check(
            result["real_provider_calls"] == 0 and not result["independent_evaluation"],
            "NO_MODEL_CREDIT",
        )
        check(
            result["state"] == row["state"] and result.get("reason") == row["reason"],
            "STATE",
        )
        check(result["calls"] == row["mock_calls"] == len(wire), "CALL_COUNT")
        check(len(result["versions"]) == row["versions"], "VERSION_COUNT")
        events = result["events"]
        check(events[-1]["kind"] == "terminal", "TERMINAL")
        for i, event in enumerate(events):
            copy = dict(event)
            check(copy.pop("event_digest") == digest(copy), "EVENT_HASH")
            check(
                event["sequence"] == i
                and event["previous_digest"] == (digest(events[i - 1]) if i else None),
                "EVENT_CHAIN",
            )
        dispatches = [e["payload"] for e in events if e["kind"] == "dispatch"]
        check(len(dispatches) == len(wire), "DISPATCH_COUNT")
        for sent, record in zip(dispatches, wire):
            check(
                sent["stage"] == record["stage"]
                and sent["payload"] == record["payload"],
                "WIRE_EVENT_BINDING",
            )
            check(record["envelope"]["model_id"] == "mock-minimal", "MOCK_MODEL")
        for version in result["versions"]:
            c.verify_artifact(version)
        for record in wire:
            stage, payload = record["stage"], record["payload"]
            if stage.startswith("review_"):
                binding = c.make_binding(payload["artifact"])
                check(binding["targets"] == payload["target_catalog"], "TARGET_MAP")
                c.validate(stage, record["envelope"]["value"], binding=binding)
            elif stage.startswith("B_"):
                given = (
                    payload["original_input"] if stage.endswith("repair") else payload
                )
                check(
                    set(given)
                    == {
                        "spec",
                        "semantics",
                        "goals",
                        "question_definitions",
                        "node_id_conventions",
                    },
                    "BASELINE_INPUT_LEAK",
                )
        total_mock_calls += result["calls"]
    check(len(evidence["cases"]) == 16, "MOCK_SCENARIO_COUNT")
    links = 0
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if path.suffix != ".md":
            continue
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            check(
                (path.parent / target.split("#")[0]).exists(), "BROKEN_LINK_" + target
            )
            links += 1
    print(
        json.dumps(
            dict(
                result="offline_preparation_passed",
                files=len(manifest["files"]),
                source_pins=len(manifest["source_pins"]),
                relative_links=links,
                exact_requests=7,
                user_approved_request_scope=7,
                actual_real_requests=0,
                mock_scenarios=16,
                mock_call_count=total_mock_calls,
                review_pending=True,
                fee_cap_verified=False,
                semantic_correctness_proven=False,
                production_scoring=False,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
