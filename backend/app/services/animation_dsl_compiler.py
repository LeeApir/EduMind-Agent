"""Deterministic AST-built Manim code from complete trusted DSL trajectories."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.services.animation_cache import FONT_DIGEST
from app.services.animation_dsl_validation import (
    EdgeState,
    NodeState,
    PointerState,
    ValidatedDSL,
    validate_animation_dsl,
)
from app.services.animation_renderer import IMAGE

_DIRECTORY = Path(__file__).parent
_POLICY_BYTES = (_DIRECTORY / "animation_dsl_compiler_policy.json").read_bytes()
POLICY = json.loads(_POLICY_BYTES)
COMPILER_VERSION = POLICY["compiler_version"]
COMPILER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
STATIC_SHA256 = hashlib.sha256((_DIRECTORY / "animation_dsl_static.py").read_bytes()).hexdigest()
COMPILER_POLICY_SHA256 = hashlib.sha256(_POLICY_BYTES + bytes.fromhex(STATIC_SHA256)).hexdigest()


class DSLCompileError(ValueError):
    pass


@dataclass(frozen=True)
class StaticReport:
    ast_sha256: str
    nodes: int


def audit_compiled_source(source: str) -> StaticReport:
    """Bound total parser/checker work in an isolated, credential-free child."""
    try:
        if type(source) is not str:
            raise DSLCompileError("DSL_COMPILE_REJECTED")
        if len(source) > POLICY["max_source_bytes"]:
            raise DSLCompileError("DSL_RESOURCE_LIMIT")
        encoded = source.encode("utf-8")
    except UnicodeError:
        raise DSLCompileError("DSL_COMPILE_REJECTED") from None
    if len(encoded) > POLICY["max_source_bytes"]:
        raise DSLCompileError("DSL_RESOURCE_LIMIT")
    try:
        if (
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != COMPILER_SHA256
            or hashlib.sha256((_DIRECTORY / "animation_dsl_static.py").read_bytes()).hexdigest()
            != STATIC_SHA256
            or (_DIRECTORY / "animation_dsl_compiler_policy.json").read_bytes() != _POLICY_BYTES
        ):
            raise DSLCompileError("DSL_COMPILE_UNAVAILABLE")
    except OSError:
        raise DSLCompileError("DSL_COMPILE_UNAVAILABLE") from None
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                str(_DIRECTORY / "animation_dsl_static.py"),
                STATIC_SHA256,
                hashlib.sha256(_POLICY_BYTES).hexdigest(),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={},
        )
    except OSError:
        raise DSLCompileError("DSL_COMPILE_UNAVAILABLE") from None
    try:
        output, _ = process.communicate(encoded, timeout=max(0, 0.9 - (time.monotonic() - started)))
        if len(output) > 1024:
            raise DSLCompileError("DSL_COMPILE_UNAVAILABLE")
        response = json.loads(output)
        if type(response) is not dict:
            raise DSLCompileError("DSL_COMPILE_UNAVAILABLE")
        if process.returncode != 0:
            code = response.get("code")
            raise DSLCompileError(
                code
                if type(code) is str
                and code
                in {
                    "DSL_RESOURCE_LIMIT",
                    "DSL_COMPILE_REJECTED",
                    "DSL_COMPILE_UNAVAILABLE",
                }
                else "DSL_COMPILE_UNAVAILABLE"
            )
        if (
            type(response) is not dict
            or set(response) != {"ast_sha256", "nodes"}
            or type(response["nodes"]) is not int
            or not 1 <= response["nodes"] <= 20000
            or type(response["ast_sha256"]) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", response["ast_sha256"])
        ):
            raise DSLCompileError("DSL_COMPILE_UNAVAILABLE")
        return StaticReport(response["ast_sha256"], response["nodes"])
    except DSLCompileError:
        raise
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise DSLCompileError("DSL_COMPILE_UNAVAILABLE") from None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def _name(value: str) -> ast.Name:
    return ast.Name(value, ast.Load())


def _call(function: str | ast.expr, *args: ast.expr, **kwargs: object) -> ast.Call:
    return ast.Call(
        _name(function) if isinstance(function, str) else function,
        list(args),
        [ast.keyword(k, ast.Constant(v)) for k, v in kwargs.items()],
    )


def _point(x: float, y: float) -> ast.List:
    return ast.List(
        [ast.Constant(round(x, 6)), ast.Constant(round(y, 6)), ast.Constant(0)], ast.Load()
    )


def _wrap(text: str) -> str:
    width = int(POLICY["caption_line_chars"])
    return "\n".join(text[i : i + width] for i in range(0, len(text), width))


class Builder:
    def __init__(self) -> None:
        self.body: list[ast.stmt] = []
        self.counter = 0

    def assign(self, expression: ast.expr) -> ast.Name:
        variable = f"m{self.counter}"
        self.counter += 1
        self.body.append(ast.Assign([ast.Name(variable, ast.Store())], expression))
        return _name(variable)

    def text(self, text: str, x: float, y: float, size: int = 16, style: str = "reset") -> ast.Name:
        expression = _call(
            "Text",
            ast.Constant(_wrap(text)),
            font=POLICY["font"],
            font_size=size,
            color=POLICY["colors"][style],
        )
        return self.assign(_call(ast.Attribute(expression, "move_to", ast.Load()), _point(x, y)))

    def group(self, *objects: ast.Name) -> ast.Name:
        return self.assign(_call("VGroup", *objects))

    def arrow(self, start: tuple[float, float], end: tuple[float, float], style: str) -> ast.Name:
        return self.assign(
            _call(
                "Arrow",
                _point(*start),
                _point(*end),
                buff=0.05,
                stroke_width=2,
                color=POLICY["colors"][style],
            )
        )

    def scene(self, method: str, *args: ast.expr, **kwargs: object) -> None:
        self.body.append(
            ast.Expr(_call(ast.Attribute(_name("self"), method, ast.Load()), *args, **kwargs))
        )

    def node(self, node: NodeState) -> tuple[ast.Name, ast.Name, ast.Name]:
        x, y = self.cell(node)
        box = _call(
            "RoundedRectangle",
            width=1.15,
            height=0.65,
            corner_radius=0.1,
            color=POLICY["colors"][node.style],
            stroke_width=2,
            fill_opacity=0.3 if node.visited else 0.08,
        )
        border = self.assign(_call(ast.Attribute(box, "move_to", ast.Load()), _point(x, y)))
        value = self.text(str(node.value), x, y, 22, node.style)
        objects = [
            border,
            value,
            self.text(node.id, x, y + 0.55, 12, node.style),
        ]
        if node.visited:
            objects.append(self.text("已访问", x, y - 0.55, 12, "success"))
        return self.group(*objects), value, border

    @staticmethod
    def cell(node: NodeState) -> tuple[float, float]:
        return (
            float(POLICY["column_start"] + POLICY["column_spacing"] * node.column),
            float(POLICY["row_start"] - POLICY["row_spacing"] * node.row),
        )

    def edge(self, edge: EdgeState, nodes: dict[str, NodeState]) -> ast.Name:
        sx, sy = self.cell(nodes[edge.source])
        if edge.target is None:
            return self.group(
                self.arrow((sx + 0.6, sy), (sx + 0.9, sy), edge.style),
                self.text("NULL", sx + 1.15, sy, 12, edge.style),
            )
        tx, ty = self.cell(nodes[edge.target])
        if sx != tx:
            sign = 1 if tx > sx else -1
            start, end = (sx + 0.6 * sign, sy), (tx - 0.6 * sign, ty)
        else:
            sign = 1 if ty > sy else -1
            start, end = (sx, sy + 0.4 * sign), (tx, ty - 0.4 * sign)
        return self.group(self.arrow(start, end, edge.style))

    def pointer(self, pointer: PointerState, offset: int, nodes: dict[str, NodeState]) -> ast.Name:
        x = -4.8 + 3.2 * offset
        label = self.text(pointer.label, x, 2.85, 14, pointer.style)
        if pointer.target is None:
            return self.group(
                label,
                self.arrow((x, 2.6), (x, 2.3), pointer.style),
                self.text("NULL", x, 2.1, 12, pointer.style),
            )
        tx, ty = self.cell(nodes[pointer.target])
        return self.group(label, self.arrow((x, 2.6), (tx, ty + 0.4), pointer.style))


def _subtitle(validated: ValidatedDSL) -> str:
    def stamp(milliseconds: int) -> str:
        seconds, ms = divmod(milliseconds, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

    return "\n".join(
        f"{i + 1}\n{stamp(f.start_ms)} --> {stamp(f.end_ms)}\n{_wrap(f.caption)}\n"
        for i, f in enumerate(validated.frames)
    )


@dataclass(frozen=True)
class CompiledDSL:
    validated: ValidatedDSL
    source: str
    subtitles: str
    source_sha256: str
    ast_sha256: str
    subtitles_sha256: str
    identity_sha256: str
    ast_nodes: int
    compiler_version: str = COMPILER_VERSION
    compiler_sha256: str = COMPILER_SHA256
    compiler_policy_sha256: str = COMPILER_POLICY_SHA256


def compile_animation_dsl(raw: bytes | str, *, knowledge_point_id: str) -> CompiledDSL:
    validated = validate_animation_dsl(raw, knowledge_point_id=knowledge_point_id)
    candidate = validated.candidate
    actions = cast(list[dict[str, object]], candidate["actions"])
    builder = Builder()
    title = builder.text(cast(str, candidate["title"]), 0, 3.5, 22)
    builder.scene("add", title)
    node_objects: dict[str, ast.Name] = {}
    values: dict[str, ast.Name] = {}
    borders: dict[str, ast.Name] = {}
    visited: set[str] = set()
    edge_objects: dict[str, ast.Name] = {}
    pointer_objects: dict[str, ast.Name] = {}
    pointer_offsets: dict[str, int] = {}
    for offset, p in enumerate(cast(list[dict[str, str]], candidate["pointers"])):
        pointer_offsets[p["id"]] = offset
        obj = builder.pointer(PointerState(p["id"], p["label"]), offset, {})
        pointer_objects[p["id"]] = obj
        builder.scene("add", obj)
    previous_caption = comparison_object = complexity_object = None
    for frame, action in zip(validated.frames, actions, strict=True):
        if previous_caption is not None:
            builder.scene("remove", previous_caption)
        if comparison_object is not None:
            builder.scene("remove", comparison_object)
            comparison_object = None
        previous_caption = builder.text(frame.caption, 0, -3.15)
        builder.scene("add", previous_caption)
        animations: list[ast.expr] = []
        nodes = {n.id: n for n in frame.nodes}
        edges = {e.id: e for e in frame.edges}
        pointers = {p.id: p for p in frame.pointers}
        op = frame.op
        if op == "create_node":
            ident = cast(str, action["id"])
            node_objects[ident], values[ident], borders[ident] = builder.node(nodes[ident])
            animations.append(_call("FadeIn", node_objects[ident]))
        elif op == "connect":
            ident = cast(str, action["id"])
            edge_objects[ident] = builder.edge(edges[ident], nodes)
            animations.append(_call("FadeIn", edge_objects[ident]))
        elif op == "disconnect":
            animations.append(_call("FadeOut", edge_objects.pop(cast(str, action["edge"]))))
        elif op == "compare":
            assert frame.comparison is not None
            c = frame.comparison
            operator = {"lt": "<", "eq": "=", "gt": ">"}[c.result]
            comparison_object = builder.text(
                f"{nodes[c.left].value} {operator} {nodes[c.right].value}", 0, -2.5, 24
            )
            animations.append(_call("FadeIn", comparison_object))
        elif op == "show_complexity":
            assert frame.complexity is not None
            obj = builder.text(
                f"Time: {frame.complexity[0]}  Space: {frame.complexity[1]}", 0, 3.0, 14
            )
            if complexity_object is None:
                complexity_object = obj
                animations.append(_call("FadeIn", obj))
            else:
                animations.append(_call("Transform", complexity_object, obj))
        elif op == "swap":
            for ident in (cast(str, action["left"]), cast(str, action["right"])):
                node = nodes[ident]
                x, y = builder.cell(node)
                new = builder.text(str(node.value), x, y, 22, node.style)
                animations.append(_call("Transform", values[ident], new))
        elif op == "visit":
            ident = cast(str, action["node"])
            x, y = builder.cell(nodes[ident])
            if ident not in visited:
                builder.scene("add", builder.text("已访问", x, y - 0.55, 12, "success"))
                visited.add(ident)
            receiver = ast.Attribute(borders[ident], "animate", ast.Load())
            animations.append(_call(ast.Attribute(receiver, "set_fill", ast.Load()), opacity=0.3))
        elif op == "highlight":
            ident = cast(str, action["object"])
            obj = node_objects.get(ident) or edge_objects.get(ident) or pointer_objects[ident]
            receiver = ast.Attribute(obj, "animate", ast.Load())
            animations.append(
                _call(
                    ast.Attribute(receiver, "set_color", ast.Load()),
                    ast.Constant(POLICY["colors"][cast(str, action["style"])]),
                )
            )
        else:
            assert op == "move_pointer"
            ident = cast(str, action["pointer"])
            new = builder.pointer(pointers[ident], pointer_offsets[ident], nodes)
            animations.append(_call("Transform", pointer_objects[ident], new))
        builder.scene("play", *animations, run_time=cast(int, action["duration_ms"]) / 1000)
        hold = cast(int, action["hold_ms"])
        if hold:
            builder.scene("wait", ast.Constant(hold / 1000))
    function = ast.FunctionDef(
        "construct",
        ast.arguments([], [ast.arg("self")], None, [], [], None, []),
        builder.body,
        [],
        None,
    )
    tree = ast.Module(
        [
            ast.ImportFrom("manim", [ast.alias(name) for name in POLICY["imports"]], 0),
            ast.ClassDef("DSLScene", [_name("Scene")], [], [function], []),
        ],
        [],
    )
    source = ast.unparse(ast.fix_missing_locations(tree)) + "\n"
    report = audit_compiled_source(source)
    subtitles = _subtitle(validated)
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    subtitle_hash = hashlib.sha256(subtitles.encode()).hexdigest()
    identity = {
        "compiler_version": COMPILER_VERSION,
        "compiler_sha256": COMPILER_SHA256,
        "compiler_policy_sha256": COMPILER_POLICY_SHA256,
        "schema_sha256": validated.schema_sha256,
        "validator_sha256": validated.validator_sha256,
        "policy_sha256": validated.policy_sha256,
        "dsl_sha256": validated.dsl_sha256,
        "trace_sha256": validated.trace_sha256,
        "source_sha256": source_hash,
        "ast_sha256": report.ast_sha256,
        "subtitles_sha256": subtitle_hash,
        "subtitles_version": POLICY["subtitles_version"],
        "image": IMAGE,
        "font_digest": FONT_DIGEST,
        "compiler_python": list(sys.version_info[:3]),
        "frame_rate": POLICY["frame_rate"],
        "pixel_height": POLICY["pixel_height"],
    }
    identity_hash = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CompiledDSL(
        validated,
        source,
        subtitles,
        source_hash,
        report.ast_sha256,
        subtitle_hash,
        identity_hash,
        report.nodes,
        compiler_version=COMPILER_VERSION,
        compiler_sha256=COMPILER_SHA256,
        compiler_policy_sha256=COMPILER_POLICY_SHA256,
    )
