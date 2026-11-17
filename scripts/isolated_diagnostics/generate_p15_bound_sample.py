"""Build a local, synthetic, self-contained teaching sample from the fixed engine."""

import json
from pathlib import Path

from scripts.isolated_diagnostics.p15_head_insertion_engine import (
    build_actions,
    build_example,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/acceptance/phase-1.5-bound-course-sample-t093"
SPEC = dict(
    version="head-insertion-spec-v1",
    initial_values=[9],
    insert_values=[1, 2],
    variant="normal",
    allocation_success=[True, True],
)


def build() -> tuple[dict, str]:
    example = build_example(SPEC)
    actions = build_actions(example, "sample:code")
    payload = dict(example=example, actions=actions)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    assert "</script" not in encoded.lower()
    html = TEMPLATE.replace("__PAYLOAD__", encoded)
    return payload, html


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>头插法：两次插入的完整开发样例</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;line-height:1.65;color:#1a2832;background:#f3f6f5} body{max-width:1120px;margin:auto;padding:24px} header,section{background:white;padding:22px;margin:0 0 18px;border:1px solid #d9e3df;border-radius:12px}h1,h2{line-height:1.2} h1{font-size:2rem}.tag{color:#69510b;background:#fff2ca;border-radius:5px;padding:4px 8px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.mono,code,pre{font-family:ui-monospace,monospace}.code{background:#12232c;color:#d9eeeb;overflow:auto;padding:12px;border-radius:8px}.line{display:block;white-space:pre}.line.active{background:#285b57;color:white}.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}button{font:inherit;padding:7px 14px;cursor:pointer;border:1px solid #65867d;border-radius:6px;background:#eef8f3}button:disabled{opacity:.45;cursor:default}pre{overflow:auto;white-space:pre-wrap;background:#f4f8f6;padding:12px;border-radius:7px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d8e2dd;padding:8px;text-align:left;vertical-align:top}details{margin:10px 0;padding:8px;border:1px solid #d8e2dd;border-radius:6px}@media(max-width:740px){body{padding:12px}.grid{grid-template-columns:1fr}}
</style></head><body>
<header><span class="tag">离线开发样例 · 手写讲解 / 程序事实</span><h1>头插法：两次插入后，谁指向新头？</h1><p>初始链表为 <code>9 → NULL</code>，先插入 1，再插入 2。这里假定两次分配成功；<code>allocation_success=1</code> 只允许调用 <code>malloc</code>，并不保证真实分配成功。状态由受限引擎构造，并未执行 C。</p><p>学习目标：追踪调用者头指针，判断遍历是否终止，写出可知值前缀，并统计分配失败。</p></header>
<section><h2>讲解</h2><p>头插把新结点接到原链表之前。函数收到的 <code>head</code> 是局部指针；先令 <code>p-&gt;next = head</code>，再返回 <code>p</code>。调用者用 <code>caller_head = insert(...)</code> 接回返回值，自己的头指针才更新。</p><p>第一次插入后，调用者头是 <code>t0</code>，链为 <code>1 → 9 → NULL</code>；第二次成功后，头是 <code>t1</code>，链为 <code>2 → 1 → 9 → NULL</code>。分配失败时函数返回旧头；本样例假定两次均成功。还未写入的结点数据和 next 记作 <code>indeterminate</code>，不当作已知值。</p></section>
<section><h2>代码与状态播放</h2><p>每一步对应引擎生成的动作：显示状态、标记代码行或前进。播放展示的是模型化轨迹，而不是执行程序。</p><div class="toolbar"><button id="play">播放</button><button id="pause">暂停</button><button id="prev">上一步</button><button id="next">下一步</button><button id="reset">重置</button></div><p id="progress" aria-live="polite"></p><div class="grid"><div><h3>代码</h3><div id="code" class="code mono" aria-label="C 源代码"></div></div><div><h3>当前动作与状态</h3><pre id="event"></pre><pre id="state"></pre></div></div></section>
<section><h2>四道练习</h2><details><summary>1. 两次插入后，调用者的头结点 ID 是什么？</summary><p>答案：<code>t1</code>。第二次调用返回 <code>t1</code>，调用者接回它。</p></details><details><summary>2. 从调用者头遍历，分类是什么？</summary><p>答案：<code>terminated</code>。依次到达 t1、t0、i0，最后为 NULL。</p></details><details><summary>3. 首次重复或不确定指针前的可知值前缀是什么？</summary><p>答案：<code>[2, 1, 9]</code>。本例到达 NULL，因此该前缀也是本例完整遍历值；对循环或未知 next 不能作相同推断。</p></details><details><summary>4. 这次合成规格里分配失败几次？</summary><p>答案：<code>0</code>。两个抽象分配掩码均为 true；真实 malloc 成败不由掩码保证。</p></details></section>
<section><h2>学习目标 → 内容 → 证据</h2><table><thead><tr><th>目标</th><th>课程内容</th><th>可核对证据</th></tr></thead><tbody><tr><td>调用者头</td><td>局部 head、返回值与 caller_head 区分</td><td>代码 return / 两次 caller 赋值；轨迹 caller 步；题 1</td></tr><tr><td>终止分类</td><td>沿 next 到 NULL</td><td>最终 t1→t0→i0→NULL；题 2</td></tr><tr><td>可知值前缀</td><td>按可达顺序读取，不把未知当完整输出</td><td>最终状态 data 2、1、9；题 3</td></tr><tr><td>分配失败</td><td>失败时返回旧头，本例假定成功</td><td>两次 allocation_success=true；引擎 observation；题 4</td></tr></tbody></table><p>模型化状态与动作的完整原件在同目录 <code>sample.json</code>。本页不是正式课程签核，不能证明任意 C 程序或真实 malloc 的行为。</p></section>
<script id="sample-data" type="application/json">__PAYLOAD__</script><script>
"use strict";
const data=JSON.parse(document.querySelector('#sample-data').textContent), actions=data.actions, states=data.example.trace.steps;
const code=document.querySelector('#code'), eventOut=document.querySelector('#event'), stateOut=document.querySelector('#state'), progress=document.querySelector('#progress');
let cursor=-1, timer=null;
data.example.code.source.trimEnd().split('\n').forEach((line,i)=>{const el=document.createElement('span');el.className='line';el.dataset.line=String(i+1);el.textContent=String(i+1).padStart(2,' ')+'  '+line;code.appendChild(el)});
function render(){let state=null,line=null;for(let i=0;i<=cursor;i++){const a=actions[i];if(a.kind==='show_state')state=states[a.step];if(a.kind==='highlight_code')line=a.line}for(const el of code.children)el.classList.toggle('active',Number(el.dataset.line)===line);const a=cursor<0?null:actions[cursor];eventOut.textContent=a?JSON.stringify(a,null,2):'尚未播放';stateOut.textContent=state?JSON.stringify(state,null,2):'尚无状态';progress.textContent=`动作 ${cursor+1} / ${actions.length}`;progress.dataset.cursor=String(cursor);document.querySelector('#prev').disabled=cursor<0;document.querySelector('#next').disabled=cursor>=actions.length-1}
function stop(){if(timer!==null){clearInterval(timer);timer=null}}function next(){if(cursor<actions.length-1){cursor++;render()}if(cursor>=actions.length-1)stop()}
document.querySelector('#play').addEventListener('click',()=>{if(timer===null && cursor<actions.length-1)timer=setInterval(next,180)});document.querySelector('#pause').addEventListener('click',stop);document.querySelector('#next').addEventListener('click',()=>{stop();next()});document.querySelector('#prev').addEventListener('click',()=>{stop();if(cursor>=0)cursor--;render()});document.querySelector('#reset').addEventListener('click',()=>{stop();cursor=-1;render()});render();
</script></body></html>
"""


if __name__ == "__main__":
    data, html = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    (OUT / "course.html").write_text(html)
    print(
        f"Built sample: {len(data['example']['trace']['steps'])} states, {len(data['actions'])} actions"
    )
