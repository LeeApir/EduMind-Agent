"""Build a download from immutable, owner-visible reviewed learning material."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classroom import DebateResult
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.models.learning_state import LearningEvidence
from app.services.owned_learning import published_scenes, visible_unit


class NotesNotFound(ValueError):
    """No owner-visible unit with a reviewed explanation is available."""


def _inline(value: object) -> str:
    """Keep untrusted labels and provenance from creating Markdown/HTML markup."""
    if not isinstance(value, str) or not value.strip():
        return "未记录"
    return escape(" ".join(value.split()), quote=False).replace("\\", "\\\\").replace(
        "`", "\\`"
    ).replace("*", "\\*").replace("_", "\\_").replace("[", "\\[").replace(
        "]", "\\]"
    )


def _time(value: datetime | None) -> str:
    return value.astimezone(timezone.utc).isoformat() if value is not None else "未记录"


def _reviewed_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    # Keep reviewed prose/code while neutralizing raw HTML and active Markdown links.
    return escape(value.strip(), quote=False).replace("[", "\\[").replace("]", "\\]")


def _first_paragraph(markdown: str) -> str:
    paragraphs = [part.strip() for part in markdown.split("\n\n") if part.strip()]
    return next((part for part in paragraphs if not part.startswith("#")), paragraphs[0])


async def _wrong_questions(
    db: AsyncSession, owner_id: UUID, unit_id: UUID,
) -> tuple[list[str], list[tuple[LearningScene, GeneratedResource]]]:
    rows = (await db.execute(
        select(LearningEvidence, GeneratedResource, LearningScene)
        .join(GeneratedResource, GeneratedResource.id == LearningEvidence.resource_id)
        .join(LearningScene, LearningScene.id == GeneratedResource.scene_id)
        .join(LearningUnit, LearningUnit.id == GeneratedResource.learning_unit_id)
        .where(
            LearningEvidence.user_id == owner_id,
            LearningEvidence.learning_unit_id == unit_id,
            LearningEvidence.evidence_type == "quiz_attempt",
            LearningEvidence.resource_version == GeneratedResource.version,
            GeneratedResource.user_id == owner_id,
            GeneratedResource.learning_unit_id == unit_id,
            GeneratedResource.resource_type == "exercise",
            GeneratedResource.review_status == "passed",
            GeneratedResource.published_at.is_not(None),
            LearningScene.learning_unit_id == unit_id,
            LearningScene.review_status == "passed",
            LearningUnit.user_id == owner_id,
            LearningUnit.status == "ready",
        )
        .order_by(LearningEvidence.created_at.desc(), LearningEvidence.id.desc())
    )).all()
    seen: set[tuple[str, str]] = set()
    wrong: list[str] = []
    sources: dict[UUID, tuple[LearningScene, GeneratedResource]] = {}
    for evidence, resource, scene in rows:
        results = evidence.payload.get("question_results")
        items = resource.content.get("items")
        if not isinstance(results, list) or not isinstance(items, list):
            continue
        questions = {
            item["id"]: item["question"] for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), str)
            and isinstance(item.get("question"), str)
        }
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get("question_id"), str):
                continue
            question_id = result["question_id"]
            key = (scene.scene_key, question_id)
            if key in seen:
                continue
            seen.add(key)
            question = questions.get(question_id)
            if result.get("correct") is False and isinstance(question, str) and question.strip():
                sources[resource.id] = scene, resource
                wrong.append(
                    f"- {_inline(question)}（场景 {_inline(scene.scene_key)} v{scene.version}，"
                    f"练习 v{resource.version}）"
                )
    return wrong, list(sources.values())


async def build_markdown_notes(db: AsyncSession, *, owner_id: UUID, unit_id: UUID) -> str:
    """Select reviewed versions once; never generate content or expose evidence payloads."""
    unit = await visible_unit(db, owner_id, unit_id)
    if unit is None:
        raise NotesNotFound
    pairs = await published_scenes(db, owner_id, unit_id)
    current_versions: dict[str, int] = {}
    for scene, _ in pairs:
        current_versions[scene.scene_key] = max(
            current_versions.get(scene.scene_key, 0), scene.version
        )
    selected: dict[tuple[str, str], tuple[LearningScene, GeneratedResource]] = {}
    for scene, resource in pairs:
        if scene.version != current_versions[scene.scene_key]:
            continue
        key = (scene.scene_key, resource.resource_type)
        previous = selected.get(key)
        if previous is None or resource.version > previous[1].version:
            selected[key] = scene, resource
    explanations = sorted(
        (pair for (key, kind), pair in selected.items() if kind == "explanation"
         and _reviewed_text(pair[1].content.get("markdown"))),
        key=lambda pair: (pair[0].scene_order, pair[0].scene_key),
    )
    if not explanations:
        raise NotesNotFound

    lines = ["# 学习笔记", "", f"课程：{_inline(unit.title)}", "",
             f"导出时间：{_time(datetime.now(timezone.utc))}", "", "## 讲解", ""]
    for scene, resource in explanations:
        markdown = _reviewed_text(resource.content.get("markdown"))
        assert markdown is not None
        lines.extend([f"### {_inline(scene.scene_key)}", "", markdown, ""])
    lines.extend(["## 知识点总结（已审核讲解摘录）", ""])
    for scene, resource in explanations:
        markdown = _reviewed_text(resource.content.get("markdown"))
        assert markdown is not None
        lines.extend([f"### {_inline(scene.scene_key)}", "", _first_paragraph(markdown), ""])

    wrong, quiz_sources = await _wrong_questions(db, owner_id, unit_id)
    lines.extend(["## 本人错题摘要", ""])
    lines.extend(wrong or ["暂无错题记录。"])
    lines.append("")

    debate = await db.scalar(select(DebateResult).where(
        DebateResult.user_id == owner_id,
        DebateResult.learning_unit_id == unit_id,
    ).order_by(DebateResult.published_at.desc(), DebateResult.id.desc()).limit(1))
    if debate is not None:
        moderator = debate.content.get("moderator")
        if isinstance(moderator, dict):
            parts = [_reviewed_text(moderator.get(key)) for key in (
                "objective_conclusion", "tradeoffs", "learner_advice",
            )]
            if all(parts):
                lines.extend(["## 已审核多视角总结", ""])
                lines.extend(part for part in parts if part is not None)
                lines.append("")

    lines.extend(["## 内容来源", ""])
    for scene, resource in explanations:
        metadata = resource.generation_metadata or {}
        lines.append(
            f"- 讲解：场景 {_inline(scene.scene_key)} v{scene.version}，资源 v{resource.version}；"
            f"模型 {_inline(metadata.get('model_id'))}；发布时间 {_time(resource.published_at)}。"
        )
    for scene, resource in quiz_sources:
        metadata = resource.generation_metadata or {}
        lines.append(
            f"- 练习：场景 {_inline(scene.scene_key)} v{scene.version}，资源 v{resource.version}；"
            f"模型 {_inline(metadata.get('model_id'))}；发布时间 {_time(resource.published_at)}。"
        )
    if debate is not None:
        lines.append(
            f"- 多视角：场景 {_inline(debate.scene_key)} v{debate.scene_version}；"
            f"生成模型 {_inline(debate.generation_model_id)}；"
            f"发布时间 {_time(debate.published_at)}。"
        )
    return "\n".join(lines) + "\n"
