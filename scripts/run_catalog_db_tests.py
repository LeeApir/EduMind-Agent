"""Use only a new isolated test database; never load server provider credentials."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "edumind-mvp03-t010-pg"
DATABASE = "edumind_catalog_20261002"


def test_environment() -> dict[str, str]:
    info = json.loads(subprocess.run(["docker", "inspect", CONTAINER], capture_output=True,
                                    text=True, check=True).stdout)[0]
    settings = dict(line.split("=", 1) for line in info["Config"]["Env"] if "=" in line)
    bindings = info["NetworkSettings"]["Ports"]["5432/tcp"]
    binding = next(b for b in bindings if b["HostIp"] in {"127.0.0.1", "0.0.0.0"})
    username = settings["POSTGRES_USER"]
    password = settings["POSTGRES_PASSWORD"]
    port = int(binding["HostPort"])

    async def create() -> None:
        connection = await asyncpg.connect(user=username, password=password, host="127.0.0.1",
                                          port=port, database="postgres")
        try:
            exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", DATABASE)
            if not exists:
                await connection.execute('CREATE DATABASE "' + DATABASE + '"')
        finally:
            await connection.close()
    asyncio.run(create())
    url = f"postgresql+asyncpg://{quote(username, safe='')}:{quote(password, safe='')}@127.0.0.1:{port}/{DATABASE}"
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_REVIEW_CANDIDATE"))}
    env.update(EDUMIND_DATABASE_URL=url, EDUMIND_TEST_DATABASE_URL=url)
    return env


def main() -> None:
    env = test_environment()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend",
                   env=env, check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q", *sys.argv[1:]], cwd=ROOT / "backend",
                   env=env, check=True)


if __name__ == "__main__":
    main()
