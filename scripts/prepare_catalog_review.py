"""Make a local escaped review preview; no approval or publication side effect."""

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.catalog_package import load_package  # noqa: E402
from app.services.knowledge_graph import default_knowledge_graph_repository  # noqa: E402


def render() -> str:
    package = load_package(ROOT / "data/course_catalog/linear-v1")
    graph = default_knowledge_graph_repository()

    def esc(value):
        return html.escape(str(value))

    navigation = "".join(
        f'<a href="#{esc(node)}">{esc(graph.get_node(node).name)}</a>'
        for node in package.nodes
    )
    sections = []
    for node, resources in package.nodes.items():
        code = resources["code"]
        questions = "".join(
            f"<li><p>{esc(q['question'])}</p><strong>标准答案：{esc(q['answer'])}</strong><p>{esc(q['explanation'])}</p></li>"
            for q in resources["exercise"]["items"]
        )
        steps = "".join(f"<li>{esc(step)}</li>" for step in code["key_steps"])
        sections.append(
            f'<section id="{esc(node)}"><h2>{esc(graph.get_node(node).name)}</h2><small>{esc(node)}</small>'
            f'<h3>讲解</h3><pre class="prose">{esc(resources["explanation"]["markdown"])}</pre>'
            f"<details><summary>完整 C 示例（含边界断言）</summary><pre><code>{esc(code['source'])}</code></pre></details>"
            f"<h3>预期输出</h3><pre>{esc(code['expected_output'])}</pre><ol>{steps}</ol>"
            f"<h3>固定练习及反馈</h3><ol>{questions}</ol></section>"
        )
    demo = "".join(
        f"<h3>{esc(p['title'])}</h3><p>{esc(p['text'])}</p>"
        for p in package.demo["perspectives"]
    )
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>线性结构课程候选 · 人工审阅</title><style>
body{{margin:0;background:#eef3f1;color:#17253a;font:16px/1.8 system-ui,sans-serif}}main{{max-width:1050px;margin:auto;padding:32px 20px}}header,section{{padding:24px;background:#fbfcf9;border:1px solid #cbd6d4;margin:20px 0}}nav{{display:flex;gap:12px;flex-wrap:wrap}}a{{color:#244c5a}}h1,h2{{line-height:1.3}}pre{{overflow:auto;background:#eaf0f2;padding:16px;font:13px/1.7 monospace}}pre.prose{{white-space:pre-wrap;font:inherit;background:transparent;padding:0}}summary{{cursor:pointer;color:#244c5a;font-weight:600}}.digest{{overflow-wrap:anywhere}}li{{margin:16px 0}}
</style><main><header><small>待人工审核 · 尚未作为正式课程发布</small><h1>线性结构课程候选</h1><p>10 节点、30 资源、30 题及一份预设演示。工程测试只验证运行、结构和边界；请审阅教学内容、完整 C 示例、题目答案与反馈。</p><p class="digest">linear-course v0.1.0<br>SHA256：<code>{package.digest}</code></p><nav>{navigation}<a href="#demo">预设演示</a></nav></header>{"".join(sections)}<section id="demo"><h2>{esc(package.demo["title"])}</h2>{demo}<h3>结论</h3><p>{esc(package.demo["summary"])}</p></section></main></html>"""


if __name__ == "__main__":
    target = ROOT / "local-materials/catalog-course-review-20261003.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render())
    print(target)
