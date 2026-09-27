"""Versioned, deterministic reduction of committed learning evidence."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Final

MASTERY_RULE_VERSION: Final = "mastery-v1"
MASTERY_RULE_CONFIG: Final[Mapping[str, float]] = MappingProxyType({
    "retention_per_event": 0.98,
    "first_quiz_gain": 0.55,
    "review_quiz_gain": 0.4125,
    "wrong_base_penalty": 0.12,
    "wrong_streak_penalty": 0.08,
    "hint_level_1_penalty": 0.04,
    "hint_level_2_penalty": 0.08,
    "weak_below": 0.4,
    "mastered_at": 0.8,
})


class MasteryRuleError(ValueError):
    """Evidence is not valid for the frozen mastery rule."""


@dataclass(frozen=True, slots=True)
class MasteryFact:
    evidence_type: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class MasteryDecision:
    score: float
    status: str
    evidence_summary: tuple[str, ...]


def _quiz_score(payload: Mapping[str, object]) -> float:
    value = payload.get("score")
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise MasteryRuleError("Quiz evidence has no server score.")
    score = float(value)
    if not isfinite(score) or not 0 <= score <= 1:
        raise MasteryRuleError("Quiz score is outside the supported range.")
    return score


def reduce_mastery(facts: Sequence[MasteryFact]) -> MasteryDecision:
    """Rebuild state from ordered facts without current projection or wall-clock input."""
    if not facts:
        return MasteryDecision(0.0, "unseen", ())
    score = 0.0
    quiz_count = 0
    wrong_streak = 0
    needs_support = False
    summary = ""
    for fact in facts:
        kind = fact.evidence_type
        payload = fact.payload
        if kind == "quiz_attempt":
            earned = _quiz_score(payload)
            score *= MASTERY_RULE_CONFIG["retention_per_event"]
            if earned >= 0.5:
                gain_key = "first_quiz_gain" if quiz_count == 0 else "review_quiz_gain"
                score += earned * MASTERY_RULE_CONFIG[gain_key]
                wrong_streak = 0
                needs_support = False
            else:
                wrong_streak += 1
                score -= (
                    MASTERY_RULE_CONFIG["wrong_base_penalty"]
                    + min(wrong_streak, 3) * MASTERY_RULE_CONFIG["wrong_streak_penalty"]
                )
                needs_support = True
            quiz_count += 1
            summary = f"quiz_score={earned:.4f};wrong_streak={wrong_streak}"
        elif kind == "hint_used":
            action = payload.get("action")
            if action not in {"hint_level_1", "hint_level_2"}:
                raise MasteryRuleError("Hint level is unsupported.")
            score *= MASTERY_RULE_CONFIG["retention_per_event"]
            score -= MASTERY_RULE_CONFIG[f"{action}_penalty"]
            needs_support = True
            summary = str(action)
        elif kind == "reexplanation_requested":
            if payload.get("action") not in {"simpler", "deeper", "different_example"}:
                raise MasteryRuleError("Reexplanation action is unsupported.")
            needs_support = True
            summary = "reexplanation_requested"
        elif kind == "explicit_feedback":
            if payload.get("action") not in {
                "too_easy",
                "too_hard",
                "liked_explanation",
                "skip",
                "mark_known",
            }:
                raise MasteryRuleError("Feedback action is unsupported.")
            if payload.get("action") in {"too_hard", "skip"}:
                needs_support = True
            summary = f"feedback={payload['action']}"
        elif kind == "resource_selected":
            summary = "resource_selected"
        else:
            raise MasteryRuleError("Evidence type is unsupported.")
        score = round(max(0.0, min(1.0, score)), 4)

    if score >= MASTERY_RULE_CONFIG["mastered_at"] and not needs_support:
        status = "mastered"
    elif score < MASTERY_RULE_CONFIG["weak_below"] or needs_support:
        status = "weak"
    else:
        status = "learning"
    return MasteryDecision(score, status, (summary,))
