"""Prepare/check an offline frozen combination; this CLI cannot run paid acceptance."""

import argparse
import json
from acceptance_support.om_benchmarks import benchmark_materials
from acceptance_support.om_preparation import (
    BASE,
    preparation,
    generation_metrics,
    audit_metrics,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.run:
        print(
            json.dumps(
                {
                    "code": "NOT_AUTHORIZED",
                    "provider_requests": 0,
                    "reason": "Offline preparation only; exact new run, human labels and paid budget not approved.",
                }
            )
        )
        return 2
    value = preparation()
    materials, labels = benchmark_materials()
    path = BASE / "frozen-combination.json"
    if args.check:
        if (
            json.loads((BASE / "benchmark-materials.json").read_text()) != materials
            or json.loads((BASE / "proposed-labels.json").read_text()) != labels
        ):
            raise SystemExit("BENCHMARK_FREEZE_CHANGED")
        if json.loads(path.read_text()) != value:
            raise SystemExit("FREEZE_CHANGED")
    else:
        BASE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        (BASE / "benchmark-materials.json").write_text(
            json.dumps(materials, ensure_ascii=False, indent=2) + "\n"
        )
        (BASE / "proposed-labels.json").write_text(
            json.dumps(labels, ensure_ascii=False, indent=2) + "\n"
        )
        report = {
            "status": "NOT_RUN",
            "generation": generation_metrics([], [t["id"] for t in value["targets"]]),
            "audits": {k: audit_metrics(k, []) for k in ("severe", "correct", "long")},
            "T040": "blocked",
            "provider_requests": 0,
            "human_decisions": 0,
        }
        (BASE / "not-run-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
    print(
        json.dumps(
            {
                "status": value["status"],
                "root_sha256": value["root_sha256"],
                "sources": len(value["sources"]),
                "targets": 100,
                "severe": 20,
                "correct": 20,
                "long": 10,
                "offline_scenarios": 20,
                "provider_requests": 0,
                "fees_authorized": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
