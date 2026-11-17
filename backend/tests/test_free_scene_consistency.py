"""Original D02 failure plus independent correct/renamed/unknown counterexamples."""

import builtins
import json
import socket
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
from test_free_scene_generation import inputs, response
from test_free_scene_semantics import HEAD

from app.services.free_scene_consistency import check_consistency
from app.services.free_scene_validation import check_scene

FIXTURE = Path(__file__).parent / "fixtures/free_scene_d02_r05.json"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("No network, subprocess or generated-code execution")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def original():
    return json.loads(FIXTURE.read_bytes())


def codes(report):
    return {f["code"] for f in report["findings"]}


def resolve(document, pointer):
    value = document
    for part in pointer.split("/")[1:]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def test_exact_r05_failure_is_located_without_rewriting_or_approving():
    data = original()
    before = deepcopy(data)
    report = check_consistency(data["raw"], data["inputs"])
    assert {"LOCAL_POINTER_CALLER_CLAIM", "QUESTION_RETURN_CONVENTION"} <= codes(report)
    assert report["status"] == "needs_review"
    assert not report["semantic_correctness_verified"] and not report["coverage"]["complete"]
    for finding in report["findings"]:
        assert finding["confirmed"] is False
        assert finding["evidence_quote"] in resolve(
            {"candidate": data["raw"], "upstream": data["inputs"]["upstream"]},
            finding["source_pointer"],
        )
        assert finding["related_code"][0]["source_sha256"]
    assert data == before
    checked = check_scene(data["raw"], data["inputs"])
    assert checked["state"] == "accepted"  # semantic advice cannot bypass ADR0026 confirmation
    assert checked["findings"][0]["report"] == report
    assert data["raw"]["blocks"][3]["items"][0]["answer_key"] == "3,2,1"


@pytest.mark.parametrize("name,param", [("prepend", "root"), ("push_front", "first")])
def test_changed_function_and_parameter_names_still_find_same_class(name, param):
    data = original()
    data = json.loads(json.dumps(data).replace("insertHead", name).replace("head", param))
    assert {"LOCAL_POINTER_CALLER_CLAIM", "QUESTION_RETURN_CONVENTION"} <= codes(
        check_consistency(data["raw"], data["inputs"])
    )


def test_corrected_text_and_explicit_caller_update_remove_the_observations():
    data = original()
    data["raw"]["blocks"][2]["markdown"] = (
        "在printList内写 `head = head->next;` 不会改变调用者main的head；"
        "这仅移动局部副本，不会永久丢失调用者入口。"
    )
    q = data["raw"]["blocks"][3]["items"][0]
    for value in (1, 2, 3):
        q["question"] = q["question"].replace(
            f"insertHead(head,{value})", f"head = insertHead(head,{value})"
        )
    report = check_consistency(data["raw"], data["inputs"])
    assert not ({"LOCAL_POINTER_CALLER_CLAIM", "QUESTION_RETURN_CONVENTION"} & codes(report))
    assert not report["semantic_correctness_verified"]


def sample(code=HEAD, question="调用 insertHead(head,1)，问新的head是什么？"):
    raw = response(["text", "code", "exercise"])
    raw["blocks"][1]["source"] = code
    raw["blocks"][2]["items"][0]["question"] = question
    return raw, inputs(forms=["text", "code", "exercise"])


@pytest.mark.parametrize(
    "question",
    [
        "执行 head = insertHead(head,1)，问head是什么？",
        "执行 updated = insertHead(head,1); head = updated;，问结果？",
        "返回 return insertHead(head,1);",
        "执行 head = (struct Node *)insertHead(head,1);",
        "执行 head = (insertHead(head,1));",
        "以下是错误调用 insertHead(head,1)，忽略返回值后caller head是否仍为空？",
        "函数insertHead的作用是什么？",
    ],
)
def test_return_capture_propagation_cast_and_deliberate_error_examples_are_not_defect_assertions(
    question,
):
    raw, data = sample(question=question)
    assert "QUESTION_RETURN_CONVENTION" not in codes(check_consistency(raw, data))


def test_bare_statement_in_real_code_is_found_but_comments_strings_and_assigned_calls_are_not():
    code = HEAD + "\nvoid f(struct Node *h){ insertHead(h,1); }"
    raw, data = sample(code, question="head = insertHead(head,1);")
    assert "RETURNED_HEAD_NOT_CAPTURED" in codes(check_consistency(raw, data))
    code = (
        HEAD + "\nvoid f(struct Node *h){ h=insertHead(h,1); /*insertHead(h,2);*/ "
        'char*s="insertHead(h,3);"; }'
    )
    raw, data = sample(code, question="head = insertHead(head,1);")
    assert "RETURNED_HEAD_NOT_CAPTURED" not in codes(check_consistency(raw, data))


