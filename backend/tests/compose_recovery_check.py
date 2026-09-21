"""Manual Compose restart recovery check for an approved learning resource.

Run this inside the API container.  It deliberately keeps the temporary session
token in the container's /tmp directory so no credential is printed or committed.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Running this file directly places ``tests`` rather than the application root
# on sys.path.  Keep the command in the recovery guide short and explicit.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.auth import COOKIE_NAME
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import GeneratedResource, LearningScene, LearningUnit

DEFAULT_STATE_PATH = Path("/tmp/edumind-compose-recovery-state.json")


def _database_url() -> str:
    database_url = os.getenv("EDUMIND_DATABASE_URL")
    if not database_url:
        raise RuntimeError("EDUMIND_DATABASE_URL must be set inside the API container")
    return database_url


def seed(state_path: Path) -> None:
    """Create one owner-scoped, reviewed resource and retain only test state."""
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/auth/guest")
        assert response.status_code == 201, response.text
        user_id = UUID(response.json()["user"]["id"])
        session_token = client.cookies[COOKIE_NAME]

    async def write_resource() -> tuple[str, str]:
        engine = create_database_engine(_database_url())
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                unit = LearningUnit(
                    user_id=user_id,
                    title="Compose restart recovery check",
                    status="ready",
                )
                db.add(unit)
                await db.flush()
                scene = LearningScene(
                    learning_unit_id=unit.id,
                    scene_key="restart-recovery",
                    scene_order=1,
                    scene_type="explanation",
                    generation_status="complete",
                    review_status="passed",
                )
                db.add(scene)
                await db.flush()
                resource = GeneratedResource(
                    user_id=user_id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="explanation",
                    content={"markdown": "compose-restart-approved-resource"},
                    review_status="passed",
                    version=1,
                    published_at=datetime.now(timezone.utc),
                )
                db.add(resource)
                await db.commit()
                return str(unit.id), str(resource.id)
        finally:
            await engine.dispose()

    unit_id, resource_id = asyncio.run(write_resource())
    state_path.write_text(
        json.dumps(
            {
                "unit_id": unit_id,
                "resource_id": resource_id,
                "session_token": session_token,
            }
        ),
        encoding="utf-8",
    )
    print(json.dumps({"seeded": True, "unit_id": unit_id, "resource_id": resource_id}))


def check(state_path: Path) -> None:
    """Read the prior resource after containers have been restarted."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(COOKIE_NAME, state["session_token"])
        unit = client.get(f"/api/learning-units/{state['unit_id']}")
        resource = client.get(f"/api/resource/{state['resource_id']}")
    assert unit.status_code == resource.status_code == 200
    assert "compose-restart-approved-resource" in unit.text
    assert resource.json()["review_status"] == "passed"
    print(json.dumps({"recovered": True, "resource_id": state["resource_id"]}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seed", "check"))
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.state_path)
    else:
        check(args.state_path)


if __name__ == "__main__":
    main()
