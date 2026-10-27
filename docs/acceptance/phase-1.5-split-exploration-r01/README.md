# 无 token／金额上界前置的隔离课程开发诊断 r01

本轮用户直接指令：“不考虑上界与费用，先完成项目”。按 [ADR-0034](../../ADR/0034-user-directed-unbounded-exploration.md)建立新的实验入口，不修改旧冻结包或生产门禁，不声称用户逐哈希审阅了新包。没有另行请求批准；授权来源如实登记 user-direction.json。

生成 DeepSeek 官方 deepseek-flash，逐场景及原20探针审核 AIAPI gpt-6.1-sol；原34槽/原顺序/完整Prompt与Schema保持。最多250 HTTP（182生成+68审核）、48场景审核、3小时、逐槽真人复核，异常/自然严重错误停止，无自动回退或未知请求重发。token和金额无上限，不先确认费率，实际费用unknown；max_output_tokens≤8000仅为请求参数。具体配置及停止规则见 plan.json、ADR-0034。

独立 ExperimentalScheduler 明确保存未验证标志false，PG输入预约字段1只是已标记兼容占位值；用量来自真实响应/settlement，金额为null。旧生产 Scheduler 拒绝同一适配器的断言已通过，故本例外不能充当原生产预算契约验证。模型意见与人工真值分离，不自动签核课程或向前推进独立质量/性能任务。

离线10项及真实隔离PG/HTTPX Mock 1项通过、0skip，覆盖真实流水、仍为false的上界标志、报告用量超过占位/请求值的诚实保留、未知停止/防重发、协议/指令/模型/用量/密钥回显失败、来源和人工暂停。证据见 offline-validation.json。旧包检查另行保留。真实结果后续附 RESULTS.md / results.json，不反写本冻结README。

```sh
backend/.venv/bin/python scripts/run_p15_split_exploration.py --check
# Step requires exact isolated EDUMIND_TEST_DATABASE_URL; one slot at a time.
backend/.venv/bin/python scripts/run_p15_split_exploration.py --step
# Import a real human report only; never fabricates it or automatically advances.
backend/.venv/bin/python scripts/run_p15_split_exploration.py --review /absolute/path/human-review.json
```

新批次p15-split-experiment-r01；私有输出 /tmp/edumind-p15-split-exploration-r01；数据库 edumind_catalog_p15_t020_exploration_20261027，仅专用回环15437测试PG。--check无凭据/DNS/PG/HTTP，--step只执行下一个已获准槽；已有输出待人工时不读Key或发HTTP。人工报告仍须原输出SHA、完整事实/答案/需求/画像逐项核对，以及新增场景审核摘要。首次采用D01-known，之后不能用助手复核冒充真人继续。

新包SHA登记于 user-direction.json，代码/输入/契约SHA在 manifest.json。准确请求、状态、原始响应、持久attempt与私有PG原件保存在本地；Git不提交凭据或真实.env。未完成教学质量/人工核对时T038继续阻塞，未push/merge/部署/开放生产。
