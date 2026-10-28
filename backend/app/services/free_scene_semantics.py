"""Versioned server guidance and bounded, non-executing C interface observations."""

import hashlib
import re
from copy import deepcopy
from typing import Any

from pycparser import c_ast, c_parser  # type: ignore[import-untyped]

CONTRACT_VERSION = "free-course-c-semantics-v2"
PRINCIPLES = [
    {
        "id": "c-value-parameters",
        "requirement": (
            "C parameters, including pointers, are passed by value. Reassigning a local pointer "
            "does not itself rebind the caller's pointer. Distinguish this from changing a pointed "
            "object or writing through an explicit pointer-to-pointer."
        ),
    },
    {
        "id": "c-returned-head",
        "requirement": (
            "When the supplied function returns a new list head, the caller must capture/propagate "
            "that return to update its head. Questions, code, solutions and keys must use the same "
            "actual signature/call convention. Never silently add a missing caller assignment."
        ),
    },
    {
        "id": "c-initialization",
        "requirement": (
            "malloc does not initialize members. Do not depict next as NULL before an explicit "
            "initialization. Distinguish calloc and explicit initialization from malloc. State "
            "allocation-success assumptions for predicted output and describe failure handling."
        ),
    },
    {
        "id": "representation-preconditions",
        "requirement": (
            "State representation and operation assumptions for complexity claims: tail insertion "
            "can be O(1) when a suitable tail pointer is maintained. Keep code, diagrams and text "
            "on the same representation and execution state."
        ),
    },
    {
        "id": "exercise-source-consistency",
        "requirement": (
            "Derive each reference answer from the question's explicitly stated operations under "
            "the actual code interface. Preserve required capture/return operations "
            "and prerequisites; "
            "a canonical answer format does not prove semantic correctness or implementation skill."
        ),
    },
]
PRINCIPLES.extend(
    [
        {
            "id": "shown-program-variant",
            "requirement": (
                "A question that changes code must show the exact complete variant in a"
                " dedicated C code "
                "block with its own anchor, and name that anchor. Do not ask readers to execute an "
                "unstated rewrite, omit operations, or silently reuse an incompatible "
                "original program."
            ),
        },
        {
            "id": "observation-scope-and-termination",
            "requirement": (
                "Distinguish function-local checkpoints, caller-final state, first k "
                "traversal steps, "
                "distinct reachable nodes, and traversal until NULL. A cycle repeats "
                "visits and has no "
                "finite tail. A self-loop is not the finite one-element output "
                "sequence. Never silently "
                "deduplicate, truncate, assume termination, or confuse allocation "
                "failure with success."
            ),
        },
        {
            "id": "answer-domain-audit",
            "requirement": (
                "For each code-state question, derive pointer links after each relevant"
                " assignment, state "
                "the allocation/input assumptions and stopping condition, and check the"
                " reference key "
                "against that outcome. Include nontermination, undefined behavior, or "
                "indeterminacy when "
                "applicable. For choice questions the genuine result must be present exactly once; "
                "otherwise rewrite or omit the question instead of selecting an "
                "incorrect finite option. "
                "Deliberately discarded returns can be valid fault questions: judge the"
                " stated outcome, "
                "not merely the presence of a discarded call."
            ),
        },
    ]
)
MAX_CODE_BYTES = 16384
MAX_AST_NODES = 3000
_COMMENT_OR_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*', re.S)
_INCLUDE = re.compile(r"\s*#\s*include\s*<(stdio|stdlib|stddef|stdint|stdbool|limits)\.h>\s*$")


def _without_comments(source: str) -> str:
    return _COMMENT_OR_LITERAL.sub(
        lambda m: " " + "\n" * m[0].count("\n") if m[0].startswith(("/*", "//")) else m[0],
        source,
    )


def _depth(node: Any) -> int:
    depth = 0
    while isinstance(node, c_ast.PtrDecl):
        depth += 1
        node = node.type
    return depth


def _id(node: Any) -> str | None:
    return node.name if isinstance(node, c_ast.ID) else None


