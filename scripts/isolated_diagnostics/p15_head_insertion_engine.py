"""ADR0041 isolated finite-template semantics. Never compiles or executes C."""

from copy import deepcopy
import hashlib
import json
from typing import Any

ENGINE_VERSION = "head-insertion-engine-v1"
TEMPLATE_VERSION = "head-insertion-c-v1"
SPEC_VERSION = "head-insertion-spec-v1"
VARIANTS = ("normal", "reversed_assignment", "discard_return", "uninitialized_next")
QUESTION_KEYS = (
    "caller_head",
    "traversal_status",
    "reachable_prefix",
    "allocation_failures",
)
INDETERMINATE = "indeterminate"


class SpecError(ValueError):
    """Stable bounded refusal; no provider or file operations."""


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_spec(value: Any) -> dict[str, Any]:
    keys = {
        "version",
        "initial_values",
        "insert_values",
        "variant",
        "allocation_success",
    }
    if type(value) is not dict or set(value) != keys:
        raise SpecError("SPEC_KEYS")
    if value["version"] != SPEC_VERSION or value["variant"] not in VARIANTS:
        raise SpecError("SPEC_VERSION_OR_VARIANT")
    for key, minimum, maximum in (("initial_values", 0, 3), ("insert_values", 1, 4)):
        values = value[key]
        if (
            type(values) is not list
            or not minimum <= len(values) <= maximum
            or any(type(v) is not int or not -99 <= v <= 99 for v in values)
        ):
            raise SpecError("SPEC_VALUES")
    mask = value["allocation_success"]
    if (
        type(mask) is not list
        or len(mask) != len(value["insert_values"])
        or any(type(v) is not bool for v in mask)
    ):
        raise SpecError("SPEC_ALLOCATION_MASK")
    return deepcopy(value)


def render_code(spec: dict[str, Any]) -> dict[str, Any]:
    """Render only fixed template statements; inputs are validated integers/bools."""
    spec = validate_spec(spec)
    lines = [
        "#include <stdlib.h>",
        "typedef struct Node { int data; struct Node *next; } Node;",
        "Node *insert(Node *head, int value, int allocation_success) {",
        "    Node *p = allocation_success ? malloc(sizeof *p) : NULL;",
        "    if (p == NULL) return head;",
        "    p->data = value;",
    ]
    anchors = {"allocate": 4, "allocation_failed": 5, "data": 6}
    if spec["variant"] == "reversed_assignment":
        lines.append("    head = p;")
        anchors["local_head"] = len(lines)
    if spec["variant"] != "uninitialized_next":
        lines.append("    p->next = head;")
        anchors["link"] = len(lines)
    lines.extend(["    return p;", "}", "int main(void) {"])
    anchors["return"] = len(lines) - 2
    for i in range(len(spec["initial_values"])):
        lines.append(f"    Node i{i};")
    for i, value in enumerate(spec["initial_values"]):
        nxt = f"&i{i + 1}" if i + 1 < len(spec["initial_values"]) else "NULL"
        lines.extend([f"    i{i}.data = {value};", f"    i{i}.next = {nxt};"])
    lines.append(
        "    Node *caller_head = " + ("&i0;" if spec["initial_values"] else "NULL;")
    )
    for i, (value, success) in enumerate(
        zip(spec["insert_values"], spec["allocation_success"])
    ):
        prefix = "" if spec["variant"] == "discard_return" else "caller_head = "
        lines.append(f"    {prefix}insert(caller_head, {value}, {int(success)});")
        anchors[f"call_{i}"] = len(lines)
    lines.extend(["    (void)caller_head;", "    return 0;", "}"])
    return {
        "version": TEMPLATE_VERSION,
        "language": "C",
        "source": "\n".join(lines) + "\n",
        "line_anchors": anchors,
        "executed": False,
        "limitations": "Abstract allocation mask; no arbitrary C or memory-safety proof.",
    }


