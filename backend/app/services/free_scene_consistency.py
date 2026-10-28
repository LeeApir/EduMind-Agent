"""Bounded, source-bound consistency observations, never semantic approval or hard gates."""

import re
from collections import defaultdict
from typing import Any

from pycparser import c_ast, c_parser  # type: ignore[import-untyped]

from app.services.free_course_snapshots import canonical, digest
from app.services.free_scene_pointer_trace import trace_c
from app.services.free_scene_question_scope import (
    finite_answer,
    modifies_program,
    question_scope,
    solution_claims_cycle,
)
from app.services.free_scene_semantics import _without_comments, inspect_c

VERSION = "free-scene-consistency-v2"
MAX_UNITS = 16
MAX_FINDINGS = 24
MAX_FUNCTIONS = 64


def _code_units(raw: dict[str, Any], inputs: dict[str, Any]) -> list[dict[str, Any]]:
    units = []
    sections = [("/candidate", raw["blocks"], None)] + [
        (f"/upstream/{i}/content", u["content"].get("blocks", []), u)
        for i, u in enumerate(inputs["upstream"])
    ]
    for root, blocks, upstream in sections:
        for i, b in enumerate(blocks):
            if b.get("kind") == "code" and b.get("language") == "c":
                units.append(
                    dict(
                        pointer=f"{root}/blocks/{i}/source",
                        code=b["source"],
                        anchor_id=b["anchor_id"],
                        upstream=upstream is not None,
                        scene_version_id=upstream["scene_version_id"] if upstream else None,
                        content_digest=upstream["digest"] if upstream else None,
                    )
                )
    return units


def _texts(raw: dict[str, Any]) -> list[tuple[str, str, str]]:
    fields = []
    for i, b in enumerate(raw["blocks"]):
        if b["kind"] == "text":
            fields.append((f"/candidate/blocks/{i}/markdown", b["markdown"], "prose"))
        elif b["kind"] == "exercise":
            fields.append((f"/candidate/blocks/{i}/question", b["question"], "prose"))
            for j, q in enumerate(b["items"]):
                fields.append(
                    (f"/candidate/blocks/{i}/items/{j}/question", q["question"], "question")
                )
                fields.append((f"/candidate/blocks/{i}/items/{j}/solution", q["solution"], "prose"))
        elif b["kind"] == "visualization":
            for j, step in enumerate(b["steps"]):
                fields.append(
                    (f"/candidate/blocks/{i}/steps/{j}/caption", step["caption"], "visual")
                )
    return fields


def _reference(unit: dict[str, Any]) -> dict[str, Any]:
    return dict(
        source_pointer=unit["pointer"],
        source_sha256=unit["inspection"]["source_sha256"],
        scene_version_id=unit["scene_version_id"],
        content_digest=unit["content_digest"],
    )


def _statement_calls(code: str) -> list[tuple[str, str]]:
    """Only called after bounded inspect_c succeeded. No preprocessor or C execution."""
    text = "\n".join(
        "" if line.lstrip().startswith("#") else line
        for line in _without_comments(code).splitlines()
    )
    tree = c_parser.CParser().parse(text, filename="<scene-memory>")
    calls = []
    stack = [(tree, None)]
    while stack:
        node, parent = stack.pop()
        if isinstance(node, c_ast.FuncCall) and isinstance(node.name, c_ast.ID):
            statement = isinstance(parent, c_ast.Compound) or (
                isinstance(parent, (c_ast.If, c_ast.For, c_ast.While, c_ast.DoWhile))
                and node
                in (
                    getattr(parent, "stmt", None),
                    getattr(parent, "iftrue", None),
                    getattr(parent, "iffalse", None),
                )
            )
            if statement:
                quote = code.splitlines()[node.coord.line - 1].strip()
                calls.append((node.name.name, quote))
        stack.extend((child, node) for _, child in node.children())
    return calls


