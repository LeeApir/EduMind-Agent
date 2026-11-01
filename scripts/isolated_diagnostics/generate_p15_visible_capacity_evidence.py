"""Bounded development stress cases for the proposed full Responses body.

No model, Provider, credentials, selected experiment sample, or scoring is used.
"""

from copy import deepcopy
from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as old
from scripts.isolated_diagnostics import p15_teaching_pilot as teaching
from scripts.isolated_diagnostics import p15_visible_request_budget_v1 as budget
from scripts.isolated_diagnostics import p15_visible_worker_v1 as worker
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.tests.test_p15_minimal_pilot import b_fixture, content
from scripts.tests.test_p15_teaching_capacity_t102 import SPEC

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = (
    ROOT / "docs/acceptance/phase-1.5-visible-migration-t102/capacity-evidence.json"
)
POLICY = budget.DevelopmentPolicy(12_000_000, 13_000_000, 8000)


def payload(arm: str, scenario: str) -> dict:
    value = b_fixture(SPEC) if arm == "B" else content()
    text = (
        "[x](u)" * 666
        if scenario == "dense"
        else "[x](u)" * 500 + '\x00"\\\n' * 150
        if scenario == "escaping"
        else "[x](u)" * 8
    )
    template = deepcopy(value["paragraphs"][0])
    value["paragraphs"] = [dict(template, key=f"p{i}", text=text) for i in range(8)]
    for question in value["questions"].values():
        question["stem"] = text
        question["explanation"] = text
    if arm == "B" and scenario != "escaping":
        # Deliberately non-teaching data at the allowed character/line boundary.
        value["code"] = "\n" * 20000
    if scenario == "max_actions":
        assert arm == "B"
        ids = ["i0", "i1", "i2", "t0", "t1", "t2", "t3"]
        nodes = [
            dict(id=name, data_status="known", data=i, next="none")
            for i, name in enumerate(ids)
        ]
        states = [
            dict(
                order=i,
                step=i,
                caller_head="none",
                local_head="none",
                p="none",
                nodes=deepcopy(nodes),
            )
            for i in range(64)
        ]
        highlights = [dict(order=64 + i, step=i, line=1) for i in range(58)]
        advances = [dict(order=122 + i, step=i) for i in range(58)]
        value["actions"] = dict(states=states, highlights=highlights, advances=advances)
    return value


def measure(stage: str, value: dict) -> dict:
    _, observation = budget.build(stage, value, POLICY)
    return observation


def main() -> None:
    catalog = c.make_catalog(SPEC)
    common = old.baseline_input(SPEC)
    output = {
        "scope": "offline adversarial structural examples; not teaching quality, formal sample, complete-domain proof or an authorized budget",
        "policy": dict(
            request_bytes=POLICY.request_bytes,
            input_reservation=POLICY.input_reservation,
            output_reservation=POLICY.output_reservation,
            allowance=POLICY.allowance,
        ),
        "real_provider_calls": 0,
        "scenarios": {},
    }
    cases = [
        ("dense", "B"),
        ("dense", "C"),
        ("escaping", "B"),
        ("escaping", "C"),
        ("max_actions", "B"),
    ]
    for scenario, arm in cases:
        value = payload(arm, scenario)
        c.validate(
            "B_generate" if arm == "B" else "C_content",
            value,
            catalog=catalog if arm == "C" else None,
        )
        plan_input = teaching.plan_input(SPEC, catalog)
        plan = dict(spec_id=catalog["spec_id"], objective_ids=list(c.GOALS))
        initial = (
            common if arm == "B" else teaching.content_input(common, catalog, plan)
        )
        stages = []
        if arm == "C":
            stages.append(measure("C_plan", plan_input))
        stages.append(measure("B_generate" if arm == "B" else "C_content", initial))
        identity = c.identity("dev", "slot", arm, 0, SPEC, None)
        first = worker.expand(value, identity, catalog)
        stages.append(measure("review_" + arm, first["view"]))
        cell = next(
            cell for cell in first["view"]["cells"] if cell["kind"] == "paragraph"
        )
        opinion = dict(
            candidate_id=first["view"]["candidate_id"],
            verdict="revise",
            uncertainty="",
            issues=[
                dict(
                    severity="minor",
                    area="difficulty",
                    target_id=cell["id"],
                    evidence_quote="[x]",
                    reason="补充说明。",
                )
            ],
        )
        worker.validate_review(
            opinion,
            canonical(first["view"]),
            first["artifact"],
            catalog,
            first["binding"],
        )
        stages.append(
            measure(
                arm + "_repair",
                teaching.repair_input(initial, first["artifact"], opinion),
            )
        )
        updated = deepcopy(value)
        for paragraph in updated["paragraphs"]:
            paragraph["text"] += "修订"
        for question in updated["questions"].values():
            question["stem"] += "修订"
            question["explanation"] += "修订"
        second = worker.expand(
            updated,
            c.identity(
                "dev", "slot", arm, 1, SPEC, first["artifact"]["artifact_digest"]
            ),
            catalog,
        )
        stages.append(measure("review_" + arm, second["view"]))
        output["scenarios"][scenario + "_" + arm] = {
            "arm": arm,
            "case": scenario,
            "original_payload_bytes": len(canonical(value)),
            "revised_payload_bytes": len(canonical(updated)),
            "visible_cells": len(first["view"]["cells"]),
            "visible_states": sum(
                cell["kind"] == "state" for cell in first["view"]["cells"]
            ),
            "visible_actions": sum(
                cell["kind"] == "action" for cell in first["view"]["cells"]
            ),
            "reference_occurrences": sum(
                len(row["occurrences"])
                for row in first["artifact"]["source"]["documents"][
                    "documents"
                ].values()
            ),
            "stages": stages,
            "sum_local_input_reservations": sum(
                stage["local_input_reservation"] for stage in stages
            ),
            "sum_local_output_reservations": sum(
                stage["local_output_reservation"] for stage in stages
            ),
        }
        print(
            scenario,
            arm,
            [(stage["stage"], stage["body_bytes"]) for stage in stages],
            flush=True,
        )
    OUTPUT.write_bytes(canonical(output) + b"\n")


if __name__ == "__main__":
    main()
