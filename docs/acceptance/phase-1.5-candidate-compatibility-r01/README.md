# 官方候选最小兼容验证 r01（仅准备，待批准）

用户已确认 OpenAI 官方 `https://api.openai.com/v1` + `gpt-6-luna`。本包没有真实调用或有效执行批准，未验证账号访问/凭据，未完成 T038，不启动课程诊断。新契约见 [ADR-0030](../../ADR/0030-official-candidate-minimal-compatibility.md)。

| 项目 | 冻结值 |
|---|---|
| 批次 | p15-candidate-compat-r01 |
| 接口 | POST /v1/responses/input_tokens → POST /v1/responses |
| 模型/推理/档位 | gpt-6-luna / none / default（Standard） |
| 其他 | store=false、stream=false、无工具/回退/重试/重定向 |
| 凭据 | 仅 EDUMIND_COMPAT_API_KEY；不读取 .env 或中转变量 |
| S1 | [准确请求](probes/S1.json)：两个 system，固定 `{"result":"OK"}`；输入占额4096/输出16 |
| S2 | [准确请求](probes/S2.json)：顶层 instructions，固定 probe/ok/echo，含中文、换行、引号；输入占额4096/输出128 |
| 次序 | S1计数→S1生成→完整验证成功→S2计数→S2生成 |
| 请求/token | 最多4 HTTP、2生成；生成输入8192、总输出144；计数输入另有相同8192的收费留额 |
| 期限 | 预约起90秒，含独立子进程DNS最多5秒；应用89秒；单计数10秒/生成30秒；每响应≤2 MiB |
| 货币 | USD本地总预算$0.02；两对最大占额$0.016528；不是发票硬限 |
| 输出 | /tmp/edumind-p15-candidate-compat-r01；独占目录，禁止重启/恢复 |

S1/S2 请求、全量 Schema、固定预期对象与 SHA 全在 manifest。响应 model 只接受准确别名 gpt-6-luna，日期快照未获证实；不猜测映射。两接口请求字节相同。所有回显、usage/计数与总数、完整本地 Schema 与固定对象必须通过。输出按类型聚合，不能假定 output[0] 是正文。S1 instructions=null 可接受；S2 顶层指令回显必须准确；max_output_tokens=null 则证据未决，停止。详细停止规则见 ADR A—C。

## 当前费率与金额

2026-10-24只读查阅 [官方模型页](https://developers.openai.com/api/docs/models/gpt-6-luna) 与 [官方定价表](https://developers.openai.com/api/docs/pricing)。Standard短上下文 USD/百万token：输入0.10、缓存读0.01、30m写0.125、12h写0.25、输出0.50。无工具费、区域加价、Fast、Flex或Batch配置。准确查阅时间及24小时有效期见 [pricing.json](pricing.json)；执行起点必须距有效期终点至少90秒；过期必须更新包、重新批准，不能用旧价继续。

生成按当前最贵缓存输入0.25计价，上限 $0.002120；普通未缓存输入则 $0.0008912。这些仅为生成估算，不是含计数的确定账单。计数独立收费没有公开明示，不写0：每对保留$0.004096计数额度，加上输入/输出按$1/百万token保守包络；S1 $0.008208、S2 $0.008320，合计$0.016528≤$0.02。计数占额附在生成ticket，计数ticket记0只为不双计，绝非断言免费。计数成功后仍保留留额；异常整对保留unknown，发票actual_invoice_usd保持null。summary 的 local_accounting.requests 是预约数，实际dispatch marker另列；marker也不是服务商收到请求的证明。

有限本地预算无法强制服务商账单硬上限；准确批准必须接受计数收费及客户端超时后计费的残余不确定性。此次不沿用旧无限金额例外。若要求账单绝不超过两美分，需要先取得服务商硬限证据，本包不作该保证。

## 离线检查与执行门禁

```bash
backend/.venv/bin/python -m pytest scripts/tests/test_p15_candidate_compatibility.py -q
backend/.venv/bin/python scripts/run_p15_candidate_compatibility.py --check
```

`--check` 仅校验材料/配置/全部历史SHA，不读凭据、不DNS、不生成输出。测试禁止真实socket和.env读取，全部注入 MockTransport。正式 `--execute` 与测试相分离：必须登记 contract-approval.json、execution-approval.json 两份人工批准；模板 [approval-template.json](approval-template.json) 不是批准，不能直接复制当作授权。两份登记须绑定同一当前manifest SHA、批次、purpose、limits及真实用户消息来源。缺失/错配/过期时在读取凭据、DNS和输出目录之前拒绝。独立凭据需由用户在进程环境安全配置，不要发到聊天或写入仓库。

完成准确批准登记且凭据配置后，唯一执行命令为 `backend/.venv/bin/python scripts/run_p15_candidate_compatibility.py --execute`，本轮禁止执行。退出0且summary为minimal_compatibility_observed_pass才表示两例观察通过；异常退出2/拒绝也必须保留目录及账本。返回pass不授权课程生成。异常、安全问题、未知、证据缺失、时钟/预算问题即停；不自动重试、不改请求追通过、不恢复旧批次。

## 供后续直接批准的表述

“批准 ADR-0030 A—C 及当前 manifest SHA256 对应的 p15-candidate-compat-r01 准确单次执行包：官方端点/gpt-6-luna/Responses/none/default；S1与S2、最多4HTTP/2生成、8192生成输入/144总输出、90秒、本地USD $0.02；接受计数留额及账单不确定性、别名准确匹配与一次性不重启约束。该批准不覆盖任何课程诊断。”

manifest SHA 由 `--check` 输出，批准必须明确该准确值。用户本轮只授权准备，以上文本尚未批准；不得预填人工身份或把选型确认登记为执行批准。
