"""Trusted local quality maintenance. Dry-run is default; apply needs an exact digest."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.services.free_course_evidence import Attestations
from app.services.free_course_quality import Maintenance, local_authority


async def execute(
    owner: UUID, draft: dict[str, Any], apply: bool, kind: str = "quality"
) -> dict[str, Any]:
    authority = local_authority()
    engine = create_database_engine()
    try:
        if kind == "attestation":
            attester = Attestations(async_sessionmaker(engine, expire_on_commit=False), authority)
            return (
                await attester.attest(owner, draft)
                if apply
                else await attester.preview_attestation(owner, draft)
            )
        service = Maintenance(async_sessionmaker(engine, expire_on_commit=False), authority)
        return await service.apply(owner, draft) if apply else await service.dry_run(owner, draft)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", type=UUID, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--kind", choices=["quality", "attestation"], default="quality")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                execute(args.owner, json.loads(args.draft.read_text()), args.apply, args.kind)
            )
        )
    )


if __name__ == "__main__":
    main()
