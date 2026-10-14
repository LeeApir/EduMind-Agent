"""Deterministic compilation, precise AST shapes and actual child timeout regressions."""

import ast
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.services import animation_dsl_compiler as compiler
from app.services.animation_dsl_compiler import (
    DSLCompileError,
    audit_compiled_source,
    compile_animation_dsl,
)

ROOT = Path(__file__).parents[2]
BASE = json.loads((ROOT / "docs/agents/animation-dsl-v1/valid-all-actions.json").read_text())


def compile_candidate(candidate=BASE):
    return compile_animation_dsl(
        json.dumps(candidate, ensure_ascii=False), knowledge_point_id="arrays"
    )


@pytest.fixture(scope="module")
def result():
    return compile_candidate()


def test_deterministic_bytes_provenance_nine_ops_and_srt_exact_intervals(result):
    assert compile_candidate() == result
    assert compile_candidate({k: BASE[k] for k in reversed(BASE)}) == result
    assert result.source_sha256 == hashlib.sha256(result.source.encode()).hexdigest()
    assert result.subtitles_sha256 == hashlib.sha256(result.subtitles.encode()).hexdigest()
    assert result.ast_sha256 == audit_compiled_source(result.source).ast_sha256
    assert (
        result.compiler_sha256
        == hashlib.sha256(
            (ROOT / "backend/app/services/animation_dsl_compiler.py").read_bytes()
        ).hexdigest()
    )
    tree = ast.parse(result.source)
    assert [a.name for a in tree.body[0].names] == compiler.POLICY["imports"]
    assert tree.body[1].name == "DSLScene"
    forbidden = (
        ast.Import,
        ast.For,
        ast.While,
        ast.If,
        ast.Try,
        ast.Lambda,
        ast.Subscript,
        ast.JoinedStr,
    )
    assert not any(isinstance(node, forbidden) for node in ast.walk(tree))
    bindings = [node.targets[0].id for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    assert bindings == [f"m{i}" for i in range(len(bindings))]
    assert not any(
        node.id in {"n0", "n1", "e0", "p"} for node in ast.walk(tree) if isinstance(node, ast.Name)
    )
    cues = result.subtitles.strip().split("\n\n")
    assert len(cues) == 11
    assert cues[0].startswith("1\n00:00:00,000 --> 00:00:02,800\n")
    assert cues[-1].startswith("11\n00:00:28,000 --> 00:00:30,800\n")
    assert [int(cue.splitlines()[0]) for cue in cues] == list(range(1, 12))
    assert ["".join(cue.splitlines()[2:]) for cue in cues] == [
        f.caption for f in result.validated.frames
    ]
    plays = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "play"
    ]
    assert len(plays) == 11
    assert len(plays[6].args) == 2 and all(a.func.id == "Transform" for a in plays[6].args)
    assert plays[8].args[0].func.id == "FadeOut"
    assert plays[7].args[0].func.attr == "set_fill"
    assert plays[4].args[0].func.attr == "set_color"


