"""Mastery v1 is deterministic and cannot infer mastery from skip or model text."""

import pytest

from app.services.mastery_rules import MasteryFact, MasteryRuleError, reduce_mastery


def quiz(score: float) -> MasteryFact:
    return MasteryFact("quiz_attempt", {"score": score})


def action(kind: str, value: str) -> MasteryFact:
    return MasteryFact(kind, {"action": value})


def test_quiz_and_review_cross_mastered_threshold_reproducibly() -> None:
    facts = [quiz(1.0), quiz(1.0)]
    first = reduce_mastery(facts[:1])
    replayed = reduce_mastery(facts)
    assert first.status == "learning"
    assert first.score == 0.55
    assert replayed == reduce_mastery(facts)
    assert replayed.status == "mastered"
    assert replayed.score > 0.8


def test_consecutive_wrong_answers_reduce_mastery_and_keep_evidence_summary() -> None:
    learned = reduce_mastery([quiz(1.0), quiz(1.0)])
    once_wrong = reduce_mastery([quiz(1.0), quiz(1.0), quiz(0.0)])
    twice_wrong = reduce_mastery([quiz(1.0), quiz(1.0), quiz(0.0), quiz(0.0)])
    assert 0 <= twice_wrong.score < once_wrong.score < learned.score <= 1
    assert twice_wrong.status == "weak"
    assert "wrong_streak=2" in twice_wrong.evidence_summary[0]


def test_hint_and_reexplanation_signal_risk_without_guessing_correctness() -> None:
    baseline = reduce_mastery([quiz(1.0)])
    hinted = reduce_mastery([quiz(1.0), action("hint_used", "hint_level_2")])
    reexplained = reduce_mastery([quiz(1.0), action("reexplanation_requested", "simpler")])
    assert hinted.score < baseline.score
    assert hinted.status == "weak"
    assert reexplained.score == baseline.score
    assert reexplained.status == "weak"


def test_skip_and_mark_known_never_create_mastered_status() -> None:
    skipped = reduce_mastery([action("explicit_feedback", "skip")])
    claimed = reduce_mastery([action("explicit_feedback", "mark_known")])
    assert skipped.score == claimed.score == 0
    assert skipped.status == claimed.status == "weak"


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, "1.0", True])
def test_invalid_or_forged_quiz_score_is_rejected(score: object) -> None:
    with pytest.raises(MasteryRuleError):
        reduce_mastery([MasteryFact("quiz_attempt", {"score": score})])
