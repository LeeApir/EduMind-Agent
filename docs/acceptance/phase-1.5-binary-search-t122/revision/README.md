# T122 十字段限定修订

原响应 SHA-256 为 `a083646c1a9109f04384dbaac2564699ec77092010fd7e8d3aee697eb7ea2409`。程序重新核对原封存清单、解密回执、原请求、完整材料及四处缺失解析，提取未准入的原稿。新请求携带原响应、原请求、原稿和材料摘要，以及准确题干、帧说明、程序代码、事实与参考答案。[原失败证据](../live-result.json)

| 唯一允许改动的位置 | 要求 |
| --- | --- |
| `questions.increase_left.stem`、`questions.increase_left.explanation` | 目标 19，第一次更新后的闭区间端点，JSON 整数数组 |
| `questions.decrease_right.stem`、`questions.decrease_right.explanation` | 目标 9，第一次更新后的闭区间端点，JSON 整数数组 |
| `questions.found_index.stem`、`questions.found_index.explanation` | 目标 19 的函数返回值，整数 |
| `questions.missing_result.stem`、`questions.missing_result.explanation` | 目标 9 的函数返回值，整数 |
| `step_notes[2].note` | f2 第 13 行。本轮刚比较 `values[2]=8 > 5`，更新右端点到 1，区间为 `[0,1]`。保留刚用过且已排除的 `mid=2` |
| `step_notes[4].note` | f4 第 11 行。本轮刚比较 `values[0]=2 < 5`，更新左端点到 1，区间为 `[1,1]`。保留刚用过且已排除的 `mid=0` |

响应外层只允许 `questions` 和 `frame_notes`。四个题键各有 `stem` 和 `explanation`，帧键为 `f2` 和 `f4`，映射到原六帧中对应的 `note`。十个叶值均为不超过 1,200 字符的非空简体中文单行纯文本。允许标点、标识符、比较符号和行内区间或 JSON 数组写法。请求禁止额外或重复键、空值、用数组代替字符串、整课、补丁、附带说明、工具、HTML、链接、Markdown 格式、围栏和代码片段。题干额外禁止花括号、分号、`#include` 和反引号。题干逐字匹配程序指定值，原 C 情境继续由程序附加。f2 和 f4 都必须说明刚完成的比较与区间更新同属本轮，突出已排除的旧中点。审核者核对准确高亮、帧语义、解题过程与全文一致性。首稿中「排除一半」的表述留给全文审核按原标准判断。

待批准额度为 1 次 DeepSeek 修订、0 次规划、0 次整课生成，重试和回退为 0。使用原 DeepSeek 官方 Responses 路由与模型配置，输入回报上限 139,264 tokens，输出上限 4,000 tokens，请求 128 KiB，响应 2 MiB，网络超时 90 秒。另登记 30 分钟窗口，发送时须至少剩余 90 秒。本批 C2 涵盖单前台尽力停止、停止后可能迟发或继续计费、本机原件无独立抗回滚保障，以及实际账单、费用硬上限、服务端留存和具体模型快照未独立确认。

共用入口为 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.course_trial <action> --topic binary-search-revision`。获准后按 `inspect`、`prepare`、`send`、`replay`、独立全文审核、`publish` 的次序使用。用当前代码重启 T122 专用本机应用并保留原库。在原访客名下核对旧操作终态并建立新操作，封存目录为 `~/.local/share/edumind/binary-search-revision-r01`。批准键为 `accept_T122_revision_scope_and_batch_C2`。终端隐藏输入密钥。阻断时按共用规则 `stop`。通过后在 [本机开发应用](http://127.0.0.1:5216/) 验收阅读、六帧高亮、播放控制、四题反馈、答案隔离和刷新恢复。

[准确请求](request.json) · [冻结清单](manifest.json) · [契约差异](../../../ADR/0062-t122-revision.md) · [统一结果记录](../RESULTS.md)
