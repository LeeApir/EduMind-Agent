"""Resolve a one-sentence goal without inventing course nodes or ambiguous defaults."""

import json
import re
from dataclasses import dataclass
from math import isfinite
from typing import Final

from app.agents.profile_agent import StructuredProfileGateway
from app.services.knowledge_graph import KnowledgeGraphRepository, KnowledgeNode
from app.services.provider_gateway import (
    ChatMessage,
    ProviderError,
    StructuredRequest,
    TaskProfile,
    TextRequest,
)

GOAL_MAPPING_VERSION: Final = "goal-node-v2"
MIN_MAPPING_CONFIDENCE: Final = 0.85
ALIASES: Final = {
    "array": ("数组", "array"),
    "c-pointer": ("C 指针", "C指针", "指针", "c-pointer"),
    "circular-queue": ("循环队列", "circular queue", "circular-queue"),
    "linked-list-concept": ("链表概念", "linked-list-concept"),
    "single-linked-list": ("单链表", "single-linked-list", "singly linked list"),
    "linked-list-insertion": (
        "链表插入",
        "插入链表",
        "单链表头插法",
        "单链表尾插法",
        "头插法",
        "尾插法",
        "linked-list-insertion",
    ),
    "linked-list-deletion": ("链表删除", "删除链表", "linked-list-deletion"),
    "linked-list-traversal": ("链表遍历", "遍历链表", "linked-list-traversal"),
    "stack": ("栈", "stack"),
    "queue": ("队列", "queue"),
}


@dataclass(frozen=True, slots=True)
class GoalNodeResolution:
    node: KnowledgeNode | None
    candidates: tuple[KnowledgeNode, ...]
    reason: str


def _alias_candidates(goal: str, graph: KnowledgeGraphRepository) -> tuple[KnowledgeNode, ...]:
    matches: list[tuple[int, int, str]] = []
    for node_id, aliases in ALIASES.items():
        for alias in aliases:
            pattern = re.escape(alias)
            if alias.isascii():
                pattern = rf"(?<![a-z0-9-]){pattern}(?![a-z0-9-])"
            for match in re.finditer(pattern, goal, flags=re.IGNORECASE):
                matches.append((match.start(), match.end(), node_id))
    ids = {
        node_id
        for start, end, node_id in matches
        if not any(
            other_start <= start and end <= other_end and other_end - other_start > end - start
            for other_start, other_end, _ in matches
        )
    }
    return tuple(node for node_id in sorted(ids) if (node := graph.get_node(node_id)) is not None)


def _teaching_scope(goal: str) -> str:
    """Remove explicit learner background, never arbitrary topics by length.

    Only a marked quoted lesson title establishes a primary scope. Independent
    learning requests outside it are still considered; implementation details
    such as traversal/free functions do not become additional lessons.
    """
    background = r"(?:为)?(?:刚|已经|已)?(?:学完|学过|掌握了)[^，。\n]*?(?:的[^，。\n]*)?[，。]"
    scoped = re.sub(
        background,
        lambda match: match.group()
        if re.search(r"但|不过|同时|还要|学习|想学|讲解|解释|比较|对比", match.group())
        else "",
        goal,
    )
    title = re.search(
        r'(?:生成|设计|制作)(?:一节|一个|一堂)[“「"]([^”」"]+)[”」"](?:微课|课程|课)', scoped
    )
    if title is None:
        return scoped
    remainder = scoped[: title.start()] + scoped[title.end() :]
    # Structural pointer references in the supporting material of a linked-list
    # lesson describe that lesson, not a separate introductory C-pointer topic.
    # Retain every other mention; an unrelated topic in a numbered requirement
    # must not disappear merely because it follows the primary title.
    if "链表" in title.group(1) or "插法" in title.group(1):
        remainder = remainder.replace("链表遍历函数", "遍历函数")
        remainder = re.sub(
            r"(?:头|尾|前驱|后继|节点)指针|指针(?:的)?(?:变化|更新|指向)",
            "节点连接状态",
            remainder,
        )
    return title.group(1) + "。" + remainder