@pytest.mark.parametrize(
    "text",
    [
        '")\n__import__("os")',  # Control characters are rejected before compilation.
        '__import__("pathlib").Path("never-created").touch()',
        '<script>alert("x")</script>',
        '"quoted" \\ slash {braces}',
        "\\n literal \\u202e literal",
        "比较 🧠 3 > 1",
        "x" * 160,
    ],
)
def test_text_is_only_ast_constant_and_never_executes(text, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = copy.deepcopy(BASE)
    data["actions"][5]["caption"] = text
    if "\n" in text:
        with pytest.raises(ValueError, match="DSL_SCHEMA_INVALID"):
            compile_candidate(data)
        return
    result = compile_candidate(data)
    strings = [
        node.value
        for node in ast.walk(ast.parse(result.source))
        if isinstance(node, ast.Constant) and type(node.value) is str
    ]
    folded = "\n".join(text[i : i + 40] for i in range(0, len(text), 40))
    assert folded in strings and folded in result.subtitles
    assert not (tmp_path / "never-created").exists()
    assert not any(
        isinstance(node, ast.Name) and node.id == "__import__"
        for node in ast.walk(ast.parse(result.source))
    )


def test_action_order_and_version_changes_invalidate_compilation_identity(result, monkeypatch):
    data = copy.deepcopy(BASE)
    data["actions"][5], data["actions"][6] = data["actions"][6], data["actions"][5]
    changed = compile_candidate(data)
    assert changed.source_sha256 != result.source_sha256
    assert changed.validated.trace_sha256 != result.validated.trace_sha256
    assert changed.validated.frames[6].comparison.result == "lt"
    monkeypatch.setattr(compiler, "COMPILER_VERSION", "animation-dsl-compiler-test-v2")
    version = compile_candidate()
    assert version.compiler_version == "animation-dsl-compiler-test-v2"
    assert version.identity_sha256 != result.identity_sha256
    monkeypatch.setattr(compiler, "COMPILER_POLICY_SHA256", "0" * 64)
    policy = compile_candidate()
    assert (
        policy.compiler_policy_sha256 == "0" * 64
        and policy.identity_sha256 != version.identity_sha256
    )


@pytest.mark.parametrize(
    "op,extra",
    [
        ("swap", {"left": "n0", "right": "n1"}),
        ("move_pointer", {"pointer": "p", "target": None}),
        ("highlight", {"object": "n0", "style": "warning"}),
        ("visit", {"node": "n0"}),
    ],
)
def test_maximum_action_count_compiles_within_source_and_ast_limits(op, extra):
    data = copy.deepcopy(BASE)
    data["pointers"] = [{"id": f"p{i}" if i else "p", "label": "pointer"} for i in range(4)]
    data["actions"] = [
        dict(
            op="create_node",
            id=f"n{i}",
            value=i,
            column=i,
            row=0,
            duration_ms=1000,
            hold_ms=0,
            caption="创建节点",
        )
        for i in range(8)
    ]
    data["actions"] += [
        dict(op=op, duration_ms=600, hold_ms=0, caption="固定动作", **extra) for _ in range(112)
    ]
    result = compile_candidate(data)
    assert len(result.validated.frames) == 120
    assert len(result.source.encode()) <= 262144 and result.ast_nodes <= 20000


def reject_source(source, code="DSL_COMPILE_REJECTED"):
    with pytest.raises(DSLCompileError) as error:
        audit_compiled_source(source)
    assert str(error.value) == code


@pytest.mark.parametrize(
    "replacement",
    [
        "import os",
        "from os import system",
        "from manim import *",
        "from manim import Scene as Other",
        "from .manim import Scene",
    ],
)
def test_unknown_alias_and_relative_imports_rejected(result, replacement):
    reject_source(replacement + "\n" + result.source.split("\n", 1)[1])


@pytest.mark.parametrize(
    "statement",
    [
        'open("SECRET_SENTINEL", "w")',
        'eval("SECRET_SENTINEL")',
        'exec("SECRET_SENTINEL")',
        '__import__("socket")',
        "self.__dict__",
        "self.mobjects[0]",
        'getattr(self,"play")',
        "while True: pass",
        "for x in []: pass",
        "if True: pass",
        "try:\n            pass\n        except: pass",
        "return",
        "x = lambda: 1",
        "x = [i for i in []]",
        "self.add(*[])",
        "self.play(m0, run_time=1)",
        "self.add(self)",
        "self.wait(True)",
        'self.wait(float("inf"))',
        "self.wait(0.1)",
        "self.wait(4)",
        "self.play(FadeIn(m0), run_time=1, rate_func=eval)",
        'm999 = Text("x",font="other",font_size=12,color="#FFFFFF")',
        "m0 = m0",
        "self.add(m999)",
        "self.wait(*[1])",
    ],
)
def test_forbidden_nodes_receivers_methods_and_args_fail_closed(result, statement):
    source = result.source + "        " + statement + "\n"
    reject_source(source)


@pytest.mark.parametrize(
    "old,new",
    [
        ("font_size=22", "font_size=999"),
        ("font_size=22", "font_size=True"),
        ("font='Noto Sans CJK SC'", "font='/tmp/font.ttf'"),
        ("color='#FFFFFF'", "color='arbitrary'"),
        ("width=1.3", "width=999"),
        ("fill_opacity=0.08", "fill_opacity=0.99"),
        ("move_to([0, 3.5, 0])", "move_to([0, 99, 0])"),
        ("run_time=1.0", "run_time=1.1"),
        ("opacity=0.3", "opacity=1.0"),
        ("set_color('#F4A261')", 'set_color(open("secret"))'),
    ],
)
def test_allowed_names_alone_do_not_authorize_invalid_argument_shapes(result, old, new):
    assert old in result.source
    reject_source(result.source.replace(old, new, 1))


def test_source_and_ast_resource_limits_are_independent(result):
    encoded = len(result.source.encode())
    assert audit_compiled_source(result.source + " " * (262144 - encoded))
    reject_source(result.source + " " * (262145 - encoded), "DSL_RESOURCE_LIMIT")
    reject_source("x=0\n" * 5000, "DSL_RESOURCE_LIMIT")
    reject_source("🧠" * 70000, "DSL_RESOURCE_LIMIT")
    reject_source("x = " + "[" * 500 + "0" + "]" * 500)


def test_actual_checker_timeout_kills_child_and_filters_sensitive_env(result, monkeypatch):
    real = subprocess.Popen
    observed = []
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "TEST_ONLY_SECRET")
    monkeypatch.setenv("EDUMIND_CREDENTIAL_KEK", "TEST_ONLY_SECRET")

    def sleeper(args, **kwargs):
        assert kwargs["env"] == {} and args[1] == "-I"
        process = real([sys.executable, "-I", "-c", "import time; time.sleep(10)"], **kwargs)
        observed.append(process)
        return process

    monkeypatch.setattr(compiler.subprocess, "Popen", sleeper)
    started = time.monotonic()
    reject_source(result.source, "DSL_COMPILE_UNAVAILABLE")
    assert 0.8 <= time.monotonic() - started < 1.0
    assert len(observed) == 1 and observed[0].poll() is not None


