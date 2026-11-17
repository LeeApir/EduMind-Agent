# T121 固定队列课程执行包

目标是交付一课可实际学习的 FIFO 队列课程。用空队列依次执行 `enqueue(3) → enqueue(8) → dequeue() → enqueue(5)`。程序提供 C 代码、五帧、事实、迁移情境及私有答案。模型仅生成教学内容。课程采用固定容量 3 的连续数组，出队前移，队头到队尾为 `[] → [3] → [3,8] → [8] → [8,5]`。第三次操作取出 3，8 成为新队头。独立 C 参考还覆盖判空、判满、前移及迁移题。[独立参考](independent-reference.json)

拟议请求为 DeepSeek 官方 `https://api.deepseek.com/responses`，模型 `deepseek-flash`，非流式，`store=false`，`temperature=0.2`，`reasoning.effort=none`，输出上限 4,000 tokens，严格 JSON Schema。请求及响应的限制为 128 KiB／2 MiB，回报输入上限 139,264 tokens，网络超时 90 秒。批准范围为 **首稿 1 次、规划 0 次、修订 0 次**，新窗口为 30 分钟。任何请求、协议或审核阻断均保全证据并停止。实际账单、具体模型快照和服务端留存无独立确认，金额没有可验证硬上限。尽力停止后仍可能迟发或计费，本机原件没有独立抗回滚保障。[准确请求](request.json) · [冻结清单](manifest.json) · [ADR0061](../../ADR/0061-fixed-queue-trial.md)

## 获准确授权后

1. 用 `PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile queue --prepare --start` 启动本机应用。应用入口为 `http://127.0.0.1:5214/`，API 8194。保留私有访客会话。使用 `/tmp/edumind-t121/env.json` 的本机开发配置，终端进程只保留必要运行变量和数据库设置。
2. 仓库根目录运行 `backend/.venv/bin/python -m scripts.course_trial inspect --topic queue` 核对冻结摘要。只有用户批准后才建立批准记录，字段为 `manifest_sha256`、`batch=queue-fifo-deepseek-r01`、`explicit_user_authorization=true`、`accept_T121_scope_and_batch_C2=true`、`max_http_requests=1`、`window_seconds=1800`。运行共用入口的 `prepare --topic queue --owner <访客 UUID> --approval <批准记录>`，登记北京时间起止。原件进入新的私有目录 `~/.local/share/edumind/queue-fifo-deepseek-r01`。
3. 同一入口运行 `send --topic queue` 一次。DeepSeek Key 仅在终端隐藏提示中输入。发送前须至少余 90 秒。响应先加密保全，再校验 HTTP、协议、用量和候选。失败用 `stop --topic queue` 取消应用操作，在途同时停止前台。已经出站的请求可能继续完成。
4. `replay --topic queue` 严格复核原件。独立审核绑定候选摘要，逐项核对主题审核规则。通过后按共用流程写入私有目录的 `review.json`，再在有效窗口内运行 `publish --topic queue`。审核阻断时记录问题并执行 `stop --topic queue`。
5. 在同一访客浏览器验收真实私有 v2 的完整阅读、五帧高亮、播放控制、四题正反反馈、答案隔离及刷新。交付记录包含候选、版本、回执、审核和失败证据。

当前执行范围为离线验证，Provider 0。旧 T118 和 T119 继续用共用 CLI 的 `replay --topic head` 与 `replay --topic stack`，按原冻结提交复核。
