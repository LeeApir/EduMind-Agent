"""Independent trace expectations and the exact frame ownership of the new request."""

import json

from app.services import binary_search_course_frames as program
from app.services import binary_search_course_materials as original


def signatures(frames):
    fields = (
        "phase", "iteration", "comparison_frame_id", "line", "left", "right", "mid",
        "comparison", "updated_endpoint", "recomputed_mid", "returned",
    )
    return [tuple(frame[key] for key in fields) for frame in frames]


def test_main_trace_binds_comparison_and_update_in_each_iteration():
    frames, result = program.trace((2, 5, 8, 12, 16), 5)
    assert result == 1
    assert signatures(frames) == [
        ("initial", None, None, 4, 0, 4, None, None, None, False, None),
        ("compare", 1, "f1", 10, 0, 4, 2, "greater", None, True, None),
        ("narrowed", 1, "f1", 13, 0, 1, 2, "greater", "right", False, None),
        ("compare", 2, "f3", 10, 0, 1, 0, "less", None, True, None),
        ("narrowed", 2, "f3", 11, 1, 1, 0, "less", "left", False, None),
        ("found", 3, "f5", 8, 1, 1, 1, "equal", None, True, 1),
    ]
    assert program.note(frames[2], original.MAIN) == (
        "第 1 轮，沿用同轮刚完成的比较：values[2]=8 大于目标 5。"
        "更新 right=mid - 1=1，闭区间变为 [0,1]。此帧保留 mid=2，尚未重新计算。"
    )
    assert program.note(frames[4], original.MAIN) == (
        "第 2 轮，沿用同轮刚完成的比较：values[0]=2 小于目标 5。"
        "更新 left=mid + 1=1，闭区间变为 [1,1]。此帧保留 mid=0，尚未重新计算。"
    )


def test_empty_and_exhausted_intervals_return_without_mid_access():
    empty, result = program.trace((), 5)
    assert result == -1
    assert signatures(empty) == [
        ("initial", None, None, 4, 0, -1, None, None, None, False, None),
        ("missing", None, None, 16, 0, -1, None, None, None, False, -1),
    ]
    exhausted, result = program.trace((5,), 6)
    assert result == -1
    assert signatures(exhausted) == [
        ("initial", None, None, 4, 0, 0, None, None, None, False, None),
        ("compare", 1, "f1", 10, 0, 0, 0, "less", None, True, None),
        ("narrowed", 1, "f1", 11, 1, 0, 0, "less", "left", False, None),
        ("missing", None, None, 16, 1, 0, None, None, None, False, -1),
    ]
    duplicate, result = program.trace((5, 5, 5), 5)
    assert result == 1
    assert signatures(duplicate)[-1] == ("found", 1, "f1", 8, 0, 2, 1, "equal", None, True, 1)


def test_versioned_request_excludes_model_frame_notes_preserving_material_and_practice():
    request = program.request()
    wire = request["text"]["format"]["schema"]
    assert set(wire["required"]) == {"paragraphs", "questions", "summary"}
    assert wire["additionalProperties"] is False
    assert wire["properties"]["questions"] == original.SCHEMA["properties"]["questions"]
    assert "The program owns all frame notes" in request["input"][0]["content"]
    assert "Write one note per" not in request["input"][0]["content"]
    supplied = json.loads(request["input"][1]["content"])
    assert supplied["plan"] == original.outline()
    assert supplied["materials"]["main"]["source"] == original.materials()["main"]["source"]
    assert supplied["materials"]["transfer"] == original.materials()["transfer"]
    assert supplied["materials"]["main"]["frames"][2]["comparison_frame_id"] == "f1"
    assert "step_notes" in original.request()["text"]["format"]["schema"]["required"]


def test_archive_owner_and_database_are_scoped_to_binary():
    from uuid import UUID

    import pytest

    from app.services import course_trial_replay as replay
    from app.services.free_course_snapshots import SnapshotError

    owner = UUID(int=1)
    parent = {"context": {"owner": str(owner)}}
    replay.require_archive_owner("binary-search", parent, owner)
    with pytest.raises(SnapshotError, match="BINARY_FRAMES_OWNER"):
        replay.require_archive_owner("binary-search", parent, UUID(int=2))

    base = "postgresql+asyncpg://127.0.0.1:15437/"
    replay.require_database(base + replay.BINARY_DATABASE, topic="binary-search")
    replay.require_database(base + replay.DATABASE, topic="stack")
    with pytest.raises(SnapshotError, match="TRIAL_REPLAY_DATABASE"):
        replay.require_database(base + replay.DATABASE, topic="binary-search")
    with pytest.raises(SnapshotError, match="TRIAL_REPLAY_DATABASE"):
        replay.require_database(base + replay.BINARY_DATABASE, topic="stack")
