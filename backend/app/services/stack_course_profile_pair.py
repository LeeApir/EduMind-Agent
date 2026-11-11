"""Two synthetic learner profiles for a controlled, fixed-material stack comparison."""

import json
from typing import Any

from app.agents.profile_schema import empty_transient_profile, validate_transient_profile
from app.services import stack_course_materials as stack
from app.services.course_question_stem import PROMPT_VERSION
from app.services.free_course_snapshots import PROFILE_FIELDS, SnapshotError, canonical

VERSION = "stack-learner-evidence-v1"
PROMPT_V2 = "stack-learner-evidence-v2"
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
INSTRUCTION_V2 = """[ROLE] Write one complete lesson in Simplified Chinese.
[GOAL AND EVIDENCE] Teach the exact supplied goal. Use only the supplied learner statements for
prior knowledge and requested focus. Null means unknown. Do not infer C proficiency, learning
style, mastery scores, or background. Do not mention the fixture or the profile label.
[SHARED TEACHING DUTIES] Both lessons must explain the concepts and the reasons that make the
implementation work. Write 4–7 substantive entries in paragraphs. Count that array before
returning; summary, step_notes, and question explanations do not count. Choose your own
paragraph structure and wording. Do not pad, split a point merely to meet the count, or copy code
as a substitute for an explanation.
- Use order and f0 to connect count to the effective prefix, and explain why the last valid
  index is the top only when there is at least one element.
- Use order, push, and f1/f2/f4 to explain why the index used for writing is available before
  incrementing count, and how write-then-increment preserves the effective prefix.
- Use order, pop, and f3 to explain why decrementing count locates the original top slot,
  and how the returned value, the remaining stack, and the new top relate. Use boundary to
  explain why an uncleared old slot is outside the logical stack.
- Use push, pop, and boundary with the actual guard positions to explain why rejection cannot
  mutate the stack or write a pop result. Distinguish bool success from the value through *out.
  The fixed array does not resize. Keep these branches distinct from the successful main trace.
[ADAPTATION] For the learner new to stacks, introduce top, push, pop, and LIFO before relying
on them. Use familiar array slots and walk through the four operations, especially why 8 is
removed and 3 becomes the top. Explain the same implementation reasons in accessible language.
For the learner familiar with stack operations, recap the terms briefly and use the available
space for the count invariant, the reasons for the update order, and failure boundaries. Keep
all five frame notes accurate and distinct. Both lessons may share necessary explanations;
retain useful explanations in the beginner lesson. Adapt emphasis and depth, not the goal,
trace, code, question scenarios, or answers.
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


def request(case: str, *, prompt_version: str = VERSION) -> dict[str, Any]:
    if prompt_version not in (VERSION, PROMPT_V2):
        raise SnapshotError("STACK_PROFILE_PROMPT_VERSION")
    instruction = INSTRUCTION_V2 if prompt_version == PROMPT_V2 else INSTRUCTION
    _, material_rules = stack.INSTRUCTION.split("[PROGRAM MATERIAL]", 1)
    body = stack.fixed_request(
        instruction + "[PROGRAM MATERIAL]" + material_rules,
        stack.GOAL, stack.outline(), stack.materials(), "edumind_stack_lifo_v1", stack.SCHEMA,
        stem_prompt_version=PROMPT_VERSION,
    )
    user = body["input"][1]
    payload = json.loads(user["content"])
    user["content"] = canonical(dict(payload, learner_evidence=learner_input(case))).decode()
    return body
