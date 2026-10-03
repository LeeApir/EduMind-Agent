"""Execute only the frozen local core journey; no .env or Provider credentials."""

import json
import subprocess
import sys

from catalog_acceptance_protocol import ROOT, sha
from run_catalog_db_tests import test_environment


def main():
    protocol = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v5-protocol.json"
    output = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v5-core.json"
    assert not output.exists()
    plan = json.loads(protocol.read_text())
    assert plan["provider_requests_authorized"] == 0
    for name, digest in plan["code_hashes"].items():
        assert sha(ROOT / name) == digest, "Frozen code changed: " + name
    env = test_environment(plan["database"])
    env.update(
        EDUMIND_PRODUCT_MODE="catalog_only",
        EDUMIND_CATALOG_PROTOCOL=str(protocol),
        EDUMIND_CATALOG_RESULT=str(output),
        EDUMIND_CATALOG_QUALITY_CACHE="/private/tmp/edumind-catalog-quality-20261003-v2",
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )
    subprocess.run(
        [sys.executable, "web/tests/e2e/catalog_journey.py"],
        cwd=ROOT,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
