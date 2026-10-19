"""Offline evidence consistency check; this never marks model quality as passing."""

import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    request = json.loads((OUT / "learning-request.json").read_text())
    goal = (OUT / "submitted-input.txt").read_bytes()
    assert request == {
        "goal": goal.decode(), "preferred_language": "c", "generation_protocol": "shared-plan-v1"
    }
    assert hashlib.sha256(goal).hexdigest() == "ca258576f14b3298728b2ea18ce9c808d31314db7a453c64e6583a128afc6e2e"
    assert goal == (OUT.parents[1] / "openmaic/head-insertion-20261019/submitted-input.txt").read_bytes()
    assert json.loads((OUT / "provider-calls.json").read_text()) == []
    database = json.loads((OUT / "database-evidence.json").read_text())
    assert len(database["operations"]) == 1
    operation = database["operations"][0]
    assert operation["goal"].encode() == goal
    assert operation["status"] == "failed" and operation["generation_call_count"] == 0
    assert json.loads(operation["error"])["code"] == "GOAL_CLARIFICATION_REQUIRED"
    assert set(database["counts"].values()) == {0}
    events = []
    for frame in (OUT / "learning-response.sse").read_text().strip().split("\n\n"):
        lines = frame.splitlines()
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    assert [e[0] for e in events] == ["agent_start", "error", "done"]
    assert all(e[1]["operation_id"] == operation["id"] for e in events)
    assert events[1][1]["code"] == "GOAL_CLARIFICATION_REQUIRED"
    assert events[2][1]["status"] == "failed"
    reproduction = json.loads((OUT / "resolver-reproduction.json").read_text())
    assert reproduction["reason"] == "ambiguous_aliases"
    assert {n["id"] for n in reproduction["candidates"]} == {
        "c-pointer", "single-linked-list", "linked-list-insertion"
    }
    for name, digest in json.loads((OUT / "artifact-manifest.json").read_text()).items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest, name
    print("PASS: evidence consistent; course generation failed before model; code quality untested")


if __name__ == "__main__":
    main()
