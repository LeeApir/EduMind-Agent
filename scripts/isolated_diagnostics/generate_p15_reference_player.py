"""Generate a synthetic, non-production preview of the reference artifact."""

import html
import json
import re
from pathlib import Path

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifacts
from scripts.isolated_diagnostics import p15_visible_review_view_v1 as visible
from scripts.isolated_diagnostics.p15_combined_candidate_contract import SPEC
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/acceptance/phase-1.5-reference-player-t102"
OLD = ROOT / "docs/acceptance/phase-1.5-combined-candidate-r01/results/candidate.json"
TEMPLATE = ROOT / "docs/acceptance/phase-1.5-real-candidate-player-t098/template.html"


def sample():
    old = json.loads(OLD.read_text())
    c.verify_artifact(old)
    value = old["raw_output"]
    value["paragraphs"][0]["text"] += (
        "\n\n`示例代码` [资料][r] [资料][r] [其它][s] <script>alert(1)</script>\n\n[r]: javascript:alert(1)\n[s]: https://example.test/other"
    )
    catalog = c.make_catalog(SPEC)
    ident = c.identity("preview", "reference_example", "C", 0, SPEC, None)
    course = artifacts.assemble(value, ident, catalog)
    artifacts.verify(course, catalog)
    view, binding = visible.build(course, catalog)
    assert binding["candidate_digest"] == course["artifact_digest"]
    return course, catalog, canonical(view)


