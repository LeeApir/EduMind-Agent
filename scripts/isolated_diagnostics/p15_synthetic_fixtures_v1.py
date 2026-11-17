"""Synthetic response fixtures; not model baseline or independent truth."""

from copy import deepcopy
import json
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_minimal_pilot as minimal
from scripts.isolated_diagnostics.p15_head_insertion_engine import build_actions, build_example


def content() -> dict[str, Any]:
    return dict(
        paragraphs=[dict(
            key="intro", text="区分调用者头、局部头和可知值前缀；循环或未知next不代表有限完整输出。",
            fact_ids=["obs_caller_head", "obs_reachable_prefix"],
        )],
        questions={
            key: dict(stem=minimal.QUESTION_DEFINITIONS[key], explanation="依据固定模板区分观察范围。", fact_ids=["obs_" + key])
            for key in c.QUESTION_KEYS
        },
    )


def baseline(spec: Any) -> dict[str, Any]:
    # This is a local fixture made from the engine, never a model baseline.
    example = build_example(spec)
    groups: dict[str, list[dict[str, Any]]] = dict(states=[], highlights=[], advances=[])
    for order, event in enumerate(build_actions(example, "slot:code")):
        step = event["step"]
        if event["kind"] == "show_state":
            groups["states"].append(dict(order=order, step=step, **c.encode_state(example["trace"]["steps"][step])))
        elif event["kind"] == "highlight_code":
            groups["highlights"].append(dict(order=order, step=step, line=event["line"]))
        else:
            groups["advances"].append(dict(order=order, step=step))
    answers = {key: deepcopy(example["observation"][key]) for key in c.QUESTION_KEYS}
    if answers["caller_head"] is None:
        answers["caller_head"] = "none"
    return dict(
        paragraphs=[dict(key="intro", text="从调用者头观察可知前缀，区分未知指针与终止。")],
        code=example["code"]["source"],
        questions={key: dict(stem=minimal.QUESTION_DEFINITIONS[key], explanation="核对固定模板对应观察。") for key in c.QUESTION_KEYS},
        answers=answers,
        actions=groups,
    )


def envelope(body: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    return dict(
        status="completed", model=body["model"], error=None, incomplete_details=None,
        store=False, tools=[], instructions=body["input"][0]["content"], reasoning=body["reasoning"],
        usage=dict(input_tokens=10, output_tokens=20, total_tokens=30, output_tokens_details=dict(reasoning_tokens=0)),
        output=[dict(type="message", role="assistant", status="completed", content=[
            dict(type="output_text", text=json.dumps(value), annotations=[])
        ])],
    )
