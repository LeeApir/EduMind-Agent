"""Synthetic role replies for the offline demo; not model or independent truth evidence."""

import json
from typing import Any

import httpx

from scripts.isolated_diagnostics.p15_agent_pilot import (
    GOALS,
    OfflineGateway,
)
from scripts.isolated_diagnostics.p15_head_insertion_engine import QUESTION_KEYS, digest

LABELS = dict(
    caller_head="调用者最终头节点ID",
    traversal_status="从调用者头开始的遍历分类",
    reachable_prefix="首次重复或不确定指针前的可知值前缀",
    allocation_failures="本次合成分配失败次数",
)


def mock_gateway() -> OfflineGateway:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        role = body["stage"].removeprefix("pilot_")
        payload = json.loads(body["messages"][1]["content"])
        value: dict[str, Any]
        if role == "plan":
            value = dict(
                objectives=list(GOALS),
                spec=payload["allowed_spec"],
                coverage=[
                    dict(objective=k, observation_key=v) for k, v in GOALS.items()
                ],
            )
        elif role == "content":
            observation = payload["example"]["observation"]
            refs = [
                dict(path="observation." + k, value=observation[k])
                for k in QUESTION_KEYS
            ]
            value = dict(
                paragraphs=[
                    dict(
                        key="intro",
                        text="区分局部head和调用者caller_head。观察分类为："
                        + observation["traversal_status"]
                        + "。reachable_prefix只记录首次重复或不确定指针前可知的值；"
                        "不能将它当作无限循环或未初始化指针的完整输出。",
                        fact_refs=refs,
                    )
                ],
                questions=[
                    dict(
                        key="q" + str(i),
                        stem=LABELS[k] + "是什么？",
                        observation_key=k,
                        explanation="根据固定完整代码及最终状态读取该观察量。",
                        fact_refs=[refs[i]],
                    )
                    for i, k in enumerate(QUESTION_KEYS)
                ],
            )
        elif role == "repair":
            value = payload["original"]
        elif role == "review":
            value = dict(
                source_digest=digest(payload["source"]),
                verdict="pass",
                scope_status="complete",
                uncertain_reason=None,
                issues=[],
            )
        else:
            raise ValueError("UNSUPPORTED_MOCK_ROLE")
        return httpx.Response(
            200,
            json=dict(
                model_id="mock-pilot",
                value=value,
                usage=dict(input_tokens=10, output_tokens=20),
            ),
        )

    return OfflineGateway(httpx.MockTransport(handler))


def course_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 头插法协作原型（Mock演示）",
        "",
        "仅用于开发流程核对，未经独立质量验收。",
        "",
    ]
    for version in result["versions"]:
        lines.extend([f"## revision {version['identity']['revision']}", ""])
        for block in version["payload"]["blocks"]:
            if block["kind"] == "text":
                lines.extend([block["markdown"], ""])
            elif block["kind"] == "code":
                lines.extend(["```c", block["text"], "```", ""])
            else:
                lines.extend(
                    [
                        block["stem"],
                        "",
                        "开发参考答案："
                        + json.dumps(block["answer_key"], ensure_ascii=False),
                        "",
                        block["explanation"],
                        "",
                    ]
                )
    return "\n".join(lines)
