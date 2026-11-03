"""Explicit offline-only T108 fixtures. Never supplied as a real model planning/course result."""

import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.services import head_course_materials as m  # noqa: E402
from scripts import head_course_goal as entry  # noqa: E402
from app.services import head_course_generation as g  # noqa: E402
from app.services.free_course_snapshots import canonical  # noqa: E402


def plan(key="head-new-A"):
    return dict(
        needs_clarification=False,
        questions=[],
        reason=None,
        source_keys=[],
        plan=dict(
            title="离线接线夹具：头插",
            objectives=[
                dict(
                    id="link",
                    description="理解新节点如何连接旧链表",
                    source="user_requirement",
                    source_key="request_1",
                    source_excerpt="理解新节点如何连接旧链表",
                ),
                dict(
                    id="return",
                    description="理解调用者接收返回值",
                    source="user_requirement",
                    source_key="request_1",
                    source_excerpt="为什么调用者需要接收函数返回值",
                ),
            ],
            shared_example=key,
            terminology=[dict(term="caller_head", meaning="离线夹具：调用者头指针")],
            conventions=["离线夹具，不是真实规划成功"],
            scenes=[
                dict(
                    scene_key="head",
                    title="离线夹具：完整课",
                    purpose="离线夹具：连接与返回值",
                    forms=deepcopy(m.SUPPORT["required_forms"]),
                    objective_ids=["link", "return"],
                    depends_on=[],
                )
            ],
        ),
    )


def content(payload):
    mat = payload["materials"]
    return dict(
        prerequisites="离线夹具：自述先备知识，不是已测掌握。",
        paragraphs=[
            dict(text="离线夹具：头插讲解", fact_ids=["trace_step_00"])
            for _ in range(3)
        ],
        step_notes=[
            dict(
                frame_id=f["frame_id"],
                title="离线夹具：" + f["kind"],
                note="离线夹具：逐帧说明，不是真实教学成果。",
            )
            for f in mat["frames"]
        ],
        questions={
            k: dict(
                stem="离线夹具：独立情境题\n"
                + mat["transfer"][
                    "discarded"
                    if k in ("discarded_values", "unreachable_count")
                    else "normal"
                ]["code"]["source"]
                + "\n离线夹具：作答 "
                + k,
                explanation="离线夹具：解析 " + k,
            )
            for k in m.QKEYS
        },
        learning_summary="离线夹具：总结",
        lifecycle="离线夹具：生命周期",
        failure_scope="离线夹具：范围",
    )


def record(payload, raw=None, parent=None):
    raw = raw or content(payload)
    return dict(
        candidate=g.candidate(
            payload, raw, parent=None if parent is None else parent["candidate_digest"]
        ),
        model="deepseek-flash",
        usage=dict(input_tokens=10, output_tokens=20),
        request=m.body(payload, parent, None),
        parent_candidate=parent,
        issues=None,
        evidence_kind="offline_fixture",
        receipt=dict(fixture=True),
        observation=dict(fixture=True),
    )


def envelope(value, phase="final_answer"):
    message = dict(
        type="message",
        role="assistant",
        status="completed",
        content=[dict(type="output_text", text=canonical(value).decode())],
    )
    if phase is not None:
        message["phase"] = phase
    return canonical(
        dict(
            status="completed",
            model="deepseek-flash",
            store=False,
            error=None,
            incomplete_details=None,
            usage=dict(input_tokens=10, output_tokens=20, total_tokens=30),
            output=[message],
        )
    )


async def populate(owner, cid, oid, key):
    context = await entry.prepare(owner, cid, oid)
    await entry.save_plan(context, plan(key))

    async def action(db):
        context = await g.generation_context(db, owner, cid, oid)
        rec = record(context["payload"])
        return await g.publish(
            db,
            owner,
            cid,
            oid,
            [rec],
            dict(
                candidate_digest=rec["candidate"]["candidate_digest"],
                verdict="pass",
                independent_evaluator="offline_fixture_only",
            ),
        )

    return await entry.database(action)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline-fixture", action="store_true", required=True)
    p.add_argument("--owner", type=UUID, required=True)
    p.add_argument("--course", type=UUID, required=True)
    p.add_argument("--operation", type=UUID, required=True)
    p.add_argument("--example", choices=list(m.SPECS), default="head-new-A")
    a = p.parse_args()
    print(json.dumps(asyncio.run(populate(a.owner, a.course, a.operation, a.example))))