def test_checker_creation_failure_is_sanitized(result, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("TEST_ONLY_SECRET")

    monkeypatch.setattr(compiler.subprocess, "Popen", unavailable)
    reject_source(result.source, "DSL_COMPILE_UNAVAILABLE")


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="actual Linux Docker required")
@pytest.mark.parametrize("type_params", [False, True])
def test_fixed_linux_image_checks_ast_without_executing_source(result, type_params):
    from app.services.animation_renderer import IMAGE

    directory = ROOT / "backend/app/services"
    source = (
        result.source.replace("class DSLScene(Scene):", "class DSLScene[T](Scene):")
        if type_params
        else result.source
    )
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "none",
        "--read-only",
        "--user",
        "10001:10001",
        "--cpus",
        "1",
        "--memory",
        "512m",
        "--pids-limit",
        "32",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
    ]
    for filename in ("animation_dsl_static.py", "animation_dsl_compiler_policy.json"):
        command.extend(
            [
                "--mount",
                f"type=bind,source={directory / filename},target=/input/{filename},readonly",
            ]
        )
    command.extend([IMAGE, "python", "-I", "/input/animation_dsl_static.py"])
    process = subprocess.run(command, input=source.encode(), capture_output=True, timeout=5)
    response = json.loads(process.stdout)
    if type_params:
        assert process.returncode == 1 and response == {"code": "DSL_COMPILE_REJECTED"}
    else:
        assert process.returncode == 0 and response["nodes"] == result.ast_nodes
        assert len(response["ast_sha256"]) == 64


