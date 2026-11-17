"""Question stems whose C scenario is appended by the program."""

PROMPT_VERSION = "course-question-stem-v2"
FORBIDDEN_MARKERS = ("#include", "```", "~~~", "{", "}", ";")


def with_stem_format(instruction: str, prompt_version: str | None) -> str:
    if prompt_version is None:
        return instruction
    if prompt_version != PROMPT_VERSION:
        raise ValueError(f"Unknown question stem prompt version: {prompt_version}")
    markers = ", ".join(repr(marker) for marker in FORBIDDEN_MARKERS)
    return (
        f"{instruction}\n[QUESTION STEM FORMAT {PROMPT_VERSION}]\n"
        "Each stem must be one nonblank line of Simplified Chinese prose. "
        "Do not include line breaks, even escaped ones in the JSON string.\n"
        "Refer to the code below. The program appends the exact C scenario after the stem. "
        "Do not copy scenario code or include C statements in the stem.\n"
        "No code fences, ASCII braces or ASCII semicolons in a stem. "
        f"The following literal markers are rejected: {markers}.\n"
        "Use square brackets for JSON integer array notation where needed. "
        "Supply the required explanation separately for every question."
    )


def is_single_line_stem(stem: str) -> bool:
    return (
        bool(stem.strip())
        and stem.splitlines() == [stem]
        and not any(marker in stem for marker in FORBIDDEN_MARKERS)
    )
