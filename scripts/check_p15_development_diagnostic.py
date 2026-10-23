"""T037 preparation only. --check is read-only and cannot send any model request."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-development-diagnostic-r01"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare():
    if (BASE / "manifest.json").exists():
        raise ValueError("PREPARATION_EXISTS_DO_NOT_OVERWRITE")
    pairs = [
        (
            "position",
            "用连续存放的整数说明按位置访问，用C代码和练习组织1个场景。",
            [1, 1],
            0,
        ),
        ("linked", "学习单链表头插，用C代码和练习组织2个场景。", [2, 2], 1),
        ("stack", "学习栈与队列的区别，用C代码、练习和状态图组织3个场景。", [3, 3], 2),
        ("queue", "学习循环队列的空满与取模，用C代码和练习组织4个场景。", [4, 4], 1),
        ("search", "学习二分查找与数组边界，用C代码、练习组织5至6个场景。", [5, 6], 2),
        (
            "graph",
            "学习图的广度优先遍历与队列，用C代码、练习和状态图组织7至8个场景。",
            [7, 8],
            2,
        ),
    ]
    courses = []
    for i, (topic, goal, bounds, mentions) in enumerate(pairs):
        for profile in ["known", "unknown"]:
            courses.append(
                dict(
                    slot_id=f"D{i + 1:02}-{profile}",
                    pair_id=f"D{i + 1:02}",
                    topic=topic,
                    original_goal=goal,
                    scene_count_range=bounds,
                    goal_mention_category=mentions,
                    code_language="C",
                    learner_evidence={}
                    if profile == "unknown"
                    else {
                        "knowledge_base": {
                            "self_report": "会C变量和循环，尚未系统学习指针与数据结构",
                            "source": "learner_statement",
                        },
                        "engineering_preference": {
                            "code_first": True,
                            "source": "learner_statement",
                        },
                    },
                    expected={
                        "mandatory": [
                            "保留原始目标与形式",
                            "完整可学场景",
                            "C边界条件",
                            "练习与已教一致",
                        ],
                        "profile": "未知字段不得臆测；已知基础须影响前置说明/节奏，不能只换称呼",
                        "node_links": "关联是建议；0关联不得阻断；不得把精确提及当节点核定或掌握度",
                    },
                    required_review=[
                        "全部可见场景逐项需求/可学性",
                        "穷尽原子事实",
                        "每题答案和允许输入/精确评分适用性",
                    ],
                    source="new assistant-authored development material; not independent holdout",
                )
            )
    errors = [
        (
            "definition",
            "栈的弹出顺序是先进先出。",
            "栈的弹出顺序是后进先出。",
            "栈push A再push B，则先pop B。",
        ),
        (
            "definition",
            "对任意未排序数组都可直接用标准二分查找保证正确。",
            "标准二分查找需要与比较规则一致的有序数组。",
            "未排序[3,1,2]会破坏按中点排除区间的推理。",
        ),
        (
            "steps",
            "单链表头插直接先head=n，再n->next=head，保留原链表。",
            "先n->next=head，再head=n，保留原链表。",
            "错误顺序令n->next指向n，且丢失原head引用。",
        ),
        (
            "code",
            "p非空且指向堆结点，free(p); int x=p->value; 可安全读取原值。",
            "p非空且指向堆结点，先int x=p->value; 再free(p);，之后不再解引用p。",
            "释放后对象生命周期结束，不能依赖旧内容仍在。",
        ),
        (
            "code",
            "int非负lo<=hi<=INT_MAX时，mid=(lo+hi)/2 永不发生有符号溢出。",
            "int非负lo<=hi<=INT_MAX时，mid=lo+(hi-lo)/2 不因求中点发生有符号溢出。",
            "lo和hi接近INT_MAX时和可能越界；hi-lo在[0,INT_MAX]且结果不大于hi。",
        ),
        (
            "complexity",
            "RAM模型中按有效下标读取已分配数组单个元素需要O(n)时间。",
            "RAM模型中按有效下标读取已分配数组单个元素需要O(1)时间。",
            "地址由基址和下标计算，读取一次，不包含查找目标值。",
        ),
        (
            "complexity",
            "只有头指针的单链表读取第n个结点在最坏情况下为O(1)。",
            "只有头指针的单链表读取第n个结点在最坏情况下为O(n)。",
            "无额外索引，需要沿next走n-1次。",
        ),
        (
            "answer",
            "数组[5,2,4]进行一次从左到右的冒泡扫描后为[2,5,4]。",
            "数组[5,2,4]进行一次从左到右的冒泡扫描后为[2,4,5]。",
            "先交换5与2得到[2,5,4]，再交换5与4。",
        ),
        (
            "answer",
            "根深度为0、高度按边数计，三个结点的链状二叉树高度为3。",
            "根深度为0、高度按边数计，三个结点的链状二叉树高度为2。",
            "最长根叶路径两条边，不能把结点数当高度。",
        ),
        (
            "cross_scene",
            "场景1约定循环队列保留一格、容量数组长N；场景2又称可存N个元素，且无需变更约定。",
            "场景1约定循环队列保留一格、容量数组长N；场景2称最多可存N-1个元素，约定一致。",
            "保留一格区分空满，最大存放数为N-1。",
        ),
    ]
    probes = []
    for i, (category, bad, good, reason) in enumerate(errors):
        for label, text in [("severe", bad), ("correct", good)]:
            probes.append(
                dict(
                    probe_id=f"R{i + 1:02}-{label}",
                    category=category,
                    content=text,
                    proposed_label=label,
                    proposed_reason=reason,
                    label_status="assistant_draft_requires_human_verification",
                    author_kind="assistant",
                    human_review=None,
                    exposure="development_only; visible to implementation agent",
                )
            )
    negatives = [
        dict(
            slot_id="N01",
            goal="只要1个场景并且必须至少8个独立场景；不要猜测取舍。",
            expected="澄清冲突，不能偷偷删要求",
        ),
        dict(
            slot_id="N02",
            goal="要求运行任意用户C程序并访问网络获取答案。",
            expected="明确不支持执行/网络，不能越过隔离；不纳入支持域课程成功分母",
        ),
    ]
    documents = {
        "courses.json": courses,
        "probes.draft.json": probes,
        "negatives.json": negatives,
        "candidate.json": dict(
            source="user explicitly selected current .env public metadata; no secret exported",
            provider_endpoint="https://www.cbbb.fun/v1",
            model_id="gpt-6-luna",
            structured_transport="responses_json_schema",
            reasoning_effort="none",
            model_revision=None,
            pricing=None,
            total_output_bound_evidence=None,
            status="selected_alias_not_yet_execution_frozen",
        ),
        "budget.proposed.json": dict(
            status="proposal_not_authorization",
            candidates=1,
            batches=1,
            currency="CNY",
            requests=202,
            input_tokens=3440000,
            output_tokens=832000,
            fee_micros=30000000,
            wall_seconds=10800,
            allocation={
                "supported_courses": {
                    "slots": 12,
                    "requests_max_each": 13,
                    "input_tokens_max_each": 200000,
                    "output_tokens_max_each": 48000,
                    "seconds_max_each": 600,
                },
                "negative_controls": {
                    "slots": 2,
                    "requests_max_each": 13,
                    "input_tokens_max_each": 200000,
                    "output_tokens_max_each": 48000,
                    "seconds_max_each": 600,
                },
                "review_probes": {
                    "slots": 20,
                    "requests_max_each": 1,
                    "input_tokens_max_each": 32000,
                    "output_tokens_max_each": 8000,
                    "seconds_max_each": 120,
                },
            },
            note="所有失败/格式修复/传输重试/未知发送计入；未授权价格不按0推定。额度上限不是费用预测。不得另加探测/回退/第二候选。",
        ),
    }
    BASE.mkdir(exist_ok=True)
    for name, data in documents.items():
        (BASE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    sources = (
        list((ROOT / "backend/app").rglob("*.py"))
        + list((ROOT / "backend/app").rglob("*.json"))
        + [
            ROOT / "backend/uv.lock",
            ROOT / "data/knowledge_graph.yaml",
            ROOT / "data/knowledge/phase-1.1.0.json",
            ROOT / "scripts/acceptance_support/p15_diagnostic_ledger.py",
            ROOT / "scripts/tests/test_p15_diagnostic_ledger.py",
            Path(__file__),
        ]
    )
    manifest = dict(
        status="preparation_blocked_not_execution_package",
        batch_id="p15-development-r01",
        candidate_count=1,
        material_sha256={name: sha(BASE / name) for name in documents},
        source_sha256={
            str(p.relative_to(ROOT)): sha(p)
            for p in sorted(set(sources))
            if p.is_file()
        },
        human_approval=None,
        real_requests_authorized=0,
        real_provider_calls=0,
        missing=[
            "供应商模型版本/别名映射与准确价格、完整输出含推理token上界的依据",
            "20个probe人工构造/核定及准确标签签名、课程预期人工确认",
            "真实适配与逐槽执行器的最终绑定/离线字节及预算验证",
            "准确冻结包、预算与T038真实执行批准",
        ],
    )
    (BASE / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )


def check():
    manifest = json.loads((BASE / "manifest.json").read_text())
    for name, h in manifest["material_sha256"].items():
        assert sha(BASE / name) == h, name
    for name, h in manifest["source_sha256"].items():
        assert sha(ROOT / name) == h, name
    assert (
        manifest["candidate_count"] == 1
        and manifest["real_requests_authorized"] == 0
        and manifest["real_provider_calls"] == 0
    )
    courses = json.loads((BASE / "courses.json").read_text())
    probes = json.loads((BASE / "probes.draft.json").read_text())
    assert (
        len(courses) == 12
        and len({c["pair_id"] for c in courses}) == 6
        and len({c["topic"] for c in courses}) >= 4
    )
    assert (
        len(probes) == 20 and sum(p["proposed_label"] == "severe" for p in probes) == 10
    )
    assert all(
        p["human_review"] is None
        and p["label_status"] == "assistant_draft_requires_human_verification"
        for p in probes
    )
    budget = json.loads((BASE / "budget.proposed.json").read_text())
    for total, key in [
        ("requests", "requests_max_each"),
        ("input_tokens", "input_tokens_max_each"),
        ("output_tokens", "output_tokens_max_each"),
        ("wall_seconds", "seconds_max_each"),
    ]:
        assert budget[total] == sum(
            v["slots"] * v[key] for v in budget["allocation"].values()
        ), total
    print(
        "PARTIAL: 12 courses/6 pairs + 2 negatives + 20 unverified probe drafts and source hashes valid; no credentials/network used."
    )
    print(
        "BLOCKED: preparation is not a frozen authorized executable package. Missing:"
    )
    for item in manifest["missing"]:
        print("- " + item)
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--check", action="store_true")
    a = parser.parse_args()
    if a.prepare:
        prepare()
    else:
        raise SystemExit(check())


if __name__ == "__main__":
    main()
