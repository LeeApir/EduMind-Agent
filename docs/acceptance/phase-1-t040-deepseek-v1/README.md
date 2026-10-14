# T040 DeepSeek 历史诊断准备

状态：已领取 T040，尚未发送真实请求。本文是具体预算提案，不是质量通过证据或执行授权。

沿用用户已选择并完成独立接入复验的 `deepseek-flash` / DeepSeek Responses 系统模型路径。
审核请求由当前生产 `ReviewAgent._review` 离线捕获，候选和上下文逐项匹配原历史 payload hash；
捕获用的合成 pass 仅用来取请求，不保留为模型观测、审核成绩或人工确认。
每个实际请求固定非思考、temperature=0、最多 4096 总输出 Token、60 秒、无重试/修正/回退。

| 独立诊断组（按顺序） | 请求上限 | 人民币费用上限 |
| --- | ---: | ---: |
| error_detection：已知缺陷检出 | 5 | 0.25 元 |
| classification：相同五例重新发送，独立分类观测 | 5 | 0.25 元 |
| correct_control：正确资源对照 | 1 | 0.05 元 |
| long_review：历史长审核 | 2 | 0.11 元 |
| 合计（不能在组间挪用） | 13 | 0.66 元 |

费用按峰值未命中输入 2 元/M、输出 8 元/M 计算，每组向上取整至分。
具体每个请求使用完整 UTF-8 body 字节数加 1024 模板 Token 作为输入上界，包含完整 schema；
13 次合计输入预留上界 109659、输出上界 53248 Token。这是保守预留，不是预计实际用量或账单。
原始价目和总输出参数语义来自独立接入阶段已查证的官方证据，见 proposal 的 pricing_evidence。

每组预算需要明确批准；可一次批准表中四组各自上限。后组只在前组全部通过并获得实际人工核对后启动，
任何能力、用量、schema、具体缺陷检出、分类或正确对照门禁失败立即停止并保留未运行槽。
人工核对记录必须绑定具体输入、请求和实际响应 hash、核对人、缺陷位置及分类；
脚本捕获或模型自身 verdict 不能替代人工事实核对。原始响应应脱敏后保存在 ignored 私有证据中供核对，
公开结果只存安全摘要和 hash。不得执行案例中的 C 代码。

[proposal.json](proposal.json) 是四组具体预算、请求上界和来源快照，
[requests.json](requests.json) 是全部 13 个实际请求正文。两份文件均不含密钥；
分类组的五次重复请求照常另计数、另计费。正式 50 个新审核例、100 个新生成槽和 9 个历史生成失败槽未发送，
未读取为调参输入。本提案不授权正式质量、DSL、T041 或动态开放。
原 A–D/标签批准继续有效，不重新征求相同设计批准。

离线准备与核对：

```sh
backend/.venv/bin/python scripts/prepare_t040_diagnostics.py --check-proposal
backend/.venv/bin/pytest -q backend/tests/test_t040_diagnostic_preparation.py backend/tests/test_phase1_dynamic_gate.py backend/tests/test_acceptance_budget.py
backend/.venv/bin/python scripts/verify_phase1_dynamic_freeze.py
```

`prepare_t040_diagnostics.py` 只提供离线准备和核对入口，没有网络执行开关。
实际发送器须在预算批准后与独立执行冻结/持久预算台账组合；不能将本预算提案伪装为已经运行或通过。
当前 `catalog_only` 保持。正式质量和 DSL 分别需要后续具体执行计划与预算，接入复验剩余额度不转入。

本次还修复两个历史校验入口：批准时的运行源码在批准提交核对，当前冻结样本仍逐字核对；
ADR 当前文本只允许等于已授权四厂商延期提交的准确版本，原批准正文仍须完整保留。
不改动旧 manifest、标签、归档任务或失败记录。
