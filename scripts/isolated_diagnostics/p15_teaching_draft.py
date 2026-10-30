"""Create a clearly attributed offline wording revision of T095, not a model output."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC
from scripts.isolated_diagnostics.p15_head_insertion_engine import digest

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = (
    ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01/results/candidate.json"
)
ORIGINAL_SHA = "3ae6a9b365c6893094b279fb07bc2db9a1253707bed88da2bec7d9c2124751a3"


def revise() -> dict[str, Any]:
    raw = ORIGINAL.read_bytes()
    c.require(hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA, "ORIGINAL_CHANGED")
    original = json.loads(raw)
    c.verify_artifact(original)
    value = deepcopy(original["raw_output"])
    texts = {
        "overview": "本例演示单链表头插：初始结点 i0 的值为 9，依次插入 1 和 2。这里假定两次实际分配都成功；规格中的成功标记只允许调用 malloc，并不保证真实分配成功。i0 是初始的栈上结点，t0、t1 是两次新结点的轨迹标签，并不是代码中的变量名。",
        "first_insertion": "第一次调用先分配 t0；其 data 和 next 在写入前未知。随后把 data 设为 1，再令 p->next 指向原头 i0。函数返回 p，调用者接回后链表为 t0 → i0 → NULL。函数返回后，其局部变量已离开作用域。",
        "second_insertion": "第二次调用在成功分配 t1 后，将 data 设为 2，令 p->next 指向当前头 t0，再返回 p。调用者接回返回值，因此头变为 t1，链表为 t1 → t0 → i0 → NULL。",
        "final_observation": "从调用者头出发依次得到 2、1、9，观察到 NULL 后终止，因此本例的可知前缀也是完整遍历结果，且两次合成分配失败数为 0。若遇到环或未知 next，只能报告重复或未知之前的可知前缀，不能声称有限的完整遍历。本轨迹只展示两次成功路径，没有单独高亮判空行，也没有演示失败分支或释放内存。动态结点不再使用时应安全释放；栈上的 i0 不可 free。对环或未知链接不能未经验证地套用释放过程。",
    }
    for paragraph in value["paragraphs"]:
        c.require(paragraph["key"] in texts, "PARAGRAPH_KEY")
        paragraph["text"] = texts[paragraph["key"]]
    questions = {
        "caller_head": (
            "两次插入后，调用者头指向哪个轨迹结点 ID？空指针用 none 表示。",
            "第二次成功调用返回新结点，调用者接回该返回值，因此为 t1。",
        ),
        "traversal_status": (
            "从最终调用者头开始遍历属于哪类？请使用 terminated（终止）、cycle（成环）或 indeterminate（未知）回答。",
            "依次经过 t1、t0 和 i0 后到达 NULL，因此为 terminated。",
        ),
        "reachable_prefix": (
            "从最终调用者头开始，在重复或未知指针之前可知的整数值前缀是什么？",
            "依次是 2、1、9。本例继续观察到 NULL，因此这一前缀同时是本例完整遍历结果。",
        ),
        "allocation_failures": (
            "这份合成规格中有几次分配失败？",
            "本例假定两次分配都成功，因此合成分配失败次数为 0；真实 malloc 仍可能失败。",
        ),
    }
    for key, (stem, explanation) in questions.items():
        value["questions"][key]["stem"] = stem
        value["questions"][key]["explanation"] = explanation
    catalog = c.make_catalog(SPEC)
    c.validate("C_content", value, catalog=catalog)
    ident = c.identity(
        original["identity"]["run_id"],
        original["identity"]["slot_id"],
        "C",
        1,
        SPEC,
        original["artifact_digest"],
    )
    ident["prompt_version"] = "assistant-offline-wording-v1"
    ident["binding_version"] = "offline-derived-v1"
    artifact = c.assemble(value, ident, catalog)
    artifact["source"]["provenance"]["content"] = "assistant_offline_revision"
    artifact["artifact_digest"] = digest(
        {k: v for k, v in artifact.items() if k != "artifact_digest"}
    )
    c.verify_artifact(artifact)
    original_source = original["source"]
    source = artifact["source"]
    assert source["actions"] == original_source["actions"]
    assert [b["text"] for b in source["blocks"] if b["kind"] == "code"] == [
        b["text"] for b in original_source["blocks"] if b["kind"] == "code"
    ]
    assert [
        (b["observation_key"], b["answer_key"])
        for b in source["blocks"]
        if b["kind"] == "question"
    ] == [
        (b["observation_key"], b["answer_key"])
        for b in original_source["blocks"]
        if b["kind"] == "question"
    ]
    assert source["resolved_facts"] == original_source["resolved_facts"]
    return artifact
