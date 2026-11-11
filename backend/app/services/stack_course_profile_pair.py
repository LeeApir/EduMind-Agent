"""Two synthetic learner profiles for a controlled, fixed-material stack comparison."""

import json
from typing import Any

from app.agents.profile_schema import empty_transient_profile, validate_transient_profile
from app.services import stack_course_materials as stack
from app.services.course_question_stem import PROMPT_VERSION
from app.services.free_course_snapshots import PROFILE_FIELDS, canonical

VERSION = "stack-learner-evidence-v1"
CASES = ("array-first", "operations-known")
STATEMENTS = {
    "array-first": "我只掌握数组基础，这是第一次学习栈。",
    "operations-known": "我已理解栈操作，需要解释边界与实现。",
}
INSTRUCTION = """[ROLE] Write one complete lesson in Simplified Chinese.
[GOAL] Teach the exact supplied goal. Treat the synthetic learner's explicit statements as the
only prior-knowledge and explanation-focus evidence. Null means unknown. Do not infer background,
C proficiency, preferences, mastery scores or other traits.
Do not mention the fixture or role label.
When the learner knows only basic arrays and is new to stacks, define top, push, pop and LIFO
before relying on them. Tie the active prefix to the array and explain each transition, especially
why 8 is removed and 3 becomes the top. Explain the implementation boundaries in plain terms.
When the learner already understands stack operations and requests implementation boundaries,
recap the terms briefly. Explain how the count invariant, guard order and bool versus *out
preserve state on failure. Explain why the old slot is not a logical element without clearing it.
Keep the same sequence and learning goal for either profile.
"""


def profile_snapshot(case: str) -> dict[str, Any]:
    statement = STATEMENTS[case]
    record = dict(
        source="learner_statement",
        confidence=1,
        observed_at="2026-11-11T00:00:00+08:00",
        profile_version=1,
    )
    profile = empty_transient_profile(stack.GOAL)
    if case == "array-first":
        profile["knowledge_base"] = dict(statement=statement)
        profile["evidence"] = dict(knowledge_base=[record])
    else:
        profile["knowledge_base"] = dict(statement="我已理解栈操作。")
        profile["learning_goals"] = dict(explanation_focus="需要解释边界与实现。")
        profile["evidence"] = dict(knowledge_base=[record], learning_goals=[record])
    return validate_transient_profile(profile)


def evidence(case: str) -> dict[str, Any]:
    profile = profile_snapshot(case)
    return {
        field: profile.get(field)
        for field in PROFILE_FIELDS
    }


def learner_input(case: str) -> dict[str, Any]:
    return dict(
        version=VERSION,
        source="synthetic_test_profile",
        statement=STATEMENTS[case],
        profile_version=1,
        evidence=evidence(case),
    )


def request(case: str) -> dict[str, Any]:
    _, material_rules = stack.INSTRUCTION.split("[PROGRAM MATERIAL]", 1)
    body = stack.fixed_request(
        INSTRUCTION + "[PROGRAM MATERIAL]" + material_rules,
        stack.GOAL, stack.outline(), stack.materials(), "edumind_stack_lifo_v1", stack.SCHEMA,
        stem_prompt_version=PROMPT_VERSION,
    )
    user = body["input"][1]
    payload = json.loads(user["content"])
    user["content"] = canonical(dict(payload, learner_evidence=learner_input(case))).decode()
    return body
