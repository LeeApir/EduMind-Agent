"""Freeze a bounded core-only rerun; prior complete performance/quality stay immutable."""

import json

from catalog_acceptance_protocol import ROOT, code_paths, save_new, sha


def main():
    previous = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v4-protocol.json"
    metrics = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v4-result.json"
    plan = json.loads(previous.read_text())
    runtime = {
        name: digest
        for name, digest in plan["code_hashes"].items()
        if name.startswith(("backend/app/", "backend/alembic/", "data/", "web/src/"))
        or name
        in {
            "backend/pyproject.toml",
            "backend/uv.lock",
            "web/package.json",
            "web/pnpm-lock.yaml",
            "web/vite.config.ts",
        }
    }
    assert all(sha(ROOT / name) == digest for name, digest in runtime.items())
    snapshot = ROOT / "docs/acceptance/catalog-metric-executor-v4.py"
    assert sha(snapshot) == plan["code_hashes"]["web/tests/e2e/catalog_acceptance.py"]
    plan.update(
        version=5,
        database="edumind_catalog_core_20261003_v5",
        execution="Core journey only: all10nodes/30resources/30questions +2 real Worker renders; no formal timing rerun.",
        reason="v4 completed20firstscreens/100cachedplays/20freshplays; core stopped at Node APIRequestContext failing to send Secure cookies over HTTP. v5 uses authenticated Chromium fetch; Secure/HttpOnly unchanged. No production code change after v4.",
        metric_component={
            "evidence": str(metrics.relative_to(ROOT)),
            "evidence_sha256": sha(metrics),
            "protocol": str(previous.relative_to(ROOT)),
            "protocol_sha256": sha(previous),
            "runtime_hashes": runtime,
            "executor_snapshot": {
                "path": str(snapshot.relative_to(ROOT)),
                "sha256": sha(snapshot),
            },
        },
    )
    paths = code_paths() + [
        ROOT / s
        for s in (
            "scripts/freeze_catalog_core.py",
            "scripts/run_catalog_core.py",
            "scripts/catalog_component_checks.py",
            "web/tests/e2e/catalog_journey.py",
        )
    ]
    plan["code_hashes"] = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    for p in (ROOT / "docs/acceptance").glob("mvp-0.3-catalog-20261003-*.json"):
        plan["protected_hashes"][str(p.relative_to(ROOT))] = sha(p)
    target = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v5-protocol.json"
    save_new(target, plan)
    print("Frozen core-only protocol", sha(target))


if __name__ == "__main__":
    main()
