"""Read-only fresh-process recovery probe; private session state arrives on stdin."""

import json
import sys

from fastapi.testclient import TestClient

from app.core.auth import COOKIE_NAME
from app.main import app


def main() -> None:
    state = json.load(sys.stdin)
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(COOKIE_NAME, state["session_token"])
        unit = client.get(f"/api/learning-units/{state['unit_id']}")
        profile = client.get("/api/profile/me")
        mastery = client.get("/api/mastery")
        path = client.get("/api/path/current", params={"target_node_id": state["target"]})
        receipt = client.get("/api/quiz-submissions/latest", params={
            "resource_id": state["resource_id"], "resource_version": 1,
        })
    assert all(response.status_code == 200 for response in (unit, profile, mastery, path, receipt))
    assert unit.json()["status"] == "ready"
    assert profile.json()["engineering_preference"] == {"code_first": True}
    assert path.json() == state["path"]
    assert mastery.json() == state["mastery"]
    assert receipt.json()["evidence_id"] == state["evidence_id"]
    print(json.dumps({"fresh_process_recovery": True, "provider_calls": 0}))


if __name__ == "__main__":
    main()
