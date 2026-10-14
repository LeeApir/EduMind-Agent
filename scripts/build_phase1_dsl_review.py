"""Prepare actual MP4/SRT/step frames with immutable hashes for human T037 review."""

import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.animation_dsl_compiler import compile_animation_dsl  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run = Path(sys.argv[1]).resolve()
    report = json.loads((run / "matrix-result.json").read_text())
    assert report["automatic_matrix_passed"] and report["human_review"] == "pending"
    protocol = run / "matrix-protocol.json"
    plan = json.loads(protocol.read_text())
    assert digest(protocol) == report["protocol_sha256"]
    target = run / "human-review"
    target.mkdir(exist_ok=False)
    entries = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        for index, case in enumerate(plan["trusted_cases"]):
            row = next(
                row
                for row in report["dsl_slots"]
                if row["case_index"] == index and row["cold"]
            )
            assert row["ok"]
            compiled = compile_animation_dsl(
                json.dumps(case["dsl"], ensure_ascii=False), knowledge_point_id="array"
            )
            assert compiled.validated.dsl_sha256 == row["dsl_sha256"]
            assert compiled.source_sha256 == row["compiled_sha256"]
            mp4s = list(
                (run / "media-cache/dsl").glob(
                    "*/objects/" + row["mp4_sha256"] + ".mp4"
                )
            )
            srts = list(
                (run / "media-cache/dsl").glob(
                    "*/objects/" + row["srt_sha256"] + ".srt"
                )
            )
            assert len(mp4s) == len(srts) == 1
            assert (
                digest(mp4s[0]) == row["mp4_sha256"]
                and digest(srts[0]) == row["srt_sha256"]
            )
            assert srts[0].read_text() == compiled.subtitles
            prefix = case["id"]
            shutil.copyfile(mp4s[0], target / (prefix + ".mp4"))
            shutil.copyfile(srts[0], target / (prefix + ".srt"))
            (target / (prefix + ".vtt")).write_text(
                "WEBVTT\n\n"
                + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", compiled.subtitles)
            )
            (target / (prefix + ".json")).write_text(
                json.dumps(case["dsl"], ensure_ascii=False, indent=2) + "\n"
            )
            page.goto((target / (prefix + ".mp4")).as_uri())
            page.wait_for_function("document.querySelector('video')?.readyState >= 2")
            dimensions = page.locator("video").evaluate(
                "v => ({width:v.videoWidth,height:v.videoHeight})"
            )
            assert dimensions == {"width": 1280, "height": 720}
            frames = []
            for frame in compiled.validated.frames:
                seconds = (frame.end_ms - 700) / 1000
                presented_seconds = page.evaluate(
                    """async t => {
                    const video = document.querySelector('video'); video.pause(); video.controls=false;
                    const presented = new Promise(resolve => {
                        const onFrame=(_,metadata)=>{
                            if(Math.abs(metadata.mediaTime-t)<=1/15+1e-6) resolve(metadata.mediaTime);
                            else video.requestVideoFrameCallback(onFrame);
                        };
                        video.requestVideoFrameCallback(onFrame);
                    });
                    video.currentTime=t;
                    const mediaTime = await Promise.race([presented,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Target frame not presented')),5000))]);
                    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                    return mediaTime;
                }""",
                    seconds,
                )
                image = prefix + f"-step-{frame.action_index + 1:02}.png"
                page.locator("video").evaluate("v => {v.controls = false;}")
                page.locator("video").screenshot(path=str(target / image))
                frames.append(
                    {
                        "action_index": frame.action_index,
                        "op": frame.op,
                        "seconds": seconds,
                        "presented_seconds": presented_seconds,
                        "caption": frame.caption,
                        "image": image,
                        "sha256": digest(target / image),
                    }
                )
            entries.append(
                {
                    "case_id": prefix,
                    "values": case["values"],
                    "dimensions": dimensions,
                    "fps": 15,
                    "dsl_sha256": row["dsl_sha256"],
                    "mp4": prefix + ".mp4",
                    "mp4_sha256": row["mp4_sha256"],
                    "srt": prefix + ".srt",
                    "srt_sha256": row["srt_sha256"],
                    "vtt": prefix + ".vtt",
                    "vtt_sha256": digest(target / (prefix + ".vtt")),
                    "dsl": prefix + ".json",
                    "dsl_file_sha256": digest(target / (prefix + ".json")),
                    "expected_final": case["expected_final"],
                    "frames": frames,
                }
            )
        browser.close()
    manifest = {
        "task_id": "PHASE-1-T037",
        "human_review": "pending",
        "qualification": "actual generated test media; no publication/dynamic-opening approval",
        "protocol_sha256": digest(protocol),
        "matrix_result_sha256": digest(run / "matrix-result.json"),
        "cases": entries,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    cards = []
    for entry in entries:
        prefix = entry["case_id"]
        steps = "".join(
            f'<figure><a href="{frame["image"]}" target="_blank" rel="noopener"><img loading="lazy" src="{frame["image"]}" alt="{html.escape(frame["op"])}"></a>'
            f"<figcaption>{frame['action_index'] + 1}. {html.escape(frame['caption'])}</figcaption></figure>"
            for frame in entry["frames"]
        )
        cards.append(
            f'<section id="{prefix}"><h2>{prefix} · {entry["values"]}</h2>'
            f'<video controls preload="metadata" src="{entry["mp4"]}"><track kind="subtitles" '
            f'srclang="zh" label="字幕" src="{prefix}.vtt"></video>'
            f'<p><a href="{entry["srt"]}">SRT字幕</a> · <a href="{entry["dsl"]}">DSL动作</a></p>'
            f"<p>最终值：n0={entry['expected_final']['n0_value']}，"
            f"n1={entry['expected_final']['n1_value']}；指针NULL；连接清除；n1已访问。</p>"
            f'<details><summary>逐动作帧（11步）</summary><div class="steps">{steps}</div></details></section>'
        )
    manifest_sha = digest(target / "manifest.json")
    page_html = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>T37 人工媒体验收</title><style>body{font:16px/1.6 system-ui;max-width:1280px;"
        "margin:32px auto;padding:0 20px;color:#202b35;background:#f6f7f9}section{background:white;"
        "padding:22px;margin:24px 0;border:1px solid #ddd;border-radius:8px}video{display:block;width:100%;height:auto;aspect-ratio:16/9;"
        "max-width:1280px}.steps{display:grid;grid-template-columns:1fr;"
        "gap:12px}figure{margin:0}img{width:100%}code{overflow-wrap:anywhere}a{color:#1265ab}</style>"
        "<h1>T37 · 720p / 15fps · 20个固定DSL样本人工核对</h1><p>逐个核对实际视频、字幕与DSL动作一致，"
        "确认创建、连接、指针、高亮、比较、值交换、访问、断连及复杂度展示。数值包括边界与相等情形。</p>"
        "<p>画面已含说明，外置字幕默认关闭。逐动作图片可点击查看原始720p画面。</p>"
        "<p>这些是隔离测试媒体。审核为明确Mock，正式动态入口保持关闭。</p>"
        f'<p>本次清单：<code>{manifest_sha}</code> · <a href="manifest.json">摘要清单</a></p>'
        "<p>请核对20个视频及必要的逐动作帧，确认通过后在聊天中回复“人工核对通过”；"
        "有问题请报告样本ID与步骤。</p>" + "".join(cards) + "</html>"
    )
    (target / "index.html").write_text(page_html)
    print(
        json.dumps(
            {
                "review_path": str(target),
                "manifest_sha256": manifest_sha,
                "cases": len(entries),
                "step_frames": sum(len(e["frames"]) for e in entries),
                "human_review": "pending",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
