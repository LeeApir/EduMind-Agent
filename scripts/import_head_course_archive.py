"""Import the approved archived response for an existing local learning identity."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services.head_course_archived_import import import_course  # noqa: E402
from scripts.head_course_goal import database  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", type=UUID, required=True)
    args = parser.parse_args()

    async def run(db):
        return await import_course(db, args.owner)

    print(json.dumps(asyncio.run(database(run))))


if __name__ == "__main__":
    main()
