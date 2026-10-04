"""Explicit administrator CLI; loads KEKs only from secret configuration."""

import asyncio
import json

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.credential_crypto import CredentialFailure, CredentialKeyring
from app.core.database import create_database_engine
from app.services.provider_connections import ProviderConnectionStore


async def rotate() -> dict[str, int]:
    keys = CredentialKeyring.from_environment()
    engine = create_database_engine()
    try:
        store = ProviderConnectionStore(async_sessionmaker(engine, expire_on_commit=False), keys)
        total = 0
        while True:
            rotated, failed = await store.rotate_batch()
            total += rotated
            if failed:
                return {"rotated": total, "failed": failed}
            if rotated == 0:
                return {"rotated": total, "failed": 0}
    finally:
        await engine.dispose()


def main() -> None:
    try:
        result = asyncio.run(rotate())
    except (CredentialFailure, Exception):
        print(json.dumps({"code": "CREDENTIAL_UNAVAILABLE"}))
        raise SystemExit(1) from None
    print(json.dumps(result))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
