# 独立 R0 单次包 r01（T089 准备，T090 待执行）

用户要求“发送R0，查看结果”。本包只发送同一份R0，作为**新的独立观察**；不恢复已停止T088，不消耗旧未用1，不改原七槽顺序或结果。T089完成适配/离线验证后提交。新准确包的窗口及本批未核实费用风险例外待明确确认；当前真实0、grant pending、窗口null。

## 准确范围

- 仅 `https://api.deepseek.com/responses` / `deepseek-flash` / reasoning none，temperature0.2，stream/store false。
- [R0.json](R0.json)逐字节复用原[R0](../phase-1.5-separated-validation-r01/R0.json)：11034字节，SHA256 `2eb90f9ee23738f3311eb14ae44231be5d1d102b3122d1b7e90676dc0b00c29d`。目标、合成完整旧候选、私有参考答案、动作与准确措辞意见均不改；不发送独立真值/真实学生/H。
- 仅输入普通minor/difficulty意见，允许改`/paragraphs/0/text`。原B完整Schema/strict/wire/local规则、原候选与意见绑定全部沿用冻结的T087 observer；没有简化Schema、修JSON、自动填答案或参考改写回显。
- 机械通过终态仍是`network_complete_pending_semantic_review`，`repair_success=false`、`diagnostic_success=false`，CLI exit3待独立语义复核。不会自动判讲解正确；R0的手写旧候选不能证明基线首次生成能力或B/C公平比较。

## 新预算与停止

[policy.json](policy.json)冻结最多**1 HTTP、新登记起120秒**，单HTTP60秒、DNS9秒；输入占额8192，总输出请求上限4096；请求/响应65536/262144字节。只发R0，没有计数、models、P/W、sol或课程调用；任何异常即终止，无重试、重定向、回退、补样或旧批重启。无论R0通过或失败都结束网络阶段。

独立[控制器](../../../scripts/isolated_diagnostics/p15_r0_once.py)不修改/monkeypatch旧全局ORDER、预算或grant；独立新scope PHASE-1.5-T090/新目录`/private/tmp/edumind-p15-r0-once-r01`。公网DNS/固定IP/TLS SNI/禁环境代理、0700/0600原件、时钟与只读重算、不重启门禁沿原实现保持。只在准确批准/费用/新窗口/无已有结果目录核对后读取专用DeepSeek Key，无其他Key/Provider回退。

[pricing.json](pricing.json)引用本日14:26核对并冻结的[官方公开标价](https://api-docs.deepseek.com/quick_start/pricing/)快照：按缓存未命中峰时输入$0.30/百万、输出$1.20/百万及全部占额，参考**$0.0073728**。这是公开参考，实际账户费率/币种、账单及上游硬限未核实，不是可验证账单硬上限。

本新批费用边界为：**实际金额不设可验证硬上限，服务可能忽略请求token限制或取消后继续计费，必须另获本包明确风险例外。** 旧T088接受的费用例外明确只属旧批，不能沿用。当前未登记已接受，不读Key、不发HTTP或启动新窗口；若不接受该边界，则不发送。

## 冻结与离线验证

manifest.json冻结原175来源、原T088全量结果清单/批准与新入口/请求/配置。原T085/T088源码、失败、原件、冻结包和预算不动。实现仅隔离适配单槽序列、120秒新窗和1次占额；复用原R0语义机械规则，不变更教学验收标准、生产API或动态门禁。

[实际控制器测试](../../../scripts/tests/test_p15_r0_once.py)用MockTransport验证两种不同合格措辞及故意错误讲解都只pending；未改/越界、非法JSON/返回Schema/额外重复字段、超限、来源/phase、HTTP/超时/重定向/秘密回显均停止；旧scope/旧费用/窗口、迟到、第二次发送/重启、结果晋升和pending读Key拒绝。旧observer/旧回归继续有效。实际结果见verification.txt；离线证据不能算新真实兼容或教学通过。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_r0_once.py --check
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_r0_once.py -q --tb=short
# 仅列接口；当前pending必须拒绝，待本包新准确批准/风险例外/窗口登记后才执行：
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_r0_once.py --run
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_r0_once.py --check-results
```

确认后仅一次R0，保留完整原响应/请求/事件/摘要与实际用量，停止或完成后交回全部证据。机械合格也只交独立评估助手复核，不能自动算修复成功、整套角色准入或启动课程。T038 blocked/catalog_only/H封存保持。