def test_pointer_to_pointer_mutator_is_not_forced_to_receive_a_return():
    code = "struct N{struct N*next;}; void push(struct N **head,struct N*n){n->next=*head;*head=n;}"
    raw, data = sample(code, question="执行 push(&head,n)，问head是什么？")
    assert "QUESTION_RETURN_CONVENTION" not in codes(check_consistency(raw, data))


@pytest.mark.parametrize("code", ["#define CHANGE 1\nint x;", "void f( {", "x" * 16385])
def test_unsupported_code_is_reported_as_unassessed_not_green(code):
    raw, data = sample(code)
    report = check_consistency(raw, data)
    assert report["status"] == "not_assessed"
    assert report["coverage"]["unassessed_units"] and not report["coverage"]["complete"]


def test_prose_only_or_unrelated_c_is_not_a_semantic_success():
    raw, data = sample("int main(void){return 0;}")
    report = check_consistency(raw, data)
    assert report["status"] == "not_assessed" and not report["semantic_correctness_verified"]
    assert check_scene(response(["text"]), inputs(forms=["text"]))["state"] == "accepted"


def test_same_interface_with_renamed_parameters_is_not_a_contract_conflict():
    raw, data = sample(question="head = insertHead(head,1);")
    data["upstream"] = [
        dict(
            scene_id="old",
            scene_version_id="v",
            digest="a" * 64,
            content=dict(
                blocks=[
                    dict(
                        kind="code",
                        anchor_id="c",
                        language="c",
                        source=HEAD.replace("head", "first"),
                    )
                ]
            ),
        )
    ]
    assert "INTERFACE_CONVENTION_CONFLICT" not in codes(check_consistency(raw, data))
    data["upstream"][0]["content"]["blocks"][0]["source"] = HEAD.replace(
        "struct Node *head,", "struct Node **head,"
    )
    assert "INTERFACE_CONVENTION_CONFLICT" in codes(check_consistency(raw, data))


def test_unknown_or_findings_do_not_turn_mechanical_failures_into_acceptance():
    raw, data = sample()
    raw["blocks"][1]["markdown"] = ""
    assert check_scene(raw, data)["state"] == "rejected"


def test_no_header_or_file_read(monkeypatch):
    raw, data = sample()

    def deny(*a, **kw):
        raise AssertionError("No file reads")

    monkeypatch.setattr(builtins, "open", deny)
    assert check_consistency(raw, data)["status"] == "needs_review"


def test_comparison_is_not_misread_as_return_capture():
    raw, data = sample(question="比较 head == insertHead(head,1)，问结果。")
    assert "QUESTION_RETURN_CONVENTION" in codes(check_consistency(raw, data))


def test_unparsed_or_deliberate_call_context_is_explicitly_unassessed():
    raw, data = sample(question='执行 insertHead(head, "text")，问结果。')
    report = check_consistency(raw, data)
    assert report["status"] == "not_assessed" and report["coverage"]["unassessed_texts"]


def test_code_unit_and_finding_limits_are_bounded_and_never_mark_full_coverage():
    raw, data = sample()
    raw["blocks"] = [raw["blocks"][0], raw["blocks"][2]] + [
        dict(kind="code", anchor_id=f"c{i}", language="c", source=HEAD) for i in range(17)
    ]
    report = check_consistency(raw, data)
    assert report["coverage"]["limits_reached"] and not report["coverage"]["complete"]
    raw, data = sample()
    group = raw["blocks"][2]
    for q in group["items"]:
        q["question"] = "调用 insertHead(head,1)，问结果。"
    raw["blocks"] = raw["blocks"][:2] + [
        {**deepcopy(group), "anchor_id": f"e{i}", "exercise_key": f"key{i}"} for i in range(13)
    ]
    report = check_consistency(raw, data)
    assert len(report["findings"]) == 24 and report["coverage"]["limits_reached"]
    assert not report["semantic_correctness_verified"]


def test_report_binds_reference_key_and_request_but_never_verifies_the_answer():
    data = original()
    first = check_consistency(data["raw"], data["inputs"])
    q = first["reference_answer_checks"][0]
    assert q["status"] == "requires_review" and not q["answer_verified"]
    assert q["source_pointer"].endswith("/items/0/answer_key")
    data["raw"]["blocks"][3]["items"][0]["answer_key"] = "NULL"
    second = check_consistency(data["raw"], data["inputs"])
    assert second["reference_answer_checks"][0]["answer_digest"] != q["answer_digest"]
    assert second["source_digest"] != first["source_digest"]
    data["inputs"]["request"]["original_goal"] += " 使用不同原始目标"
    third = check_consistency(data["raw"], data["inputs"])
    assert third["source_digest"] != second["source_digest"]
