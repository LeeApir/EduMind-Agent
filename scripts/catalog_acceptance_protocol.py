"""Offline freeze and deterministic metrics for the independent catalog run."""

import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEM = "mvp-0.3-catalog-20261003-v4"
PROTOCOL = ROOT / "docs/acceptance" / (STEM + "-protocol.json")
RESULT = ROOT / "docs/acceptance" / (STEM + "-result.json")
QUALITY = ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v2-quality.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def p95(rows: list[dict], key: str, denominator: int) -> float | str:
    if len(rows) > denominator or denominator < 1:
        raise ValueError("Invalid fixed denominator")
    values = [
        float(row[key]) if row.get("ok") is True and key in row else math.inf
        for row in rows
    ] + [math.inf] * (denominator - len(rows))
    values = [v if math.isfinite(v) and v >= 0 else math.inf for v in values]
    value = sorted(values)[math.ceil(0.95 * denominator) - 1]
    return "+inf" if not math.isfinite(value) else value


def save_new(path: Path, value: dict) -> None:
    with path.open("x") as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def code_paths() -> list[Path]:
    paths = []
    for directory in (
        "backend/app",
        "backend/alembic",
        "web/src",
        "data/course_catalog/linear-v1",
        "data/animation_templates",
    ):
        paths += [
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        ]
    paths += [
        ROOT / s
        for s in (
            "scripts/catalog_acceptance_protocol.py",
            "scripts/run_catalog_acceptance.py",
            "scripts/run_catalog_db_tests.py",
            "scripts/verify_catalog_acceptance.py",
            "web/tests/e2e/catalog_acceptance.py",
            "backend/tests/run_mvp03_animation_quality.py",
            "backend/tests/catalog_fixtures.py",
            "web/tests/e2e/animation_benchmark.py",
            "backend/pyproject.toml",
            "backend/uv.lock",
            "web/package.json",
            "web/pnpm-lock.yaml",
            "web/vite.config.ts",
            "data/knowledge_graph.yaml",
        )
    ]
    return sorted(set(paths))


def freeze() -> None:
    old = json.loads(
        (ROOT / "docs/acceptance/mvp-0.3-t032-frozen-slots.json").read_text()
    )
    nodes = list(
        json.loads((ROOT / "data/course_catalog/linear-v1/manifest.json").read_text())[
            "nodes"
        ]
    )
    protected = sorted((ROOT / "docs/acceptance").glob("*t033*"))
    protected += sorted(
        (ROOT / "docs/acceptance").glob("mvp-0.3-catalog-20261003-*.json")
    )
    protected += [ROOT / ".env"] if (ROOT / ".env").exists() else []
    quality_protocol = (
        ROOT / "docs/acceptance/mvp-0.3-catalog-20261003-v2-protocol.json"
    )
    old_quality = json.loads(quality_protocol.read_text())
    quality_hashes = {
        name: digest
        for name, digest in old_quality["code_hashes"].items()
        if name.startswith(("backend/app/", "backend/alembic/", "data/"))
        or name
        in {
            "backend/pyproject.toml",
            "backend/uv.lock",
            "backend/tests/run_mvp03_animation_quality.py",
            "backend/tests/catalog_fixtures.py",
        }
    }
    assert all(sha(ROOT / name) == digest for name, digest in quality_hashes.items())
    plan = {
        "version": 4,
        "previous_attempt": "v1 quality92/100 retained; v2 quality100/100 retained, browser initial navigation blocked by unread401body (0 formal slots). v3 fixed frontend bodies; queue selector ambiguity failed2/20, stopped after18 cache slots, fresh20 unattempted. v4 exact node label only, same frontend/backend/template/quality runtime.",
        "quality_component": {
            "evidence": str(QUALITY.relative_to(ROOT)),
            "evidence_sha256": sha(QUALITY),
            "protocol": str(quality_protocol.relative_to(ROOT)),
            "protocol_sha256": sha(quality_protocol),
            "runtime_hashes": quality_hashes,
            "reuse_basis": "Independent T045 quality component remains100/100; unchanged backend/content/template/quality runtime verified before browser execution. No new quality claims or blending with T033.",
        },
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scope": "Catalog engineering acceptance only; TEST_ONLY approval, no human release",
        "provider_requests_authorized": 0,
        "provider_cumulative_unchanged": "2033/2500",
        "database": "edumind_catalog_accept_20261003_v4",
        "product_mode": "catalog_only",
        "content_digest": "92bb0dd4778391e23aae978b8a411b466d8b5988d1cff61cff01654604af21a1",
        "code_hashes": {str(p.relative_to(ROOT)): sha(p) for p in code_paths()},
        "protected_hashes": {
            str(p.relative_to(ROOT)): sha(p) for p in protected if p.is_file()
        },
        "first_screen_slots": [
            {"id": node + "-" + mode, "node_id": node, "mode": mode}
            for node in nodes
            for mode in ("cold", "warm")
        ],
        "first_screen_definition": {
            "cold": "New browser context/owner; no enrollment or browser HTTP cache; timer starts navigation, selects node immediately when ready; API/DB processes remain warm.",
            "warm": "Same owner/unit/tab, page reload, browser HTTP cache still disabled; timer starts reload.",
            "dom": "Navigation to exact full candidate explanation visible after two animation frames; includes catalog/JS/auth/enrollment, no human think time.",
            "http": "Sum requestStart..responseEnd for required auth/session, guest, catalog, catalog/sessions, and GET learning-unit responses completed before readable DOM; includes proxy. Runtime/demo/classroom/path are auxiliary and excluded.",
            "failure": "Every failed/missing slot is +inf in fixed denominator 20; nearest-rank P95.",
            "thresholds": {"http_p95_seconds": 2, "dom_p95_seconds": 10},
        },
        "quality_slots": old["quality_slots"],
        "cache_browser_slots": old["cache_browser_slots"],
        "render_browser_slots": old["render_browser_slots"],
        "animation_definition": "Independent new cache, 100 matrix slots (20 unique real renders +80 validated cache repeats); 100 cached browser plays; 20 renders each new cache. Click to loadeddata AND playing, owner curated binding, HTTP cache disabled, one concurrent render. Failure/missing +inf, availability fixed denominator100.",
        "animation_thresholds": {
            "availability": 0.98,
            "cache_p95_seconds": 2,
            "cache_each_seconds": 2,
            "render_p95_seconds": 90,
        },
        "journey": [
            "10nodes/30resources/30questions exact content and answers hidden",
            "real quiz feedback/mastery/path/repeat no new mastery",
            "preset begin/reload/exit and return tab",
            "notes wrong questions/manual provenance",
            "two real Worker bindings/video/MP4/SRT downloads/reload",
            "cross owner/CSRF/dynamic409/revocation",
            "backend and browser external network attempts zero",
        ],
        "limits": "Local fixed media/CPU only, no Provider/key, no retries or automatic paid stages; no production publish/deploy; preserve all failures and old evidence.",
    }
    save_new(PROTOCOL, plan)
    print("Frozen:", PROTOCOL.name, sha(PROTOCOL))


if __name__ == "__main__":
    freeze()
