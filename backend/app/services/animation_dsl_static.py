"""Fixed stdlib-only AST checker subprocess. Never execute/import candidate source."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import resource
import sys
import unicodedata
from pathlib import Path

POLICY_BYTES = Path(__file__).with_name("animation_dsl_compiler_policy.json").read_bytes()
POLICY = json.loads(POLICY_BYTES)


class StaticError(ValueError):
    pass


def require(condition: bool) -> None:
    if not condition:
        raise StaticError("DSL_COMPILE_REJECTED")


def number(node: ast.AST, low: float, high: float) -> float:
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        sign, node = -1, node.operand
    require(isinstance(node, ast.Constant) and type(node.value) in (int, float))
    assert isinstance(node, ast.Constant)
    result = sign * float(node.value)
    require(math.isfinite(result) and low <= result <= high)
    return result


def string(node: ast.AST, *, choices: tuple[str, ...] | None = None) -> str:
    require(isinstance(node, ast.Constant) and type(node.value) is str)
    assert isinstance(node, ast.Constant)
    value: str = node.value
    require(1 <= len(value) <= 164 and bool(value.strip()))
    require(unicodedata.normalize("NFC", value) == value)
    require(not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c != "\n" for c in value))
    require(value.count("\n") <= 3)
    if choices is not None:
        require(value in choices)
    return value


def coordinate(node: ast.AST) -> None:
    require(isinstance(node, ast.List) and isinstance(node.ctx, ast.Load) and len(node.elts) == 3)
    assert isinstance(node, ast.List)
    number(node.elts[0], -6.6, 6.6)
    number(node.elts[1], -3.8, 3.8)
    require(number(node.elts[2], 0, 0) == 0)


class Checker:
    def __init__(self) -> None:
        self.bindings: dict[str, str] = {}
        self.duration_ms = 0

    def keywords(self, call: ast.Call, names: set[str]) -> dict[str, ast.expr]:
        require(len(call.keywords) == len(names))
        require({k.arg for k in call.keywords} == names)
        return {str(k.arg): k.value for k in call.keywords}

    def bound(self, node: ast.AST, kinds: tuple[str, ...]) -> str:
        require(isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load))
        assert isinstance(node, ast.Name)
        kind = self.bindings.get(node.id, "")
        require(kind in kinds)
        return kind

    def object(self, node: ast.AST) -> str:
        require(isinstance(node, ast.Call))
        assert isinstance(node, ast.Call)
        if isinstance(node.func, ast.Attribute):
            require(node.func.attr == "move_to" and isinstance(node.func.ctx, ast.Load))
            kind = self.object(node.func.value)
            require(kind in ("text", "box") and len(node.args) == 1 and not node.keywords)
            require(
                isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name)
            )
            coordinate(node.args[0])
            return kind
        require(isinstance(node.func, ast.Name) and isinstance(node.func.ctx, ast.Load))
        assert isinstance(node.func, ast.Name)
        name = node.func.id
        colors = tuple(POLICY["colors"].values())
        if name == "Text":
            require(len(node.args) == 1)
            string(node.args[0])
            kw = self.keywords(node, {"font", "font_size", "color"})
            string(kw["font"], choices=(POLICY["font"],))
            require(number(kw["font_size"], 18, 28) in POLICY["font_sizes"])
            string(kw["color"], choices=colors)
            return "text"
        if name == "RoundedRectangle":
            require(not node.args)
            kw = self.keywords(
                node, {"width", "height", "corner_radius", "color", "stroke_width", "fill_opacity"}
            )
            require(number(kw["width"], 1.3, 1.3) == 1.3)
            require(number(kw["height"], 1.35, 1.35) == 1.35)
            number(kw["corner_radius"], 0.1, 0.1)
            number(kw["stroke_width"], 3, 3)
            require(number(kw["fill_opacity"], 0.08, 0.3) in (0.08, 0.3))
            string(kw["color"], choices=colors)
            return "box"
        if name == "Arrow":
            require(len(node.args) == 2)
            for point in node.args:
                coordinate(point)
            require(ast.dump(node.args[0]) != ast.dump(node.args[1]))
            kw = self.keywords(
                node,
                {"buff", "stroke_width", "color", "tip_length", "max_tip_length_to_length_ratio"},
            )
            number(kw["buff"], 0.04, 0.04)
            number(kw["tip_length"], 0.14, 0.14)
            number(kw["max_tip_length_to_length_ratio"], 0.3, 0.3)
            number(kw["stroke_width"], 3, 3)
            string(kw["color"], choices=colors)
            return "arrow"
        require(name == "VGroup" and not node.keywords and 1 <= len(node.args) <= 4)
        for arg in node.args:
            self.bound(arg, ("text", "box", "arrow"))
        return "group"

    def animation(self, node: ast.AST) -> None:
        require(isinstance(node, ast.Call))
        assert isinstance(node, ast.Call)
        if isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            require(
                isinstance(receiver, ast.Attribute)
                and receiver.attr == "animate"
                and isinstance(receiver.ctx, ast.Load)
                and isinstance(node.func.ctx, ast.Load)
            )
            assert isinstance(receiver, ast.Attribute)
            if node.func.attr == "set_color":
                self.bound(receiver.value, ("group",))
                require(len(node.args) == 1 and not node.keywords)
                string(node.args[0], choices=tuple(POLICY["colors"].values()))
            else:
                require(node.func.attr == "set_fill" and not node.args)
                self.bound(receiver.value, ("box",))
                kw = self.keywords(node, {"opacity"})
                number(kw["opacity"], 0.3, 0.3)
            return
        require(isinstance(node.func, ast.Name))
        assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        require(isinstance(node.func.ctx, ast.Load) and not node.keywords)
        if node.func.id in ("FadeIn", "FadeOut"):
            require(len(node.args) == 1)
            self.bound(node.args[0], ("group", "text"))
        else:
            require(node.func.id == "Transform" and len(node.args) == 2)
            require(
                self.bound(node.args[0], ("group", "text"))
                == self.bound(node.args[1], ("group", "text"))
            )

    def statement(self, statement: ast.stmt) -> None:
        if isinstance(statement, ast.Assign):
            require(len(statement.targets) == 1 and not statement.type_comment)
            target = statement.targets[0]
            require(isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store))
            assert isinstance(target, ast.Name)
            require(
                target.id == f"m{len(self.bindings)}"
                and re.fullmatch(r"m[0-9]+", target.id) is not None
            )
            self.bindings[target.id] = self.object(statement.value)
            return
        require(isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call))
        assert isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
        call = statement.value
        require(isinstance(call.func, ast.Attribute) and isinstance(call.func.ctx, ast.Load))
        assert isinstance(call.func, ast.Attribute)
        require(
            isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
            and isinstance(call.func.value.ctx, ast.Load)
        )
        if call.func.attr in ("add", "remove"):
            require(len(call.args) == 1 and not call.keywords)
            self.bound(call.args[0], ("text", "group"))
        elif call.func.attr == "play":
            require(1 <= len(call.args) <= 2)
            for arg in call.args:
                self.animation(arg)
            kw = self.keywords(call, {"run_time"})
            self.time(kw["run_time"], 0.2, 2)
        else:
            require(call.func.attr == "wait" and len(call.args) == 1 and not call.keywords)
            self.time(call.args[0], 0.2, 3)

    def time(self, node: ast.AST, low: float, high: float) -> None:
        ms = number(node, low, high) * 1000
        require(abs(ms - round(ms)) < 0.000001 and round(ms) % 200 == 0)
        self.duration_ms += round(ms)
        require(self.duration_ms <= 90000)


def check_source(source: bytes) -> tuple[str, int]:
    if len(source) > POLICY["max_source_bytes"]:
        raise StaticError("DSL_RESOURCE_LIMIT")
    try:
        tree = ast.parse(source.decode("utf-8"), mode="exec")
    except (ValueError, SyntaxError, UnicodeError, RecursionError):
        raise StaticError("DSL_COMPILE_REJECTED") from None
    count = sum(1 for _ in ast.walk(tree))
    if count > POLICY["max_ast_nodes"]:
        raise StaticError("DSL_RESOURCE_LIMIT")
    require(len(tree.body) == 2 and not tree.type_ignores)
    imported, scene = tree.body
    require(isinstance(imported, ast.ImportFrom))
    assert isinstance(imported, ast.ImportFrom)
    require(
        imported.module == "manim"
        and imported.level == 0
        and [a.name for a in imported.names] == POLICY["imports"]
        and not any(a.asname for a in imported.names)
    )
    require(isinstance(scene, ast.ClassDef))
    assert isinstance(scene, ast.ClassDef)
    require(
        scene.name == "DSLScene"
        and len(scene.bases) == 1
        and not scene.keywords
        and not scene.decorator_list
        and len(scene.body) == 1
        and not getattr(scene, "type_params", [])
    )
    require(
        isinstance(scene.bases[0], ast.Name)
        and scene.bases[0].id == "Scene"
        and isinstance(scene.bases[0].ctx, ast.Load)
    )
    construct = scene.body[0]
    require(isinstance(construct, ast.FunctionDef))
    assert isinstance(construct, ast.FunctionDef)
    args = construct.args
    require(
        construct.name == "construct"
        and not construct.decorator_list
        and construct.returns is None
        and construct.type_comment is None
        and not getattr(construct, "type_params", [])
        and not args.posonlyargs
        and not args.kwonlyargs
        and not args.defaults
        and not args.kw_defaults
        and args.vararg is None
        and args.kwarg is None
        and len(args.args) == 1
        and args.args[0].arg == "self"
        and args.args[0].annotation is None
        and args.args[0].type_comment is None
    )
    checker = Checker()
    for statement in construct.body:
        checker.statement(statement)
    require(30000 <= checker.duration_ms <= 90000)
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest(), count


def main() -> None:
    try:
        if (
            f"{sys.version_info.major}.{sys.version_info.minor}"
            not in POLICY["static_python_minors"]
        ):
            raise StaticError("DSL_COMPILE_UNAVAILABLE")

        # Limits apply to the parser/checker, not to the parent API process.
        def limit(kind: int, maximum: int) -> None:
            soft, hard = resource.getrlimit(kind)
            ceiling = min(maximum, hard) if hard != resource.RLIM_INFINITY else maximum
            if soft != resource.RLIM_INFINITY:
                ceiling = min(ceiling, soft)
            resource.setrlimit(kind, (ceiling, ceiling))

        limit(resource.RLIMIT_CPU, 1)
        limit(resource.RLIMIT_STACK, 8 * 1024 * 1024)
        if sys.platform.startswith("linux"):
            limit(resource.RLIMIT_DATA, POLICY["memory_bytes"])
            limit(resource.RLIMIT_AS, POLICY["memory_bytes"])
        limit(resource.RLIMIT_FSIZE, 0)
        limit(resource.RLIMIT_NOFILE, 32)
        source = sys.stdin.buffer.read(POLICY["max_source_bytes"] + 1)
        digest, count = check_source(source)
        print(json.dumps({"ast_sha256": digest, "nodes": count}, separators=(",", ":")))
    except StaticError as error:
        print(json.dumps({"code": str(error)}))
        sys.exit(1)
    except Exception:
        print('{"code":"DSL_COMPILE_UNAVAILABLE"}')
        sys.exit(1)


if __name__ == "__main__":
    main()
