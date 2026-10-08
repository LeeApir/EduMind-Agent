"""Strict bounded JSON and deterministic state simulation for accepted ADR-0010."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, validators  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "data/animation_dsl/v1"
_SCHEMA_BYTES = (CONTRACT / "schema.json").read_bytes()
_POLICY_BYTES = (CONTRACT / "policy.json").read_bytes()
_POLICY = json.loads(_POLICY_BYTES)
POLICY_VERSION = "animation-dsl-policy-v1"
SCHEMA_SHA256 = hashlib.sha256(_SCHEMA_BYTES).hexdigest()
POLICY_SHA256 = hashlib.sha256(_POLICY_BYTES).hexdigest()
VALIDATOR_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# The approved schema uses local refs only; no candidate selects a schema or resolver.
_SCHEMA = json.loads(_SCHEMA_BYTES)
_StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int
    ),
)
_VALIDATOR = _StrictValidator(_SCHEMA)


class DSLValidationError(ValueError):
    def __init__(self, code: str, action_index: int | None = None) -> None:
        super().__init__(code)
        self.code, self.action_index = code, action_index


def _reject(code: str = "DSL_SCHEMA_INVALID", index: int | None = None) -> None:
    raise DSLValidationError(code, index)


def _text(value: str, index: int | None = None) -> None:
    if (
        not value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)
    ):
        _reject(index=index)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _constant(value: str) -> None:
    _reject()


def _decode(raw: bytes | str) -> dict[str, object]:
    if type(raw) not in (bytes, str):
        _reject()
    if len(raw) > _POLICY["max_bytes"]:
        _reject("DSL_RESOURCE_LIMIT")
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > _POLICY["max_bytes"]:
            _reject("DSL_RESOURCE_LIMIT")
        text = encoded.decode("utf-8", errors="strict")
    except UnicodeError:
        raise DSLValidationError("DSL_SCHEMA_INVALID") from None
    if text.startswith("\ufeff"):
        _reject()
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > _POLICY["max_depth"]:
                _reject("DSL_RESOURCE_LIMIT")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _reject()
    try:
        candidate = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except DSLValidationError:
        raise
    except (ValueError, RecursionError):
        raise DSLValidationError("DSL_SCHEMA_INVALID") from None
    if type(candidate) is not dict:
        _reject()
    return cast(dict[str, object], candidate)


@dataclass(frozen=True)
class NodeState:
    id: str
    value: int
    column: int
    row: int
    visited: bool = False
    style: str = "reset"


@dataclass(frozen=True)
class EdgeState:
    id: str
    source: str
    target: str | None
    style: str = "reset"


@dataclass(frozen=True)
class PointerState:
    id: str
    label: str
    target: str | None = None
    style: str = "reset"


@dataclass(frozen=True)
class Comparison:
    left: str
    right: str
    result: str


@dataclass(frozen=True)
class DSLFrame:
    action_index: int
    op: str
    start_ms: int
    end_ms: int
    caption: str
    nodes: tuple[NodeState, ...]
    edges: tuple[EdgeState, ...]
    pointers: tuple[PointerState, ...]
    comparison: Comparison | None
    complexity: tuple[str, str] | None


@dataclass(frozen=True)
class ValidatedDSL:
    """Immutable snapshot; structural validity is never an independent review pass."""

    canonical_json: str
    frames: tuple[DSLFrame, ...]
    duration_ms: int
    dsl_sha256: str
    trace_sha256: str
    schema_sha256: str = SCHEMA_SHA256
    policy_sha256: str = POLICY_SHA256
    validator_sha256: str = VALIDATOR_SHA256
    policy_version: str = POLICY_VERSION

    @property
    def candidate(self) -> dict[str, object]:
        return cast(dict[str, object], json.loads(self.canonical_json))

    @property
    def trace_json(self) -> str:
        return _canonical([asdict(frame) for frame in self.frames])


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _schema(candidate: dict[str, object]) -> None:
    # Schema errors win over maxItems errors at the same layer. Text safety is
    # part of that schema layer, so it is checked before resource-only errors.
    resource = False
    for error in _VALIDATOR.iter_errors(candidate):
        if error.validator == "maxItems":
            resource = True
            continue
        path = tuple(error.absolute_path)
        index = path[1] if len(path) > 1 and path[0] == "actions" else None
        _reject(index=index if type(index) is int else None)

    def strings(value: object, index: int | None = None) -> None:
        if isinstance(value, str):
            _text(value, index)
        elif isinstance(value, dict):
            for item in value.values():
                strings(item, index)
        elif isinstance(value, list):
            for item in value:
                strings(item, index)

    for key, value in candidate.items():
        if key == "actions":
            for i, action in enumerate(cast(list[dict[str, object]], value)):
                strings(action, i)
        else:
            strings(value)
    if resource:
        _reject("DSL_RESOURCE_LIMIT")


def validate_animation_dsl(raw: bytes | str, *, knowledge_point_id: str) -> ValidatedDSL:
    """Validate the complete candidate before exposing any trusted trajectory."""
    candidate = _decode(raw)
    _schema(candidate)
    if (
        type(knowledge_point_id) is not str
        or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", knowledge_point_id)
        or candidate["knowledge_point_id"] != knowledge_point_id
    ):
        _reject("DSL_REFERENCE_INVALID")
    nodes: dict[str, NodeState] = {}
    edges: dict[str, EdgeState] = {}
    pointers: dict[str, PointerState] = {}
    seen: set[str] = set()
    cells: set[tuple[int, int]] = set()
    for pointer in cast(list[dict[str, str]], candidate["pointers"]):
        ident = pointer["id"]
        if ident in seen:
            _reject("DSL_REFERENCE_INVALID")
        seen.add(ident)
        pointers[ident] = PointerState(ident, pointer["label"])
    frames: list[DSLFrame] = []
    total = created_edges = 0
    complexity: tuple[str, str] | None = None
    for i, action in enumerate(cast(list[dict[str, object]], candidate["actions"])):

        def reference(condition: bool) -> None:
            if not condition:
                _reject("DSL_REFERENCE_INVALID", i)

        def resource(condition: bool) -> None:
            if not condition:
                _reject("DSL_RESOURCE_LIMIT", i)

        op = cast(str, action["op"])
        comparison = None
        if op == "create_node":
            ident = cast(str, action["id"])
            cell = (cast(int, action["column"]), cast(int, action["row"]))
            reference(ident not in seen)
            resource(len(nodes) < _POLICY["max_nodes"] and cell not in cells)
            seen.add(ident)
            cells.add(cell)
            nodes[ident] = NodeState(ident, cast(int, action["value"]), *cell)
        elif op == "connect":
            ident = cast(str, action["id"])
            source, target = cast(str, action["source"]), cast(str | None, action["target"])
            reference(ident not in seen and source in nodes)
            reference(target is None or target in nodes)
            reference(source != target)
            reference(not any(e.source == source and e.target == target for e in edges.values()))
            resource(created_edges < _POLICY["max_edges_created"])
            created_edges += 1
            seen.add(ident)
            edges[ident] = EdgeState(ident, source, target)
        elif op == "disconnect":
            ident = cast(str, action["edge"])
            reference(ident in edges)
            del edges[ident]
        elif op == "move_pointer":
            ident, target = cast(str, action["pointer"]), cast(str | None, action["target"])
            reference(ident in pointers and (target is None or target in nodes))
            pointers[ident] = replace(pointers[ident], target=target)
        elif op == "highlight":
            ident, style = cast(str, action["object"]), cast(str, action["style"])
            reference(ident in nodes or ident in edges or ident in pointers)
            if ident in nodes:
                nodes[ident] = replace(nodes[ident], style=style)
            elif ident in edges:
                edges[ident] = replace(edges[ident], style=style)
            else:
                pointers[ident] = replace(pointers[ident], style=style)
        elif op in ("compare", "swap"):
            left, right = cast(str, action["left"]), cast(str, action["right"])
            reference(left in nodes and right in nodes and left != right)
            lv, rv = nodes[left].value, nodes[right].value
            if op == "compare":
                comparison = Comparison(left, right, "lt" if lv < rv else "gt" if lv > rv else "eq")
            else:
                nodes[left], nodes[right] = (
                    replace(nodes[left], value=rv),
                    replace(nodes[right], value=lv),
                )
        elif op == "visit":
            ident = cast(str, action["node"])
            reference(ident in nodes)
            nodes[ident] = replace(nodes[ident], visited=True)
        elif op == "show_complexity":
            complexity = (cast(str, action["time"]), cast(str, action["space"]))
        else:
            _reject(index=i)
        end = total + cast(int, action["duration_ms"]) + cast(int, action["hold_ms"])
        resource(end <= _POLICY["max_duration_ms"])
        frames.append(
            DSLFrame(
                i,
                op,
                total,
                end,
                cast(str, action["caption"]),
                tuple(nodes.values()),
                tuple(edges.values()),
                tuple(pointers.values()),
                comparison,
                complexity,
            )
        )
        total = end
    if total < _POLICY["min_duration_ms"]:
        _reject("DSL_RESOURCE_LIMIT")
    canonical = _canonical(candidate)
    trace = _canonical([asdict(frame) for frame in frames])
    return ValidatedDSL(
        canonical,
        tuple(frames),
        total,
        hashlib.sha256(canonical.encode()).hexdigest(),
        hashlib.sha256(trace.encode()).hexdigest(),
    )
