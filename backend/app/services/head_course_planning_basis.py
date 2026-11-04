"""Program facts for T108's two fixed examples; no planner, C execution or prose fallback."""

from typing import Any

from app.services import head_course_materials as m
from app.services.free_course_snapshots import SnapshotError, digest
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_example

VERSION = "head-planning-example-basis-v1"


def _calls(example: dict[str, Any]) -> list[dict[str, Any]]:
    steps = example["trace"]["steps"]
    before = steps[0]["caller_head"]
    lines = example["code"]["source"].splitlines()
    result = []
    for i in range(len(example["spec"]["insert_values"])):
        link, returned, caller = (
            next(s for s in steps if s["attempt"] == i and s["phase"] == phase)
            for phase in ("link", "return", "caller")
        )
        row = dict(
            attempt=i,
            statement=lines[example["code"]["line_anchors"][f"call_{i}"] - 1].strip(),
            caller_before=before,
            local_head_at_link=link["local_head"],
            p=link["p"],
            p_next=link["nodes"][link["p"]]["next"],
            local_head_at_return=returned["local_head"],
            returned=returned["returned"],
            caller_after=caller["caller_head"],
        )
        receives = example["spec"]["variant"] == "normal"
        if not (
            row["local_head_at_link"] == row["p_next"] == row["local_head_at_return"] == before
            and row["returned"] == row["p"]
            and row["caller_after"] == (row["p"] if receives else before)
        ):
            raise SnapshotError("HEAD_PLANNING_BASIS_MISMATCH")
        result.append(row)
        before = row["caller_after"]
    return result


def _example(key: str) -> dict[str, Any]:
    mat = m.materials_for_example(key)
    example = mat["catalog"]["example"]
    ignored = build_example(dict(m.SPECS[key], variant="discard_return"))
    code = example["code"]
    lines = code["source"].splitlines()
    end = lines.index("}")
    function = lines[2 : end + 1]
    # Capacity check for this exact existing template, not a parser for arbitrary C.
    if function != [
        "Node *insert(Node *head, int value, int allocation_success) {",
        "    Node *p = allocation_success ? malloc(sizeof *p) : NULL;",
        "    if (p == NULL) return head;",
        "    p->data = value;",
        "    p->next = head;",
        "    return p;",
        "}",
    ]:
        raise SnapshotError("HEAD_PLANNING_BASIS_MISMATCH")
    expected = list(reversed(m.SPECS[key]["insert_values"])) + m.SPECS[key]["initial_values"]
    # Closed-form expectations independent of the engine's computed observation.
    if not (
        example["observation"]["reachable_prefix"] == expected
        and ignored["observation"]["caller_head"] == "i0"
        and ignored["observation"]["reachable_prefix"] == m.SPECS[key]["initial_values"]
        and ignored["observation"]["unreachable_allocated_ids"] == ["t0", "t1"]
        and example["observation"]["unreachable_allocated_ids"] == []
    ):
        raise SnapshotError("HEAD_PLANNING_BASIS_MISMATCH")
    caller_decl = next(line.strip() for line in lines if "Node *caller_head = " in line)
    initial_decl = next(line.strip() for line in lines if line.strip() == "Node i0;")
    initial = m.SPECS[key]["initial_values"]
    if len(initial) != 1 or lines[end + 1 :] != [
        "int main(void) {",
        "    Node i0;",
        f"    i0.data = {initial[0]};",
        "    i0.next = NULL;",
        "    Node *caller_head = &i0;",
        *[
            f"    caller_head = insert(caller_head, {value}, 1);"
            for value in m.SPECS[key]["insert_values"]
        ],
        "    (void)caller_head;",
        "    return 0;",
        "}",
    ]:
        raise SnapshotError("HEAD_PLANNING_BASIS_MISMATCH")
    ignored_lines = list(lines)
    for i in range(len(m.SPECS[key]["insert_values"])):
        line = code["line_anchors"][f"call_{i}"] - 1
        ignored_lines[line] = ignored_lines[line].replace("caller_head = insert(", "insert(")
    if ignored["code"]["source"] != "\n".join(ignored_lines) + "\n":
        raise SnapshotError("HEAD_PLANNING_BASIS_MISMATCH")
    data = dict(
        example_id=key,
        engine_version=example["engine_version"],
        template_version=example["template_version"],
        spec_digest=example["spec_digest"],
        example_digest=example["payload_digest"],
        materials_digest=mat["materials_digest"],
        code_digest=digest("head-planning-code", source=code["source"]),
        function_interface=function[0].removesuffix(" {"),
        function_code="\n".join(function),
        variable_scopes=[
            dict(
                name="head",
                scope="insert.parameter",
                declaration="Node *head",
                trace_field="local_head",
                passing="pointer_value_copy",
                active_after_return=False,
            ),
            dict(
                name="value",
                scope="insert.parameter",
                declaration="int value",
                active_after_return=False,
            ),
            dict(
                name="allocation_success",
                scope="insert.parameter",
                declaration="int allocation_success",
                active_after_return=False,
            ),
            dict(
                name="p",
                scope="insert.local",
                declaration=function[1].strip(),
                points_to_storage="dynamic_on_success",
                active_after_return=False,
            ),
            dict(name="caller_head", scope="main.local", declaration=caller_decl),
            dict(name="i0", scope="main.local", declaration=initial_decl, storage="automatic"),
        ],
        key_code=[
            dict(
                anchor=a,
                line=code["line_anchors"][a],
                statement=lines[code["line_anchors"][a] - 1].strip(),
            )
            for a in ("allocate", "allocation_failed", "data", "link", "return")
        ],
        receive_return=dict(calls=_calls(example), observation=example["observation"]),
        ignore_return=dict(
            calls=_calls(ignored),
            observation=ignored["observation"],
            example_digest=ignored["payload_digest"],
        ),
        assumptions=dict(
            allocation_success=m.SPECS[key]["allocation_success"],
            actual_malloc_assumed_success=True,
            actual_malloc_failure_animated=False,
            c_executed=False,
            cleanup_animated=False,
        ),
    )
    return dict(**data, example_basis_digest=digest("head-planning-example-basis", data=data))


def build_basis() -> dict[str, Any]:
    data = dict(version=VERSION, examples={key: _example(key) for key in m.SPECS})
    return dict(**data, basis_digest=digest("head-planning-basis", data=data))


def selected_basis(materials: dict[str, Any]) -> dict[str, Any]:
    basis = build_basis()
    evidence = basis["examples"][materials["selected_example"]]
    if evidence["materials_digest"] != materials["materials_digest"] or evidence[
        "code_digest"
    ] != digest("head-planning-code", source=materials["catalog"]["example"]["code"]["source"]):
        raise SnapshotError("HEAD_PLANNING_BASIS_MISMATCH")
    return dict(
        binding=dict(
            version=VERSION,
            basis_digest=basis["basis_digest"],
            selected_example=evidence["example_id"],
            example_basis_digest=evidence["example_basis_digest"],
            materials_digest=materials["materials_digest"],
        ),
        evidence=evidence,
    )
