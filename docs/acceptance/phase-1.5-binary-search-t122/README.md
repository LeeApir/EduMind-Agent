# T122 固定二分查找执行包

学习目标是用零基下标和闭区间在 `[2,5,8,12,16]` 中查找 5。程序代码执行 `mid = left + (right - left) / 2`。六帧记录初始化、两次比较及其更新、命中返回 1。四题共用另一组升序数据和两次独立查找，分别考查左右端点首次更新、命中和未命中。程序提供练习参考答案给模型用于撰写解析，答案及解析在提交前留在服务端。[独立预期](independent-reference.json)

## 批准项

- DeepSeek 官方 `https://api.deepseek.com/responses`，请求模型 `deepseek-flash`，非流式，`store=false`，`temperature=0.2`，`reasoning.effort=none`，严格 JSON Schema。上限为输入回报 139,264 tokens、输出 4,000 tokens，请求 128 KiB、响应 2 MiB，网络超时 90 秒。
- **首稿 1 次，规划、修订、重试和回退均为 0**。实际启动前登记新 30 分钟窗口，发送时至少剩余 90 秒。本批无获准修订字段。请求、协议、未知结果或审核阻断时保存证据并停止，本批交付失败。
- 本批 C2 沿用单前台尽力停止，停止后可能迟发或继续计费。本机封存无独立抗回滚保障。实际账单、金额硬上限、服务端留存及具体模型快照无独立确认。

[最终请求](request.json) · [冻结清单](manifest.json) · [ADR0062](../../ADR/0062-fixed-binary-search-trial.md)

## 执行和验收

1. 使用 `PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile binary-search --prepare --start` 启动本机入口 `http://127.0.0.1:5216/`（API 8196）。保留本机访客，核对浏览器会话、专用库和该访客的活动操作状态。若未创建发送记录而已有旧操作占位，先按现有恢复流程核实终态。
2. 共用入口为 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.course_trial <action> --topic binary-search`。先用 `inspect` 核对准确包。只有用户批准后才使用 `prepare --owner <访客 UUID> --approval <批准 JSON>` 建立新窗口。批准字段为 `manifest_sha256`、`batch=binary-search-deepseek-r01`、`explicit_user_authorization=true`、`accept_T122_scope_and_batch_C2=true`、`max_http_requests=1` 和 `window_seconds=1800`。记录起止时间及新目录 `~/.local/share/edumind/binary-search-deepseek-r01`。
3. 同一入口 `send` 只执行一次，凭据仅在干净环境中的本机终端隐藏提示输入。原始响应先加密保存。使用 `replay` 复核请求、响应、候选和材料绑定。异常时保留原件并用 `stop` 关闭本机操作。发出的请求可能继续完成。
4. 独立评估者对准确候选重算六帧和四题，逐段复核教学、事实引用、区间、比较、终止和重复值边界，以及题目条件、唯一性与解析。审核必须通过 `BINARY_SEARCH.checks` 的八项且无阻断。绑定 `review.json` 后在窗口内 `publish`，有阻断即停止。
5. 用原访客验收全文、六帧、高亮、播放暂停、前后步与重置、四题正反反馈、答案隔离和刷新恢复。课程入口、授权窗口、用量、封存摘要、候选审核和最终状态记录在 [统一结果](RESULTS.md)。
