# 分层审核输入与政策契约 v1（待批准）

依据 [ADR-0017](../ADR/0017-layered-review-responsibilities.md)。本文件是 T056 提案，不是当前运行行为。

## 1. 服务端输入结构

沿现有 `review_input` 构造完整 `authoritative_teaching_goal`、`reference_context`、原始 `plan/candidate` 或完整 `unit`、`student_delivery`、`anchor_catalog`、`mandatory_checks`。原始用户全文、实际内容、目标 ID/原文与全部计划场景不能裁剪。职责结构在这些数据之后由服务端覆盖写入，候选中同名键不被提升为可信规则。

新增可信 `review_responsibilities`，其字段固定如下：

| 字段 | 类型/来源 | 含义 |
| --- | --- | --- |
| version | string，按实施阶段表 | 不由候选提供 |
| scope | resource / unit，服务端调用参数 | 和结果 scope 一致 |
| resource_role | explanation / code / exercise / null | resource 时必须恰好一个已验证候选；unit 为 null |
| scene_commitments | array，原 plan.scenes 精确副本 | 含 role/scene_key/objective_ids/depends_on；不增删原承诺 |
| assigned_objectives | array，resource 对应场景 objective_ids 的完整 id/text；unit 全部目标 | 分工贡献不是已完成证明；共享 ID 不要求各场景全文重复 |
| role_responsibilities | string[]，服务端静态角色规则 | 讲解/代码/练习分别按 ADR-0017 A；unit 为完整交付与一致性规则 |
| unit_verification_obligations | string[]，服务端固定规则 | 原始需求与计划完整覆盖、跨载体支持及时序、过程测量、跨场景一致性、媒体实际交付；不填当前推定缺口 |
| sibling_content_supplied | boolean，按实际传入已验证候选计算 | resource 为 false，unit 只有完整三资源时才为 true；不是兄弟正确性结论 |
| assignment_is_delivery_evidence | const false | 内部计划分工不能证明交付 |

构造前复核 scope、候选数量和 role、候选 payload 与实际对象相等、计划 digest、scene role/目标引用及 input digest。unit 必须完整三角色且符合依赖/动作绑定。缺角色、伪造 assignment、跨摘要拼接在发请求前以 `REVIEW_RESPONSIBILITY_BINDING_MISMATCH` 拒绝，零模型发送；不猜默认讲解角色。既有字段错误继续沿原门禁。

输入角色元数据与整单元资格是不同问题：资源请求没有兄弟正文时，不证明兄弟缺失也不证明兄弟交付。模型需要兄弟真实内容才能判断某个本资源具体主张时，列清实际依赖，而不是把所有整课职责复制进 unresolved。

## 2. 学情上下文

T058 新增 `learner_review_context`：`version=learner-evidence-review-v1`、`evidence`（从绑定 input_snapshot / 完整已核验参考中取得的 learner_evidence 原样副本）、`source`（说明实际载体路径）、`self_report_is_mastery=false`、`unknown_alone_blocks_publication=false`、`unsupported_personalization_requires_resolution=true`。

空 evidence 仍原样为空，不创造“已掌握”“困难”“偏好”。用户自述原句仍在 authoritative_teaching_goal.user_request，不能当独立测验；发生冲突时保留两边来源，不通过选一个来源静默覆盖。任何新源字段须验证它属于当前已绑定快照；候选或未绑定客户端字段不能当学情证据。

此结构是审核规则与证据载体，不是学情分类器，不自行判断自然语言是否个性化或课程是否合适。具体语义判断由审核承担，离线不能以预置答案宣称真实模型会遵守。

## 3. 必检项的明确含义

