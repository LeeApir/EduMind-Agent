# T040 high 完整历史诊断 r04 提案

当前状态：用户确认两例策略结果并批准四组预算，按 `31ed911` 冻结执行。
第一组前两例具体检出正确，第三例漏检索引约定/步数问题而停止；实际 3 次、20492 Token，余 10 槽未发。
T040 仍为 blocked，未进入下一组。见 [实际结果](results/error-detection-r04.json) 与
[核对说明](results/error-detection-r04.md)。以下保留提案时范围与预算。前置参考是
[high 两例结果](../phase-1-t040-reasoning-check/results/strategy-r03.md)，
不能以其代替本轮四组或最终质量分数；用户人工确认未推定。

实际审核配置与两例检查相同：`deepseek-flash` / Responses / Prompt v3 / reasoning=high，
最大总输出 8192 Token、串行、单次总期限 120 秒（底层 HTTP read 60 秒）、无重试/修正/回退。
temperature=0 仍发送，但提供方思考模式不使用该参数，不宣称输出确定性。

| 独立组及顺序 | 请求上限 | 费用上限 |
| --- | ---: | ---: |
| error_detection | 5 | CNY 0.43 |
| classification，同五例重新发送并单独计费 | 5 | CNY 0.43 |
| correct_control | 1 | CNY 0.08 |
| long_review | 2 | CNY 0.18 |
| 合计，不跨组挪用 | 13 | CNY 1.12 |

使用原已批准 5/5/1/2 历史案例及顺序，payload/参考上下文/系统 Prompt/schema 均不改写。
全部 13 槽重新执行、独立计数，不将两例成绩填入本轮，也不复用旧 Prompt/预算或抹去失败。
按完整 wire UTF-8 字节加 1024 模板 Token、峰值未命中输入 2 元/M、输出 8 元/M 保守预留；
总输出包括推理，不依赖缓存或折扣，实际账单未知。

任何具体漏检、分类错误、误拒、长审核不完整及协议/身份/schema/用量/预算异常立即停止。
每次只发送一条，具体检出须核对实际回答；前一组完整且经实际人工确认才可进入后一组。
机器结果或 assistant 判断不冒充人工签核。通过本轮也不自动授权正式质量、DSL、T041 或动态开放。
生产 `.env` 和 none/catalog_only 默认不切换。

[proposal.json](proposal.json) 绑定源码、锁文件、原失败及两例策略证据的 SHA，
[requests.json](requests.json) 是 13 个确切正文。执行组合为 `scripts/t040_high_diagnostics.py`，
独立目录、r04 审批与持久台账；无具体审批不能发送。

```sh
backend/.venv/bin/python scripts/t040_high_diagnostics.py --check-proposal
backend/.venv/bin/pytest -q backend/tests/test_t040_high_plan.py
```

新增计划回归 1 项通过、Ruff 和提案来源哈希核对通过；生产适配器此前 128 离线检查保持有效。
