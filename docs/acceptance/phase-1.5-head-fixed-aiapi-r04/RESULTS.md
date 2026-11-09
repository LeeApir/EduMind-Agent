# T111 · AIAPI 复测结果

2026-11-09 在 AIAPI 请求 `gpt-6.1-sol`。前台记录两次出站尝试、一次完整 HTTP 200、一次结果未知。北京时间 14:00:38 写入 [STOP](STOP)。

| 样本 | 原 DeepSeek 结果 | AIAPI 复测 |
| --- | --- | --- |
| 规划 | HTTP 200，本地及独立语义通过。审核完成时应用操作已超时 | HTTP 200，12,070 字节，本地及独立语义通过 |
| 正文第一次 | HTTP 200，虚构事实 ID，`HEAD_FACT_REFERENCE` | 13:59:08 出站，等待响应头 90 秒后 `ReadTimeout`。无 HTTP 状态或可评估正文，服务端结果未知 |
| 正文第二次 | HTTP 200，结构及事实引用通过，教学评估因 F01/Q01 停止 | 随批停止，未发送 |

规划保留原目标和自述先备。独立评估核对了 `head-new-C`、作用域、判空、接收后 `[9,-2,5]` 和忽略后 `[5]`，以及忽略时两个新节点不可达。[规划输出](plan.result.json) · [独立审核](ASSESSMENT.md)

规划响应报告 `gpt-6.1-sol`。请求为 `reasoning.effort=none`、`temperature=0.2` 和 `max_output_tokens=8000`，响应分别回显 `low`、`1.0` 和 `null`，还在教学指令回显尾部增加了 `You are a helpful coding assistant.`。用量回报输入 2,975、输出 565、推理 0。参数和指令回显差异限制了控制变量比较，实际执行参数及两次请求的扣费未知。

[准确请求和授权](README.md) · [规划收据](plan.body.json) · [正文尝试](draft1.attempt.json) · [超时记录](failure.json) · [本机原件索引](originals-manifest.json)

回读规划加密原件后校验响应摘要和完整字节，重放本地映射与独立审核绑定。正文尝试及 STOP 收据一致，保留 `ACTIVE` 标识未能确认服务端终态。Ruff、工作流检查、diff 检查及原冻结源重放均通过。原 r01/r02/r03 记录独立保留。本次产出一份通过审核的规划，课程交付 0，T111 状态为 blocked。
