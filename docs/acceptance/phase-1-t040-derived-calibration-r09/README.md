# T040 r09：两历史例有界校准，等待准确运行批准

用户“开始”后完成6b8ba27剩余准备；没有将此前零调用授权解释为真实费用授权。本轮当前Provider请求0、费用0，未读真实Key、未创建真实账本/registry，生产仍catalog_only，T040继续blocked。

## 准确运行方案

[运行根清单](run-r09.json)规范字节SHA256：`9fafc55d9034be4f6958004a921a2ec8bcf0972bb379d95a84b0bd7e6cab8db4`。固定202个来源文件及目标、角色Prompt/schema、派生规则、原样本/标签、费用和期限；[target](target.json)、[consent](consent.json)、[labels](labels.json)、[prerequisites](prerequisites.json)均绑定其中。真实批准登记尚不存在。

| 项目 | 本轮范围 |
| --- | --- |
| 模型/传输 | https://api.deepseek.com / deepseek-flash / Responses JSON schema；low、temperature0（思考时上游忽略温度）；文档版本DeepSeek-V4.1-Flash，实际权重revision unknown |
| 案例 | 原queue:explanation:1错误例 → 人工事实确认 → 原correct-list-concept正确对照 |
| 上限 | K16/C0，每例最多19次、全组最多38次潜在请求；并发1、无修正/重试/回退 |
| 输出/期限 | 每次8192总输出（含推理）、120秒；首次建账起固定10800秒；绝对到期2026-10-18 23:59:59 Asia/Shanghai，取更早者，重启不延长 |
| 费用预留 | **120149000微人民币 = CNY120.149000**；按完整最大可达图/各阶段最大wire计算，每项分别向上取整；不是预计消费 |
| 边界 | 仅独立校准，不替代原四组诊断、正式质量、DSL或T041；不恢复旧r01–r08、不拼分、不开放动态生产 |

## Token/费用界的依据与限制

[费用证明](token-cost-proof.json)改用整个上游上下文窗口的**契约上界**，不使用字节到Token比例或服务端格式1024估计。[官方模型规格与人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)列出1M窗口及峰值未命中输入2元/百万Token、输出8元/百万Token。[官方Responses兼容说明](https://api-docs.deepseek.com/guides/responses_api/)说明超窗请求返回400；[接口说明](https://api-docs.deepseek.com/api/create-response/)明确max_output_tokens包含可见输出与推理。2026-10-15直开超时后用官方域搜索结果复核，无模型调用。

推导（工程侧推论）：按1M可能采用的十进制/二进制口径，取上界1048576输入Token，已包含服务端格式。现有计数器仍以`I=实际wire字节数+1048576`预留，额外wire项只增加余量，并不声称1 byte=1 Token。各阶段在批准前使用证明过的最大wire计算最大可达图，因此得到120.149000元的保守组预算；实际每槽以具体wire预留，不退款或转授额外槽。

该界依赖供应商遵守已公布窗口、usage口径和峰值标价，属于供应商契约预算，不是供应商账户的硬支出限制或独立验证过的tokenizer证明；供应商若违约不能声称程序已经阻止超额。价格/身份/规格变化或无法复核时停止并重新评估。未知账单保持unknown，不凭实际较低用量扩额。预计消费未估算。批准时须复核条款，当日有效，跨日不自动刷新批准记录。

## 已接好的启动与人工门禁

[准备脚本](../../../scripts/prepare_t040_derived_run.py)只对真实.env做metadata stat，固定device/inode/size/mtime/ctime；不读取、散列或输出Key。凭据引用绑定此文件版本；任何修改/替换/符号链接均拒绝，换Key须新轮次批准。文件metadata不是Key内容或可跨机器的版本标识，不承诺抵抗能改写全部本地状态的攻击者。

[单步入口](../../../scripts/run_t040_derived_calibration.py)在准确运行批准前不建账/读Key/DNS/联网。受信操作人必须依据真实用户决定另存run-approval.json，内容准确绑定根/目标/同意/证明摘要、38次、120149000微人民币、期限、批准原话、可回查的聊天消息引用和当日条款复核。它是受信人工登记，程序不能从任意JSON、模型approved=true或文件名证明人类身份；无此登记不可执行。没有自动生成批准、自动同意回退或默认付费。

批准后每次step只发送一个合法从未尝试槽；consume持久化后凭据lease才重新核验批准、文件版本及服务端目标配置并读取既有Key。固定IP/Host/SNI/无代理/无重定向/无重试保持。失败仍消耗预留；悬挂尝试恢复即停，未知用量不伪填。

每例完成后固定停在CASE_REVIEW_REQUIRED。report以只读SQLite输出原可见结构化审核、finding引用、用量、来源摘要和标准，验证保留结果、请求/父/槽位绑定；不留原始响应/推理/密钥。实际人工确认后，受信操作人将逐项观察与finding_refs、报告摘要、批准原话及消息引用写入独立assessment，assess才允许下一例。队列必须同时核对计数回绕错误、空满混淆及fact类别；正确对照不能误拒。程序验证证据引用和结构，**不以这些校验代替人工语义判断**。失败确认会ADMISSION_FAILED停止；旧报告/伪造引用/缺项/未完成报告不得晋级。第二例人工通过也只完成本次校准，不标T040完成。

```sh
# 以下两个命令无真实调用，也不创建运行批准
backend/.venv/bin/python scripts/prepare_t040_derived_run.py --check
backend/.venv/bin/python scripts/run_t040_derived_calibration.py check
# 必须另获本轮确切批准后，才允许逐次使用；不是自动循环
backend/.venv/bin/python scripts/run_t040_derived_calibration.py step
backend/.venv/bin/python scripts/run_t040_derived_calibration.py report
backend/.venv/bin/python scripts/run_t040_derived_calibration.py assess --assessment /absolute/path/to/actual-human-assessment.json
```

## 验证

[验证记录](validation.json)：28项新增+311项既有=339项离线通过；Ruff、生产app mypy166源文件、流程/历史批准/冻结校验通过。包括缺失/伪造/过期批准、轮次/费用/同意错误、凭据轮换、撤销、逐例真实调用数mock计数、人工门禁失败停机、旧报告/伪造finding拒绝、收据/槽绑定和符号链接拒绝。真实CLI step实际返回NOT_AUTHORIZED（退出1是预期门禁结果），实际无ledger/registry；所有发送测试只使用合成.env/审批/人工事实及MockTransport，真实socket/DNS禁止，不证明模型质量、真实账户费用/TLS或同意身份。

scripts仍未纳入严格mypy，app类型检查不能冒称这些脚本已严格类型验证。原六规则附件、r08 186来源及1次CONCRETE_DEFECT_MISSED停止台账保持。真正开跑前仍需用户对本根、38次和120.149000元上限单独批准；随后才能保存实际批准登记并逐槽运行。
