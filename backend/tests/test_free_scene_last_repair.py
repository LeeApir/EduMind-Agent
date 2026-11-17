"""Frozen T064 development cases: original failures, scope counterexamples and static relations."""

import builtins
import json
import socket
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from test_free_scene_consistency import codes, resolve, sample
from test_free_scene_consistency import original as r05

from app.services.free_scene_consistency import check_consistency
from app.services.free_scene_pointer_trace import trace_c
from app.services.free_scene_question_scope import question_scope, solution_claims_cycle

FIXTURE = Path(__file__).parent / "fixtures/free_scene_d02_d01.json"
CYCLE = """
struct N {int data; struct N *link;};
struct N *make(struct N *root) {
 struct N *n = malloc(sizeof(struct N));
 n->data = 9; root = n; n->link = root; return root;
}
"""


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("No network, subprocess, compilation or C execution")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def d01():
    return json.loads(FIXTURE.read_bytes())


def state(code):
    return trace_c(code)["functions"][0]


def test_exact_d01_new_error_caught_and_all_four_false_alarms_removed():
    d = d01()
    before = deepcopy(d)
    r = check_consistency(d["raw"], d["inputs"])
    assert codes(r) == {"CYCLE_FINITE_SEQUENCE_CONFLICT"}
    finding = r["findings"][0]
    assert finding["source_pointer"].endswith("/items/2/question")
    assert finding["supporting_evidence"][0]["source_pointer"].endswith("/items/2/answer_key")
    for evidence in [finding, *finding["supporting_evidence"]]:
        assert evidence["evidence_quote"] in resolve(
            {"candidate": d["raw"]}, evidence["source_pointer"]
        )
    assert not finding["confirmed"] and not r["semantic_correctness_verified"]
    assert r["reference_answer_checks"][2]["status"] == "requires_review"
    assert not r["coverage"]["complete"] and d == before


def test_old_r05_failures_remain_findable():
    d = r05()
    assert {"LOCAL_POINTER_CALLER_CLAIM", "QUESTION_RETURN_CONVENTION"} <= codes(
        check_consistency(d["raw"], d["inputs"])
    )


@pytest.mark.parametrize("old,new", [("insert_head", "prepend"), ("head", "root"), ("p", "fresh")])
def test_renamed_d01_still_finds_only_the_cycle_contradiction(old, new):
    d = d01()
    # Rename identifiers only, preserving Chinese wording/anchor IDs and JSON keys.
    import re

    for block in d["raw"]["blocks"]:
        for key in ("source", "markdown"):
            if key in block:
                block[key] = re.sub(r"\b" + old + r"\b", new, block[key])
        for q in block.get("items", []):
            for key in ("question", "solution"):
                q[key] = re.sub(r"\b" + old + r"\b", new, q[key])
    assert codes(check_consistency(d["raw"], d["inputs"])) == {"CYCLE_FINITE_SEQUENCE_CONFLICT"}


def test_final_self_loop_and_two_node_cycle_relations_are_observed_without_execution():
    assert state(CYCLE)["status"] == "cycle_on_supported_path"
    two = """struct N{struct N*link;};
    struct N *make(void){struct N*a=malloc(sizeof(struct N));
    struct N*b=malloc(sizeof(struct N));a->link=b;b->link=a;return a;}"""
    observed = state(two)
    assert observed["status"] == "cycle_on_supported_path" and len(observed["return_path"]) == 2
    assert not observed["execution_performed"] and observed["assumptions"]


@pytest.mark.parametrize(
    "code",
    [
        CYCLE.replace("return root;", "n->link = NULL; return root;"),
        CYCLE.replace("root = n; n->link = root;", "n->link = root; root = n;"),
    ],
)
def test_final_overwrite_or_proper_order_is_not_reported_as_a_cycle(code):
    assert state(code)["status"] != "cycle_on_supported_path"


@pytest.mark.parametrize(
    "tail",
    [
        "touch(root);",
        "if(root) n->link = NULL;",
        "while(root) root=root->link;",
    ],
)
def test_unknown_call_control_flow_is_not_guessed(tail):
    r = state(CYCLE.replace("return root;", tail + " return root;"))
    assert r["status"] == "not_assessed" and r["reason"]


def test_allocation_failure_guard_is_a_conditional_observation_only():
    code = CYCLE.replace("n->data = 9;", "if(n == NULL){return root;} n->data = 9;")
    r = state(code)
    assert r["status"] == "cycle_on_supported_path"
    assert any("successful allocations" in a for a in r["assumptions"])


