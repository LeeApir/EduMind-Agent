# 当前.env供应原故障复测 r01（准备完成后待准确批准）

用户选择当前.env新供应：“先尝试原来会报错的地方，如果还是报错不使用这个中转”；随后明确没有价格资料。本包没有真实请求或执行批准，旧官方批准不可套用。准确新边界见 [ADR-0031](../../ADR/0031-current-relay-original-fault-regression.md)。

| 冻结项 | 值 |
|---|---|
| env公开身份 | https://www.cbbb.fun / gpt-6-luna / responses_json_schema |
| 显式路径映射 | root → https://www.cbbb.fun/v1；不改.env、不探测其他路由 |
| 两个请求 | POST /v1/responses/input_tokens → POST /v1/responses，准确同体 |
| 请求体 | [request.json](request.json)，原p01/S1的549字节，完整Schema与固定OK不改 |
| 配置 | reasoning none、default、store/stream false、strict true、无工具 |
| 最大预算 | 2 HTTP / 1生成；生成输入本地4096、总输出请求16；90秒（DNS5/计数10/生成30；应用89秒） |
| 本地金额规划 | USD $0.01；单对最大规划占额$0.008208，**非发票保证** |
| 供应商报价 | 输入/输出/计数费率与币种均未知；无资料，不套官方价格 |
| 凭据 | 仅批准后提取项目.env的EDUMIND_PROVIDER_API_KEY；不继承shell旧变量、不向官方发送 |
| 输出/唯一性 | /tmp/edumind-p15-relay-regression-r01，独占创建，禁止重试/重启/补样本 |

原p01观察计数37而reported input4438、追加21336字符指令、请求输出16回显null；本次不预填新计数，也不把更换key当修复证据。按[OpenAI计数与输出契约](https://developers.openai.com/api/docs/guides/token-counting)作为对照，不声称供应商已实现。S1 instructions=null合法；非null须与请求system准确对应。max_output_tokens=null为证据未决而停；usage须与计数一致、总数正确、输出≤16、模型与Schema准确、固定OK完整本地校验通过。

**费用风险待此次明确批准**：用户无费率资料，实际币种/收费与上游输入/输出硬界未知，可能越过本地占额，也可能客户端取消后仍计费。$1/百万token及$0.004096计数额度只是规划假设，无法证明覆盖中转实际价格；不得以local_accounting或fee_units_are_conservative字段宣称实际费用已可信结算。assessment.json会明确标记未验证规划额、实际币种/价格/发票均null。不继承旧无限金额例外或官方r01风险批准。

一对失败即 `candidate_rejected_stop_using`，停止使用该供应，不继续调试或改教学Prompt。干净则仅 `original_fault_not_observed_one_case_only`，不是完整兼容通过，不解锁课程诊断；S2或课程均需另冻包批准。不存在本轮先过再自动追加。

## 零调用核验

```bash
backend/.venv/bin/python -m pytest scripts/tests/test_p15_relay_regression.py -q
backend/.venv/bin/python scripts/run_p15_relay_regression.py --check
```

--check只查冻结SHA与请求身份，不读.env、不DNS、不创建输出；执行入口在准确双批准之后才读取.env。模板不是批准。当前用户的方向指令没有被登记成对未知实际收费风险的接受。将来唯一执行命令是 `backend/.venv/bin/python scripts/run_p15_relay_regression.py --execute`，此轮不执行。

## 可直接批准的准确范围

“批准 ADR-0031 A—C 及本manifest SHA256的 p15-relay-regression-r01 单次执行：当前.env cbbb/gpt-6-luna，显式root到/v1，原S1同体计数+生成，最多2HTTP/1生成、4096输入本地占额/16请求总输出、90秒、本地USD0.01规划额。我接受实际币种/费率未知、账单不能保证封顶及上游参数限额未验的风险；失败即停止使用该供应，无重试/重启/追加，不授权课程诊断。”

准确manifest SHA由--check输出。只有此包的独立契约和执行批准登记通过才允许发送；不会因为旧官方批准或方向指令而自动发起。
