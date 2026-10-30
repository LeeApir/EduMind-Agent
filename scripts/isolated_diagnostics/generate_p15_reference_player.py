"""Generate a synthetic, non-production preview of the reference artifact."""

import html
import json
import re
from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifacts
from scripts.isolated_diagnostics import p15_reference_review_v1 as review
from scripts.isolated_diagnostics import p15_reference_document_v1 as documents
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/acceptance/phase-1.5-reference-player-t102"
OLD = ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01/results/candidate.json"
TEMPLATE = ROOT / "docs/acceptance/phase-1.5-real-candidate-player-t098/template.html"


def sample():
    old = json.loads(OLD.read_text())
    c.verify_artifact(old)
    value = old["raw_output"]
    value["paragraphs"][0]["text"] += (
        "\n\n`示例代码` [资料][r] [资料][r] <script>alert(1)</script>\n\n[r]: javascript:alert(1)"
    )
    catalog = c.make_catalog(SPEC)
    ident = c.identity("preview", "reference_example", "C", 0, SPEC, None)
    course = artifacts.assemble(value, ident, catalog)
    artifacts.verify(course, catalog)
    body, binding = review.review_body(course, catalog)
    assert binding["artifact"] == course
    return course, catalog, body


def build(course=None, catalog=None):
    c.require((course is None) == (catalog is None), "PREVIEW_INPUT_PAIR")
    if course is None:
        course, catalog, _ = sample()
    artifacts.verify(course, catalog)
    c.require(course["identity"]["arm"] == "C", "PREVIEW_C_ONLY")
    _, binding = review.review_body(course, catalog)
    target_ids = {value["path"]: key for key, value in binding["targets"].items()}
    source = course["source"]
    docs = source["documents"]
    example = catalog["example"]

    def esc(s):
        return html.escape(str(s), quote=True)

    paragraphs = "".join(
        '<p class="model-paragraph" data-target-id="'
        + esc(target_ids[f"/raw_output/paragraphs/{i}/text"])
        + '">'
        + esc(docs["documents"][b["document"]]["original"])
        + "</p>"
        for i, b in enumerate(row for row in source["blocks"] if row["kind"] == "text")
    )
    questions = "".join(
        '<details class="question"><summary>'
        + esc(docs["documents"][b["stem_document"]]["original"])
        + "</summary><p>程序参考答案：<code>"
        + esc(json.dumps(b["answer_key"], ensure_ascii=False))
        + '</code></p><p class="explanation">'
        + esc(docs["documents"][b["explanation_document"]]["original"])
        + "</p></details>"
        for b in source["blocks"]
        if b["kind"] == "question"
    )
    refs = "".join(
        '<li class="reference" data-id="'
        + esc(key)
        + '" data-target-id="'
        + esc(target_ids[f"/source/documents/references/{key}"])
        + '">'
        + esc(json.dumps(value, ensure_ascii=False))
        + "</li>"
        for key, value in docs["references"].items()
    )
    occurrences = "".join(
        '<li class="occurrence" data-document="'
        + esc(key)
        + '" data-path="'
        + esc(json.dumps(row["path"]))
        + '" data-id="'
        + esc(row["reference_id"])
        + '" data-target-id="'
        + esc(
            target_ids[
                f"/source/documents/documents/{key}/occurrences/{index}/{'label' if row['label'] else 'kind'}"
            ]
        )
        + '">'
        + esc(row["kind"])
        + "："
        + esc(documents.occurrence_label(docs, key, row))
        + "（文档 "
        + esc(key)
        + "，解析树位置 "
        + esc(json.dumps(row["path"]))
        + "）"
        + "</li>"
        for key, value in docs["documents"].items()
        for index, row in enumerate(value["occurrences"])
    )
    questions += (
        '<section><h2>集中引用定义与解析树位置</h2><ul id="references">'
        + refs
        + '</ul><ul id="occurrences">'
        + occurrences
        + "</ul></section>"
    )
    code = next(b["text"] for b in source["blocks"] if b["kind"] == "code")
    data = dict(
        candidate_digest=course["artifact_digest"],
        representation_digest=docs["digest"],
        code=code,
        states=example["trace"]["steps"],
        actions=source["actions"],
    )
    encoded = (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = (
        TEMPLATE.read_text()
        .replace("真实生成候选 · 未签核", "合成开发预览 · 非模型结果")
        .replace("头插法：真实候选及状态回放", "头插法：引用表示开发预览")
        .replace(
            "讲解、题干和解析来自模型；", "内容由助手改写用于离线预演，不是模型新结果；"
        )
    )
    template = template.replace(
        "</style>",
        ".model-paragraph,.question summary,.question .explanation{white-space:pre-wrap}</style>",
    )
    replacements = {
        "__PARAGRAPHS__": paragraphs,
        "__QUESTIONS__": questions,
        "__PAYLOAD__": encoded,
        "__DIGEST__": esc(course["artifact_digest"]),
    }
    for key in replacements:
        assert template.count(key) == 1
    return re.sub(
        r"__(?:PARAGRAPHS|QUESTIONS|PAYLOAD|DIGEST)__",
        lambda match: replacements[match.group()],
        template,
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "course.html").write_text(build())
