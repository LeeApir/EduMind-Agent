"""Pointer update order, boundaries and synchronized captions for insertion."""

import re

import pytest

from app.animation_templates.insertion_plan import (
    CAPTIONS,
    CUE_SECONDS,
    STAGE_IDS,
    plan_insertion,
    srt_for_insertion,
)
from app.services.animation_templates import TemplateValidationError


@pytest.mark.parametrize("values,index,value,expected", [
    ([], 0, 7, [7]),
    ([1, 2], 0, 7, [7, 1, 2]),
    ([1, 2], 1, 7, [1, 7, 2]),
    ([1, 2], 2, 7, [1, 2, 7]),
])
def test_insert_step_pointer_order(
    values: list[int], index: int, value: int, expected: list[int]
) -> None:
    frames = plan_insertion(values, index, value)
    assert tuple(frame.stage for frame in frames) == STAGE_IDS
    before, save, link, after = frames[1:5]
    successor = f"n{index}" if index < len(values) else None
    assert before.head == ("n0" if values else None)
    assert "new" not in dict(before.links)
    assert save.head == before.head
    assert save.next_of("new") == successor
    if index > 0:
        predecessor = f"n{index - 1}"
        assert save.next_of(predecessor) == successor
        assert link.next_of(predecessor) == "new"
    else:
        assert link.head == "new"
    assert link.next_of("new") == successor
    assert after.links == link.links
    current = after.head
    visited = []
    while current is not None:
        assert current not in visited
        visited.append(current)
        current = after.next_of(current)
    actual = [value if node == "new" else values[int(node[1:])] for node in visited]
    assert actual == expected


@pytest.mark.parametrize("values,index", [([], 1), ([1], -1), ([1], 2), (list(range(8)), 0)])
def test_invalid_insert_never_builds_frames(values: list[int], index: int) -> None:
    with pytest.raises(TemplateValidationError):
        plan_insertion(values, index, 4)


def test_srt_has_six_nonoverlapping_synchronized_cues() -> None:
    srt = srt_for_insertion()
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == len(STAGE_IDS) == len(CAPTIONS) == 6
    for i, block in enumerate(blocks):
        number, times, caption = block.splitlines()
        assert int(number) == i + 1
        assert caption == CAPTIONS[i]
        start = i * CUE_SECONDS
        end = (i + 1) * CUE_SECONDS
        assert times == f"00:00:{start:02},000 --> 00:00:{end:02},000"
        assert re.search(r"[\u4e00-\u9fff]", caption)
    assert blocks[-1].splitlines()[1].endswith("00:00:36,000")
