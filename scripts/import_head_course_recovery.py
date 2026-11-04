"""Import only the fixed r03 derived private preview; no Provider or old-batch resume."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.main import app  # noqa: E402,F401
from app.services import head_course_derivation as d  # noqa: E402
from scripts.head_course_goal import database  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--import-preview", action="store_true", required=True)
    p.add_argument(
        "--owner",
        type=UUID,
        help="Current authenticated local preview identity; original source owner remains in audit",
    )
    args = p.parse_args()
    record, _ = d.mapping()

    async def action(db):
        return await d.import_course(
            db,
            args.owner or UUID(record["original_context"]["owner"]),
            record["independent_review"],
        )

    print(json.dumps(asyncio.run(database(action))))
