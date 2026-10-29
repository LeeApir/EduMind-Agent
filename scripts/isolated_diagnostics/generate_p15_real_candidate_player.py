"""Render the actual frozen pilot candidate as an isolated static local player."""

import html
import json
from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC
from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_actions,
    build_example,
    digest,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01/results/candidate.json"
)
OUT = ROOT / "docs/acceptance/phase-1.5-real-candidate-player-t098"


def build() -> str:
    artifact = json.loads(SOURCE.read_text())
    c.verify_artifact(artifact)
    example = build_example(SPEC)
    source = artifact["source"]
    blocks = source["blocks"]
    code = next(x for x in blocks if x["kind"] == "code")
    assert (
        source["example_digest"] == example["payload_digest"]
        and code["text"] == example["code"]["source"]
    )
    assert source["actions"] == build_actions(example, code["anchor"])
    for a in source["actions"]:
        assert a["anchor"] == code["anchor"]
        if a["kind"] == "show_state":
            assert a["state_digest"] == digest(example["trace"]["steps"][a["step"]])
        if a["kind"] == "highlight_code":
            assert a["line"] == example["trace"]["steps"][a["step"]]["code_line"]

    def esc(s):
        return html.escape(str(s), quote=True)

    paragraphs = "".join(
        '<p class="model-paragraph">' + esc(b["markdown"]) + "</p>"
        for b in blocks
        if b["kind"] == "text"
    )
    questions = "".join(
        '<details class="question"><summary>'
        + esc(b["stem"])
        + "</summary><p>程序参考答案：<code>"
        + esc(json.dumps(b["answer_key"], ensure_ascii=False))
        + '</code></p><p class="explanation">'
        + esc(b["explanation"])
        + "</p></details>"
        for b in blocks
        if b["kind"] == "question"
    )
    data = dict(
        candidate_digest=artifact["artifact_digest"],
        code=code["text"],
        states=example["trace"]["steps"],
        actions=source["actions"],
    )
    encoded = (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = (OUT / "template.html").read_text()
    for key, value in {
        "__PARAGRAPHS__": paragraphs,
        "__QUESTIONS__": questions,
        "__PAYLOAD__": encoded,
        "__DIGEST__": esc(artifact["artifact_digest"]),
    }.items():
        assert template.count(key) == 1
        template = template.replace(key, value)
    return template


if __name__ == "__main__":
    rendered = build()
    (OUT / "course.html").write_text(rendered)
    print("real candidate player generated:", len(rendered.encode()), "bytes")
