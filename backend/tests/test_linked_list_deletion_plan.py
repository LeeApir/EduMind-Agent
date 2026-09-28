"""Pointer ordering, boundaries and no dereference after deletion release."""

import pytest

from app.animation_templates.deletion_plan import (
    CAPTIONS,
    CUE_SECONDS,
    STAGE_IDS,
    plan_deletion,
    srt_for_deletion,
)
from app.services.animation_templates import TemplateValidationError


@pytest.mark.parametrize("values,index,expected", [
    ([7], 0, []),
    ([1, 2, 3], 0, [2, 3]),
    ([1, 2, 3], 1, [1, 3]),
    ([1, 2, 3], 2, [1, 2]),
])
def test_delete_order_and_final_links(
    values: list[int], index: int, expected: list[int]
) -> None:
    frames = plan_deletion(values, index)
    assert tuple(frame.stage for frame in frames) == STAGE_IDS
    before, saved, relinked, released, after = frames[1:6]
    target = f"n{index}"
    successor = f"n{index + 1}" if index + 1 < len(values) else None
    predecessor = f"n{index - 1}" if index else None
    assert before.next_of(target) == successor
    assert saved.links == before.links
    assert saved.saved_successor == successor and saved.show_saved
    assert target in dict(relinked.links) and relinked.target_visible
    if predecessor is None:
        assert relinked.head == successor
    else:
        assert saved.next_of(predecessor) == target
        assert relinked.next_of(predecessor) == successor
    assert target not in dict(released.links)
    assert not released.target_visible and not released.show_saved
    assert after.links == released.links
    for frame in frames[4:]:
        current, visited = frame.head, []
        while current is not None:
            assert current not in visited and current != target
            visited.append(current)
            current = frame.next_of(current)
        assert [values[int(node[1:])] for node in visited] == expected
    for frame in frames[5:]:
        assert all(node != target and next_node != target for node, next_node in frame.links)


@pytest.mark.parametrize("values,index", [([], 0), ([1], -1), ([1], 1), ([1, 2], 2)])
def test_invalid_delete_never_builds_frames(values: list[int], index: int) -> None:
    with pytest.raises(TemplateValidationError):
        plan_deletion(values, index)


def test_srt_has_seven_synchronized_cues_and_release_warning() -> None:
    blocks = srt_for_deletion().strip().split("\n\n")
    assert len(blocks) == len(STAGE_IDS) == len(CAPTIONS) == 7
    for i, block in enumerate(blocks):
        number, times, caption = block.splitlines()
        assert int(number) == i + 1 and caption == CAPTIONS[i]
        assert times == (
            f"00:00:{i * CUE_SECONDS:02},000 --> "
            f"00:00:{(i + 1) * CUE_SECONDS:02},000"
        )
    assert "释放后不能再访问" in srt_for_deletion()
