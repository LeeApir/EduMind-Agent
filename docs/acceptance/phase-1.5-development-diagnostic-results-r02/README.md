# T038 r02：请求 Schema 被拒，批次已停止

T038 状态为 blocked，不能完成或准入 T039。准确包为 T037 完成提交 `7d3fef3` 的 r02，manifest SHA256 `4d987857ab227a366c8b506f4ed365c8360b778017aa9418425493a212527f44`，冻结原件保持原字节。

用户对准确问题明确回复“批准该准确包执行 T038”。登记见 [执行批准](../phase-1.5-development-diagnostic-r02/execution-approval.json)，只授权该单候选单批次，不是内容质量核定、生产开放或新批次批准。运行仍为 catalog_only；无 push/merge/部署，H01–H08 未访问。

实际执行：

```sh
backend/.venv/bin/python scripts/run_p15_development_diagnostic.py --start
backend/.venv/bin/python scripts/run_p15_development_diagnostic.py --advance
```

首次槽 D01-known 的 `/responses/input_tokens` 返回准确预计数 **635**。随后生成请求只返回 `error`：

```text
type: invalid_request_error
code: invalid_json_schema
param: text.format.schema
Invalid schema for response_format 'edumind_result': In context=(), 'allOf' is not permitted.
```

这是冻结规划 Schema 与实际 Responses 接口的兼容性失败。没有 model/usage 证明，不能据此认定模型生成成功或推断零收费。冻结适配器未保存 HTTP 状态码，本报告明确保持 null，不从错误 JSON 推测 HTTP 状态。实际 Schema 和错误响应 SHA 均保留。

批次账本终态为 `stopped / provider_contract_failure`。**已发送 2 次 HTTP：1 次计数、1 次生成**。计数请求已结算，模型尝试保持 unknown；保留完整 **32,000 输入/8,000 总输出**预约及 40,000 USD micros 保守参考单位。635 是请求前计数，不是实际执行/计费 usage；实际中转费用仍 unknown，不能把参考单位当发票。

固定分母保持 34 槽：12 支持域课程中完成0、失败未知1、未运行11；2负例均未运行；20审核探针均未运行。没有可学场景或教学正文，人工自然质量评测/审核观点评测都未开展；事实、答案、可学性、个性化、审核召回/精确率均未验证，不捏造百分比或人工 pass。不能用 T037 Mock 的50通过替代实际准入。

原始账本、PG 快照、请求/计数/错误响应/停止收据和第一个槽输出保留在受保护目录 `/tmp/edumind-p15-t038-r02`。本目录仅提交必要元数据与 SHA，不提交鉴权头、真实 `.env` 或私有原件。准确文件、全部槽状态及限制见 [results.json](results.json)。SQLite 使用已关闭批次的一致性 backup 快照供只读审计，不修改原始预约或收据。

```sh
python3 scripts/check_p15_development_diagnostic_results.py --check
```

该命令纯只读，无凭据、网络、Docker 或 PG 访问；**退出2表示证据完整且结果为 blocked**，不是验收通过。摘要丢失、假 pass、unknown 改成零用量、原件/授权/账本替换均拒绝。测试命令：`backend/.venv/bin/python -m pytest scripts/tests/test_p15_diagnostic_results.py -q`。

T037 历史准备 checker 明确要求“无执行批准”，因此获批后不再用其退出0当 T038结果；其源码保持冻结，由本任务新的只读 checker 核对准确包、批准和真实失败证据。

下一步需要用户决定是否准备仅修复严格 JSON Schema 兼容性的新包。原 batch 不重启、不补样本，不静默删除约束、切换协议或更换模型；若修复，先做离线等价/安全验证，再冻结新准确包并独立批准新预算和执行。此次调用不证明候选教学质量好坏。