def build_example(value: Any) -> dict[str, Any]:
    spec = validate_spec(value)
    nodes: dict[str, dict[str, Any]] = {}
    for i, number in enumerate(spec["initial_values"]):
        nodes[f"i{i}"] = {
            "data": number,
            "next": f"i{i + 1}" if i + 1 < len(spec["initial_values"]) else None,
        }
    caller: str | None = "i0" if nodes else None
    steps: list[dict[str, Any]] = []
    code = render_code(spec)

    def record(
        phase: str,
        attempt: int | None,
        local_head: str | None,
        p: str | None,
        returned: str | None = None,
    ) -> None:
        anchor = f"call_{attempt}" if phase == "caller" else phase
        steps.append(
            {
                "phase": phase,
                "attempt": attempt,
                "caller_head": caller,
                "local_head": local_head,
                "p": p,
                "returned": returned,
                "nodes": deepcopy(nodes),
                "code_line": code["line_anchors"].get(anchor),
            }
        )

    record("initial", None, None, None)
    failures = 0
    for attempt, (number, success) in enumerate(
        zip(spec["insert_values"], spec["allocation_success"])
    ):
        local = caller
        p = f"t{attempt}" if success else None
        if p is not None:
            nodes[p] = {"data": INDETERMINATE, "next": INDETERMINATE}
        record("allocate", attempt, local, p)
        if not success:
            failures += 1
            returned = local
            record("allocation_failed", attempt, local, p, returned)
        else:
            assert p is not None
            nodes[p]["data"] = number
            record("data", attempt, local, p)
            if spec["variant"] == "reversed_assignment":
                local = p
                record("local_head", attempt, local, p)
            if spec["variant"] != "uninitialized_next":
                nodes[p]["next"] = local
                record("link", attempt, local, p)
            returned = p
            record("return", attempt, local, p, returned)
        if spec["variant"] != "discard_return":
            caller = returned
        record("caller", attempt, local, p, returned)

    seen: list[str] = []
    prefix: list[int] = []
    cursor = caller
    status = "terminated"
    cycle = None
    while cursor is not None:
        if cursor in seen:
            status, cycle = "cycle", cursor
            break
        seen.append(cursor)
        prefix.append(nodes[cursor]["data"])
        nxt = nodes[cursor]["next"]
        if nxt == INDETERMINATE:
            status = INDETERMINATE
            break
        cursor = nxt
    observation = {
        "caller_head": caller,
        "reachable_prefix": prefix,
        "traversal_status": status,
        "cycle_entry": cycle,
        "allocation_failures": failures,
        "unreachable_allocated_ids": sorted(set(nodes) - set(seen)),
    }
    example = {
        "schema_version": "head-insertion-example-v1",
        "spec": spec,
        "spec_digest": digest(spec),
        "engine_version": ENGINE_VERSION,
        "template_version": TEMPLATE_VERSION,
        "code": code,
        "trace": {"steps": steps},
        "observation": observation,
    }
    example["payload_digest"] = digest(example)
    return example


def validate_example(example: dict[str, Any]) -> None:
    if type(example) is not dict or "spec" not in example:
        raise SpecError("EXAMPLE_BINDING")
    expected = build_example(example["spec"])
    if canonical(example) != canonical(expected):
        raise SpecError("EXAMPLE_BINDING")


def answer(example: dict[str, Any], observation_key: str) -> Any:
    """Only finite supported observations, never an indeterminate exact traversal."""
    validate_example(example)
    if observation_key not in QUESTION_KEYS:
        raise SpecError("unsupported_question")
    return deepcopy(example["observation"][observation_key])


def build_actions(example: dict[str, Any], anchor: str) -> list[dict[str, Any]]:
    validate_example(example)
    if type(anchor) is not str or not anchor or len(anchor) > 128:
        raise SpecError("ACTION_ANCHOR")
    actions = []
    for i, step in enumerate(example["trace"]["steps"]):
        actions.append(
            {
                "kind": "show_state",
                "anchor": anchor,
                "step": i,
                "state_digest": digest(step),
            }
        )
        if step["code_line"] is not None:
            actions.append(
                {
                    "kind": "highlight_code",
                    "anchor": anchor,
                    "line": step["code_line"],
                    "step": i,
                }
            )
        if i + 1 < len(example["trace"]["steps"]):
            actions.append({"kind": "advance_step", "anchor": anchor, "step": i + 1})
    return actions
