"""Focused recovery regressions; no DB, Provider, or permissive JSON path."""

import json
from copy import deepcopy

import pytest

from app.services import head_course_materials as m
from app.services.head_course_duplicate_recovery import recover
from scripts.head_course_goal_fixture import content, plan


def sample():
    return content(
        m.content_payload(
            dict(original_goal=m.GOAL, course_id="c", operation_id="o", request_id="r"),
            plan()["plan"],
        )
    )


def encode(value, members):
    return (
        json.dumps({k: v for k, v in value.items() if k != "questions"})[:-1]
        + ',"questions":{'
        + ",".join(json.dumps(k) + ":" + json.dumps(v) for k, v in members)
        + "}}"
    )


def test_identical_and_normal():
    value = sample()
    pairs = list(value["questions"].items())
    result, changes = recover(encode(value, pairs + pairs))
    assert result == value and len(changes) == 4
    assert all(c["occurrence"] == 2 for c in changes)
    assert recover(json.dumps(value)) == (value, [])


@pytest.mark.parametrize("kind", ["stem", "explanation", "type", "extra", "missing"])
def test_conflicts(kind):
    value = sample()
    pairs = list(value["questions"].items())
    other = deepcopy(pairs[0][1])
    if kind in ("stem", "explanation"):
        other[kind] += " changed"
    elif kind == "type":
        other["stem"] = 1
    elif kind == "extra":
        other["extra"] = "x"
    else:
        del other["explanation"]
    with pytest.raises(Exception, match="CONFLICT"):
        recover(encode(value, pairs + [(pairs[0][0], other)]))


@pytest.mark.parametrize(
    "kind", ["third", "outside", "nested", "unknown", "missing", "truncated", "syntax", "constant"]
)
def test_rejections(kind):
    value = sample()
    pairs = list(value["questions"].items())
    text = json.dumps(value)
    if kind == "third":
        text = encode(value, pairs + [pairs[0], pairs[0]])
    if kind == "outside":
        text = text[:-1] + ',"lifecycle":' + json.dumps(value["lifecycle"]) + "}"
    if kind == "nested":
        text = text.replace('"stem":', '"stem":"x","stem":', 1)
    if kind == "unknown":
        text = encode(value, pairs + [("unknown", pairs[0][1]), ("unknown", pairs[0][1])])
    if kind == "missing":
        text = encode(value, pairs[1:])
    if kind == "truncated":
        text = text[:-1]
    if kind == "syntax":
        text = text[:-1] + ",}"
    if kind == "constant":
        text = text.replace('"lifecycle":', '"lifecycle": NaN,"unused":', 1)
    with pytest.raises(Exception):
        recover(text)
