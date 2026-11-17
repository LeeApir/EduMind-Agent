# T113 · 固定 Provider 接入评估与下一轮方案

**当前 AIAPI `gpt-6.1-sol` 路线不适合作为下一轮固定验证来源。** 封存规划和正文分别通过了独立内容检查，但两份回执均未同时满足固定来源、执行参数、指令和 Schema 证据要求。缺字段只是其中一项。已停止对该路线追加适配，建议下一轮改用 DeepSeek 官方 Responses 直连。本次新增 Provider 调用 **0**，交付为接入判断和替代执行提案。

## 封存证据与原契约

对照 [ADR0055](../../ADR/0055-fixed-head-course-validation.md) 及其 [固定配置](../phase-1.5-head-fixed-t111/candidate-config.json)。原请求固定 system/user 顺序、`stream=false`、`store=false`、`reasoning.effort=none`、`temperature=0.2`、规划及正文输出上限 8,000、严格 JSON Schema、无工具。r04/r05 替换地址和请求模型，r05 只调整客户端读取超时并重用 r04 的准确正文请求。对照规则区分了现有校验行为和下一轮固定来源应满足的条件。早期适配器通过不等于后者通过。

- **r04 规划**：回读 12,070 字节。原 AIAPI 适配器接受外层，规划独立语义通过。正文第一次在 90 秒内未取得响应头，服务端结果和费用未知。第二次未发。[r04 结果](../phase-1.5-head-fixed-aiapi-r04/RESULTS.md)
- **r05 正文**：约 92 秒收到 27,627 字节。原入口重放仍拒绝 `AIAPI_ENVELOPE`；原文、独立评估和 [T112 限定导入](../phase-1.5-archived-head-import-t112/README.md) 可分别核对。该导入资格来自 ADR0057，不能转成这条接口的正常准入。[r05 结果](../phase-1.5-head-fixed-aiapi-r05/RESULTS.md)
- **更早的 AIAPI 对照**：S1 已观察到 128 的输出上限回显 `null`。流式 S2 的请求上限是 512，响应自报输出 802，含推理 128，同时本地规划 Schema 失败。流式证据不能证明本次非流式 r05 超限，也不能用 r05 的自报 6,659 低于 8,000 证明上限会执行。[S1](../phase-1.5-aiapi-minimal-r01/RESULTS.md) · [S2](../phase-1.5-aiapi-s2-once/RESULTS.md)

复核匹配了请求、批准、原件索引、加密原始字节、HTTP 收据、失败与 STOP，并重放了 DeepSeek r01 规划和 r03 正文作为同合同对照。[逐字段观测 JSON](observations.json) 列出四个完整回执的顶层键、消息键、关键参数值、Schema 差异路径和用量。它省略原文、响应 ID 和账号、缓存、审计等关联标识的值。

## 差异与处置

表中“可处理”是可在限定适配中处理的表示差异。它不授权对 AIAPI 放行，也不产生新的准入入口。

