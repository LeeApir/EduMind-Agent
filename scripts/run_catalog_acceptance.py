"""Run only frozen local catalog acceptance without loading .env or provider keys."""

import json
import subprocess
import sys
from pathlib import Path

from catalog_acceptance_protocol import PROTOCOL, QUALITY, RESULT, ROOT, sha
from run_catalog_db_tests import test_environment


def main() -> None:
    plan = json.loads(PROTOCOL.read_text())
    assert plan["provider_requests_authorized"] == 0
    for name, digest in plan["code_hashes"].items():
        assert sha(ROOT / name) == digest, "Frozen code changed: " + name
    assert not RESULT.exists(), "Existing evidence must not be overwritten"
    env = test_environment(plan["database"])
    env["EDUMIND_PRODUCT_MODE"] = "catalog_only"
    env["EDUMIND_CATALOG_PROTOCOL"] = str(PROTOCOL)
    env["EDUMIND_CATALOG_RESULT"] = str(RESULT)
    env["EDUMIND_CATALOG_QUALITY_CACHE"] = (
        "/private/tmp/edumind-catalog-quality-20261003-v2"
    )
    env["EDUMIND_CATALOG_FRESH_ROOT"] = "/private/tmp/edumind-catalog-fresh-20261003-v4"
    assert Path(env["EDUMIND_CATALOG_QUALITY_CACHE"]).exists()
    assert not Path(env["EDUMIND_CATALOG_FRESH_ROOT"]).exists()
    # No dotenv loader, no provider environment; separate test DB, not the development volume.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )
    component = plan["quality_component"]
    assert sha(QUALITY) == component["evidence_sha256"]
    for name, digest in component["runtime_hashes"].items():
        assert sha(ROOT / name) == digest, "Quality runtime changed"
    quality = json.loads(QUALITY.read_text())
    if quality["summary"]["availability"] < 0.98:
        raise RuntimeError("Quality gate failed; browser batches remain unattempted")
    subprocess.run(
        [sys.executable, "web/tests/e2e/catalog_acceptance.py"],
        cwd=ROOT,
        env=env,
        check=True,
    )


if __name__ == "__main__":
    main()
