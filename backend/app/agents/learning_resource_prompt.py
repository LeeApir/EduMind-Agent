"""Versioned, type-specific instructions for P0 learning resource generation."""

from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
)

_COMMON_INSTRUCTIONS = """Create exactly one requested learning resource in Chinese.
Return only JSON matching the supplied schema. Use the requested prompt_version unchanged.
Do not claim to execute, compile, or run code; code is display-only. Do not add facts that
are unsupported by the learning context."""

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
        f"Requested resource type: {normalized_type.value}.\n"
        f"{_TYPE_INSTRUCTIONS[normalized_type]}"
    )