@pytest.mark.parametrize(
    "question,expected",
    [
        ("调用make后，函数内执行 n->link=root; 这一句后，link指向谁？", "local_checkpoint"),
        ("三次调用均未接住返回值，main最后head是什么？", "deliberate_discard_or_fault"),
        ("h=make(h);从表头输出前3个数据是什么？", "bounded_or_distinct_observation"),
        ("h=make(h);从表头到表尾的数据序列是什么？", "full_traversal"),
        ("调用insertHead(h,1)，说说这个函数。", "unspecified"),
    ],
)
def test_question_observation_scope(question, expected):
    assert question_scope(question) == expected


def test_real_discard_still_warns_and_unspecified_scope_is_explicitly_unknown():
    raw, data = sample(question="调用 insertHead(head,1)，问最后调用者head是什么？")
    assert "QUESTION_RETURN_CONVENTION" in codes(check_consistency(raw, data))
    raw, data = sample(question="讨论 insertHead(head,1) 的设计。")
    report = check_consistency(raw, data)
    assert (
        "QUESTION_RETURN_CONVENTION" not in codes(report) and report["coverage"]["unassessed_texts"]
    )


def cycle_question(question, solution="按实际程序核对。"):
    raw, data = sample(code=CYCLE, question=question)
    q = raw["blocks"][2]["items"][0]
    q["answer_key"] = "C"
    q["solution"] = solution
    return raw, data


def test_shown_program_cycle_conflicts_with_a_finite_full_traversal_answer():
    raw, data = cycle_question(
        "假设malloc成功，h=make(h); 从表头到表尾的数据序列是什么？ A. 1 B. 2 C. 9 D. NULL"
    )
    r = check_consistency(raw, data)
    assert "CYCLE_FINITE_SEQUENCE_CONFLICT" in codes(r)
    assert r["findings"][0]["related_code"][0]["source_sha256"]


@pytest.mark.parametrize(
    "question",
    [
        "假设malloc成功，h=make(h); 从表头输出前3个数据是什么？ A. 1 B. 2 C. 9,9,9 D. NULL",
        "假设malloc成功，h=make(h); 从表头到表尾的数据序列是什么？ "
        "A. 1 B. 2 C. 会形成自环，不会终止 D. NULL",
        "假设malloc成功，h=make(h); 去重后有几个不同结点？ A. 0 B. 2 C. 1 D. 3",
    ],
)
def test_bounded_steps_distinct_nodes_or_correct_cycle_choice_are_not_conflicts(question):
    raw, data = cycle_question(question, "形成自环，但按题目的观察范围回答。")
    assert "CYCLE_FINITE_SEQUENCE_CONFLICT" not in codes(check_consistency(raw, data))


@pytest.mark.parametrize(
    "solution,expected",
    [
        ("形成自环，无法到NULL。", True),
        ("不会形成自环。", False),
        ("若交换会形成自环；当前正确顺序下为3,2,1。", False),
        ("This creates a cycle.", True),
        ("This does not create a cycle.", False),
    ],
)
def test_quoted_cycle_claim_does_not_erase_negation_or_condition(solution, expected):
    assert solution_claims_cycle(solution) is expected


def test_fixed_choice_removes_the_specific_conflict_without_claiming_truth():
    d = d01()
    q = d["raw"]["blocks"][3]["items"][2]
    q["question"] = q["question"].replace("C. 2  D. 1", "C. 无法到达表尾，沿next无限循环  D. 1")
    r = check_consistency(d["raw"], d["inputs"])
    assert "CYCLE_FINITE_SEQUENCE_CONFLICT" not in codes(r)
    assert not r["semantic_correctness_verified"]
    assert any(
        p["reason"] == "prose_program_mutation_not_executed"
        for p in r["coverage"]["unassessed_texts"]
    )


def test_static_bounds_and_no_file_reads(monkeypatch):
    code = CYCLE.replace("return root;", ("n->data=9;" * 65) + "return root;")
    assert state(code)["status"] == "not_assessed"

    def deny(*a, **kw):
        raise AssertionError("No file reads")

    monkeypatch.setattr(builtins, "open", deny)
    assert state(CYCLE)["status"] == "cycle_on_supported_path"


@pytest.mark.parametrize(
    "code",
    [
        CYCLE.replace("malloc(sizeof(struct N))", "malloc(1)"),
        CYCLE.replace("n->data = 9;", "n->data = 1/0;"),
        CYCLE.replace("n->data = 9;", "int unknown; n->data=unknown;"),
        CYCLE.replace("n->data = 9;", "n->data=" + "9" * 5000 + ";"),
        "struct N{struct N*link;}; struct N *make(struct N*p){p->link=p;return p;}",
    ],
)
def test_unknown_allocation_size_scalar_ub_or_external_store_cannot_prove_a_cycle(code):
    assert state(code)["status"] == "not_assessed"