| 项目 | r04 规划／r05 正文 | 处理边界 |
| --- | --- | --- |
| 终态与正文容器 | 均为 HTTP 200、`object=response`、`completed`，一条完成的助手消息、`phase=final_answer`、一个 `output_text`。r04 空 `annotations/logprobs`、明确 `error/incomplete_details=null`；r05 无 `logprobs`、`error`、`incomplete_details` 键，新增顶层 `output_text` 且与消息逐字相同。 | 可复用现有仅允许缺省或 `final_answer` 的规则。经明确约定，允许空可选诊断字段缺省；附加文本只能核对相等，正文仍取唯一消息。错误、截断、非最终阶段、多个正文、不同副本、工具/推理/拒答输出、非空注解或未知内容类型均拒绝。 |
| 模型与存储 | r04 回报请求的 `gpt-6.1-sol` 和 `store=false`；r05 两键缺失。 | 分开保存请求值、回报值和键是否存在。缺失的回报值为未知，现有固定来源要求可核对标签和 `store=false` 回报，缺失、错值或 `true` 均拒绝。匹配回报也不能证明实际模型快照或内部留存策略。 |
| 推理、采样与输出上限 | 两次请求均为 `none / 0.2 / 8000`。r04 回报 `low / 1.0 / null`，推理还多了 `context=all_turns`、`mode=standard`、`summary=null`。r05 三项无键，自报有 **303** 推理 token。两份响应均未直接回报 `stream` 键，实际收取完整非流式 HTTP 实体。 | 回显冲突和与 `none` 不一致的推理用量必须拒绝。缺失或 `null` 的执行参数保持未知。低于上限的自报用量只是单次观测；上限未获确认或自报超预约均停止。只依据实际 HTTP 形态识别非流式传输。 |
| 指令 | r04 回显完整 system 文本后附加 `\n\nYou are a helpful coding assistant.`（37 字符）；r05 无 `instructions` 回显。 | 可记录追加内容的类别和准确原件，不能删去后缀再判一致。固定教学协议拒绝已观察到的额外指令。缺失或 `null` 只能记回显不可用；无法据此推断存在或不存在其他内部指令，也无法确认上游实际上下文。 |
| 结构化输出回显 | 两份均回报原 Schema 名、`json_schema` 与 `strict=true`。r04 回显删除 `source_keys` 及场景 `forms`、`depends_on`、`objective_ids` 上的四个 `uniqueItems`，另有 `description=null`、`verbosity=medium`；r05 删除 `paragraphs[].fact_ids` 的 `uniqueItems`。同阶段 DeepSeek 封存对照保留全部 Schema 约束。 | 描述和呈现元数据可按已知形态单独记录。约束消失是实质差异，固定来源按原请求 Schema 及本地业务契约验结果，不能用服务端回显覆盖它；下一轮固定入口拒绝回显的约束丢失或变更。即便回显一致，也只表示 Provider 报告一致。 |
| 执行模式、会话和工具 | r04 `background=false`、`previous_response_id=null`、`tools=[]`、`max_tool_calls=null`，另有 `tool_choice=auto`、`parallel_tool_calls=true`，工具用量中的图像和搜索均报零；r05 无这些键。 | `auto` 或 parallel 的默认回显与实际工具调用是两件事。已知空字段、无输出项及零报告可分别记录。非空工具、非零工具用量、背景执行、会话继承或其他超出约定的行为均拒绝。r05 无自报工具使用细节；从单条文本只可判断未见工具输出。 |
| 运行默认值及缓存 | r04 额外回报 `top_p=0.98`、`top_logprobs=0`、两个 penalty 为 0、`service_tier=default`、`truncation=disabled`。还有非空 `prompt_cache_key`、`prompt_cache_retention=24h`、`image.context_compression=disabled`、`access_programs.cyber=standard`、`moderation=null`。r05 均缺。 | 已知、非行为性元数据仅作私有审计。影响采样、服务或留存的字段必须作为独立观测，不从默认值倒推出实际执行；对下一轮已声明的固定值，出现冲突则拒绝。缓存与响应保存是不同维度，`store=false` 不能抵消缓存留存回报。若必须证明零留存，需独立供应商证据。 |
| 身份和时间元数据 | 两份均有响应 ID、消息 ID、创建时间；仅 r04 有完成时间、`safety_identifier`、`user=null`、`metadata={}`。 | 有限验证字段形态，留在私有原件，关联标识不参与业务身份映射、学生页面或教学审核。缺少完成时间不能补造；时间窗口以本地可核对记录为准。额外字段按版本逐项识别，未知语义不自动放行。 |
| 用量 | r04 2,975 入 / 565 出 / 3,540 总，推理 0，另带按消息与请求字段计量的 `attribution`。r05 9,772 入 / 6,659 出 / 16,431 总，推理 303，包含额外的缓存/模态明细，无 `attribution`。 | 主账只采用明确口径的 Provider 自报总量，验证整数、加和、推理子集和本地上限；不把明细再加进主账或据它补算费用。附加明细隔离保存，计量准确性和实际账单仍未知。 |

这次能够安全处理的主要是终态、重复文本和可选元数据的表示差异。固定来源所需的关键证据不能由客户端补齐。尤其是 r04 已有冲突回显和指令追加，r05 报告了与请求不一致的推理用量，并未回报可确认的模型、存储、温度和上限。额外的 Schema 约束变化提供了另一个独立的拒绝理由。因此本次没有实现 AIAPI 正常生成适配，也没有登记可执行的 AIAPI 批次。

## 替代执行提案 · 仅供评估，真实授权为 0

