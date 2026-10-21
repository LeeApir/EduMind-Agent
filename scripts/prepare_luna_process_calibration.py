"""Build four process-assessment calibration materials without network or credentials.

This is a review draft, not an executable freeze or a human-approved label set.
"""

# ruff: noqa: E402
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import prepare_v49_materials as original
from prepare_luna_admission import capture_review
from acceptance_support.luna_schema_projection import projection
from acceptance_support.qwen_review_budget import canonical, sha

BASE = ROOT / "docs/acceptance/phase-1-luna-process-calibration-r01"
PARENT = ROOT / "docs/acceptance/phase-1-luna-schema-validation-r01"
SPECS = (
    ("cal-01", "screen-complete", "complete", "pass"),
    ("cal-02", "screen-distributed", "distributed", "pass"),
    ("cal-03", "screen-teaching-gap", "teaching-gap", "needs_human"),
    ("cal-04", "screen-assessment-gap", "assessment-gap", "needs_human"),
)
OLD_CONTENT = original.content


def content(kind):
    c = deepcopy(OLD_CONTENT("complete"))
    if kind not in {s[2] for s in SPECS}:
        return OLD_CONTENT(kind)
    # Same explicit process questions in the first three cases. Incorrect
    # propositions are clearly questions, never asserted as teaching facts.
    c["exercise"]["items"] = [
        dict(
            id="q1",
            question="[判断题] 不直接复述讲解：从s=0出发，按代码逐轮推演，先在草稿中推算i=0、i=1两轮各自结束时的s，再判断‘i=1这一轮结束后s=12’是否成立。仅填 T 或 F（T=正确，F=错误）。",
            answer="F",
            explanation="i=0时s=0+3=3；i=1时s=3+8=11，因此题中12不成立。",
        ),
        dict(
            id="q2",
            question="[判断题] 请继续推演循环：找出第一次条件检查失败时的i，判断是否会执行访问a[3]的循环体，再判断‘首次失败时i=4，且此前循环体处理过a[3]’是否成立。仅填 T 或 F（T=正确，F=错误）。",
            answer="F",
            explanation="i=2这一轮后s=15，递增i至3；检查3<3为假，立即退出，不执行a[3]，不是到i=4才退出。",
        ),
        dict(
            id="q3",
            question="[判断题] ‘函数将累计和作为返回值交给调用方，但自身不打印。’仅填 T 或 F（T=正确，F=错误）。",
            answer="T",
            explanation="函数执行return s，没有打印语句。",
        ),
    ]
    if kind == "distributed":
        c["explanation"]["markdown"] = "本节用total追踪数组{3,8,4}求和，返回15，无打印；关键状态在代码步骤中，退出边界在练习解析中。仅覆盖该求和过程，不承诺完整数组节点。"
        c["code"]["key_steps"] = [
            "初始s=0；i=0时先加a[0]=3得到s=3；i=1时加a[1]=8得到s=11；i=2时加a[2]=4得到s=15。",
            "退出边界和是否执行a[3]见q2解析；这里不把内部计划当已交付内容。",
        ]
    if kind == "teaching-gap":
        c["explanation"]["markdown"] = "本节承诺用C实现并追踪数组{3,8,4}求和的关键状态及退出条件，并用题目检查过程掌握。下面给出正确实现，函数返回15，无打印；请自行阅读代码。"
        c["code"]["key_steps"] = ["按所给代码运行。", "返回累计和。"]
        # Do not accidentally repair missing teaching via worked solutions.
        for item in c["exercise"]["items"][:2]:
            item["explanation"] = "答案为F。本题不展示展开的状态表或退出边界推演。"
    if kind == "assessment-gap":
        c["exercise"]["items"] = [
            dict(id="q1", question="[填空题] 3+8+4=____，仅填一个整数。", answer="15", explanation="3+8=11，11+4=15。"),
            dict(id="q2", question="[填空题] 8+4+3=____，仅填一个整数。", answer="15", explanation="8+4=12，12+3=15。"),
            dict(id="q3", question="[判断题] ‘3+8+4=16’，仅填 T 或 F（T=正确，F=错误）。", answer="F", explanation="算术和为15，不是16。"),
        ]
    return c


