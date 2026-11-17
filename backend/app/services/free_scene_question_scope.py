"""Explicit observation scopes and source-quoted answer contradictions, not NL execution."""

import re
from typing import Any


def question_scope(text: str) -> str:
    if re.search(
        r"(?:函数内|函数内部|inside.{0,20}function).{0,80}"
        r"(?:这一句后|此句后|这条语句后|中间状态|immediately after)",
        text,
        re.I,
    ):
        return "local_checkpoint"
    if re.search(
        r"(?:均?未|没有|不)(?:接住|接收|保存).{0,5}返回值|忽略返回值|丢弃返回值|错误(?:写法|调用)|错误地|故意|"
        r"仅作反例|incorrect|discard|ignore.{0,20}return|without.{0,20}captur",
        text,
        re.I,
    ):
        return "deliberate_discard_or_fault"
    if re.search(
        r"前[0-9一二三四五六七八九十]+(?:步|次|个)|(?:最先|最初|首次|第一次)|去重|不同的?(?:结点|节点|数据)|"
        r"distinct|first\s+\d+|at most\s+\d+",
        text,
        re.I,
    ):
        return "bounded_or_distinct_observation"
    if re.search(
        r"从.{0,16}(?:表头|head|首结点).{0,12}(?:表尾|NULL)|(?:完整|直到\s*NULL|"
        r"full).{0,20}(?:遍历|travers|sequence)|travers.{0,30}until\s*NULL|"
        r"(?:遍历|输出).{0,15}(?:序列|结果)",
        text,
        re.I,
    ):
        return "full_traversal"
    if re.search(r"调用者|main|最终|最后|新的?\s*head|结果|序列|caller|final", text, re.I):
        return "caller_result"
    return "unspecified"


def modifies_program(text: str) -> bool:
    return bool(
        re.search(
            r"(?:若把|如果把|若将|如果将).{0,100}(?:改为|改成|交换)|\b(?:swap|replace)\b",
            text,
            re.I,
        )
    )


def finite_answer(question: dict[str, Any]) -> str | None:
    key = question["answer_key"].strip()
    options = re.findall(
        r"(?:^|\s)([A-F])[.:、]\s*(.*?)(?=\s+[A-F][.:、]|$)", question["question"], re.S
    )
    if re.fullmatch(r"[A-F]", key):
        selected = [value.strip() for label, value in options if label == key]
        if len(selected) != 1:
            return None
        key = selected[0]
    if len(key) > 128:
        return None
    return (
        key
        if re.fullmatch(
            r"(?:NULL|空表|空链表|[+-]?\d+(?:\s*(?:,|，|->|→)\s*[+-]?\d+)*(?:\s*(?:->|→)\s*NULL)?)",
            key,
            re.I,
        )
        else None
    )


def solution_claims_cycle(solution: str) -> bool:
    # An explicit quoted claim is evidence of an internal contradiction, not proof of C behavior.
    pattern = (
        r"(?:形成|构成|出现|产生)(?:了)?(?:一个)?自环|next\s*(?:指向|指回)(?:了)?"
        r"(?:p\s*)?自身|(?:forms?|creates?)\s+(?:a\s+)?(?:self[- ]loop|cycle)"
    )
    for sentence in re.split(r"[。；;\n]", solution):
        for match in re.finditer(pattern, sentence, re.I):
            prefix = sentence[: match.start()]
            if re.search(r"(?:不(?:会|曾|再)?|没有|并未|并不|未|not|never|no)\s*$", prefix, re.I):
                continue
            if re.search(r"如果|假如|若|\bif\b|unless|otherwise", prefix, re.I):
                continue
            return True
    return False
