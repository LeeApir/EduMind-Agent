"""Versioned lightweight rules for tiered classroom-speech review.

Ordinary classroom speech is classified deterministically without a provider
call: low-risk speech streams temporary tokens and is committed, while
high-risk speech (instruction hijack, over-privileged request, or dangerous
generated content) is escalated to the ReviewAgent before anything is
published. Rules are pure and versioned so a replay of the same text always
reaches the same verdict.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

SPEECH_RULES_VERSION: Final = "classroom-speech-rules-v1"

# Student-input markers for jailbreak / instruction-hijack attempts.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"忽略(?:所有|之前|上述|任何)?(?:的)?(?:指令|规则|提示|要求)", re.IGNORECASE),
    re.compile(
        r"ignore\s+(?:all|previous|above|any)\s+(?:instructions|rules|prompts?)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:系统提示|system\s*prompt|提示词|开发者模式|developer\s*mode)", re.IGNORECASE),
    re.compile(r"(?:角色扮演|扮演(?:一个)?(?:任何|其他)?角色|越狱|jailbreak)", re.IGNORECASE),
    re.compile(r"泄露(?:你的)?(?:系统提示|提示词|指令|规则)", re.IGNORECASE),
)

# Student-input markers for over-privileged or credential-seeking requests.
_OVERPOWERED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:执行|运行)(?:这段|以下|一个)?(?:代码|命令|脚本|程序)", re.IGNORECASE),
    re.compile(
        r"(?:获取|查看|泄露)(?:你的)?(?:密钥|密码|api\s*key|api_?key|令牌|token)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:删除|清空|格式化)(?:数据库|所有文件|整个磁盘)", re.IGNORECASE),
    re.compile(r"(?:写|编写)(?:一个)?(?:病毒|恶意程序|木马|蠕虫)", re.IGNORECASE),
)

# Prohibited execution / I/O primitives that must never appear in generated speech.
_DANGEROUS_CODE = re.compile(
    r"\b(?:__import__|eval|exec|os\.system|subprocess(?:\.|\b)|socket(?:\.|\b)|requests(?:\.|\b))\b"
)


class SpeechRisk(StrEnum):
    LOW = "low"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class SpeechVerdict:
    """A deterministic risk decision; reasons are stable, content-free categories."""

    risk: SpeechRisk
    reasons: tuple[str, ...]

    @property
    def escalated(self) -> bool:
        return self.risk is SpeechRisk.ESCALATE


_LOW_RISK = SpeechVerdict(SpeechRisk.LOW, ())


def classify_student_speech(text: str) -> SpeechVerdict:
    """Classify the student's own message for hijack or over-privileged requests."""
    reasons: list[str] = []
    if any(pattern.search(text) for pattern in _INJECTION_PATTERNS):
        reasons.append("instruction_hijack")
    if any(pattern.search(text) for pattern in _OVERPOWERED_PATTERNS):
        reasons.append("over_privileged_request")
    if not reasons:
        return _LOW_RISK
    return SpeechVerdict(SpeechRisk.ESCALATE, tuple(reasons))


def classify_tutor_turn(text: str) -> SpeechVerdict:
    """Classify a generated turn for prohibited execution or I/O suggestions."""
    if _DANGEROUS_CODE.search(text):
        return SpeechVerdict(SpeechRisk.ESCALATE, ("dangerous_content",))
    return _LOW_RISK


def combined_speech_verdict(*verdicts: SpeechVerdict) -> SpeechVerdict:
    """Union of student-input and turn verdicts; any escalation escalates the turn."""
    reasons: list[str] = []
    for verdict in verdicts:
        reasons.extend(verdict.reasons)
    deduped = tuple(dict.fromkeys(reasons))
    if not deduped:
        return _LOW_RISK
    return SpeechVerdict(SpeechRisk.ESCALATE, deduped)
