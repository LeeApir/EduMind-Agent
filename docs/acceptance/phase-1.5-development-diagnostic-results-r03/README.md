# T038 r03：输入计数与生成回执不一致，批次已停止

T038 仍为 blocked，不能进入 T039。用户已明确批准 bd477dd 的准确 r03 包：manifest SHA256 `a734e125e8ea1d6aef8eb8223fbc773b55fdf495f6e5098dddd8b921e38ae857`；[本批次批准](../phase-1.5-development-diagnostic-r03/execution-approval.json)独立登记，r02 没有被重启或修改。生产继续 catalog_only，无 push/merge/部署，H01–H08未访问。

实际执行：

```sh
backend/.venv/bin/python scripts/run_p15_strict_diagnostic.py --start
backend/.venv/bin/python scripts/run_p15_strict_diagnostic.py --advance
```

首槽 D01-known 共发出 **2次HTTP：1次输入计数、1次模型生成**。新 wire Schema/strict/guidance 的准确字节已保留；本次服务返回 `model:gpt-6-luna / status:completed / error:null` 及一份规划候选，没有再次返回 `invalid_json_schema`。这不证明中转逐条执行了全部 strict 约束，也不证明教学质量。

| 证据 | 输入token | 输出token |
|---|---:|---:|
| `/responses/input_tokens` 回执 | 1,677 | 不适用 |
| `/responses` 服务报告 usage | 6,507 | 480 |

输入相差 **4,830**。两次使用相同 body 的计数/生成路径由冻结代码及既有 wire 测试约束；本次不通过补发请求探测差异。服务报告 usage 落在32k/8k预约范围内，但没有满足准确包中“输入计数必须与回执一致”的门禁。不能把问题猜成具体服务端实现缺陷、精确计费差额或已修复问题。

独立账本已 `stopped / provider_contract_failure`，模型尝试仍为 unknown，保留全部 **32,000输入/8,000总输出**预约。服务报告值在 `provider_reported_usage` 中原样记录，`model_usage_actual` 与实际中转费用保持 null：有报告值不等于按本包规则完成可信结算，也不假装本次没有返回usage。原传输没有保存 HTTP状态码，仍为null，不从 completed JSON 推测状态。

规划候选没有被应用或发布，PG 无正式规划/场景生成记录，未请求场景正文。固定34槽中首槽失败未知、其余33未运行：12支持课程完成0/失败未知1/未运行11，2负例和20审核probe全部未运行。没有人工自然质量核对、审核召回/精确率或独立验收结论；不把没有评测写成零分或pass。

**包含r02后，累计4次HTTP/2次生成请求。** r02的unknown预约和失败保留，两批合计仍保留64k输入/16k输出unknown占额，不能转为新预算或退款。各批次原件分别留在 `/tmp/edumind-p15-t038-r02` 与 `/tmp/edumind-p15-t038-r03`；本目录仅提交元数据与SHA，不提交真实.env、鉴权头或私有原件。

[results.json](results.json)绑定准确批准、363份冻结源文件、实际request/count/response/projection、终止槽和一致性SQLite快照。新只读校验器不读凭据、不启动Docker/PG或网络：

```sh
python3 scripts/check_p15_r03_diagnostic_results.py --check
```

预期退出2，含义为“失败证据完整且结果blocked”，不是验收通过。14项独立测试覆盖原件/批准/账本/WAL篡改、漏槽、伪造pass、将unknown写成零用量、伪称计数相等、退款或隐藏旧失败；准确XML与源码SHA见 validation.json。旧r02的结果checker继续独立核对，预期同样退出2。r03准备checker曾要求“没有批准/运行目录”，获批后不再用它的退出0冒充真实验收；冻结源码不改。

下一步需要决定如何确认输入计数口径：先核对中转计数接口与生成回执的差异；若考虑独立可证明的输入上界或调整一致性契约，必须先提出准确边界、离线验证及必要ADR，再冻结新包独立批准。不得静默忽略差异、改成看到usage就通过、重启r03、换模型或自动试下一批。
