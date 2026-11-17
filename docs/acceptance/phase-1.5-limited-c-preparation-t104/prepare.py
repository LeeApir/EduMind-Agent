"""Finite C course proposal: pure preparation, validation and assembly, no network."""

import argparse
import hashlib
from copy import deepcopy
from pathlib import Path

from jsonschema import validate
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_teaching_revision as teaching
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERSION = "limited-c-full-course-r01"
SPECS = {
    "C01": dict(
        version="head-insertion-spec-v1",
        variant="normal",
        initial_values=[9],
        insert_values=[1, 2],
        allocation_success=[True, True],
    ),
    "C02": dict(
        version="head-insertion-spec-v1",
        variant="normal",
        initial_values=[],
        insert_values=[-3, 5],
        allocation_success=[False, True],
    ),
}
BASE_KEYS = ("paragraphs", "questions")


def frames(catalog):
    rows = []
    for i, state in enumerate(catalog["example"]["trace"]["steps"]):
        rows.append(
            dict(
                frame_id=f"f{len(rows):02d}",
                state_index=i,
                line=state["code_line"],
                kind=state["phase"],
                fact_id=f"trace_step_{i:02d}",
            )
        )
        if state["phase"] == "allocate" and state["p"] is not None:
            rows.append(
                dict(
                    frame_id=f"f{len(rows):02d}",
                    state_index=i,
                    line=5,
                    kind="success_null_check",
                    fact_id=f"trace_step_{i:02d}",
                )
            )
    return rows


def schema():
    s = deepcopy(c.schema_for("C_content"))
    text = dict(type="string")
    s["properties"].update(
        prerequisites=text,
        learning_summary=text,
        lifecycle=text,
        failure_scope=text,
        step_notes=dict(
            type="array",
            items=dict(
                type="object",
                additionalProperties=False,
                properties=dict(frame_id=text, title=text, note=text),
                required=["frame_id", "title", "note"],
            ),
        ),
    )
    s["required"] = list(s["properties"])
    return s


def instruction(stage="C_content"):
    # Replace the old field list, rather than appending a conflicting override.
    source = teaching.instruction(stage)
    if stage == "C_content":
        source = source.replace(
            "Return only\nparagraphs and the four fixed questions in the supplied Schema.",
            "Return all fields of the supplied full-course Schema.",
        )
    else:
        source = source.replace(
            "Return the same C content Schema:\nparagraphs and all four fixed questions with fact_ids from the same example.",
            "Return all fields of the same full-course Schema, retaining fact_ids from the same example.",
        )
    return (
        source
        + """
Full-course teaching requirements (limited-c-full-course-r01):
Write prerequisites, learning_summary, lifecycle and failure_scope in Simplified Chinese.
Write one step_notes item per supplied presentation_frame, in its exact order, using its
frame_id. Generate a specific Chinese title and explanation of that exact state and code
location. No assistant will fill in missing teaching prose. Explain local scope, caller
assignment, unknown uninitialized data, and each successful or failed NULL check accurately.
Explain this exact example's allocation assumptions, complete traversal when NULL is reached,
and the resource lifetime and safe release order, without claiming cleanup was executed.
Initial nodes are stack nodes, successful t nodes are dynamically allocated; do not free stack
nodes or read a freed node. No cleanup code or cleanup animation is supplied or requested.
Generate natural teaching content, never a protocol echo. The learner knows basic C pointers,
structs, NULL and return values; no other learner history is known. Four fixed questions only.
Do not copy T103 or any assistant-written course: none is supplied. Paragraphs must cover the
initial list, each attempt, caller result, and final observation. Use only this fixed example.
"""
    )


