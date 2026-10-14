# T040 新审核指令诊断 r02

当前状态：修复候选及离线回归完成，真实调用 0，独立预算待批准。
原 `phase-1-t040-deepseek-v1` 中 r01 首例漏检及停止台账不修改，不将其成绩或剩余额度转入本轮。

修复：生产 `resource-review-instructions-v3` 检查失败返回值、调用者赋值、已有状态与内存所有权、
后续清理及注释真实性；同时保留正确处理路径，避免见到 NULL 或分配失败就拒绝。
指令适用于代码及讲解/练习中的嵌入代码，不按案例 ID 或标准答案返回 verdict。
输出 schema、模型、采样/非思考参数和最大 4096 总输出 Token 不变。
旧首例候选及上下文逐字不变，仅系统审核指令变化；旧实际失败保留。
历史诊断例允许用于本次调优，正式 50 个新例和 100 生成槽未用于调优。

| 按顺序的独立组 | 请求上限 | 费用上限 |
| --- | ---: | ---: |
| error_detection | 5 | CNY 0.26 |
| classification | 5 | CNY 0.26 |
| correct_control | 1 | CNY 0.05 |
| long_review | 2 | CNY 0.12 |
| 合计（不能跨组挪用） | 13 | CNY 0.69 |

这是修改后配置的新轮次预算申请，不是原 0.66 元预算的继续消费。
费用仍按峰值未命中输入 2 元/M、输出 8 元/M，以完整请求字节数加 1024 模板 Token 保守预留，
每组上取整至分；账单未知。单次 60 秒、串行、无重试/修正/回退；任何质量、协议、用量失败即停。
前组全部通过且经实际人工核对后才能进入后组，不将 assistant 判断冒充人工签核。
本轮不授权正式质量、DSL、T041 或动态开放。

[proposal.json](proposal.json) 包含具体预算、旧失败引用和当前执行源码/锁文件 SHA，
[requests.json](requests.json) 包含 13 个实际审核请求。独立目录、审批、r02 执行清单和私有持久台账
由 `scripts/t040_diagnostics_v2.py` 组合；运行前仍须核验确切审批记录。
准备工具和执行器均已纳入提案来源哈希，无预算批准不能发出请求。

离线验证：

```sh
backend/.venv/bin/python scripts/t040_diagnostics_v2.py --check-proposal
backend/.venv/bin/pytest -q backend/tests/test_review_failure_paths.py backend/tests/test_review_agent.py backend/tests/test_review_context.py backend/tests/test_objective_exercises.py backend/tests/test_t040_diagnostic_runner.py backend/tests/test_t040_diagnostic_preparation.py backend/tests/test_phase1_dynamic_gate.py backend/tests/test_acceptance_budget.py
```

本次 94 项离线测试通过，Ruff 和 166 个源文件的严格类型检查通过；历史批准、冻结样本及活动任务检查通过。
这些结果证明指令组装、候选不变、输出契约和流程边界，不证明真实模型语义审核已经修复。
