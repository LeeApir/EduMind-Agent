"""Read-only holdout partition/hash guard; never loads a model or grades semantics."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from acceptance_support.qwen_review_budget import canonical, sha  # noqa:E402

BASE = ROOT / "docs/acceptance/phase-1-holdout-reserve-r01"


def check_partition(reserved, development):
    ids = [c["id"] for c in reserved]
    goals = [c["original_request"] for c in reserved]
    old_ids = {c["id"] for c in development}
    old_goals = {c["original_request"] for c in development}
    if len(ids) != len(set(ids)) or len(goals) != len(set(goals)):
        raise ValueError("DUPLICATE_HOLDOUT")
    if old_ids.intersection(ids) or old_goals.intersection(goals):
        raise ValueError("DEVELOPMENT_MATERIAL_CANNOT_BE_HOLDOUT")
    for c in reserved:
        if (
            c["partition"] != "reserved_holdout"
            or c["not_for_prompt_tuning"] is not True
            or c["generated_material"] is not None
            or c["actual_model_result"] is not None
            or c["reviewer_model_result"] is not None
        ):
            raise ValueError("RESERVATION_NOT_AN_OBSERVATION")


def check():
    def read(p):
        return json.loads(p.read_text())

    manifest = read(BASE / "manifest.json")
    for name, digest in manifest["files"].items():
        p = ROOT / name
        if (
            p.is_symlink()
            or not p.resolve().is_relative_to(ROOT)
            or sha(p.read_bytes()) != digest
        ):
            raise ValueError("RESERVE_CHANGED:" + name)
    index = read(BASE / "index.json")
    registry = read(BASE / "partition-registry.json")
    reserved = []
    development = []
    if (
        index["released_for_acceptance"]
        or index["independent_human_signoff"] is not None
    ):
        raise ValueError("RESERVATION_NOT_YET_SIGNED")
    for e in index["entries"]:
        c = read(BASE / e["input"])
        label = read(BASE / e["prelabel"])
        if (
            sha(canonical(c)) != e["input_sha256"]
            or sha(canonical(label)) != e["prelabel_sha256"]
            or c["id"] != e["id"]
            or label["id"] != e["id"]
        ):
            raise ValueError("BINDING_CHANGED")
        if (
            label["human_signoff"] is not None
            or label["status"] != "pending_independent_human_check"
        ):
            raise ValueError("DO_NOT_PRETEND_HUMAN_SIGNOFF")
        reserved.append(c)
    for entry in registry["development"]:
        directory = ROOT / entry["root"]
        directory = directory / (
            "cases" if (directory / "cases").exists() else "inputs"
        )
        for p in directory.glob("*.json"):
            c = read(p)
            goal = c.get(
                "original_request",
                c.get("input_snapshot", {}).get("metadata", {}).get("goal"),
            )
            development.append(dict(id=c["id"], original_request=goal))
    check_partition(reserved, development)
    if len(reserved) != 8 or set(registry["reserved"]["ids"]) != {
        c["id"] for c in reserved
    }:
        raise ValueError("RESERVATION_SET_CHANGED")
    return dict(
        reserved=8,
        developer_inputs_checked=len(development),
        human_signoff="pending; Lee assigned only",
        provider_calls=0,
        material_root=sha(canonical(manifest)),
    )


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False))