def initial(slot):
    catalog = c.make_catalog(SPECS[slot])
    payload = dict(
        original_goal="用中文学会头插，分清局部指针与调用者头，解释每步和分配边界，独立完成四题。",
        learner_known=["C pointers", "struct", "NULL", "function return"],
        learner_unknown="all other personal profile fields",
        example=catalog["example"],
        fact_catalog=catalog["facts"],
        catalog_digest=catalog["catalog_digest"],
        presentation_frames=frames(catalog),
        question_definitions={k: v for k, v in c.QUESTION_DEFINITIONS.items()}
        if hasattr(c, "QUESTION_DEFINITIONS")
        else {
            "caller_head": "final node ID or none",
            "traversal_status": "terminated/cycle/indeterminate",
            "reachable_prefix": "known integer prefix; full traversal if NULL observed",
            "allocation_failures": "number of unsuccessful synthetic attempts",
        },
    )
    return payload


def body(slot, previous=None, issues=None):
    stage = "C_content" if previous is None else "C_repair"
    payload = initial(slot)
    if previous is not None:
        payload = dict(
            original_input=payload,
            original=previous["raw_output"],
            previous_candidate_digest=previous["artifact_digest"],
            issues=issues,
            immutable_question_types=list(c.QUESTION_KEYS),
        )
    return dict(
        model=wire.ROUTES["generation"]["model"],
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        max_output_tokens=8000,
        temperature=0.2,
        input=[
            dict(role="system", content=instruction(stage)),
            dict(role="user", content=canonical(payload).decode()),
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_limited_c_full_course",
                strict=True,
                schema=schema(),
            )
        ),
    )


def check_content(slot, value):
    validate(value, schema())
    catalog = c.make_catalog(SPECS[slot])
    c.validate("C_content", {k: value[k] for k in BASE_KEYS}, catalog=catalog)
    expected = [f["frame_id"] for f in frames(catalog)]
    assert [r["frame_id"] for r in value["step_notes"]] == expected, "FRAME_BINDING"
    for row in value["step_notes"]:
        c.bounded_text(row["title"], 100)
        c.bounded_text(row["note"], 2000)
    for key in ("prerequisites", "learning_summary", "lifecycle", "failure_scope"):
        c.bounded_text(value[key], 4000)
    return catalog


def artifact(slot, value, parent=None):
    catalog = check_content(slot, value)
    ident = c.identity(
        "limited_c_r01", slot, "C", int(parent is not None), SPECS[slot], parent
    )
    ident["prompt_version"] = VERSION
    base = c.assemble({k: value[k] for k in BASE_KEYS}, ident, catalog)
    return dict(
        version=VERSION,
        slot=slot,
        raw_output=value,
        base_artifact=base,
        parent_digest=parent,
        artifact_digest=digest(
            dict(
                slot=slot,
                raw_output=value,
                parent_digest=parent,
                example_digest=catalog["example"]["payload_digest"],
            )
        ),
    )


