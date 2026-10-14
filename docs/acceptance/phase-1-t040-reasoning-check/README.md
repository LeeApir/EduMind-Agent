# T040 同模型推理策略小检查

当前状态：预算已获用户批准，按 `575402d` 冻结完成两次真实检查，均符合预期。
错误例具体检出丢链/泄漏并归 code_safety，正确对照 pass；共 5658 Token，其中推理 1329。
这不是完整诊断或 T040 完成，实际人工确认未推定。见 [结果](results/strategy-r03.json) 和
[核对说明](results/strategy-r03.md)。r01/r02 的漏检、输入标签和停止台账保留；下文保留准备时范围。

已核验发送器校验了实际 wire 与冻结正文，未观察到本地漏传审核系统指令。
当前生产适配器原先固定发送 `reasoning.effort=none`，两份保留响应的 `reasoning_tokens` 均为 0。
这不是模型漏检的唯一已证实根因，仅提供需要单独检验的策略假设。

本次在相同 `deepseek-flash` / Responses 上显式使用 `high`，总输出上限 8192（包括推理），
单次总期限 120 秒；底层 HTTP read 期限仍为 60 秒。temperature=0 保留在 wire，
但官方说明思考模式中该参数不生效，不能宣称确定性输出。
与 r02 相比同时改变推理档位、总输出上限和总期限，因此结果不能解释为严格单变量因果实验。

仅发送两条原已批准的历史输入，顺序如下：

1. `linked-list-concept:explanation:1`：必须具体检出分配失败覆盖非空 head 导致丢链/泄漏，分类 code_safety。
2. `correct-list-concept`：必须 pass，防止通过一律拒绝伪造检出能力。

两条的用户 payload、参考上下文、系统 Prompt v3 和 schema 均与 r02 对应项完全一致。
不重新发送非思考基线，不添加错误答案到 Prompt，不读取正式新例进行调优，不执行样本代码。
每次只发送一条，由执行者核对实际回答后再决定能否发送下一条；明确漏检、错误分类、误拒、
schema/完成/身份/用量/预算异常立即停止。模型 reject 不自动计为具体检出或人工确认。
实际推理 Token 数只记提供方的有效数值；0 或缺失不能被解释为已证实使用了推理策略。

预算：**2 次，CNY 0.17 上限**，无重试/修正/回退，串行。每次均先写入独立 SQLite 预留，
首条保守预留 CNY 0.089728，第二条 CNY 0.079984，共 CNY 0.169712，向上取整至分。
按峰值未命中输入 2 元/M、输出 8 元/M，完整 wire UTF-8 字节数加 1024 模板 Token 保守预留；
不依赖缓存/时段折扣，不进行美元与人民币换算，真实账单未知。

官方依据（2026-10-14 核对）：[Responses 参数](https://api-docs.deepseek.com/api/create-response/)、
[Responses 兼容说明](https://api-docs.deepseek.com/guides/responses_api/)、
[人民币定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。中文页面直读超时后以同一官方域搜索缓存核对价目，
英文页面使用美元，不将其价格换算成本次人民币预算。

[proposal.json](proposal.json) 绑定完整请求、当前生产适配器/组合层/发送器/测试/锁文件及旧失败证据 hash；
[requests.json](requests.json) 保存确切请求正文。`scripts/t040_reasoning_check.py` 使用独立目录、
r03 审批与持久台账，不能恢复旧停止账本或转用旧余额。

本检查通过也不替代原四组 5/5/1/2 诊断，不授权正式质量、DSL、T041 或动态开放。
生产默认和本机 `.env` 均不切换。后续正式策略仍需经完整同配置验收及明确采纳。

本次离线 128 项测试通过，Ruff 和 166 源文件严格类型检查通过；
历史批准/冻结样本、活动任务依赖和新提案来源哈希核对通过。尚不能声称真实审核可靠性已改善。

```sh
backend/.venv/bin/python scripts/t040_reasoning_check.py --check-proposal
```
