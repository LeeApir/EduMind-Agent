# 教学节点数据与 API 契约 v1（T060 待批准）

规范性上位决定：[ADR-0018 A–D](../ADR/0018-teaching-node-binding.md)。本文件是设计，不是现有 API 行为。

## 1. teaching_context

结构为服务端生成的对象；客户端和模型只能提出教学模式，不能自报节点/路径事实。

| 字段 | 类型与规则 |
| --- | --- |
| version | const teaching-node-binding-v1 |
| teaching_mode | target / recommended |
| target_node_id | 确认目标解析得到的合法节点 |
| recommended_node_id | string 或 null，仅来自同 owner/目标的冻结路径；target 无有效推荐时可为 null |
| teaching_node_id | 由批准选择矩阵取得；不得 null 或凭空默认 |
| selection_reason | direct_target / recommended_prerequisite / recommended_target |
| original_request | 操作保存的完整 goal；原接口已有边界空白规范化保持，进入应用后的原文不再删改 |
| segment_goal | target 为 original_request；前置为服务端固定模板“为学习{目标名}，本节先学习路径推荐的{教学节点名}。原目标尚待后续完成。” |
| segment_scope | target_lesson / prerequisite_segment，与选择关系一致 |
| path_version_id | UUID 或 null，冻结路径行身份 |
| path_version | 正整数或 null，和 path_version_id 同时有/无 |
| graph_version | 当前批准图谱版本 |
| graph_digest | 同一图谱快照摘要 |

original_request 的完整配套要求仍在生成/审核上下文中；模板不声称每个原约束已经适用或完成。模型须检查原始约束与本节范围，真实不明仍报告。目标解析失败、节点不存在、recommended 缺推荐、路径 owner/target 不符时不生成上下文，不选替代节点。

PlanInputs 新增可选 teaching_context，不能塞入 plan-v1 的 metadata 后通过模型回显身份。PlanInputs.snapshot() 对新共享计划输入包含该对象；save_plan 的 input_digest 据完整快照计算。review_input 验证摘要后，使用 teaching_context.original_request 为原文来源，并提供服务端 segment_scope/segment_goal，不把 plan.goal 当原始请求。旧无上下文的历史/单测输入沿原 metadata.goal，实际新生产 shared-plan 入口必须具备上下文。

## 2. 数据传播矩阵

| 边界 | 必须验证 |
| --- | --- |
| 操作选择 | owner、原文/模式、确认目标、路径目标/owner/版本、图谱版本/摘要与合法节点；原子设置一次上下文 |
| 输入与模型计划 | metadata.node_id=teaching，metadata.goal=segment_goal；原文/模式/路径仍在完整输入中，plan 不可重选节点 |
| 计划保存 | input_snapshot.teaching_context=operation.teaching_context；unit.node=plan.node=teaching；不同主题不复用单元 |
| 场景/资源 | 三角色全部属于同 plan/unit；resource.node=teaching；依赖/摘要链仍完整 |
| material/案件/决定 | material.teaching_context 等于绑定 input_snapshot；unit_digest 纳入 context，旧摘要不能装新键；有缺失/冲突拒绝，不自动修正 |
| 原子发布 | 锁内复核 operation/plan/unit/resource/material/案件版本上下文、当前批准图谱资格及全部原审核条件；失败不新增正式指针 |
| 读取 | 按准确 publication_version 显示该版本上下文；不从当前路径拼装；撤回/owner规则不变 |
| 作答/掌握度 | 对新planned资源从实际发布快照取teaching，并核对resource/plan/unit；不再对新planned资源使用unit回退猜测；证据不可改写 |
| 路径 | 依据新证据所属teaching节点重规划原目标路径；不把原目标或所有前置一并标为已掌握 |
| 重解释/换例 | 精确继承原发布的教学绑定；内容/资源重审，依赖全部失效规则不变；改变主题须新单元 |

