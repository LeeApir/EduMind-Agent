"""Bounded static pointer relations for one straight-line successful-allocation path.

This is not a C executor: no calls, loops, memory operations, headers or I/O run.
Unknown syntax/control flow discards the observation instead of guessing a final state.
"""

from typing import Any

from pycparser import c_ast, c_parser  # type: ignore[import-untyped]

from app.services.free_scene_semantics import _allocation, _depth, _without_comments, inspect_c

MAX_STATEMENTS = 64
MAX_POINTERS = 32
_UNKNOWN = "<unknown>"


class Unsupported(Exception):
    pass


def _id(node: Any) -> str | None:
    return node.name if isinstance(node, c_ast.ID) else None


def _null(node: Any) -> bool:
    return _id(node) == "NULL" or (
        isinstance(node, c_ast.Constant) and node.type == "int" and node.value == "0"
    )


def _struct(node: Any) -> str | None:
    if _depth(node) != 1:
        return None
    node = node.type
    return (
        node.type.name
        if isinstance(node, c_ast.TypeDecl) and isinstance(node.type, c_ast.Struct)
        else None
    )


def _pure_scalar(node: Any, initialized: set[str]) -> bool:
    # No arithmetic/indirection guesses: overflow, zero division and uninitialized reads
    # could invalidate the path before a syntactic cycle is reached.
    if isinstance(node, c_ast.ID):
        return node.name in initialized
    if isinstance(node, c_ast.Constant) and node.type == "int":
        return (
            len(node.value) <= 10 and node.value.isdecimal() and 0 <= int(node.value) <= 2147483647
        )
    return False


def _trace(function: Any, structures: dict[str, dict[str, bool]]) -> dict[str, Any]:
    name = function.decl.name
    result: dict[str, Any] = dict(
        function=name,
        status="not_assessed",
        reason=None,
        assumptions=[
            "successful allocations only; NULL guards take the non-NULL branch",
            "standard malloc/calloc with exact sizeof(struct); initialized scalar copies only",
            "explicit struct pointer declarations; NULL denotes the null pointer",
            "parameter successor links unknown",
        ],
        execution_performed=False,
    )
    aliases: dict[str, str | None] = {}
    types: dict[str, str] = {}
    edges: dict[str, str | None] = {}
    allocated: set[str] = set()
    initialized: set[str] = set()
    steps = []

    def register(variable: str, tag: str, value: str | None) -> None:
        if variable == "NULL" or len(aliases) >= MAX_POINTERS or tag not in structures:
            raise Unsupported("unknown_type_or_pointer_limit")
        if sum(structures[tag].values()) != 1:
            raise Unsupported("ambiguous_link_field")
        aliases[variable], types[variable] = value, tag

    def value(node: Any, tag: str) -> str | None:
        if _null(node):
            return None
        if isinstance(node, c_ast.ID) and node.name in aliases:
            if types[node.name] != tag:
                raise Unsupported("pointer_type_change")
            return aliases[node.name]
        if _allocation(node):
            call = node
            while isinstance(call, c_ast.Cast):
                if _struct(call.to_type.type) != tag:
                    raise Unsupported("allocation_cast_type_unknown")
                call = call.expr
            arguments = call.args.exprs if call.args else []
            if _id(call.name) == "calloc":
                if (
                    len(arguments) != 2
                    or not isinstance(arguments[0], c_ast.Constant)
                    or arguments[0].value != "1"
                ):
                    raise Unsupported("allocation_extent_unknown")
                arguments = arguments[1:]
            if len(arguments) != 1:
                raise Unsupported("allocation_extent_unknown")
            size = arguments[0]
            if (
                not isinstance(size, c_ast.UnaryOp)
                or size.op != "sizeof"
                or not isinstance(size.expr, c_ast.Typename)
                or not isinstance(size.expr.type, c_ast.TypeDecl)
                or not isinstance(size.expr.type.type, c_ast.Struct)
                or size.expr.type.type.name != tag
            ):
                raise Unsupported("allocation_extent_unknown")
            identity = "allocation:" + str(len(allocated))
            allocated.add(identity)
            edges[identity] = _UNKNOWN
            return identity
        raise Unsupported("unsupported_pointer_expression")

    try:
        return_type = _struct(function.decl.type.type)
        if return_type is None:
            raise Unsupported("not_single_struct_pointer_return")
        for p in function.decl.type.args.params if function.decl.type.args else []:
            if (
                isinstance(p, c_ast.Typename)
                and isinstance(p.type.type, c_ast.IdentifierType)
                and p.type.type.names == ["void"]
            ):
                continue
            if not isinstance(p, c_ast.Decl):
                raise Unsupported("unsupported_parameter")
            if _depth(p.type):
                tag = _struct(p.type)
                if tag is None:
                    raise Unsupported("unsupported_pointer_parameter")
                identity = "parameter:" + p.name
                register(p.name, tag, identity)
                edges[identity] = _UNKNOWN
            elif isinstance(p.type, c_ast.TypeDecl) and isinstance(
                p.type.type, c_ast.IdentifierType
            ):
                initialized.add(p.name)
            else:
                raise Unsupported("unsupported_scalar_parameter")
        statements = function.body.block_items or []
        if (
            not statements
            or len(statements) > MAX_STATEMENTS
            or not isinstance(statements[-1], c_ast.Return)
        ):
            raise Unsupported("statement_limit_or_nonfinal_return")
        for n in statements[:-1]:
            if isinstance(n, c_ast.Decl):
                if _depth(n.type):
                    tag = _struct(n.type)
                    if tag is None or n.init is None:
                        raise Unsupported("uninitialized_or_unsupported_pointer")
                    register(n.name, tag, value(n.init, tag))
                elif n.init is not None and not _pure_scalar(n.init, initialized):
                    raise Unsupported("scalar_initializer_side_effect")
                elif n.init is not None:
                    initialized.add(n.name)
            elif isinstance(n, c_ast.If):
                cond = n.cond
                returns = (
                    n.iftrue.block_items if isinstance(n.iftrue, c_ast.Compound) else [n.iftrue]
                )
                guard_name = (
                    _id(cond.left)
                    if isinstance(cond, c_ast.BinaryOp) and _null(cond.right)
                    else _id(cond.right)
                    if isinstance(cond, c_ast.BinaryOp) and _null(cond.left)
                    else None
                )
                if (
                    not isinstance(cond, c_ast.BinaryOp)
                    or cond.op != "=="
                    or n.iffalse is not None
                    or guard_name not in aliases
                    or aliases[guard_name] not in allocated
                    or len(returns or []) != 1
                    or not isinstance(returns[0], c_ast.Return)
                    or not (_null(returns[0].expr) or _id(returns[0].expr) in aliases)
                ):
                    raise Unsupported("unsupported_control_flow")
            elif isinstance(n, c_ast.Assignment) and n.op == "=":
                target = n.lvalue
                if isinstance(target, c_ast.ID):
                    if target.name in aliases:
                        aliases[target.name] = value(n.rvalue, types[target.name])
                    elif not _pure_scalar(n.rvalue, initialized):
                        raise Unsupported("unknown_assignment_side_effect")
                    else:
                        initialized.add(target.name)
                elif isinstance(target, c_ast.StructRef) and target.type == "->":
                    variable, field = _id(target.name), _id(target.field)
                    if variable not in aliases or aliases[variable] in (None, _UNKNOWN):
                        raise Unsupported("unknown_or_null_store_target")
                    tag, identity = types[variable], aliases[variable]
                    if identity not in allocated:
                        raise Unsupported("external_store_validity_unknown")
                    if field not in structures[tag]:
                        raise Unsupported("unknown_struct_field")
                    if structures[tag][field]:
                        edges[identity] = value(n.rvalue, tag)
                        steps.append(
                            dict(
                                line=n.coord.line,
                                pointer=variable,
                                field=field,
                                target=edges[identity],
                            )
                        )
                    elif not _pure_scalar(n.rvalue, initialized):
                        raise Unsupported("scalar_store_side_effect")
                else:
                    raise Unsupported("unsupported_store")
            elif not isinstance(n, c_ast.EmptyStatement):
                raise Unsupported("unsupported_statement_or_call")
        returned = value(statements[-1].expr, return_type)
        seen: set[str] = set()
        path: list[str] = []
        cursor = returned
        for _ in range(MAX_STATEMENTS + 1):
            if cursor is None:
                return {
                    **result,
                    "status": "no_cycle_in_supported_path",
                    "reason": None,
                    "link_steps": steps,
                    "return_path": path,
                }
            if cursor == _UNKNOWN or cursor not in edges:
                raise Unsupported("unknown_successor")
            if cursor in seen:
                return {
                    **result,
                    "status": "cycle_on_supported_path",
                    "reason": None,
                    "link_steps": steps,
                    "return_path": path,
                    "cycle_entry": cursor,
                }
            seen.add(cursor)
            path.append(cursor)
            cursor = edges[cursor]
        raise Unsupported("trace_limit")
    except Unsupported as exc:
        return {**result, "reason": str(exc)}


