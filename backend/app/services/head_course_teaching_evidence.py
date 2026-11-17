"""Versioned evidence supplement: displayed frames and a separately computed comparison.

The original material catalog, candidate and planning basis are never modified.
This module derives facts; it neither generates teaching text nor authorizes publication.
"""

from copy import deepcopy
from typing import Any

from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, canonical, digest
from app.services.head_course_planning_basis import selected_basis
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example

VERSION = "head-teaching-evidence-v1"
DISPLAYED = "head_evidence_v1.displayed_success_path"
DISCARDED = "head_evidence_v1.discard_return_comparison"
INSTRUCTION = """[EVIDENCE head-teaching-evidence-v1]
The program-owned teaching_evidence supplement separates displayed_trace facts from a
computed_counterfactual. Only frames listed under displayed_success_path were shown in the
main player. Both allocation attempts succeed; both NULL conditions execute and are false,
so insertion continues. Neither the mask-disabled no-allocation path nor actual malloc
failure is shown. The discard-return comparison is computed separately, not animated in
those main frames. Cite its exact ID for claims about unchanged caller entry and unreachable
new nodes. Do not describe a static code capability or computed comparison as a displayed
branch. These are simulated program materials, not execution of C or a semantic review pass.
"""


def build(payload: dict[str, Any]) -> dict[str, Any]:
    mat = payload["materials"]
    if canonical(mat) != canonical(m.materials_for_example(mat["selected_example"])) or canonical(
        payload["planning_basis"]
    ) != canonical(selected_basis(mat)):
        raise SnapshotError("HEAD_TEACHING_EVIDENCE_SOURCE")
    example = mat["catalog"]["example"]
    frames, states = mat["frames"], example["trace"]["steps"]
    allocations, checks = [], []
    for i, frame in enumerate(frames):
        state = states[frame["state_index"]]
        if frame["kind"] == "allocate":
            if state["p"] is None:
                raise SnapshotError("HEAD_TEACHING_EVIDENCE_SCOPE")
            allocations.append(
                dict(
                    frame_id=frame["frame_id"],
                    state_index=frame["state_index"],
                    attempt=state["attempt"],
                    allocated_node=state["p"],
                    success=True,
                    code_line=frame["line"],
                )
            )
        if frame["kind"] == "success_null_check":
            after = frames[i + 1]
            if state["p"] is None or after["kind"] != "data":
                raise SnapshotError("HEAD_TEACHING_EVIDENCE_SCOPE")
            checks.append(
                dict(
                    frame_id=frame["frame_id"],
                    state_index=frame["state_index"],
                    attempt=state["attempt"],
                    p=state["p"],
                    code_line=frame["line"],
                    condition="p == NULL",
                    condition_evaluated=True,
                    condition_result=False,
                    early_return_taken=False,
                    continues_to_frame=after["frame_id"],
                )
            )
    attempts = len(example["spec"]["insert_values"])
    no_allocation = [f["frame_id"] for f in frames if f["kind"] == "allocation_failed"]
    if len(allocations) != attempts or len(checks) != attempts or no_allocation:
        raise SnapshotError("HEAD_TEACHING_EVIDENCE_SCOPE")

    # Independent closed-form oracle: discarding both returns preserves the caller entry.
    # The existing finite engine computes a distinct trace; it is not a displayed main trace.
    contrast = build_example(dict(example["spec"], variant="discard_return"))
    initial = example["spec"]["initial_values"]
    initial_head = "i0" if initial else None
    expected_ids = [f"t{i}" for i in range(attempts)]
    observation = contrast["observation"]
    basis = payload["planning_basis"]["evidence"]["ignore_return"]
    if (
        observation["reachable_prefix"] != initial
        or observation["caller_head"] != initial_head
        or observation["unreachable_allocated_ids"] != expected_ids
        or observation["allocation_failures"] != 0
        or observation["traversal_status"] != "terminated"
        or basis["observation"] != observation
        or basis["example_digest"] != contrast["payload_digest"]
    ):
        raise SnapshotError("HEAD_TEACHING_EVIDENCE_COMPARISON")
    data = dict(
        version=VERSION,
        source=dict(
            materials_digest=mat["materials_digest"],
            example_digest=example["payload_digest"],
            spec_digest=example["spec_digest"],
            engine_version=example["engine_version"],
            template_version=example["template_version"],
            planning_basis_binding=deepcopy(payload["planning_basis"]["binding"]),
            frames_digest=digest("head-displayed-frames", frames=frames),
        ),
        facts={
            DISPLAYED: dict(
                origin="program_derived",
                evidence_kind="displayed_trace",
                displayed_in_main_player=True,
                c_executed=False,
                source_paths=[
                    "materials.frames",
                    "materials.catalog.example.trace.steps",
                    "materials.catalog.example.code",
                ],
                value=dict(
                    frame_ids=[f["frame_id"] for f in frames],
                    allocation_success_count=len(allocations),
                    allocation_events=allocations,
                    null_condition_evaluations=checks,
                    no_allocation_frame_ids=no_allocation,
                    mask_disabled_path_displayed=False,
                    actual_malloc_failure_displayed=False,
                    null_checks_are_program_projected=True,
                ),
            ),
            DISCARDED: dict(
                origin="program_derived",
                evidence_kind="computed_counterfactual",
                displayed_in_main_player=False,
                main_frame_ids=[],
                c_executed=False,
                source_paths=[
                    "materials.catalog.example.spec",
                    "planning_basis.evidence.ignore_return",
                ],
                source_spec=deepcopy(contrast["spec"]),
                source_example_digest=contrast["payload_digest"],
                source_code=contrast["code"]["source"],
                value=dict(calls=deepcopy(basis["calls"]), observation=deepcopy(observation)),
                independent_reference=dict(
                    method="unchanged_caller_entry_nonempty_head_insertion_closed_form"
                    if initial
                    else "unchanged_null_caller_entry_closed_form",
                    expected_caller_head=initial_head,
                    expected_reachable_values=deepcopy(initial),
                    expected_unreachable_allocated_ids=expected_ids,
                ),
            ),
        },
    )
    return dict(**data, evidence_digest=digest("head-teaching-evidence", data=data))


def validate(payload: dict[str, Any], bundle: dict[str, Any]) -> None:
    if canonical(bundle) != canonical(build(payload)):
        raise SnapshotError("HEAD_TEACHING_EVIDENCE_BINDING")


def with_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    if "teaching_evidence" in result:
        validate(result, result["teaching_evidence"])
    else:
        result["teaching_evidence"] = build(result)
    return result
