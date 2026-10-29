# T085 七槽真实合成兼容：4槽通过，S5失败后终止

**实际5 real HTTP，前4槽通过；S5虽HTTP200，输出不是约定实例且JSON非法。S6/S7未预约、未发送，本批不可重启，未用2请求失效。** 本轮没有课程、真实学生、e03/H、审核Provider调用或教学质量结论。

准备提交de65386；准确manifest `0312764b635f62310f36513683c9fdd98653186224471e024601fcff5658df79`（129文件）。原请求字节等于fb61d70中已批准的七份合成候选。用户已批准ADR0047 A—D、七HTTP/900秒范围，明确“开始真实调用”，并在本次准确费用风险问题中答复“接受本批费用例外并执行”。独立窗口2026-10-29T13:13:27.473640+08:00至13:28:27.473640+08:00，不继承旧窗口/费用例外。

| 槽 | 实际观察 | 报告输入/输出token | 结论 |
| --- | --- | ---: | --- |
| S1 C规划 | DeepSeek HTTP200 | 354 / 52 | 严格Schema/本地规则/准确echo通过 |
| S2 C内容 | DeepSeek HTTP200 | 2514 / 178 | 同上 |
| S3 C修复 | DeepSeek HTTP200 | 2824 / 178 | 同上；仅合成修复包装，不是教学修复收益 |
| S4 B生成 | DeepSeek HTTP200 | 2248 / 265 | 同上；固定echo不证明B会独立解题 |
| S5 B修复 | DeepSeek HTTP200、completed、reasoning none | 2637 / 1031 | message.text非法且不是预期实例，立即停止 |
| S6/S7 B/C审核 | 未预约、未发送；无AIAPI DNS | N/A | 未验证，不能借旧sol样例准入 |

只读结果见[assessment.json](assessment.json)，逐槽摘要/原错误分析见[failure-analysis.json](failure-analysis.json)，私有原件哈希见[evidence-manifest.json](evidence-manifest.json)。原件在`/private/tmp/edumind-p15-minimal-live-r01`，0700/0600；Key/Authorization未落盘，未修改响应或截取有效片段重新当成功。

## S5的准确错误

原始响应message.text共3306字符，严格解析失败：

```text
JSONDecodeError: Extra data: line 1 column 3288 (char 3287)
```

只读raw_decode用于解释错误，**未用于准入**：前3287字符解成一个含additionalProperties/properties/required的对象，逐值等于本次请求Schema去掉根type后的对象；随后还有非法尾部：

```text
, "type": "object"}
```

因此服务实际返回了Schema片段，不是paragraphs/code/questions/answers/actions的合成实例；即使截掉尾部，前段仍不是预期实例且不符合输出Schema。没有截取、补括号或重发。外层status为completed、incomplete_details为空、报告输出1031低于请求4096，不是有证据的输出上限截断。

S4/S5输出Schema和expected_output完全相同；S4成功、S5失败，用户输入包装（生成/修复上下文）不同。本次证明S5准确请求返回了非法且错误形态的内容；**不能据此唯一归因于修复上下文、采样、生成模型还是服务处理，更不能评价教学事实质量**。所有5个请求都是200，S5的外层Schema回显也准确；回显和strict:true不能保证实际内容始终有效，不能把它当作已验证的远端强制保证。

## 预算、停止与证据

26条持久事件，运行约21.44秒；逐个完整通过才推进，S5未validated。原始终止reason是通用`ROLE_LOCAL_PROTOCOL_OR_TRANSPORT`，只读复现进一步定位到JSONDecodeError；不修改冻结执行器或原汇总来重写诊断。

真实发送5、响应记录5、准入4/7；1个已发协议结果未获信任，后2未运行。有效前4报告输入7940/输出673；含失败S5的外层报告合计输入10577/输出1704（总12281），只是响应自报，不是账单/上游硬限认证。实际费用/币种和中转完整上下文仍未知；本批金额例外已明确接受，不退还未知占额或自动再开新批。

实际`--run`与`--check-results`均exit2，表示合规停止且未完成全部协议准入；原件/请求/来源/窗口/终态只读核验通过。停止后另外将credential加载器设为必失败的陷阱，只调用CLI前置门禁，准确返回`EXISTING_OUTPUT_NO_RESTART`/exit2，未读取Key且私有目录逐文件摘要不变；没有新增模型HTTP。

准备阶段412项离线测试仅证明程序检查行为，不能记为新增真实教学或质量分子。旧冻结/批次及教学标准不变，T038 blocked/catalog_only/H保持。

## 交接

T085只完成按批准范围采集与解释证据，不表示兼容成功。整套角色尚未准入，因此不能进入课程生成实验。停止当前准确批次，交回原件与分析；不逐字段改Schema，不自动修Prompt/补样/换模型/重启或消耗剩余2请求。下一步应基于该输出格式失败整体评估执行路线，再决定是否另提方案；本轮不追加调用。