def trace_c(code: str) -> dict[str, Any]:
    inspection = inspect_c(code)
    result = dict(
        source_sha256=inspection["source_sha256"],
        status="not_assessed",
        functions=[],
        execution_performed=False,
    )
    if inspection["status"] != "parsed":
        return {**result, "reason": inspection["reason"]}
    text = "\n".join(
        "" if line.lstrip().startswith("#") else line
        for line in _without_comments(code).splitlines()
    )
    try:
        tree = c_parser.CParser().parse(text, filename="<pointer-relations-memory>")
        structures = {}
        stack = [tree]
        while stack:
            node = stack.pop()
            if isinstance(node, c_ast.Struct) and node.name and node.decls:
                fields: dict[str, bool] = {}
                for field in node.decls:
                    # Only one self-referential pointer field is supported.
                    if _depth(field.type) and _struct(field.type) != node.name:
                        fields = {}
                        break
                    if not _depth(field.type) and not (
                        isinstance(field.type, c_ast.TypeDecl)
                        and isinstance(field.type.type, c_ast.IdentifierType)
                    ):
                        fields = {}
                        break
                    fields[field.name] = bool(_depth(field.type))
                structures[node.name] = fields
            stack.extend(child for _, child in node.children())
        functions = [
            _trace(f, structures)
            for f in tree.ext
            if isinstance(f, c_ast.FuncDef) and _depth(f.decl.type.type) == 1
        ]
        return {
            **result,
            "status": "observed" if functions else "not_assessed",
            "functions": functions,
        }
    except (c_parser.ParseError, RecursionError):
        return {**result, "reason": "unsupported_syntax"}