@pytest.mark.parametrize(
    "response,status",
    [
        ([], 1),
        ({"code": []}, 1),
        ({"code": "SECRET_SENTINEL"}, 1),
        ({"nodes": True, "ast_sha256": "0" * 64}, 0),
        ({"nodes": 1, "ast_sha256": "not-a-digest"}, 0),
    ],
)
def test_malformed_checker_protocol_never_reports_success_or_raw_error(
    result, response, status, monkeypatch
):
    real = subprocess.Popen

    def malformed(args, **kwargs):
        # A fixed trusted test reporter; no generated source is executed.
        program = "import sys; print(" + repr(json.dumps(response)) + f"); sys.exit({status})"
        return real([sys.executable, "-I", "-c", program], **kwargs)

    monkeypatch.setattr(compiler.subprocess, "Popen", malformed)
    reject_source(result.source, "DSL_COMPILE_UNAVAILABLE")


def test_loaded_checker_digest_drift_requires_reload(result, monkeypatch):
    monkeypatch.setattr(compiler, "STATIC_SHA256", "0" * 64)
    reject_source(result.source, "DSL_COMPILE_UNAVAILABLE")


def test_centered_layout_typography_and_bounded_arrow_geometry(result):
    tree = ast.parse(result.source)
    texts = {}
    arrows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "move_to":
            inner = node.func.value
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "Text"
            ):
                texts.setdefault(inner.args[0].value, []).append(
                    (
                        ast.literal_eval(node.args[0]),
                        {k.arg: ast.literal_eval(k.value) for k in inner.keywords},
                    )
                )
        if isinstance(node.func, ast.Name) and node.func.id == "Arrow":
            arrows.append({k.arg: ast.literal_eval(k.value) for k in node.keywords})
    x0, style0 = texts["n0"][0]
    x1, style1 = texts["n1"][0]
    assert x0[0] < 0 < x1[0] and x0[0] == -x1[0]
    assert x0[1] == x1[1]
    assert style0["font_size"] == style1["font_size"] >= 20
    assert texts["p"][0][1]["font_size"] >= style0["font_size"]
    assert arrows and all(0 < a["tip_length"] <= 0.15 and a["stroke_width"] == 3 for a in arrows)
    assert compiler.POLICY["pixel_width"] == 1280
    assert compiler.POLICY["pixel_height"] == 720 and compiler.POLICY["frame_rate"] == 15


@pytest.mark.parametrize(
    "old,new",
    [
        ("tip_length=0.14", "tip_length=10"),
        ("max_tip_length_to_length_ratio=0.3", "max_tip_length_to_length_ratio=1"),
        ("height=1.35", "height=99"),
        ("stroke_width=3", "stroke_width=0"),
    ],
)
def test_presentation_parameters_remain_exactly_whitelisted(result, old, new):
    assert old in result.source
    reject_source(result.source.replace(old, new, 1))


def test_legal_complexity_only_scene_has_stable_empty_grid():
    data = copy.deepcopy(BASE)
    data["pointers"] = []
    data["actions"] = [
        {
            "op": "show_complexity",
            "time": "O(1)",
            "space": "O(1)",
            "duration_ms": 2000,
            "hold_ms": 3000,
            "caption": "固定规模常数复杂度",
        }
        for _ in range(6)
    ]
    result = compile_candidate(data)
    assert result.validated.duration_ms == 30000
    assert not any(f.nodes for f in result.validated.frames)


def test_card_value_position_does_not_jump_during_swap(result):
    values = []
    for node in ast.walk(ast.parse(result.source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "move_to"
        ):
            text = node.func.value
            if (
                isinstance(text, ast.Call)
                and isinstance(text.func, ast.Name)
                and text.func.id == "Text"
            ):
                if text.args[0].value in {"3", "1"}:
                    values.append(ast.literal_eval(node.args[0]))
    assert len(values) == 4
    assert all(point[1] == -0.1 for point in values)
    assert sorted(point[0] for point in values) == [-2.25, -2.25, 2.25, 2.25]