| scope | ID | 必检内容 |
| --- | --- | --- |
| resource | facts | 本资源实际全部事实、术语和算法主张；证据强度/每条主辅引用规则保持 v4.5 |
| resource | code_safety | 实际片段/程序/安全主张的可达错误、失败路径、调用者所有权；适用于讲解和练习中的代码 |
| resource | learner_fit | 有据约束一致、无无据掌握度/困难/偏好归因；不是证明个性化效果；未知按 ADR-0017 B |
| resource | objectives | 自身明确承诺和分工贡献，检查计划是否缺漏用户要求但不假定兄弟缺失；整课待核验职责不等于自己的真实缺口 |
| resource | reference_scope | 正确使用已绑定参考，不虚构支持；图谱背景不是额外课程目标，原始需求不被窄计划替换 |
| unit | terminology | 三资源全部术语、接口语义和归属一致；一致地说错仍是事实缺陷 |
| unit | conventions | 下标、容量、所有权、返回/更新接口与表示约定一致且实际正确 |
| unit | example_trace | 共享示例的输入、状态、退出条件与实际程序一致；计划不是演算真值 |
| unit | answer_consistency | 题干、答案、解析与实际代码/讲解一致；不代替过程测量检查 |
| unit | action_references | 动作准确引用同一版本资源/锚点，动作本身不算教学正文 |
| unit | objectives（新增） | 原始请求＋所有显式承诺的完整学生可见覆盖；分别检查实现、过程教学、过程测量及明确时序/媒体交付 |

`checked` 仅使用该 scope 的精确 ID。资源保留五个；T059 起 unit 必须六个。未做或无法完成留 unchecked/unresolved，并按原本地路由处理；六个 ID 都出现不保证判断正确。纯覆盖缺口仅 needs_human/unresolved，真实严重缺陷仍单独 reject 并保留混合缺口。结果字段和 finding 类别不扩展。

## 4. 各实施任务的版本与政策

| 任务 | Prompt | review_input | review_scope | review_responsibilities | review_coverage | learner_review |
| --- | --- | --- | --- | --- | --- | --- |
| 当前基线（未改） | evidence-resource-review-v4.5 | authoritative-review-input-v1 | goal-bound-review-scope-v2 | 无 | fixed-check-ids-v1 | 无独立规则键 |
| T057 完成后 | evidence-resource-review-v4.6 | authoritative-review-input-v2 | role-bound-review-scope-v3 | review-responsibilities-v1 | fixed-check-ids-v1 | 无独立规则键 |
| T058 完成后 | evidence-resource-review-v4.7 | authoritative-review-input-v3 | role-learner-review-scope-v4 | review-responsibilities-v1 | fixed-check-ids-v1 | learner-evidence-review-v1 |
| T059 完成后 | evidence-resource-review-v4.8 | authoritative-review-input-v3 | layered-review-scope-v5 | review-responsibilities-v1 | fixed-check-ids-v2 | learner-evidence-review-v1 |

各新常量进入 POLICY 摘要并有实际请求捕获断言，不只改文件名。政策结构名 hybrid-review-v1、result resource-review-v4、覆盖标准 student-visible-goal-coverage-v1、plan learning-plan-v1、actions teaching-actions-v1 不改。保存 v4.5 的强度与逐项引用规则；每版镜像与运行指令一致测试，不能用保留旧镜像而运行未版本化附加指令绕过绑定。

T057/T058 是串行可验证行为，不声称已完成最终 unit 六项检查。每次政策换版都验证旧摘要不能获新批准/发布；T059 验证最终组合、已发布准确历史读取、取消/撤回和原子发布竞争。旧案件及旧快照不原地迁移，停止包不能重冻成新成功。

## 5. 验收与实施批准范围

正反例精确列在[对照材料](../acceptance/phase-1-layered-review-design-r01/cases.json)。标签为设计预期，除引用既有用户明确裁定外均不是人类语义签核或模型实测。

T057 捕获实际新请求/完整原文和 Schema、scope/role/目标绑定失败、资源职责与真实错误反例；T058 配对未知学情/自述/冲突/无据个性化与真实依赖；T059 验证 unit 六 ID、完整内容/动作、独立审核及资源未决/严重拒绝优先，并在隔离 PG 验证版本与发布。

本次批准不涉及目标/路径/教学节点的选择或历史错绑修复，不涉及 C 执行器、通用沙箱、Provider 真实请求或动态开放。那些选择分别由 T060、T065 和后续真实验收独立审查。