async def build():
    with patch.object(original, "content", content), patch.object(
        original, "uid", lambda name: str(uuid5(NAMESPACE_URL, "luna-process-calibration-r01:" + name))
    ):
        built, _ = await original.build()
    cases, requests, labels = {}, {}, []
    supported = json.loads((PARENT / "request.json").read_bytes())
    supported_body = json.loads(bytes.fromhex(supported["wire_hex"]))
    for name, old_name, kind, verdict in SPECS:
        case = built[old_name]
        case["provenance"] = "authored after observed Luna failure for criterion calibration; NOT independent/holdout/formal test"
        cases[name] = case
        captured = await capture_review(case)
        body = json.loads(bytes.fromhex(captured["wire_hex"]))
        body["text"]["format"]["schema"], changes = projection(body["text"]["format"]["schema"])
        # This is a derived request preview. Only the earlier full pipeline
        # capture is real MockTransport capture; do not call this live proof.
        for key in ("model", "reasoning", "max_output_tokens", "temperature", "text"):
            assert body[key] == supported_body[key], key
        assert body["input"][0] == supported_body["input"][0]
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        requests[name] = dict(
            wire_hex=raw.hex(), wire_sha256=sha(raw), wire_bytes=len(raw),
            anchor_catalog=captured["anchor_catalog"],
            business_schema_sha256=captured["business_schema_sha256"],
            wire_schema_sha256=sha(canonical(body["text"]["format"]["schema"])),
            projection_profile=changes["profile"],
            target=captured["target"],
            evidence_type="offline original adapter capture followed by same schema projection; derived preview, NOT executable final wire or live route proof",
        )
        labels.append(dict(
            id=name, material_sha256=sha(canonical(case)), proposed_verdict=verdict,
            teaching_evidence="missing explicit original trace and exit teaching across ALL student carriers" if kind == "teaching-gap" else "visible original trace and exit boundary",
            process_assessment="final arithmetic only" if kind == "assessment-gap" else "explicitly requires deriving intermediate state and first failed condition; question form is not a rejection reason",
            independent_human_status="pending", actual_model_result=None,
        ))
    return cases, requests, labels


def review_book(cases):
    lines = ["# 四例完整材料：先独立核对，后查看标签", "", "本册不列拟定结论。先逐例记录教学覆盖、过程考查、事实/安全、引用证据和自己的结论，再对照labels-review.md。Codex制作及离线检查不等于独立人工签核。练习答案和解析属于学生可见材料，必须计入教学覆盖。内部计划仅供审核上下文。", ""]
    for name, case in cases.items():
        m = case["material"]
        visible = {c["role"]: c["envelope"]["content"] for c in m["candidates"]}
        lines += [f"## {name}", "", "### 学生可见正文（完整，不含内部计划）", "", visible["explanation"]["markdown"], "", "```c", visible["code"]["source"], "```", "", visible["code"]["expected_output"], "", "代码关键步骤："]
        lines += ["- " + s for s in visible["code"]["key_steps"]]
        for q in visible["exercise"]["items"]:
            lines += ["", f"**{q['id']}** {q['question']}", "", f"答案：{q['answer']}；解析：{q['explanation']}"]
        lines += ["", "本节没有动画承诺；动作描述不冒充已播放动画。", "", "### 原始目标与实际绑定输入", "", "```json", json.dumps(case["input_snapshot"], ensure_ascii=False, indent=2), "```", "", "### 完整单元（含全部学生内容、内部计划、动作与引用来源）", "", "```json", json.dumps(m, ensure_ascii=False, indent=2), "```", "", "独立记录：教学证据____；考查是否要求推演____；事实/安全问题____；自己的结论及理由____。", ""]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    cases, requests, labels = asyncio.run(build())
    outputs = {"cases.json": cases, "request-previews.json": requests, "proposed-labels.json": dict(status="pending independent human review", calibration_only=True, labels=labels)}
    for name, value in outputs.items():
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        path = BASE / name
        if a.write:
            BASE.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
        elif path.read_text() != raw:
            raise ValueError("DRAFT_CHANGED: " + name)
    book = review_book(cases)
    if a.write:
        (BASE / "materials-review.md").write_text(book)
    else:
        assert (BASE / "materials-review.md").read_text() == book
    print(json.dumps(dict(materials=4, labels_human="pending", real_requests=0, live_authorization=0, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
