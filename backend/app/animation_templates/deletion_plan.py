"""Data-only singly linked list deletion plan; no dereference after release."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from app.services.animation_templates import load_template, normalize_parameters


@dataclass(frozen=True)
class DeletionFrame:
    stage: str
    original_values: tuple[int, ...]
    index: int
    head: str | None
    links: tuple[tuple[str, str | None], ...]
    target_visible: bool
    saved_successor: str | None
    show_saved: bool

    def next_of(self, node: str) -> str | None:
        return dict(self.links)[node]


STAGE_IDS = (
    "intro", "before", "save_successor", "relink", "release", "after", "recap",
)
CAPTIONS = (
    "单链表删除：先找到目标、前驱和后继，再安全地调整连接。",
    "删除前，从 head 沿 next 定位目标；不要先释放目标节点。",
    "先保存目标节点的 next；删除尾节点时保存的是 NULL。",
    "再让前驱节点的 next 指向已保存后继；头删则更新 head。",
    "连接已更新，最后释放目标；释放后不能再访问该节点。",
    "删除完成，从 head 沿 next 只会遍历到保留的节点。",
    "记住顺序：保存后继、更新连接、最后释放目标。",
)
CUE_SECONDS = 6


def plan_deletion(values: list[int], index: int) -> tuple[DeletionFrame, ...]:
    spec = load_template("linked-list-deletion")
    validated = normalize_parameters(spec, {"values": values, "index": index})
    original = tuple(cast(list[int], validated["values"]))
    position = cast(int, validated["index"])
    ids = tuple(f"n{i}" for i in range(len(original)))
    links = tuple(
        (node, ids[i + 1] if i + 1 < len(ids) else None) for i, node in enumerate(ids)
    )
    target = ids[position]
    successor = ids[position + 1] if position + 1 < len(ids) else None
    predecessor = ids[position - 1] if position else None
    head_before = ids[0]
    head_after = successor if predecessor is None else head_before
    relinked = dict(links)
    if predecessor is not None:
        relinked[predecessor] = successor
    released = tuple((node, next_node) for node, next_node in relinked.items() if node != target)
    frames = (
        DeletionFrame("intro", original, position, head_before, links, True, None, False),
        DeletionFrame("before", original, position, head_before, links, True, None, False),
        DeletionFrame("save_successor", original, position, head_before, links,
                      True, successor, True),
        DeletionFrame("relink", original, position, head_after, tuple(relinked.items()),
                      True, successor, True),
        DeletionFrame("release", original, position, head_after, released,
                      False, successor, False),
        DeletionFrame("after", original, position, head_after, released,
                      False, successor, False),
        DeletionFrame("recap", original, position, head_after, released,
                      False, successor, False),
    )
    return frames


def srt_for_deletion() -> str:
    lines: list[str] = []
    for number, caption in enumerate(CAPTIONS, start=1):
        start = (number - 1) * CUE_SECONDS
        end = number * CUE_SECONDS
        lines.extend((
            str(number),
            f"00:00:{start:02},000 --> 00:00:{end:02},000",
            caption,
            "",
        ))
    return "\n".join(lines)