def _allocation(node: Any) -> bool:
    while isinstance(node, c_ast.Cast):
        node = node.expr
    return isinstance(node, c_ast.FuncCall) and _id(node.name) in {"malloc", "calloc"}


def _interface(function: Any) -> dict[str, Any]:
    declaration = function.decl.type
    parameters = [
        p
        for p in (declaration.args.params if declaration.args else [])
        if isinstance(p, c_ast.Decl)
    ]
    modes = [{"name": p.name, "pointer_depth": _depth(p.type)} for p in parameters]
    statements = function.body.block_items or []
    replacements: list[str] = []
    # Recognize only the explicit, straight-line allocate/link/rebind/return idiom.
    # This is a syntactic observation, not a proof of every path, allocation, or alias.
    if statements and isinstance(statements[-1], c_ast.Return) and _depth(declaration.type) == 1:
        for p in parameters:
            if _depth(p.type) != 1 or _id(statements[-1].expr) != p.name:
                continue
            allocated = {
                n.name for n in statements if isinstance(n, c_ast.Decl) and _allocation(n.init)
            }
            for index, n in enumerate(statements):
                if not (
                    isinstance(n, c_ast.Assignment)
                    and n.op == "="
                    and _id(n.lvalue) == p.name
                    and _id(n.rvalue) in allocated
                ):
                    continue
                if any(
                    isinstance(before, c_ast.Assignment)
                    and before.op == "="
                    and isinstance(before.lvalue, c_ast.StructRef)
                    and before.lvalue.type == "->"
                    and _id(before.lvalue.name) == _id(n.rvalue)
                    and _id(before.lvalue.field) == "next"
                    and _id(before.rvalue) == p.name
                    for before in statements[:index]
                ):
                    replacements.append(p.name)
    return dict(
        name=function.decl.name,
        parameters=modes,
        return_pointer_depth=_depth(declaration.type),
        return_rebinding_parameters=sorted(set(replacements)),
        evidence_kind="bounded_ast_pattern_not_semantic_proof",
        type_resolution="explicit_declarators_only",
    )


def inspect_c(source: str) -> dict[str, Any]:
    """Never preprocess, open headers, compile, import model code, or execute C."""
    result: dict[str, Any] = dict(
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        status="not_assessed",
        interfaces=[],
        reason=None,
    )
    if len(source.encode()) > MAX_CODE_BYTES:
        return {**result, "reason": "code_size_limit"}
    lines = _without_comments(source).splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            if not _INCLUDE.fullmatch(line):
                return {**result, "reason": "unsupported_preprocessor"}
            lines[index] = ""
    try:
        # The in-memory API has no cpp invocation and never resolves include paths.
        tree = c_parser.CParser().parse("\n".join(lines), filename="<scene-memory>")
        stack, count = [tree], 0
        while stack:
            node = stack.pop()
            count += 1
            if count > MAX_AST_NODES:
                return {**result, "reason": "ast_size_limit"}
            stack.extend(child for _, child in node.children())
        return {
            **result,
            "status": "parsed",
            "interfaces": [_interface(f) for f in tree.ext if isinstance(f, c_ast.FuncDef)],
        }
    except (c_parser.ParseError, RecursionError):
        return {**result, "reason": "unsupported_syntax"}


def generation_semantics(inputs: dict[str, Any]) -> dict[str, Any]:
    hints = []
    for upstream_index, upstream in enumerate(inputs["upstream"]):
        for block_index, block in enumerate(upstream["content"].get("blocks", [])):
            if block.get("kind") == "code" and block.get("language") == "c":
                hints.append(
                    dict(
                        scene_id=upstream["scene_id"],
                        scene_version_id=upstream["scene_version_id"],
                        content_digest=upstream["digest"],
                        source_pointer=f"/upstream/{upstream_index}/content/blocks/{block_index}/source",
                        **inspect_c(block["source"]),
                    )
                )
    return dict(
        version=CONTRACT_VERSION,
        principles=deepcopy(PRINCIPLES),
        necessary_upstream_interfaces=hints,
        execution_performed=False,
        semantic_correctness_verified=False,
        unsupported_semantics="requires_review",
    )
