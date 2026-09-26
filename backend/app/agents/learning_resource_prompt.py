"""Versioned, type-specific instructions for P0 learning resource generation."""

import json

from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
    resource_output_schema,
)

RESOURCE_INSTRUCTION_VERSION = "learning-resources-instructions-v3"

_COMMON_INSTRUCTIONS = """Create exactly one requested learning resource in Chinese.
Return only JSON matching the supplied schema. Use the requested prompt_version unchanged.
Do not claim to execute, compile, or run code; code is display-only. Do not add facts that
are unsupported by the learning context."""

_JSON_SERIALIZATION_INSTRUCTIONS = r"""Serialization contract: emit one complete JSON object,
not Markdown around JSON. All Markdown and source code belong INSIDE JSON string values.
Escape every newline as \n, double quote as \", and backslash as \\ inside strings.
Never put literal line breaks inside a quoted JSON string. For math, prefer plain text;
if using LaTeX, escape its backslashes for JSON (for example \\frac, not \frac).
Do not wrap the response in a ```json fence or add comments/trailing commas. Check that
the whole response parses as JSON before returning; do not claim to have run a parser."""


def explanation_serialization_example() -> str:
    """Use real serialization so the instruction example cannot teach invalid JSON."""
    return json.dumps({
        "resource_type": "explanation",
        "prompt_version": RESOURCE_PROMPT_VERSION,
        "content": {"markdown": '# 示例\n数组下标访问通常为 O(1)。示例字符串："x"。'},
    }, ensure_ascii=False)

_TYPE_INSTRUCTIONS: dict[LearningResourceType, str] = {
    LearningResourceType.EXPLANATION: (
        "Write a short Markdown explanation with a concrete example and only necessary formulas."
    ),
    LearningResourceType.CODE: (
        "Use exactly the requested programming language. Include one source listing, expected "
        "output, and concise key steps; set display_only to true."
    ),
    LearningResourceType.EXERCISE: (
        "Create about three independent exercises (two to four) with a concise answer and "
        "explanation for each item."
    ),
}


def learning_resource_prompt(resource_type: LearningResourceType | str) -> str:
    """Build the versioned system instruction for a single resource type."""
    try:
        normalized_type = LearningResourceType(resource_type)
    except ValueError:
        raise ValueError("Unsupported learning resource type.") from None
    return (
        f"{_COMMON_INSTRUCTIONS}\nPrompt version: {RESOURCE_PROMPT_VERSION}.\n"
        f"Instruction version: {RESOURCE_INSTRUCTION_VERSION}.\n"
        f"Requested resource type: {normalized_type.value}.\n"
        f"{_TYPE_INSTRUCTIONS[normalized_type]}\n{_JSON_SERIALIZATION_INSTRUCTIONS}"
        + "\nRequired output contract (all nested required keys must be present; "
        "use exactly these names and types, including expected_output, key_steps and "
        "display_only for code and answer/explanation for every exercise):\n"
        + json.dumps(resource_output_schema(normalized_type), ensure_ascii=False)
        + (
            "\nSerialization example only; replace its facts with the requested node:\n"
            + explanation_serialization_example()
            if normalized_type is LearningResourceType.EXPLANATION else ""
        )
    )