def _question_calls(text: str, name: str) -> tuple[list[str], bool]:
    """Parse candidate C-call fragments as expressions, rather than matching arbitrary names."""
    scope = question_scope(text)
    if scope in (
        "local_checkpoint",
        "deliberate_discard_or_fault",
        "bounded_or_distinct_observation",
        "unspecified",
    ):
        return [], bool(re.search(r"\b" + re.escape(name) + r"\s*\(", text))
    calls = []
    unassessed = False
    for match in re.finditer(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"\s*\(", text):
        start, index, depth = match.start(), match.end(), 1
        # Bounded fragments only; nested/string-rich C expressions remain unassessed here.
        while index < len(text) and index - start < 300 and depth:
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
            index += 1
        if depth:
            unassessed = True
            continue
        prefix = text[max(0, start - 80) : start].rstrip()
        if (
            re.search(r"(?<![=<>!])=(?!=)\s*$", prefix)
            or re.search(r"\breturn\s*$", prefix)
            or re.search(r"(?:(?<![=<>!])=(?!=)|\breturn)\s*(?:\([^)]{0,60}\)\s*)+\(?\s*$", prefix)
            or re.search(r"(?:(?<![=<>!])=(?!=)|\breturn)\s*\(\s*$", prefix)
        ):
            continue
        fragment = text[start:index]
        if '"' in fragment or "'" in fragment or text[index:].lstrip().startswith("{"):
            unassessed = True
            continue
        try:
            tree = c_parser.CParser().parse("void probe(void){" + fragment + ";}")
            statement = tree.ext[0].body.block_items[0]
            if isinstance(statement, c_ast.FuncCall):
                calls.append(fragment)
        except (c_parser.ParseError, RecursionError):
            unassessed = True
    return calls, unassessed