def clarification_payload(
    resolution: GoalNodeResolution, graph: KnowledgeGraphRepository
) -> dict[str, object]:
    messages = {
        "ambiguous_aliases": "检测到多个并列或尚不能确定主次的主题，请选择本次主要教学目标。",
        "multiple_topic_scope": "请求涉及多个主题，请明确本次主要教学目标。",
        "negated_target": "请求包含排除或否定的主题，请明确本次要学习的目标。",
        "generic_linked_list": "链表范围较宽，请选择要学习的具体知识点。",
        "provider_failed": "暂时无法确认学习目标，请从可选知识点中明确一个目标。",
    }
    return {
        "code": "GOAL_CLARIFICATION_REQUIRED",
        "reason": resolution.reason,
        "message": messages.get(resolution.reason, "无法可靠确定学习目标，请选择一个具体知识点。"),
        "retryable": False,
        "candidate_nodes": [
            {"id": node.id, "name": node.name}
            for node in (resolution.candidates or graph.all_nodes())
        ],
    }


async def resolve_goal_node(
    goal: str, *, graph: KnowledgeGraphRepository, gateway: StructuredProfileGateway
) -> GoalNodeResolution:
    scope = _teaching_scope(goal)
    candidates = _alias_candidates(scope, graph)
    if any(marker in goal for marker in ("不想学", "不要讲", "不学", "不讲", "别讲")):
        return GoalNodeResolution(None, candidates, "negated_target")
    generic_list = "链表" in scope or "linked list" in scope.lower()
    if generic_list and candidates and not any("linked-list" in node.id for node in candidates):
        return GoalNodeResolution(None, candidates, "multiple_topic_scope")
    if len(candidates) == 1:
        return GoalNodeResolution(candidates[0], candidates, "explicit_alias")
    if len(candidates) > 1:
        return GoalNodeResolution(None, candidates, "ambiguous_aliases")
    if generic_list:
        options = tuple(
            node
            for node_id in ("linked-list-concept", "single-linked-list")
            if (node := graph.get_node(node_id)) is not None
        )
        return GoalNodeResolution(None, options, "generic_linked_list")
    request = StructuredRequest(
        prompt=TextRequest(
            messages=(
                ChatMessage(
                    role="system",
                    content=(
                        "Map the student's goal to one listed course node only when unambiguous. "
                        "General goals or generic linked-list goals require clarification. "
                        "Never invent a node. Return node_id=null and needs_clarification=true "
                        "if unsure. "
                        f"Version: {GOAL_MAPPING_VERSION}."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "goal": goal,
                            "nodes": [
                                {"id": node.id, "name": node.name} for node in graph.all_nodes()
                            ],
                        },
                        ensure_ascii=False,
                    ),
                ),
            ),
            task_profile=TaskProfile.FAST,
        ),
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["node_id", "confidence", "needs_clarification"],
            "properties": {
                "node_id": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "needs_clarification": {"type": "boolean"},
            },
        },
    )
    try:
        result = await gateway.generate_structured(request, retry_safe=True)
    except ProviderError:
        return GoalNodeResolution(None, (), "provider_failed")
    value = result.value
    confidence = value.get("confidence")
    node_id = value.get("node_id")
    if (
        set(value) != {"node_id", "confidence", "needs_clarification"}
        or value.get("needs_clarification") is not False
        or not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not isfinite(confidence)
        or not MIN_MAPPING_CONFIDENCE <= confidence <= 1
        or not isinstance(node_id, str)
    ):
        return GoalNodeResolution(None, (), "insufficient_confidence")
    node = graph.get_node(node_id)
    if node is None:
        return GoalNodeResolution(None, (), "unknown_candidate")
    return GoalNodeResolution(node, (node,), "validated_candidate")
