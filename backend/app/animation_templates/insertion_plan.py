"""Data-only singly linked list insertion plan shared by tests and the Manim scene."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from app.services.animation_templates import load_template, normalize_parameters


@dataclass(frozen=True)
class InsertionFrame:
    stage: str
    original_values: tuple[int, ...]
    value: int
    index: int
    head: str | None
    links: tuple[tuple[str, str | None], ...]
    visible_new: bool

    def next_of(self, node: str) -> str | None:
        return dict(self.links)[node]


STAGE_IDS = (
    "intro", "before", "save_successor", "link_predecessor", "after", "recap",
)
CAPTIONS = (
    "单链表插入：先观察原有连接，再按顺序修改指针。",
    "插入前，从 head 沿 next 到达每个节点；目标位置的原节点是后继。",
    "先让新节点的 next 指向原后继；尾插时后继是 NULL。",
    "再更新前驱节点的 next；头插则更新 head 指向新节点。",
    "插入完成，沿 head 和 next 可以依次访问全部节点。",
    "记住顺序：先连新节点到后继，再连前驱或 head 到新节点。",
)
CUE_SECONDS = 6


def plan_insertion(values: list[int], index: int, value: int) -> tuple[InsertionFrame, ...]:
    spec = load_template("linked-list-insertion")
    validated = normalize_parameters(spec, {"values": values, "index": index, "value": value})
    original = tuple(cast(list[int], validated["values"]))
    position = cast(int, validated["index"])
    inserted = cast(int, validated["value"])
    ids = tuple(f"n{i}" for i in range(len(original)))
    before_links = tuple(
        (node, ids[i + 1] if i + 1 < len(ids) else None) for i, node in enumerate(ids)
    )
    successor = ids[position] if position < len(ids) else None
    previous = ids[position - 1] if position > 0 else None
    initial_head = ids[0] if ids else None
    after_links = dict(before_links)
    after_links["new"] = successor
    if previous is not None:
        after_links[previous] = "new"
    frames = (
        InsertionFrame("intro", original, inserted, position, initial_head, before_links, False),
        InsertionFrame("before", original, inserted, position, initial_head, before_links, False),
        InsertionFrame(
            "save_successor", original, inserted, position, initial_head,
            (*before_links, ("new", successor)), True,
        ),
        InsertionFrame(
            "link_predecessor", original, inserted, position,
            "new" if previous is None else initial_head,
            tuple(after_links.items()), True,
        ),
        InsertionFrame(
            "after", original, inserted, position,
            "new" if previous is None else initial_head,
            tuple(after_links.items()), True,
        ),
        InsertionFrame(
            "recap", original, inserted, position,
            "new" if previous is None else initial_head,
            tuple(after_links.items()), True,
        ),
    )
    return frames


def srt_for_insertion() -> str:
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
