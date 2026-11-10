# T121 Q01 单段修订执行包

父稿为 `39742e3ccc803c1afe313c7d90dc69fb778ea349227db248a09decd295c1cb97`。准备请求时核对原结果记录、11 项封存摘要、加密原件重解、严格响应结构、候选和独立失败审核。仅将原段、邻段只读文字、原 C 源码、原段引用的三个事实、固定提纲和 Q01 反例发送给模型。请求不包含迁移题答案。父稿原件、提纲和程序材料的摘要列在请求中。[首稿结果与原件索引](../live-result.json)

唯一可改字段为 `raw_output.paragraphs[2].text`。修订须保留出队判空、`*out`、前移、`count` 和时间复杂度，说明被移除元素与后续队头的原位置或身份不同、数值可以相同，以及单元素出队后为空和原第二个元素成为队头的条件。程序接受一个必填字符串 `paragraph_2_text`，拒绝其他字段、空文本、原样回显或复制其他段。事实正确性与教学职责由独立全文重评确认。合并前后仅该字段不同。

[最终请求](request.json) · [冻结清单](manifest.json) · [契约补充提案](../../../ADR/0061-t121-q01-revision.md)

## 批准项

- DeepSeek `https://api.deepseek.com/responses`，请求模型 `deepseek-flash`，非流式，`store=false`，`temperature=0.2`，`reasoning.effort=none`，严格单字段 JSON Schema。上限为输入回报 139,264 tokens、输出 4,000 tokens，请求 128 KiB、响应 2 MiB，网络超时 90 秒。
- 只批准 0 次规划、0 次整课生成、1 次局部修订，重试和回退均为 0。实际启动前另登记 30 分钟窗口。发送时至少剩余 90 秒。结构失败、未知结果或独立审核失败时封存停止。
- 本批 C2 沿用单前台尽力停止，停止后可能迟发或继续计费。本机封存无独立抗回滚保障。实际账单、金额硬上限、服务端留存及具体模型快照无独立确认。

## 执行与验收

共用入口为 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.course_trial <action> --topic queue-revision`。先用 `inspect` 核对请求与清单。准确获批后才为原访客以 `prepare --owner <原访客 UUID> --approval <本批批准 JSON>` 建立新课程操作和独立封存目录 `~/.local/share/edumind/queue-fifo-q01-revision-r01`。批准 JSON 采用共用入口的六个精确字段，即 `manifest_sha256`、`batch`、`explicit_user_authorization=true`、`accept_T121_Q01_scope_and_batch_C2=true`、`max_http_requests=1`、`window_seconds=1800`。先用更新后的代码重启 `scripts/run_head_course_goal_dev.py --profile queue` 开发应用，保留原库和原访客会话。原提纲和已取消操作按原记录复核。

用同一入口的 `send` 仅执行一次。Key 只在干净环境中的本机终端隐藏提示输入。共用封存文件的 `generate.*` 名称沿用已有流程，本批原件记录为局部修订。用 `replay` 重放，核对父子差异仅限第 3 段。由独立评估者对新候选重评原八项，重点核对 Q01 两个反例、讲解职责、事实支持及完整课程一致性。通过后封存候选绑定的 `review.json`，在窗口内执行 `publish`。任何阻断均记录并用 `stop` 关闭新批。原首稿可用 `replay --topic queue` 从冻结提交重放。

实际应用在 `http://127.0.0.1:5214/` 的原访客会话验收。核对本批来源和父稿摘要、全文、五帧与代码高亮、播放暂停和步进重置、四题错误与正确反馈、提交前答案隔离和刷新恢复。结果追加到 [T121 统一结果记录](../RESULTS.md)，分别列首稿、局部修订和最终交付。离线夹具仅用于验证接线。