def check_consistency(raw: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """The caller supplies a structurally valid candidate. Nothing here rewrites or rejects it."""
    units = _code_units(raw, inputs)
    report: dict[str, Any] = dict(
        version=VERSION,
        source_digest=digest("scene-consistency-source", raw=raw, inputs=inputs),
        status="not_assessed",
        semantic_correctness_verified=False,
        execution_performed=False,
        disposition="advisory_only",
        findings=[],
        reference_answer_checks=[],
        question_scope_checks=[],
        pointer_relation_observations=[],
        coverage=dict(
            complete=False,
            parsed_units=0,
            unassessed_units=[],
            unassessed_texts=[],
            unassessed_pointer_paths=[],
            limits_reached=False,
            supported_rules=[
                "returned-head-call",
                "local-pointer-claim",
                "interface-conflict",
                "cycle-finite-answer-conflict",
            ],
        ),
    )
    coverage, findings = report["coverage"], report["findings"]
    if len(units) > MAX_UNITS:
        coverage["limits_reached"] = True
        coverage["unassessed_units"].append(dict(reason="code_unit_limit"))
    functions: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for unit in units[:MAX_UNITS]:
        inspection = inspect_c(unit["code"])
        unit["inspection"] = inspection
        if inspection["status"] != "parsed":
            coverage["unassessed_units"].append(
                dict(source_pointer=unit["pointer"], reason=inspection["reason"])
            )
            continue
        coverage["parsed_units"] += 1
        for fn in inspection["interfaces"]:
            if len(fn["name"]) > 128 or sum(map(len, functions.values())) >= MAX_FUNCTIONS:
                coverage["limits_reached"] = True
                continue
            functions[fn["name"]].append((fn, unit))

    def add(
        code: str,
        pointer: str,
        quote: str,
        message: str,
        related: list[dict[str, Any]],
        supporting: list[dict[str, Any]] | None = None,
    ) -> None:
        if len(findings) >= MAX_FINDINGS:
            coverage["limits_reached"] = True
            return
        row = dict(
            rule_id=f"{VERSION}:{code}",
            code=code,
            status="needs_review",
            source_pointer=pointer,
            evidence_quote=quote[:240],
            message=message,
            related_code=related[:2],
            confirmed=False,
            supporting_evidence=supporting or [],
        )
        if row not in findings:
            findings.append(row)

    usable = {}
    for name, definitions in functions.items():

        def signature(f: dict[str, Any]) -> bytes:
            return canonical(
                dict(
                    pointer_depths=[p["pointer_depth"] for p in f["parameters"]],
                    returns=f["return_pointer_depth"],
                    rebinding=[
                        i
                        for i, p in enumerate(f["parameters"])
                        if p["name"] in f["return_rebinding_parameters"]
                    ],
                )
            )

        contracts = {signature(f) for f, _ in definitions}
        if len(contracts) > 1:
            current = next(((f, u) for f, u in definitions if not u["upstream"]), definitions[0])
            add(
                "INTERFACE_CONVENTION_CONFLICT",
                current[1]["pointer"],
                current[1]["code"][:240],
                "同名函数在当前/必要上游中的声明或返回约定不同，请核对变更与跨场景引用。",
                [_reference(u) for _, u in definitions],
            )
        selected = [d for d in definitions if not d[1]["upstream"]] or definitions
        selected_contracts = {signature(f) for f, _ in selected}
        if len(selected_contracts) == 1:
            usable[name] = selected[0]

    applicable = any(
        f["return_rebinding_parameters"] or any(p["pointer_depth"] == 1 for p in f["parameters"])
        for f, _ in usable.values()
    )
    coverage["applicable_interface_patterns"] = applicable
    for unit in units[:MAX_UNITS]:
        if unit.get("inspection", {}).get("status") != "parsed" or unit["upstream"]:
            continue
        for name, quote in _statement_calls(unit["code"]):
            if name in usable and usable[name][0]["return_rebinding_parameters"]:
                add(
                    "RETURNED_HEAD_NOT_CAPTURED",
                    unit["pointer"],
                    quote,
                    "此接口的受支持语法模式返回新头，但该调用作为独立语句丢弃返回值；请核对调用者更新意图。",
                    [_reference(usable[name][1])],
                )

    cyclic_functions: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for unit in units[:MAX_UNITS]:
        if unit.get("inspection", {}).get("status") != "parsed" or unit["upstream"]:
            continue
        observation = trace_c(unit["code"])
        report["pointer_relation_observations"].append(
            dict(**_reference(unit), observation=observation)
        )
        for fn in observation["functions"]:
            if fn["status"] == "not_assessed":
                coverage["unassessed_pointer_paths"].append(
                    dict(
                        source_pointer=unit["pointer"], function=fn["function"], reason=fn["reason"]
                    )
                )
        cyclic_functions.extend(
            (f, unit) for f in observation["functions"] if f["status"] == "cycle_on_supported_path"
        )
    for i, block in enumerate(raw["blocks"]):
        if block["kind"] != "exercise":
            continue
        for j, question in enumerate(block["items"]):
            root = f"/candidate/blocks/{i}/items/{j}"
            text = question["question"]
            scope = question_scope(text)
            mutation = modifies_program(text)
            if len(report["question_scope_checks"]) >= 16:
                coverage["limits_reached"] = True
            else:
                report["question_scope_checks"].append(
                    dict(
                        source_pointer=root + "/question",
                        scope=scope,
                        program_variant_in_prose=mutation,
                        semantic_verified=False,
                    )
                )
            if mutation:
                coverage["unassessed_texts"].append(
                    dict(
                        source_pointer=root + "/question",
                        reason="prose_program_mutation_not_executed",
                    )
                )
            answer = finite_answer(question)
            if scope != "full_traversal" or answer is None:
                continue
            cycle_claim = solution_claims_cycle(question["solution"])
            traced = [
                (fn, unit)
                for fn, unit in cyclic_functions
                if not mutation
                and re.search(r"(?<![=<>!])=(?!=)\s*" + re.escape(fn["function"]) + r"\s*\(", text)
            ]
            if cycle_claim or traced:
                supporting = [
                    dict(
                        source_pointer=root + "/answer_key",
                        evidence_quote=question["answer_key"],
                        role="candidate_key_not_truth",
                    )
                ]
                if cycle_claim:
                    supporting.append(
                        dict(
                            source_pointer=root + "/solution",
                            evidence_quote=question["solution"][:240],
                            role="solution_asserts_cycle_not_execution_proof",
                        )
                    )
                add(
                    "CYCLE_FINITE_SEQUENCE_CONFLICT",
                    root + "/question",
                    text,
                    "题目要求完整遍历到表尾，但所选答案是有限序列；解析声称有环或受限指针关系观察到环。请核对终止条件、实际代码变体与选项，不能把自环截为一个元素。",
                    [_reference(unit) for _, unit in traced],
                    supporting,
                )
    for pointer, text, kind in _texts(raw):
        if kind == "question":
            for name, (fn, unit) in usable.items():
                if fn["return_rebinding_parameters"]:
                    calls, unassessed = _question_calls(text, name)
                    if unassessed:
                        coverage["unassessed_texts"].append(
                            dict(
                                source_pointer=pointer,
                                reason="unsupported_or_deliberate_call_context",
                            )
                        )
                    for quote in calls:
                        add(
                            "QUESTION_RETURN_CONVENTION",
                            pointer,
                            quote,
                            "题干调用丢弃了新头返回值；请按准确C接口核对参考答案，不能暗补调用者赋值。",
                            [_reference(unit)],
                        )
        if kind != "prose":
            continue
        for paragraph in text.split("\n\n"):
            if (
                not re.search(r"函数返回后|调用者|main|caller|after.*function", paragraph, re.I)
                or not re.search(r"永久|无法再访问|permanently|loses?", paragraph, re.I)
                or re.search(
                    r"不会|并不|不影响|仍可|局部副本|唯一保存的入口|does not|still.*access",
                    paragraph,
                    re.I,
                )
            ):
                continue
            for _, (fn, unit) in usable.items():
                for p in fn["parameters"]:
                    name = p["name"]
                    if p["pointer_depth"] != 1 or not name:
                        continue
                    pattern = r"\b" + re.escape(name) + r"\s*=\s*" + re.escape(name) + r"\s*->"
                    if re.search(pattern, paragraph):
                        add(
                            "LOCAL_POINTER_CALLER_CLAIM",
                            pointer,
                            paragraph,
                            "存在传值指针形参与‘移动后调用者永久失去入口’的描述，请区分局部副本和调用者变量。",
                            [_reference(unit)],
                        )
                        break
    for i, block in enumerate(raw["blocks"]):
        if block["kind"] != "exercise":
            continue
        for j, question in enumerate(block["items"]):
            pointer = f"/candidate/blocks/{i}/items/{j}"
            related = [f["code"] for f in findings if f["source_pointer"] == pointer + "/question"]
            report["reference_answer_checks"].append(
                dict(
                    question_id=question["question_id"],
                    source_pointer=pointer + "/answer_key",
                    answer_digest=digest(
                        "consistency-reference-answer", answer=question["answer_key"]
                    ),
                    status="requires_review" if related else "not_assessed",
                    related_rules=related,
                    answer_verified=False,
                )
            )
    if findings:
        report["status"] = "needs_review"
    elif (
        applicable
        and coverage["parsed_units"]
        and not coverage["unassessed_units"]
        and not coverage["unassessed_texts"]
        and not coverage["unassessed_pointer_paths"]
        and not coverage["limits_reached"]
    ):
        report["status"] = "no_conflict_detected_in_supported_rules"
    if len(canonical(report)) > 32768:
        return dict(
            version=VERSION,
            source_digest=report["source_digest"],
            status="not_assessed",
            semantic_correctness_verified=False,
            execution_performed=False,
            disposition="advisory_only",
            findings=[],
            coverage=dict(complete=False, limits_reached=True, reason="report_size_limit"),
        )
    return report
