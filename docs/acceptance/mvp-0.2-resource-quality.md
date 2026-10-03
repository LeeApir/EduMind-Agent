# MVP 0.2 正式资源质量基准

> 2026-10-03 整理：下列本地材料路径沿用原仓库相对路径；读取及历史恢复方式见[材料索引](README.md)。旧指标、失败与判定不变。

当前状态：指令v3完整真实基准schema60/60（100%）、严重召回20/20（100%）、正确对照10/10，达标且主要问题已逐项核对。首次75%和v2的95%失败基线保留。小样本结论仅适用于记录环境，不宣称生产全课程质量。

## 样本与口径

样本版本 `resource-quality-v1`，来源为 `data/quality/resource_review_v1.json`，全部由项目原创编写，不含教材正文、学习者身份、真实目标或原始作答。SHA-256：`f6dca43e80ad6244136ba88af7ff4d01dad5bd81501cee350d26e5c2e76caed3`。

- Schema 生成：10 个种子节点 × 讲解/代码/练习 × 2 次独立生成，共 60 份输出。失败请求计入分母；本地严格 schema 校验通过才计入分子。不以修正后的结果替代首次失败。
- 严重错误集：16 个语义错误及 4 个本地可检测的危险代码，共 20 项。覆盖错误概念、前置方向、链表连接、边界/空指针、栈队列顺序和循环队列。标准答案与判断依据仅保存在基准文件，不发送给审核模型。
- 正确对照：每个种子节点 1 项，共 10 项，单独报告通过率以识别过度拒绝。
- 审核测量首次 verdict，不运行定向修正。只有实际模型返回非 pass，且至少有一项同领域 major/severe 问题，才计为检出；Provider 不可用导致的 fail-closed reject 不算检出。需逐项核对问题内容是否命中了原始严重错误，不能仅凭拒绝或领域标签认定召回。
- 总召回与剔除本地代码门禁后的语义模型召回分别记录；数值检查要求 schema ≥98%、总召回 ≥90% 且语义模型召回 ≥90%。正确对照和逐项问题审计作为额外可信性证据，不以“全部拒绝”冒充有效审核。

一次完整运行最多 86 次模型请求（60 次生成 + 16 次语义错误审核 + 10 次正确对照），4 项危险代码由本地门禁直接拒绝。关闭 Provider 重试及资源修正；任何错误保留在分母。资源生成输出上限为 2048 tokens，审核沿用项目 Provider 默认上限。仅使用当前服务端配置的单一 Provider，不切换厂商或模型。

## 命令

纯离线，无网络调用：

```bash
cd backend
uv run python -m tests.resource_quality --mode offline
uv run pytest -q tests/test_resource_quality.py
```

真实评测必须先获得用户明确的费用授权；参数本身不是授权证据。根 `.env` 必须被 Git 忽略且仅在服务端读取；不得打印环境变量或凭据。

```bash
cd backend
uv run --env-file ../.env python -m tests.resource_quality \
  --mode provider --confirm-billable \
  --output ../docs/acceptance/mvp-0.2-resource-quality-provider.json
```

输出包含模型 ID、版本、样本量、成功/错误项、首轮审核 verdict/问题及耗时，不含凭据、Cookie、Base URL、真实用户数据或生成资源全文。审核问题针对公开原创基准内容，可用于人工核对。报告必须保存脱敏证据，并核对 Provider 返回的实际模型 ID。模型/提示词/图谱改变后重新运行；小样本仅描述当前环境，不代表所有课程或生产质量。

## 当前证据与下一步

2026-09-26 离线运行：30/30 原创候选满足资源 schema，4/4 危险代码命中本地门禁；16 个语义错误未被离线判断，真实生成通过率与严重错误召回均为 `null`，阶段门禁为 `false`。

### 2026-09-26 真实评测

用户回复“确认”后执行上面的命令，203.82 秒完成，退出码 1（质量门禁失败）。配置模型与成功响应实际模型均为 `deepseek-flash`；86 次请求，无重试、无修正。原始脱敏报告见 provider JSON（本地材料 `docs/acceptance/mvp-0.2-resource-quality-provider.json`）。

- Schema：45/60，75%，未达 98%。讲解 6/20、代码 19/20、练习 20/20；15 项失败均为 `INVALID_OUTPUT`，没有偷偷剔除分母。
- 严重错误保守自动计数：19/20，95%；剔除本地代码门禁后的语义模型计数为 15/16，93.75%。两项均达 90%。
- 正确对照：10/10 pass，无过度拒绝对照样本。
- 逐项核对 16 项语义审核的主要问题，均明确命中对应错误：数组复杂度/搬移、指针地址和无效解引用、链表布局/前置/终止/索引/链接更新/释放、栈队列顺序、循环队列判空满与回绕。`pointer-null` 实际被 reject，且事实问题准确指出 NULL 解引用未定义行为；预先固定的同领域计数要求 `code_safety`，模型标记为 `fact`，因此原始报告仍保守计为未检出，不修改口径来提高指标。
- 部分辅助 difficulty/misconception 问题仍有对短资源覆盖范围要求过高或推断过强的情况；不能把所有辅助意见直接视为可靠教学建议。主要严重错误及正确对照足以支持本次召回证据，不支持全课程泛化。

