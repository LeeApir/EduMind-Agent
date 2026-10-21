"""Prepare/check fixed defect fixtures through MockTransport; never reads keys or sends HTTP."""

# ruff: noqa: E402
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.defect_regression import FAMILIES, VARIANTS, build_case
from acceptance_support.qwen_review_budget import canonical, sha
from app.services.learning_policy import active_policy_digest
from prepare_five_hour_materials import capture_case

BASE = ROOT / "docs/acceptance/phase-1-defect-regression-r01"


async def build():
    result = {}
    index = []
    labels = {}
    for family in FAMILIES:
        for variant in VARIANTS:
            case, label = await build_case(family, variant)
            name = case["id"]
            req = await capture_case(case)
            result[f"cases/{name}.json"] = case
            result[f"requests/{name}.json"] = req
            labels[name] = label
            index.append(
                dict(
                    id=name,
                    family=family,
                    variant=variant,
                    case_sha256=sha(canonical(case)),
                    wire_sha256=req["wire_sha256"],
                )
            )
    result["case-index.json"] = dict(
        cases=index, real_requests_authorized=0, actual_results=None
    )
    result["labels.json"] = dict(
        labels=labels,
        independent_human=False,
        status="authored calibration; do not inject labels into reviewer requests",
    )
    return result


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "check"])
    a = p.parse_args()
    files = await build()
    if a.command == "prepare":
        if any((BASE / name).exists() for name in files):
            raise ValueError("NO_MATERIAL_OVERWRITE")
        for name, v in files.items():
            path = BASE / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
    else:
        manifest_path = BASE / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest["policy_digest"] != active_policy_digest():
                raise ValueError("POLICY_CHANGED")
            for name, expected in manifest["files"].items():
                path = ROOT / name
                if (
                    path.is_symlink()
                    or not path.resolve().is_relative_to(ROOT)
                    or sha(path.read_bytes()) != expected
                ):
                    raise ValueError("FREEZE_CHANGED:" + name)
        for name, v in files.items():
            if json.loads((BASE / name).read_text()) != v:
                raise ValueError("MATERIAL_OR_CURRENT_REQUEST_CHANGED:" + name)
    print(json.dumps(dict(cases=12, families=4, provider_calls=0, mode=a.command)))


if __name__ == "__main__":
    asyncio.run(main())
