"""Publication-only objective-answer format gate; legacy schema/scoring stay unchanged."""

import re
from collections.abc import Mapping

_OPTION = re.compile(r"^([A-D])\.\s+(.+)$", re.MULTILINE)
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*|-[1-9][0-9]*)\Z")
_OPEN_RESPONSE = re.compile(r"请(?:说明|解释|证明)|说明理由|写出.*(?:理由|过程)")


def objective_exercise_issues(content: Mapping[str, object]) -> list[dict[str, str]]:
    """Check answerability format, not knowledge correctness or semantic uniqueness."""
    items = content.get("items")
    if not isinstance(items, list) or not 2 <= len(items) <= 4:
        valid = False
    else:
        valid = all(_valid_item(item) for item in items)
    if valid:
        return []
    return [
        {
            "area": "fact",
            "severity": "major",
            "message": "Scored exercises require objective single-answer formats: "
            "[单选题] A-D with four distinct options; [判断题] T/F; "
            "[填空题] one ____ and one canonical integer. State the response format. "
            "No open explanations or multi-part answers; put reasoning in explanation.",
        }
    ]


def _valid_item(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    question, answer = item.get("question"), item.get("answer")
    if not isinstance(question, str) or not isinstance(answer, str):
        return False
    if _OPEN_RESPONSE.search(question):
        return False
    # A why-stem can ask the learner to choose one reason, not write prose.
    if "为什么" in question and not question.startswith("[单选题]"):
        return False
    if question.startswith("[单选题]"):
        options = _OPTION.findall(question)
        return (
            len(options) == 4
            and [label for label, _ in options] == list("ABCD")
            and len({text.strip().casefold() for _, text in options}) == 4
            and answer in list("ABCD")
            and "仅填 A、B、C 或 D" in question
        )
    if question.startswith("[判断题]"):
        return answer in {"T", "F"} and "仅填 T 或 F（T=正确，F=错误）" in question
    if question.startswith("[填空题]"):
        return (
            question.count("____") == 1
            and "仅填一个整数" in question
            and _INTEGER.fullmatch(answer) is not None
        )
    return False


def objective_format_diagnostics(content: Mapping[str, object]) -> list[dict[str, object]]:
    """Fixed format metrics only; never include question, answer or explanation text."""
    items = content.get("items")
    if not isinstance(items, list):
        return [{"items_is_list": False}]
    result: list[dict[str, object]] = []
    for index, item in enumerate(items):
        if _valid_item(item):
            continue
        if not isinstance(item, dict):
            result.append({"index": index, "item_is_object": False})
            continue
        question, answer = item.get("question"), item.get("answer")
        if not isinstance(question, str) or not isinstance(answer, str):
            result.append({"index": index, "question_and_answer_are_strings": False})
            continue
        options = _OPTION.findall(question)
        result.append({
            "index": index,
            "kind": "choice" if question.startswith("[单选题]") else
                    "judgment" if question.startswith("[判断题]") else
                    "integer_fill" if question.startswith("[填空题]") else "unknown",
            "open_response_request": bool(_OPEN_RESPONSE.search(question)),
            "why_non_choice": "为什么" in question and not question.startswith("[单选题]"),
            "option_count": len(options),
            "option_labels_abcd": [label for label, _ in options] == list("ABCD"),
            "distinct_option_count": len({text.strip().casefold() for _, text in options}),
            "blank_count": question.count("____"),
            "choice_suffix_present": "仅填 A、B、C 或 D" in question,
            "judgment_suffix_present": "仅填 T 或 F（T=正确，F=错误）" in question,
            "integer_suffix_present": "仅填一个整数" in question,
            "answer_is_choice_letter": answer in list("ABCD"),
            "answer_is_tf": answer in {"T", "F"},
            "answer_is_canonical_integer": _INTEGER.fullmatch(answer) is not None,
        })
    return result