本地检查发现 Adapter 将 JSON 解析和 schema 不匹配统一归为 `INVALID_OUTPUT`；本轮未保存生成全文，因此无法进一步确认是转义、字段不匹配还是截断。14/15 失败集中在 Markdown 讲解是诊断线索，不是已证实根因。不能放宽 schema 或根据猜测重写原始报告。

### 不计费诊断准备

经用户确认，仅开展离线诊断开发。`ProviderError` 新增服务端内部 `output_failure_reason`，只允许固定枚举：响应 JSON 无效、结构化 JSON 无效、非对象、schema 不匹配、请求 schema 无效、响应未完成、明确的输出 token 上限。外部错误码和安全错误消息保持不变，不把厂商内容、JSON 解析异常、schema 错误路径/值或输出正文放入异常/报告。只有响应明确说明 `max_output_tokens` 才标记 token 上限，未知 incomplete 不猜测为截断。

未来基准在生成失败条目中记录该枚举，旧报告不回填未知原因。单元回归通过 MockTransport 验证裸换行/围栏拒绝、正确转义 Markdown 接受、非对象/schema 类型失败分别归类，以及未知厂商理由不泄漏、任意诊断文本拒绝。严格校验、首轮失败分母、无重试和86次上限均保持。此变更修复诊断缺失，不证明真实生成质量已改善。

另提供 `diagnostic` 模式，固定复查上轮失败的 array/c-pointer/circular-queue/linked-list-deletion 讲解和 linked-list-insertion 代码，共最多5次请求；2048-token生成上限与原基准一致，无审核/重试/修正。此模式不计算 schema 通过率或召回，门禁恒为 false，不能代替60份质量样本。每次运行必须另获费用授权：

```bash
cd backend
uv run --env-file ../.env python -m tests.resource_quality \
  --mode diagnostic --confirm-billable \
  --output ../docs/acceptance/mvp-0.2-resource-quality-diagnostic.json
```

### 2026-09-26 固定5次真实诊断与修复候选

用户回复“同意”后执行 diagnostic 命令，共5请求、16.35秒；脱敏诊断报告（本地材料 `docs/acceptance/mvp-0.2-resource-quality-diagnostic.json`）保存原结果。array讲解及insertion代码有效；c-pointer/circular-queue/deletion讲解均为 `STRUCTURED_JSON_INVALID`。此报告使用修改前的v1指令；没有请求重试或定向修正。已证实这3项为JSON语法解析层失败，而不是schema类型错误或明确输出上限；但未保存正文，不能进一步断定具体语法缺陷。不同轮同一样本结果会变化，不能用2份通过覆盖原报告失败。

针对JSON解析层失败，新增 `learning-resources-instructions-v2` 明确序列化约束及完整对象示例；示例由 `json.dumps` 构造并经schema测试验证。schema/envelope版本仍为 `learning-resources-v1`，不改变字段/容忍度/输出上限；新生成及定向修正保存指令版本，历史候选无版本时保持原metadata而不是误标为v2。参考与约束见 [指令v2](../agents/prompts/learning-resources-instructions-v2.md)。未改变Review提示或原始质量样本。

验证：隔离PostgreSQL全量288 passed、无跳过、7原有依赖警告；Ruff/Mypy53文件/diff检查通过。第一次全量回归发现未知指令版本被写成null导致历史metadata契约不兼容，已修复为未知不写入，并补新版本持久化与旧候选不误标测试。该修复候选的真实效果未测，不能宣称达98%。

下一步：申请新一次最多86请求完整质量重测授权，使用新文件 `mvp-0.2-resource-quality-provider-v2.json` 保留v1失败基线，不覆盖旧证据。此前86次基准及5次诊断授权均已用完，不自动重跑、不领取依赖 T023 的 T024/T025，不创建完成提交。

### 2026-09-26 指令v2完整重测（未达标）

用户再次回复“同意”，明确授权新的最多86次请求。执行相同provider命令，输出文件改为 `mvp-0.2-resource-quality-provider-v2.json`；原始脱敏报告（本地材料 `docs/acceptance/mvp-0.2-resource-quality-provider-v2.json`）完整保留。实际模型 `deepseek-flash`，229.44秒、86/86请求，禁重试/修正，exit1。

