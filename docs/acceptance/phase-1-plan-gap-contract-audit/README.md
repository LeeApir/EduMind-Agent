# plan-only-gap实际请求契约复核（零调用）

来源是已冻结suite-r01的41439字节真实请求，非重新拼装Prompt。wire SHA5cfdfa15cc68e61959d10e5ef60d2a6e8bd53e0f17e24bc4872e8df3fa46798b。脚本audit_plan_gap_contract.py校验其摘要、当前Prompt逐字相同、完整Schema与带原锚点的unit输出Schema相同，并复核原始目标/mandatory verdicts。

| 项目 | 复核结果 |
|---|---|
| 顶层 | 仅schema_version/scope/verdict/findings/coverage/unresolved，六项必需，禁止额外字段 |
| unresolved | 数组，元素是长度1–2000的字符串，至多32项；不是对象列表或单字符串 |
| coverage | checked/unchecked对象，禁止额外字段；checked只接受五个必查ID |
| findings | 数组，条目仅category/severity/anchors/condition_or_counterexample/impact，禁止额外字段，锚点枚举绑定本材料 |
| Prompt | unit只准pass/reject/needs_human；纯覆盖缺口放unresolved而非伪造fact；没有要求unresolved对象或顶层额外解释 |
| 实际输出示例 | 请求只有system指令与user材料，没有assistant/few-shot审核输出示例；学生示例和内部轨迹是审核输入，不能算输出示例 |
| 离线输出示例 | 既有valid_review(unit)与合成needs_human字符串数组示例通过实际Schema；原契约文档resource示例通过resource Schema（必查ID与unit不同），均未新增发送给模型 |

Prompt的“with findings only, no repairs”表述不够精确，但上下文为报告问题而不修复，后文和Schema要求协议字段；没有明确要求省略六个必填字段。Prompt没有复述unresolved的元素类型，Schema已明确string。以上是可改善表达的地方，不是已证实的冲突或本次额外字段根因，当前保持不变。

四个离线反例分别验证unresolved对象列表、unresolved单字符串、顶层explanation、coverage额外reason均被Schema拒绝。它们是合成反例，不代表旧真实响应含有这些字段。

Provider核对：实际POST /responses，text.format={type:json_schema,name:edumind_result,schema:原Schema}。DeepSeek官方Responses参数表说明json_schema及name/schema，兼容页说明format支持；所查响应格式表未列strict，因此不把缺strict判为配置错误，也不套用工具Beta strict。SDK/服务端内部是否做到强制约束未独立证实，本地Draft202012Validator严格校验仍保留。没有改请求、Schema、Prompt或Provider参数。

官方页面：[Responses参数](https://api-docs.deepseek.com/api/create-response/)、[兼容说明](https://api-docs.deepseek.com/guides/responses_api/)。参数页直读超时后用官方索引全文复核，兼容页直接读取，日期2026-10-16。文档对应不等于Provider不会输出Schema违规。

结论：未发现明确契约冲突，允许按用户顺序准备独立单次定位包；这不是语义质量通过，也不确定旧additionalProperties发生在哪个字段。旧响应缺失，具体字段与verdict继续未知。audit.json保存机器可复核摘要与反例结果。