def render(slot, value):
    catalog = check_content(slot, value)
    data = dict(
        version=VERSION,
        code=catalog["example"]["code"]["source"],
        states=catalog["example"]["trace"]["steps"],
        frames=frames(catalog),
        content=value,
        answers=catalog["example"]["observation"],
    )
    payload = (
        canonical(data)
        .decode()
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (HERE / "course-template.html").read_text().replace("__PAYLOAD__", payload)


def generate():
    import importlib.metadata
    import platform
    import sys

    result = {
        "runtime.json": canonical(
            dict(
                python=platform.python_version(),
                interpreter_path=sys.executable,
                interpreter_sha256=hashlib.sha256(
                    Path(sys.executable).read_bytes()
                ).hexdigest(),
                packages={
                    name: importlib.metadata.version(name)
                    for name in ["httpx", "cryptography", "jsonschema", "pydantic"]
                },
            )
        )
        + b"\n"
    }
    for slot in SPECS:
        payload = body(slot)
        raw = canonical(payload)
        assert len(raw) <= 131072
        result[f"{slot}-input.json"] = canonical(initial(slot)) + b"\n"
        result[f"{slot}-request.json"] = raw
    result["output-schema.json"] = canonical(schema()) + b"\n"
    result["candidate.json"] = (
        canonical(
            dict(
                version=VERSION,
                response_adapter="limited-c-message-phase-v1",
                samples=SPECS,
                route=wire.ROUTES["generation"],
                http_limit=4,
                per_sample_limit=2,
                output_tokens=8000,
                request_bytes=131072,
                response_bytes=2097152,
                local_input_reservation_per_call=139264,
                batch_window_seconds=1800,
                request_io_timeout_seconds=90,
                repairs="at most one ordinary wording repair per sample, only after independent evaluation; no format/fact/safety repair; stop on unknown",
            )
        )
        + b"\n"
    )
    return result


def manifest(outputs):
    import ast

    seeds = [
        "app.core.provider_target",
        "scripts.isolated_diagnostics.p15_minimal_contract",
        "scripts.isolated_diagnostics.p15_teaching_revision",
        "scripts.isolated_diagnostics.p15_pilot_wire",
    ]
    seen, paths_to_check = set(), list(seeds)
    while paths_to_check:
        name = paths_to_check.pop()
        if name in seen:
            continue
        seen.add(name)
        source = None
        for base in (ROOT, ROOT / "backend"):
            for candidate in (
                base.joinpath(*name.split(".")).with_suffix(".py"),
                base.joinpath(*name.split(".")) / "__init__.py",
            ):
                if candidate.is_file():
                    source = candidate
                    break
            if source:
                break
        if source is None:
            continue
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                paths_to_check.extend(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = (
                    name.split(".")
                    if source.name == "__init__.py"
                    else name.split(".")[:-1]
                )
                if node.level:
                    prefix = prefix[: len(prefix) - node.level + 1]
                    module = ".".join(prefix + ([node.module] if node.module else []))
                else:
                    module = node.module or ""
                paths_to_check.append(module)
                paths_to_check.extend(
                    module + "." + n.name for n in node.names if n.name != "*"
                )
    deps = []
    for name in seen:
        for base in (ROOT, ROOT / "backend"):
            for candidate in (
                base.joinpath(*name.split(".")).with_suffix(".py"),
                base.joinpath(*name.split(".")) / "__init__.py",
            ):
                if candidate.is_file():
                    deps.append(str(candidate.relative_to(ROOT)))
    deps = sorted(
        set(
            deps
            + [
                "backend/pyproject.toml",
                "backend/uv.lock",
                "docs/acceptance/phase-1.5-minimal-output-contract-r01/schemas.json",
            ]
        )
    )
    own = [
        "prepare.py",
        "execute_once.py",
        "course-template.html",
        "test_preparation.py",
        "check_player.py",
        "README.md",
        "T103-OWNERSHIP.md",
        "CONTRACT-DIFF.md",
        "PHASE-COMPATIBILITY-T105.md",
        "manifest-before-t105.json",
    ]
    paths = {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sorted(deps)
    }
    paths.update(
        {
            str((HERE / p).relative_to(ROOT)): hashlib.sha256(
                (HERE / p).read_bytes()
            ).hexdigest()
            for p in own
        }
    )
    paths["docs/ADR/0050-limited-c-course-feasibility.md"] = hashlib.sha256(
        (ROOT / "docs/ADR/0050-limited-c-course-feasibility.md").read_bytes()
    ).hexdigest()
    return (
        canonical(
            dict(
                version=VERSION,
                status="proposed_not_authorized",
                files=paths,
                generated={
                    k: hashlib.sha256(v).hexdigest() for k, v in outputs.items()
                },
            )
        )
        + b"\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = generate()
    outputs["manifest.json"] = manifest(outputs)
    for name, raw in outputs.items():
        if args.check:
            assert (HERE / name).read_bytes() == raw, name
        else:
            (HERE / name).write_bytes(raw)
    print(
        "Finite C package reproducible; 2 development samples, 4 HTTP ceiling; real calls 0."
    )