- Schema57/60=95%，仍低于98%。讲解20/20、代码18/20、练习19/20。相比v1的75%，本轮观察到改善，但不能由两次小样本证明稳定性或泛化效果。
- 失败为 `circular-queue:code:1` / `circular-queue:exercise:1` 的 `STRUCTURED_SCHEMA_MISMATCH`，以及 `circular-queue:code:2` 的 `STRUCTURED_JSON_INVALID`。没有放宽解析或忽略失败。现有脱敏分类不能指出具体违背哪条schema，仍不能猜测字段缺失、类型或内容问题。
- 严重召回20/20=100%，其中语义16/16=100%；正确对照10/10 pass。逐项核对16项语义审核主要意见，均明确对应原创错误，NULL项本轮亦有code_safety严重问题；本地4项仍由静态安全门禁拒绝。辅助难度/覆盖建议存在既有过度要求限制，不等于全部审核意见可信。

第二轮完整授权也已耗尽，不能继续付费重跑。下一步建议补固定枚举的schema关键字分类（不记录输出值、字段路径、厂商正文），以最多3次循环队列生成诊断定位剩余失败，再基于证据修复；需要用户重新授权这些请求。质量仍未达标，T024/T025不能领取，当前成果保留未提交，未push/merge。

### 2026-09-26 循环队列3次诊断

用户回复“同意”后，新增白名单 `schema_keyword` 分类及 `circular-diagnostic` 模式，经mock预算/授权/敏感内容隔离测试通过后执行：

```bash
cd backend
uv run --env-file ../.env python -m tests.resource_quality \
  --mode circular-diagnostic --confirm-billable \
  --output ../docs/acceptance/mvp-0.2-resource-quality-circular-diagnostic.json
```

共3/3请求、11.90秒、deepseek-flash、无重试/修正。code:1为 `STRUCTURED_JSON_INVALID`，exercise:1及code:2有效。本轮未复现schema mismatch，因此没有具体schema关键字证据。不能推断旧失败已修复，也不能拿2个新成功替换质量报告中的失败。完整schema门禁仍57/60=95%。独立诊断报告（本地材料 `docs/acceptance/mvp-0.2-resource-quality-circular-diagnostic.json`）保留原结果。

当前所有已授权请求已用完。继续盲跑完整基准或重复3次样本不能保证定位。下一步应先把JSON解析失败细分为固定、无内容的语法类别（如无效转义、未转义控制字符、未闭合字符串等），以真实失败类别为修复依据；不记录厂商正文或学习者数据、不放宽解析。需要新的明确费用授权才能再采集真实诊断证据。未创建T023完成提交，后续依赖保持阻塞。

### 离线语法分类准备（2026-09-26）

用户确认仅进行离线开发。新增 `JsonSyntaxReason` 枚举及基准 `json_syntax_reason` 字段：无效转义（含无效Unicode转义）、未转义控制字符、字符串未闭合、缺少分隔符、缺少属性名/值、额外数据、其他。只映射Python JSON解析器固定消息前缀，不传递原文、异常文本、位置、行列、字段路径或值；未知解析异常归其他，不猜测根因。任意字符串或非结构化JSON错误上的语法标签均被拒绝。

验证：隔离PostgreSQL全量303 passed，无跳过、7原有依赖警告；针对性47 passed；Ruff/Mypy53文件/diff通过。覆盖转义/控制字符/围栏/尾逗号/分隔符/额外输出与标签泄漏边界，基准mock报告保留固定类别。0真实请求，不修改生成指令/严格解析/旧报告。新分类须实际采集后才有真实语法证据。

### 当天统一费用授权与v3达标证据

用户明确授权2026-09-26当天所有当前Provider、MVP0.2范围计费请求。语法诊断最多三轮，实际两轮共6请求后停止：第一轮3有效，第二轮2有效/1循环队列代码schema `required` 失败，报告为 `mvp-0.2-resource-quality-circular-syntax-diagnostic{,-2}.json`。仍未采到具体JSON语法类别，但已确定存在必填结构缺失，不猜测具体字段。

第二轮实质不同修复为 [instruction-v3](../agents/prompts/learning-resources-instructions-v3.md)：实际完整schema同时写入提示正文，强化所有嵌套required键可见性；输出schema-v1、校验、基准集、2048token、单Provider均不变。旧instruction-v2文档和资源版本不回填。

执行provider模式，输出另存 v3真实报告（本地材料 `docs/acceptance/mvp-0.2-resource-quality-provider-v3.json`），86请求、227.57秒、exit0、实际deepseek-flash、无重试/修正：schema60/60、严重召回20/20、语义16/16、正确对照10/10。逐项核对16份语义审核主要意见均对应原创错误：复杂度/搬移、指针地址与无效解引用、链表布局/前置方向/终止/索引/遍历/链接更新/释放、LIFO/FIFO、循环队列判空满和取模。安全4项由原静态门禁命中。辅助difficulty/misconception意见仍保留已记录限制，不因此把所有辅助建议当准确事实。

最终离线303 passed无跳过，7原有依赖警告；Ruff/Mypy53文件/diff通过。今天统一授权后本任务实际新增92请求（6诊断+86基准）；本任务累计已记录272请求，不代表已知货币金额，实际费用以Provider账单为准。授权不跨北京时间日期，不更换Provider，不授权push/merge。T023质量证据已满足，后续完整学习闭环与性能由T024/T025独立验收。
