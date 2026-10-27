"""Code fidelity and inactive links/HTML across parsed Markdown round trips."""

from copy import deepcopy
from html.parser import HTMLParser
from itertools import product

import mistune
import pytest
from test_free_scene_generation import inputs, response

from app.services.free_scene_markdown import clean_code_markdown
from app.services.free_scene_validation import RULE_VERSION, check_scene, clean_markdown


def flatten(tokens):
    for t in tokens:
        yield t
        yield from flatten(t.get("children", []))


def parsed(value):
    return list(flatten(mistune.create_markdown(renderer=None, plugins=[])(value)))


def codes(value):
    return [(t["type"], t["raw"]) for t in parsed(value) if t["type"] in {"codespan", "block_code"}]


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)


def assert_inert(value):
    assert not any(
        t["type"] in {"link", "image", "inline_html", "block_html"} for t in parsed(value)
    )
    # Deliberately use a renderer that permits raw HTML: the cleaned AST has none.
    html = mistune.create_markdown(escape=False, plugins=[])(value)
    rendered = Elements()
    rendered.feed(html)
    assert not set(rendered.tags) & {
        "a",
        "img",
        "script",
        "iframe",
        "svg",
        "math",
        "object",
        "embed",
        "video",
        "audio",
    }
    assert not any(k.startswith("on") or k in {"href", "src", "srcdoc"} for k, _ in rendered.attrs)


@pytest.mark.parametrize(
    "raw",
    [
        "```c\nint scores[6] = {72, 85, 90, 66, 78, 95};\n```",
        "`scores[i] < LEN && i >= 0`",
        '```c\n#include <stdio.h>\nprintf("%d\\n", a[i]);\n```',
        "``text with `ticks` and [brackets]``",
        '~~~c\nchar *p="```";\n~~~~\n',
        "````c\n```\n[x](https://example.com)\n````",
        "> ```c\n> int a[6];\n> ```",
        "- code:\n\n  ```c\n  int a[6];\n  ```",
        "    int a[6];\n    a[0] = 3;\n",
        "`<script>alert(1)</script> &#60;img&#62; [x](javascript:bad)`",
        "```c\nint a[6];",
        "`` a[i] `` and `` `literal` ``",
        "`first\nsecond`",
    ],
)
def test_code_payload_and_nested_or_unclosed_delimiters_remain_inert(raw):
    cleaned = clean_code_markdown(raw)
    assert codes(raw) and codes(cleaned) == codes(raw)
    assert_inert(cleaned)


ATTACKS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    '<iframe srcdoc="boom"></iframe>',
    "<https://example.com>",
    "<javascript:alert(1)>",
    "[x](javascript:alert(1))",
    "![x](data:text/html,boom)",
    "[x](https://example.com)",
    "[x](file:///private/data)",
    "[x][ref]\n\n[ref]: https://example.com",
    "[x][ref]\n\n[ref]: javascript:boom",
    r"\[x](javascript:boom)",
    r"\\![x](javascript:boom)",
    "&#x3c;script&#x3e;alert(1)",
    '<a href="https://example.com">label</a>',
    "![x](https://example.com/a.png)",
    "[label `x[i]`](https://example.com)",
    "<!-- comment -->",
]


@pytest.mark.parametrize("attack", ATTACKS)
def test_mixed_code_prose_does_not_recreate_html_links_images_or_definitions(attack):
    raw = "`int a[6];`\n\n" + attack
    cleaned = clean_code_markdown(raw)
    assert codes(cleaned) == codes(raw)
    assert_inert(cleaned)


def test_deterministic_delimiter_and_escaped_label_combinations():
    for code, attack, wrapper in product(
        ["a[i] < n", r'printf("\\n");', "[x](javascript:x)", "<svg/onload=x>"],
        ATTACKS[:8],
        ["`{};`", "```c\n{};\n```"],
    ):
        raw = wrapper.format(code) + "\n\n" + attack
        out = clean_code_markdown(raw)
        assert codes(out) == codes(raw)
        assert_inert(out)


def test_r03_declaration_is_correct_after_admission_without_changing_answers_or_source():
    raw = response()
    raw["blocks"][0]["markdown"] = "```c\nint scores[6] = {72, 85, 90, 66, 78, 95};\n```"
    raw["blocks"][2]["items"][0]["solution"] = "Use `scores[3]` and `0 <= i && i < 6`."
    original = deepcopy(raw)
    checked = check_scene(raw, inputs())
    assert checked["state"] == "accepted" and RULE_VERSION == "free-scene-hard-gate-v3"
    blocks = checked["cleaned"]["content"]["blocks"]
    assert codes(blocks[0]["markdown"]) == codes(raw["blocks"][0]["markdown"])
    assert r"scores\[6\]" not in blocks[0]["markdown"]
    assert blocks[1]["source"] == raw["blocks"][1]["source"]
    assert blocks[2]["items"][0]["answer_key"] == raw["blocks"][2]["items"][0]["answer_key"]
    assert codes(blocks[2]["items"][0]["solution"]) == codes(
        raw["blocks"][2]["items"][0]["solution"]
    )
    assert raw == original
    assert r"scores\[6\]" in clean_markdown(raw["blocks"][0]["markdown"])  # v1 is frozen behavior.


def test_prose_only_keeps_exact_legacy_escape_bytes():
    for raw in ATTACKS[:17] + ["# title\n\n**bold** and array."]:
        if not codes(raw):
            assert clean_code_markdown(raw) == clean_markdown(raw)
