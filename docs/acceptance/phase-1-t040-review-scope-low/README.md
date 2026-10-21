# T040 low 推理审核职责小检查 r07

状态：用户已批准 2 次 / CNY 0.18；首条只检出原两项缺陷中的计数错误，已停止，第二条未发。
结果见 [review-scope-r07.json](results/review-scope-r07.json)，执行源码 `3c5936c`。

r06 首条 HTTP 200、模型匹配，但未完成且没有可解析审核；8192 总输出全部计为推理。
现有证据符合输出预算耗尽，未保存供应商具体未完成原因，不能唯一确定内部原因。
原结果、标签与 INVALID_OUTPUT 停止台账保留，不重放、不移动剩余额度。

本轮仅将 `reasoning.effort` 从 high 改为 low：模型 deepseek-flash、Responses 路径、
审核 Prompt v5、历史候选、参考上下文、schema、8192 总输出及 120 秒总期限均保持。
HTTP read 仍为 60 秒。low 仍是思考模式，不能保证推理少于某个固定数量，也不保证完成/检出。
不修改生产默认 none 或 catalog_only；不更换厂商、不读取正式新样本调参。

逐条执行：

1. 原 queue:explanation:1：具体检出回绕计数与空满条件矛盾，fact 分类。
2. 原 correct-list-concept：pass 且 issues=[]。

与 r06 一样分别记录检出、分类、审核职责/回答事实、schema/完成/模型/用量。
审核仅给定位、条件、真实反例/后果，不给通用替换公式、代码或补丁步骤。
任何维度失败即停；无重试、回退或修正。修正质量 NOT_RUN。
两个样本通过也不代替完整四组诊断、人工事实签核、正式 T040 或 T041。

另外只增加本地诊断观察：从响应提取白名单 status、incomplete_details.reason
（仅 max_output_tokens / content_filter），以及 message/reasoning/function_call 数量。
未知值记 null/忽略，不存任意供应商错误正文、部分回答或推理正文；不放宽完成解析/失败门禁。
旧 r06 没有保存的字段不回填推断值。

申请预算：2 次，CNY 0.18 上限。保守预留第一条 CNY 0.090640、第二条 CNY 0.083530，
合计 CNY 0.174170，向上取整到分；完整 wire UTF-8 字节加 1024 Token 输入上界，
输出包含推理，按峰值输入 2 元/M、输出 8 元/M，不依赖缓存/时段折扣，实际账单未知。

[proposal.json](proposal.json) 固定全部维度、请求哈希、配置及来源；
[requests.json](requests.json) 保存确切两条正文。批准后再冻结独立执行清单与台账。

```sh
backend/.venv/bin/python scripts/t040_reasoning_check.py --round r07 --check-proposal
# 仅在该提案获得确切预算批准并保存批准记录后：
backend/.venv/bin/python scripts/t040_reasoning_check.py --round r07 --freeze
backend/.venv/bin/python scripts/t040_reasoning_check.py --round r07 --run-one
```

验证：146 项离线测试、Ruff、mypy 166 源文件通过；新增 low/high 在实际适配器中的
严格 JSON/文本 wire 覆盖及总输出计费口径测试，未完成原因白名单/畸形值不泄露测试，
r07 与 r06 请求除 effort 外完全一致及评分维度一致检查。
Mock 只证明工程流程，不证明模型质量。r06 的 186 个冻结来源按 93ac1f0 归档核验，
只读 SQLite 仍 1 条且 INVALID_OUTPUT；当前源码变化不会使旧轮次重新生效。

官方依据（2026-10-14 核对）：

- [Responses 参数](https://api-docs.deepseek.com/api/create-response/)：支持 low/high，输出上限含推理，未完成原因枚举。
- [人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：峰值输入未命中 2 元/M、输出 8 元/M。
- [ADR-0011 D](../../ADR/0011-independent-dynamic-acceptance.md)：配置变化须形成新轮次独立批准。

实际首条 HTTP 200/completed、schema/模型/用量有效，28.677132 秒；输入 2784、
总输出 5036（推理 4862 包含其中），合计 7820 Token。
原计数错误具体检出，fact 分类正确，所给反例有效且未夹带修复方案；
但没有指出 front==rear 也可能是满队列，未达到事前固定的“两项均检出”条件。
独立语义评估将台账停止为 CONCRETE_DEFECT_MISSED，原自动行 quality_failure=null 不修改。
不能把已检出的计数问题改记漏检，也不能以 revise 代替两项检出。
保守预留 CNY 0.090640，峰值标价参考 CNY 0.045856，真实账单未知。
正确对照/修正均未运行，不代表完整诊断或正式验收通过，也不由单样本断言 low 的因果效果。
