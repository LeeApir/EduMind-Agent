# T040 逐条审核零调用原型

用户在 ADR-0013 设计稿（681dca1）后回复“继续”，授权先实现零调用原型。
本目录不授予真实 Provider、动态子请求派生、正式质量或生产开放权限；T040 仍 blocked。

## 已实现的实验范围

代码位于 `scripts/acceptance_support/claim_review_prototype.py`，没有生产路由注册或 Provider 依赖。
Replay 只接受预制的合成 JSON tape；没有 URL、Key、transport 或模型回调参数，也不读 `.env`。
每条响应必须显式 `synthetic_only=true`；该标记是实验输入约束，不是身份签名或真实调用授权。
没有任何把结果发布为正式资源的方法，`Result.approved` 仅为合成回放的内部状态。

- 按 content 叶子字段编号，保留中文、CRLF、JSON Pointer、数组顺序和完整代码/题目字段。
- 原文锚点严格校验区间与 exact quote；稳定服务端 claim_id，候选、上下文、配置与最终清单摘要分别绑定。
- 提取清单先通过结构/映射校验，才进入覆盖检查；补出声明计入同一16条上限，未知/不确定排除阻止通过。
- 每条审核始终带完整候选与参考上下文；焦点 findings 和 incidental_findings 分开处理。
- 聚合保留全部不同定位的问题及来源；完全相同定位/内容才去重。焦点 pass 不抵消其他有效问题，冲突/清单外发现阻止通过。
- 缺失/截断/未知用量/超模拟上限/错误绑定/额外字段/无效 verdict 组合都变为 unavailable，不能触发修正。
- 整体检查保留跨声明问题；覆盖未完成时保留已知问题并阻止通过，不自发追加声明审核。
- 最多两次合成修正；每次完整重建清单和审核，旧候选 pass 不可用于新候选。
- SQLite 在读取合成响应前记录模拟步骤与请求hash/父响应hash；重启不能开启同一ledger的第二次回放。
  次数来自数据库，清空内存调试记录不能扩额。最终回应以摘要链绑定，无真实 wire 或实际Token消耗。

## 可执行内部协议（不是已批准的模型协议）

`tape` 是 slot→envelope 字典，slot 如 `0.inventory`、`0.coverage`、`0.claim.<id>`、`0.overall`、`0.correction`。
Envelope 精确包含 synthetic_only/status/input_tokens/output_tokens/value；用量是合成测试数据。
内部 inventory 使用 claims 和 exclusions，并在本地从锚点推导块映射，代替设计稿概念中的显式 block_dispositions。
覆盖结果精确包含 version/missing_claims/uncertainties/invalid_exclusions。具体实例可读测试中的 round_tape。

持久记录只是 **offline** 步骤账本，不是 ADR-0011 真实预算计数器：没有币种/金额、权限批准或 DNS/出站逻辑。
59步是16条声明、三轮审核及两次修正的理论上限；模拟默认输入65536/输出8192 Token界、30秒整体期限
只是合成数据约束，不批准任何真实参数。未实现真实预算、动态 wire 派生冻结或生产 ReviewOutcome 适配。

## 明确限制

锚点来自原文不代表声明描述语义正确；所有字段有映射也不代表所有事实已提取。
覆盖/审核 verdict 在测试中事先提供，代码不能凭空发现未给出的缺陷或证明事实反例成立。
原型只做 JSON 结构与引用验证，不能替代正式 learning-resource schema、AST、安全门禁或发布事务；
测试中 code/exercise 的字段是合成结构，不冒充已通过正式资源 schema。
不会执行候选代码。原型从未接入 ReviewAgent，也不把声明数作为资源级验收分母。
旧 r07/r08、Prompt v6、生产 none/catalog_only 与正式标签保持。

## 实际验证

```sh
backend/.venv/bin/pytest -q backend/tests/test_claim_review_prototype.py
backend/.venv/bin/ruff check scripts/acceptance_support/claim_review_prototype.py scripts/measure_t040_claim_inputs.py backend/tests/test_claim_review_prototype.py
backend/.venv/bin/python scripts/measure_t040_claim_inputs.py
backend/.venv/bin/python scripts/check_catalog_workflow.py
backend/.venv/bin/python scripts/verify_phase1_dynamic_approval.py
backend/.venv/bin/python scripts/verify_phase1_dynamic_freeze.py
# 从backend目录执行，验证原生产模块保持通过：
.venv/bin/mypy app
```

最终原型测试61通过；本轮另有原148项相关回归通过，生产mypy166源文件通过，Ruff通过。
初次 Ruff 发现测试中未使用 json import，已删除并复查；没有删弱失败断言。
尺寸报告 [input-size-screen.json](input-size-screen.json) 只读取原8个历史payload，未读取正式新例。
8个输入均在48KiB/48叶字段内（最大5871字节，每例1字段）；声明数量仍 NOT_MEASURED，
无法据此断言16条声明上限合理或模型质量改善。[validation.json](validation.json) 记录来源与验证边界。
测试产生的 SQLite 仅在 pytest 临时目录，不提交运行账本或私有内容。

下一步须先决定 ADR-0011 的动态派生冻结补充；真实适配器/预算与完整诊断仍需可执行方案和确切批准。
不能直接用这个合成回放器发送模型请求，不能把测试中双问题都存在于输入当成模型检出改善证据。
