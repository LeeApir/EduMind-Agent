"""Read-only verifier for completed pilot MOCK evidence; never a live-run acceptance."""

import argparse
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from scripts.isolated_diagnostics import p15_agent_pilot as pilot  # noqa: E402
from scripts.isolated_diagnostics.p15_head_insertion_engine import (  # noqa: E402
    canonical,
    digest,
    validate_example,
)


class EvidenceError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceError(reason)


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4000000:
        raise EvidenceError("EVIDENCE_FILE")
    return json.loads(path.read_bytes())


def verify(path: Path) -> dict[str, Any]:
    path = path.absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "EVIDENCE_SYMLINK")
    result = read_json(path / "result.json")
    raw = read_json(path / "mock-wire.json")
    require(result["state"] == "mock_advisory_pass", "NOT_COMPLETED_MOCK_PASS")
    require(
        result["independent_evaluation"] is False
        and result["production_scoring"] is False,
        "AUTHORITY_INFLATION",
    )
    events = result["events"]
    require(type(events) is list and len(events) > 0, "EVENTS_EMPTY")
    previous = None
    example = None
    dispatches = []
    responses = []
    candidates = []
    reviews = []
    known = {"example", "dispatch", "response", "candidate", "review"}
    for index, event in enumerate(events):
        body = deepcopy(event)
        sha = body.pop("event_digest")
        require(
            digest(body) == sha
            and event["sequence"] == index
            and event["previous_digest"] == previous,
            "EVENT_CHAIN",
        )
        previous = digest(event)
        require(event["kind"] in known, "UNKNOWN_OR_FAILED_EVENT")
        value = event["payload"]
        if event["kind"] == "example":
            require(example is None and index == 0, "EXAMPLE_POSITION")
            example = value["example"]
            validate_example(example)
        elif event["kind"] == "dispatch":
            dispatches.append(value)
        elif event["kind"] == "response":
            responses.append(value)
        elif event["kind"] == "candidate":
            candidates.append(value)
        else:
            reviews.append(value)
    if example is None:
        raise EvidenceError("MISSING_EXAMPLE")
    require(
        candidates == result["versions"] and 1 <= len(candidates) <= 2,
        "CANDIDATE_VERSION_COUNT",
    )
    roles = [r["role"] for r in dispatches]
    require(
        roles
        in [
            ["plan", "content", "review"],
            ["plan", "content", "review", "repair", "review"],
        ],
        "CALL_SEQUENCE",
    )
    # Require event ordering, not only the same multiset of role objects.
    expected_order = [
        "example",
        "dispatch",
        "response",
        "dispatch",
        "response",
        "candidate",
        "dispatch",
        "response",
        "review",
    ]
    if len(candidates) == 2:
        expected_order += [
            "dispatch",
            "response",
            "candidate",
            "dispatch",
            "response",
            "review",
        ]
    require([e["kind"] for e in events] == expected_order, "EVENT_ORDER")
    require(
        result["calls"] == len(raw) == len(dispatches) == len(responses), "CALL_COUNT"
    )
    schemas = dict(
        plan=pilot.PLAN_SCHEMA,
        content=pilot.CONTENT_SCHEMA,
        repair=pilot.CONTENT_SCHEMA,
        review=pilot.REVIEW_SCHEMA,
    )
    example_identity = events[0]["payload"]["identity"]
    require(
        example_identity["spec_digest"] == digest(example["spec"])
        and example_identity["arm"] == "C"
        and example_identity["revision"] == 0
        and example_identity["parent_digest"] is None
        and example_identity["prompt_version"] == pilot.PROMPT_VERSION
        and example_identity["schema_version"] == "pilot-artifact-v1",
        "EXAMPLE_IDENTITY",
    )
    for i, (wire, dispatch, response) in enumerate(zip(raw, dispatches, responses)):
        role = dispatch["role"]
        require(response["role"] == role, "ROLE_ORDER")
        require(
            dispatch["instruction_digest"] == digest(pilot.INSTRUCTIONS[role]),
            "PROMPT_DRIFT",
        )
        req = wire["request"]
        require(
            wire["request_digest"] == digest(req)
            and wire["response_digest"] == digest(wire["response_text"]),
            "WIRE_DIGEST",
        )
        require(
            wire["status"] == 200
            and req["stage"] == "pilot_" + role
            and req["schema"] == schemas[role] == dispatch["schema"],
            "WIRE_PROTOCOL",
        )
        require(
            req["messages"][0] == dict(role="system", content=pilot.INSTRUCTIONS[role]),
            "WIRE_INSTRUCTION",
        )
        require(
            json.loads(req["messages"][1]["content"]) == dispatch["payload"],
            "WIRE_INPUT",
        )
        require(
            req["prompt"]["messages"] == req["messages"]
            and not req["prompt"]["images"]
            and req["prompt"]["image_consent"] is None,
            "WIRE_PARAMETER",
        )
        returned = json.loads(wire["response_text"])
        require(
            returned
            == dict(
                value=response["value"],
                model_id=response["model_id"],
                usage=response["usage"],
            ),
            "WIRE_RESPONSE",
        )
        require(
            returned["model_id"] == "mock-pilot"
            and all(type(n) is int and n >= 0 for n in returned["usage"].values()),
            "MODEL_OR_USAGE",
        )
        pilot.check_schema(response["value"], schemas[role])
        identity = dispatch["identity"]
        for key in (
            "run_id",
            "slot_id",
            "arm",
            "spec_digest",
            "engine_version",
            "template_version",
        ):
            require(identity[key] == example_identity[key], "ROLE_IDENTITY")
        require(identity["revision"] == (1 if i >= 3 else 0), "DISPATCH_REVISION")
        if role == "content":
            require(
                dispatch["payload"]["plan"] == responses[0]["value"], "CONTENT_PLAN"
            )
        if role in ("content", "repair"):
            require(
                dispatch["payload"]["example" if role == "content" else "reference"]
                == example,
                "REFERENCE_DRIFT",
            )
            pilot.validate_content(response["value"], example)
        if role == "plan":
            require(
                dispatch["payload"]
                == dict(goal=list(pilot.GOALS), allowed_spec=example["spec"]),
                "PLAN_REQUEST",
            )
            require(
                canonical(response["value"]["spec"]) == canonical(example["spec"])
                and {
                    r["objective"]: r["observation_key"]
                    for r in response["value"]["coverage"]
                }
                == pilot.GOALS,
                "PLAN_DRIFT",
            )
        if role == "review":
            source = dispatch["payload"]["source"]
            require(dispatch["payload"]["reference"] == example, "REVIEW_REFERENCE")
            pilot.validate_review(response["value"], source)
            require(
                not any(
                    issue["severity"] == "severe"
                    or issue["area"] in ("fact", "code_safety")
                    for issue in response["value"]["issues"]
                ),
                "IGNORED_SEVERE_ERROR",
            )
    for i, candidate in enumerate(candidates):
        identity = candidate["identity"]
        source = candidate["payload"]
        content_response = responses[1 if i == 0 else 3]["value"]
        parent = None if i == 0 else digest(candidates[0])
        expected_source = pilot.assemble(
            content_response, example, example_identity["slot_id"], i, parent
        )
        require(
            source == expected_source and candidate["payload_digest"] == digest(source),
            "CANDIDATE_BINDING",
        )
        expected_identity = {**example_identity, "revision": i, "parent_digest": parent}
        require(identity == expected_identity, "CANDIDATE_IDENTITY")
        require(
            identity["revision"] == i and identity["parent_digest"] == parent,
            "REVISION_BINDING",
        )
        pilot.validate_actions(source, example)
        review_index = 2 if i == 0 else 4
        require(
            dispatches[review_index]["payload"]["source"] == source
            and dispatches[review_index]["payload"]["source_digest"] == digest(source),
            "REVIEW_CANDIDATE",
        )
        require(reviews[i] == responses[review_index]["value"], "REVIEW_EVENT")
    require(reviews[-1]["verdict"] == "pass", "NO_FINAL_ADVISORY")
    if len(candidates) == 2:
        require(reviews[0]["verdict"] == "revise", "UNAUTHORIZED_REPAIR")
        require(
            dispatches[3]["payload"]["original"] == responses[1]["value"]
            and dispatches[3]["payload"]["issues"] == reviews[0],
            "REPAIR_SOURCE",
        )
    return dict(
        kind="verified_mock_evidence_only",
        calls=len(raw),
        versions=len(candidates),
        real_http=0,
        independent_truth=False,
        T069_completed=False,
        T070_completed=False,
        usage=dict(
            input_tokens=sum(r["usage"]["input_tokens"] for r in responses),
            output_tokens=sum(r["usage"]["output_tokens"] for r in responses),
        ),
        file_digests={
            name: hashlib.sha256((path / name).read_bytes()).hexdigest()
            for name in ("result.json", "mock-wire.json")
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.directory), ensure_ascii=False, sort_keys=True))
        return 0
    except (EvidenceError, ValueError, KeyError, TypeError, OSError):
        print("Evidence refused; no writes, keys, databases or live requests.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