上下文在 publication.material 中作为版本化可选键保存。新格式声明必须提供并绑定该键，旧 material 不加键且继续按原 unit_digest 算法校验；不能将旧字节用新算法重哈希覆盖。旧已发布版本不迁移。新 material 使用 learning-publication-v2 的 unit 摘要域，并把 teaching_context 作为摘要参数；无该键的旧 material 仅用原 learning-publication-v1，不允许把两个算法交叉验收。input 摘要域仍 learning-input-v1，完整新增上下文字段自然改变 input_digest。T061 范围规则使用 Prompt evidence-resource-review-v4.9、authoritative-review-input-v4、teaching-bound-review-scope-v6，政策增加 teaching_scope=teaching-node-binding-v1；T062 绑定门禁增加 teaching_binding=teaching-node-binding-v1。两次政策摘要必须不同，T061不声称T062的DB约束已生效。T063/064不改变审核Prompt语义，若实现发现需改变则先版本化并评审。T062字段迁移不重写原学习计划Schema。

Alembic 下一修订仅新增 nullable learning_operations.teaching_context(JSONB) 及“已非空不允许修改/清空”的数据库约束/触发器。旧行 NULL 保留；仅新共享计划操作在首次选定后写入。新字段的内容/版本/一致性由应用完整校验；数据库不可变约束不能代替这些语义检查。取消或失败保留该冻结选择作为审计，不改成别的节点。

## 3. HTTP/SSE 与幂等

- POST /api/learning-sessions：shared-plan-v1 可选 teaching_mode，默认 target。legacy 不接收 recommended（422），不复用同参表示不同协议。新共享请求摘要包括规范化模式和selection_version=teaching-node-binding-v1。旧已存在键仅在客户端未提供teaching_mode且旧摘要精确匹配时只读重放，不重新解释成新模式；旧键后来显式指定任一新模式都409，避免将旧未知选择冒充target。legacy的target是默认无新增语义，摘要沿原算法；recommended不接受。不因旧记录缺上下文而新发模型请求。
- 新 SSE 事件 teaching_selected：operation_id 与完整经过公开字段白名单的 teaching_context，首次计划生成前排入流；事件仅告知已冻结选择，不表示发布或先修掌握，不包含画像原始明细或凭据。
- GET learning-operations 与 GET learning-units 的准确版本响应新增 teaching_context 及 binding_status=bound/legacy_unverified。pending 操作可告知已选节点，但不提供未发布正文。已发布页面同时展示“目标、路径建议、本节教学”；不同节点的提示不能只显示一个模糊标题。
- 页面 target 默认，提供清楚的“按路径推荐先学”选择；此选择发新模式、新请求，不在失败/恢复期间静默切换。刷新/迟到响应按原generation/owner/版本保护。目录页面保持原行为。

错误：选择条件不足为 TEACHING_SELECTION_UNAVAILABLE（422/失败SSE）；任何已确定上下文/节点不一致为 TEACHING_BINDING_MISMATCH（409，禁止发布/评分）；旧planned缺新可信绑定不能新增掌握度为 TEACHING_BINDING_UNVERIFIED（409）；幂等参数冲突沿IDEMPOTENCY_CONFLICT；目标歧义沿GOAL_CLARIFICATION_REQUIRED。所有错误均不自动换主题、重跑、发布或推断旧数据已纠正。

## 4. 兼容和验证

无计划 legacy、目录课程、旧学习证据按原协议；旧 planned 已发布可读但标未核对，新评分按ADR0018 D保守处理。原已有提交同幂等键仍重放已有回执，不产生新证据；撤回资源仍遵守原资格检查。

T061先实现内部选择函数、PlanInputs及范围Prompt/输入并用Mock验证，不提前依赖尚未迁移的operation新列或声称完整DB保证；本节范围已绑定于输入快照。T062迁移后才将operation上下文与该输入快照强制相等并补齐完整保存/发布门禁；T063 评分证据与路径；T064 HTTP/OpenAPI/页面。内部入口需要提前接收模式以便T061验证，公开接口/页面由T064完整交付前不宣称产品完成。阶段中不开放dynamic或发真实调用，不用中间版本重新签旧课程。

必须覆盖正反例见冻结包 cases.json；隔离PG、请求捕获和浏览器行为分别记录，Mock不计真实模型质量。原错误r02保持原图谱节点、内容和待审结论，不能直接更新字段后当新通过。