def build(course=None, catalog=None):
    c.require((course is None) == (catalog is None), "PREVIEW_INPUT_PAIR")
    if course is None:
        course, catalog, _ = sample()
    artifacts.verify(course, catalog)
    arm = course["identity"]["arm"]
    c.require(arm in ("B", "C"), "PREVIEW_ARM")
    view, binding = visible.build(course, catalog)
    target_ids = {
        value["pointer"]: key
        for key, value in binding["paths"].items()
        if value["root"] == "artifact"
        and value["projection"]["type"]
        in ("identity", "reference_occurrence", "reference_definition")
    }
    source = course["source"]
    docs = source["documents"]
    example = catalog["example"]

    def esc(s):
        return html.escape(str(s), quote=True)

    paragraphs = "".join(
        '<p class="model-paragraph" data-target-id="'
        + esc(target_ids[f"/raw_output/paragraphs/{i}/text"])
        + '"></p>'
        for i, b in enumerate(row for row in source["blocks"] if row["kind"] == "text")
    )
    questions = "".join(
        '<details class="question"><summary data-target-id="'
        + esc(target_ids[f"/raw_output/questions/{b['observation_key']}/stem"])
        + '">'
        + (
            '</summary><p>程序参考答案：<code data-target-id="'
            if arm == "C"
            else '</summary><p>模型原始答案：<code data-target-id="'
        )
        + esc(
            target_ids[
                f"/source/blocks/{i}/answer_key"
                if arm == "C"
                else f"/raw_output/answers/{b['observation_key']}"
            ]
        )
        + '">'
        + '</code></p><p class="explanation" data-target-id="'
        + esc(target_ids[f"/raw_output/questions/{b['observation_key']}/explanation"])
        + '">'
        + "</p></details>"
        for i, b in enumerate(source["blocks"])
        if b["kind"] == "question"
    )
    refs = "".join(
        '<li class="reference" data-id="'
        + esc(key)
        + '" data-target-id="'
        + esc(target_ids[f"/source/documents/references/{key}"])
        + '"><code class="reference-summary" data-target-id="'
        + esc(target_ids[f"/source/documents/references/{key}"])
        + '"></code><span class="reference-url" data-target-id="'
        + esc(target_ids[f"/source/documents/references/{key}/url"])
        + '"></span><span class="reference-title" data-target-id="'
        + esc(target_ids[f"/source/documents/references/{key}/title"])
        + '"></span></li>'
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
        + '"><span class="occurrence-label"></span><code class="evidence-target"></code>'
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
    state_cells = [cell for cell in view["cells"] if cell["kind"] == "state"]
    state_steps = (
        list(range(len(example["trace"]["steps"])))
        if arm == "C"
        else [
            action["step"]
            for action in source["actions"]
            if action["kind"] == "show_state"
        ]
    )
    c.require(len(state_cells) == len(state_steps), "PREVIEW_STATE_BINDING")
    state_targets = {
        str(step): {"id": cell["id"], "text": cell["text"]}
        for step, cell in zip(state_steps, state_cells)
    }
    action_cells = [cell for cell in view["cells"] if cell["kind"] == "action"]
    c.require(len(action_cells) == len(source["actions"]), "PREVIEW_ACTION_BINDING")
    data = dict(
        candidate_digest=course["artifact_digest"],
        representation_digest=docs["digest"],
        view_digest=binding["view_digest"],
        visible_cells={cell["id"]: cell for cell in view["cells"]},
        code=code,
        code_lines=code.splitlines(keepends=True),
        code_line_targets=[
            cell["id"] for cell in view["cells"] if cell["kind"] == "code_line"
        ],
        state_targets=state_targets,
        action_targets=[
            {"id": cell["id"], "text": cell["text"]} for cell in action_cells
        ],
        states=example["trace"]["steps"]
        if arm == "C"
        else {
            str(action["step"]): action["state"]
            for action in source["actions"]
            if action["kind"] == "show_state"
        },
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
        .replace(
            "两次 malloc 的实际成功是本例假设", "分配成功或失败由本例抽象测试掩码指定"
        )
    )
    if arm == "B":
        template = template.replace("模型题目与程序参考答案", "模型题目与模型原始答案")
        template = template.replace(
            "代码、答案与轨迹来自程序。",
            "B 臂的代码、答案、状态和动作来自传入候选，不用参考值代填。",
        )
        template = template.replace("函数内部状态。", "模型输出状态，作用域仍需审核。")
    template = template.replace(
        "</style>",
        ".model-paragraph,.question summary,.question .explanation{white-space:pre-wrap}</style>",
    )
    assert template.count("data.code.trimEnd().split('\\n')") == 1
    template = template.replace(
        "data.code.trimEnd().split('\\n')",
        r"data.code_lines.map(line => line.replace(/(?:\r\n|[\n\v\f\r\x1c-\x1e\x85\u2028\u2029])$/u, ''))",
    )
    assert template.count("el.dataset.line=String(i+1);") == 1
    template = template.replace(
        "el.dataset.line=String(i+1);",
        "el.dataset.line=String(i+1);el.dataset.targetId=data.code_line_targets[i];",
    )
    assert template.count("let state=null,line=null;") == 1
    assert template.count("function render()") == 1
    template = template.replace(
        "function render()",
        "document.querySelectorAll('.model-paragraph,.question summary,.question code,.question .explanation,.reference-summary,.reference-url,.reference-title').forEach(el=>{el.textContent=data.visible_cells[el.dataset.targetId].text});document.querySelectorAll('.occurrence').forEach(el=>{const c=data.visible_cells[el.dataset.targetId];el.querySelector('.occurrence-label').textContent=c.reference_kind+'：'+c.label+'（文档 '+c.document+'，解析树位置 '+el.dataset.path+'，定义 '+c.reference_id+'）';el.querySelector('.evidence-target').textContent=c.text});function render()",
    )
    template = template.replace(
        "let state=null,line=null;", "let state=null,line=null,stateTarget=null;"
    )
    assert template.count("state=states[a.step];line=null") == 1
    template = template.replace(
        "state=states[a.step];line=null",
        "state=states[a.step];stateTarget=data.state_targets[String(a.step)];line=null",
    )
    old_render = "eventOut.textContent=action?JSON.stringify(action,null,2):'尚未播放';stateOut.textContent=state?JSON.stringify(state,null,2):'尚无状态';"
    new_render = "eventOut.textContent=action?data.action_targets[cursor].text:'尚未播放';eventOut.dataset.targetId=action?data.action_targets[cursor].id:'';stateOut.textContent=stateTarget?stateTarget.text:'尚无状态';stateOut.dataset.targetId=stateTarget?stateTarget.id:'';"
    assert template.count(old_render) == 1
    template = template.replace(old_render, new_render)
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
