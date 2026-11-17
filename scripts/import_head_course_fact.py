"""Import the single reviewed fact revision into a private development learning identity."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.main import app  # noqa: E402,F401
from app.services.head_course_fact_publication import import_course  # noqa: E402
from scripts.head_course_goal import database  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner", type=UUID, required=True)
    a = p.parse_args()

    async def run(db):
        return await import_course(db, a.owner)

    print(json.dumps(asyncio.run(database(run))))
