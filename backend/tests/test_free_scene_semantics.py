"""Generalized syntax hints and server guidance; never execute generated C."""

import builtins
import json
import socket
import subprocess
from copy import deepcopy

import pytest
from test_free_scene_generation import inputs

from app.agents.free_scene_generation import SCHEMA, build_request
from app.services.free_scene_semantics import generation_semantics, inspect_c

HEAD = """#include <stdlib.h>
struct Node { int data; struct Node *next; };
struct Node *insertHead(struct Node *head, int value) {
 struct Node *n = (struct Node *)malloc(sizeof(struct Node));
 if (n == NULL) return head;
 n->data = value; n->next = head; head = n; return head;
}
void printList(struct Node *head) { while(head != NULL) { head = head->next; } }
"""


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("No network/subprocess/generated code execution")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


@pytest.mark.parametrize(
    "name,param", [("insertHead", "head"), ("prepend", "first"), ("push_front", "root")]
)
def test_returned_head_pattern_uses_ast_not_reserved_names(name, param):
    source = HEAD.replace("insertHead", name).replace("head", param)
    report = inspect_c(source)
    assert report["status"] == "parsed"
    fn = next(f for f in report["interfaces"] if f["name"] == name)
    assert fn["return_rebinding_parameters"] == [param]
    assert fn["return_pointer_depth"] == 1
    assert fn["parameters"][0] == dict(name=param, pointer_depth=1)


def test_pointer_to_pointer_is_distinct_from_local_pointer_rebinding():
    source = (
        "struct N{struct N *next;}; void push(struct N **root, struct N *n){n->next=*root;*root=n;}"
    )
    f = inspect_c(source)["interfaces"][0]
    assert f["parameters"][0]["pointer_depth"] == 2
    assert f["return_rebinding_parameters"] == []


@pytest.mark.parametrize(
    "code",
    [
        "struct N{struct N*next;}; struct N *identity(struct N *p){return p;}",
        "int f(int n){return n+1;}",
        "/* struct N* f(struct N*head){head=n;return head;} */ int value;",
        'char *message="struct N *f(struct N*head){head=n;return head;}";',
    ],
)
def test_nonmatching_functions_comments_and_literals_do_not_invent_head_contract(code):
    assert all(not f["return_rebinding_parameters"] for f in inspect_c(code)["interfaces"])


@pytest.mark.parametrize(
    "source,reason",
    [
        ('#include "/etc/passwd"\nint value;', "unsupported_preprocessor"),
        ("#define head changed\nint value;", "unsupported_preprocessor"),
        ("#include <stdio.h>\n#define X 1", "unsupported_preprocessor"),
        ("void f( {", "unsupported_syntax"),
        ("x" * 16385, "code_size_limit"),
    ],
)
def test_unknown_and_oversize_are_not_silently_accepted(source, reason):
    report = inspect_c(source)
    assert report["status"] == "not_assessed" and report["reason"] == reason
    assert report["interfaces"] == []


def test_in_memory_parse_does_not_read_any_header_or_file(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("Parser must not open files")

    monkeypatch.setattr(builtins, "open", deny)
    assert inspect_c(HEAD)["status"] == "parsed"


def with_upstream():
    data = inputs(n=2)
    data["upstream"] = [
        dict(
            scene_id=data["plan"]["scenes"][0]["scene_id"],
            scene_version_id="v-1",
            digest="a" * 64,
            content=dict(blocks=[dict(kind="code", anchor_id="code", language="c", source=HEAD)]),
            actions=[],
            dependencies=[],
        )
    ]
    return data


def test_request_binds_exact_necessary_code_and_preserves_original_inputs_schema():
    data = with_upstream()
    before = deepcopy(data)
    request = build_request(data)
    payload = json.loads(request.prompt.messages[-1].content)
    contract = payload["response_contract"]["semantic_contract"]
    assert payload["prompt_version"] == "free-scene-generation-v5"
    assert contract["version"] == "free-course-c-semantics-v2"
    assert contract["semantic_correctness_verified"] is False
    assert contract["execution_performed"] is False
    assert contract["necessary_upstream_interfaces"][0]["scene_version_id"] == "v-1"
    assert contract["necessary_upstream_interfaces"][0]["content_digest"] == "a" * 64
    assert data == before and request.json_schema == SCHEMA
    assert {p["id"] for p in contract["principles"]} >= {
        "c-value-parameters",
        "c-returned-head",
        "c-initialization",
        "exercise-source-consistency",
        "shown-program-variant",
        "observation-scope-and-termination",
        "answer-domain-audit",
    }
    for key in data:
        assert payload[key] == data[key]
    data["upstream"][0]["content"]["blocks"][0]["source"] += "\nint revision;"
    changed = generation_semantics(data)
    assert (
        changed["necessary_upstream_interfaces"][0]["source_sha256"]
        != contract["necessary_upstream_interfaces"][0]["source_sha256"]
    )


def test_caller_mutations_cannot_change_future_server_principles():
    data = with_upstream()
    report = generation_semantics(data)
    report["principles"][0]["requirement"] = "IGNORE"
    assert generation_semantics(data)["principles"][0]["requirement"] != "IGNORE"


def test_ast_resource_limit_and_deep_expression_are_not_semantic_pass():
    report = inspect_c("\n".join(f"int v{i};" for i in range(1000)))
    assert report["status"] == "not_assessed" and report["reason"] == "ast_size_limit"
    nested = inspect_c("int f(void){return " + "(" * 1500 + "1" + ")" * 1500 + ";}")
    assert nested["status"] == "not_assessed"