**建议使用 `https://api.deepseek.com/responses` 的 `deepseek-flash`。** 官方文档列明支持 Responses JSON Schema、关闭推理模式、非推理模式温度与输出上限，并说明响应接口的 `store=false` 语义。文档中的模型版本是别名当前映射，不是未来单笔调用的独立证明。封存 r01 与 r03 响应已实测返回匹配的标签、`store=false`、`none`、`0.2`、8,000 及原 Schema；回显的独立 `instructions` 字段为 `null`，请求中的 system 消息仍按原字节保存。这些证据支持选路，不证明新课程必然通过。T111 的 DeepSeek 正文曾有无效事实引用，以及 F01/Q01 教学阻断；这些仍是下一轮须检查的质量风险。[DeepSeek Responses](https://api-docs.deepseek.com/guides/responses_api/) · [模型与价格](https://api-docs.deepseek.com/quick_start/pricing/) · [T111 r02](../phase-1.5-head-fixed-continuation-r02/RESULTS.md) · [T111 r03](../phase-1.5-head-fixed-repeat-r03/RESULTS.md)

| 项目 | 下一轮拟固定规则 |
| --- | --- |
| 对照对象 | 使用 `head-new-C` 原准确目标与固定输入，初始 `[5]`，插入 `-2,9`，两次分配成功。从真实表单、新访客、新私有操作重新规划。保持同一输入以检验接入，全部新教学内容来自新批次；这项验证不测输入多样性。 |
| 请求与入口 | 以 `scripts/head_course_goal.py` 的有限前台 `prepare → send plan → send generate → 条件 send repair → publish` 和现有私有开发库为基础，另冻新批标识、源码和原件目录。保留原 system/user、`stream=false`、`store=false`、`reasoning.effort=none`、`temperature=0.2`、无工具、重试、重定向或回退。沿用 `head-goal-plan-grounded-v3`、`head-goal-planning-wire-v2`、`head-fixed-course-v1` 的首稿材料/Schema 与 `head-reviewed-local-revision-v2`。 |
| 先验准入规则 | 限定本机准确 HTTPS 路由、收齐原件后严格解析，只接受一条最终助手文本。要求 `model=deepseek-flash`、`store=false`、`reasoning.effort=none`、零自报推理、`temperature=0.2`、输出上限回报等于请求、原 `text.format` 类型/名称/strict/Schema 一致。已观察到的 `description=null` 和 `verbosity=null` 单独核对。允许独立 `instructions` 回显缺省或 `null` 并记录未知，非空时必须等于原 system；任何已观察到的追加或替换都停止。已知无行为的元数据限字段、形态与必要的零值，保留原件。发现未知行为字段、工具、回显冲突或必需值缺失即 STOP。不同候选走同一动态摘要与原件、审核绑定流程，无候选摘要白名单。 |
| 请求与时间预算 | 拟最多 3 次 HTTP，规划 1、正文 1、符合范围的条件修订 1；上限依次 8,000/8,000/4,000 输出，输入本地预约每次 139,264，合计 417,792 输入和 20,000 输出。请求≤131,072 字节，响应≤2 MiB，I/O 90 秒。提议新批和专用开发操作采用同一 30 分钟截止，在环境、评估者和终端均就绪后创建真实应用操作，并以其创建时间起算；剩余不足 90 秒拒绝出站。窗口到期后禁止发下一项和写准入。30 分钟与同步起点是待确认的限定变更，仅限这一个开发批，不修改普通调度时限。 |
| 费用与停止 | 以当前公开峰时非缓存入价与输出价估算满预约约 **USD 0.14934**，实际金额未知，估算不构成硬上限。另需准确批准本批 C2 例外，沿用单前台尽力停止，可能迟发或继续计费，本机加密原件不具独立抗回滚保障。不启用 T102。请求前做路由、额度、窗口、操作、审批和上一阶段检查；任何协议/事实绑定/规划/安全失败、超限、超时或未知结果原样封存、写 STOP、作废余额。没有独立规划 pass 则不发正文。 |
| 审核与正常课程交付 | 沿用 [T111 审核与验收](../phase-1.5-head-fixed-t111/review-policy.md)，仅正文四个题目键的同值重复允许现有确定性恢复，单列来源和原失败。最多一次模型局部修订，按准确父稿审核只改指定段落及引用、总结或失败范围，复评全文；题干或解析阻断仍停止。通过后走现有私有候选准入、版本仓储、播放器和服务端练习，验真实应用阅读、13 帧/高亮、控制、四题错答/正答、答案隔离与刷新恢复。分别登记首稿结构、首轮教学、恢复、修订及最终学习验收。 |

费率估算使用每百万非缓存输入 USD 0.30、输出 USD 1.20。公开定价会变化，冻结新包时复查，历史额度不继承。[DeepSeek 官方定价](https://api-docs.deepseek.com/quick_start/pricing/)

如确认这条路线，才准备独立零调用冻结包，并检查新的本地回显门禁及限定时限、两条正常准入路径和失败边界。执行包须锁定实际输入/提示词/Schema、角色配置、构造函数及模板、证据规则和可运行入口。真实开始前另外批准准确 manifest、预算、窗口及 C2 条款。本页是可审查的替代提案，无批准记录、可运行新批或新课程结果。

## 离线复核

```bash
PYTHONPATH=backend backend/.venv/bin/python -m scripts.check_head_course_provider_review | python3 -m json.tool
```

对照该命令输出与 [观测 JSON](observations.json)。脚本只读取本机原件，通过历史响应适配器重放已记录结果，并通过 T112 导入的独立绑定核验 r05 正文。与观测 JSON 逐字节一致。固定首稿材料与限定合并的两项离线检查通过，Ruff、工作流及 diff 检查通过。数据库、浏览器和真实生成验收留在新批。r04/r05 旧目录、停止、失败、原额度、运行代码、T111、T102 和 T038 的门禁均保持历史记录。
