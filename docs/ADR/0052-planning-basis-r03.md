# ADR0052 补充：T108 同版示例依据与规划职责 r03

2026-11-04。状态：本轮限定零调用准备已获范围授权；新准确包交评估，真实批次另行批准。原r01/r02批准、停止、模型原稿和失败不改。[r02独立规划失败](../acceptance/phase-1.5-head-goal-live-r02/PLAN-ASSESSMENT.md)是本次输入缺口的依据，不能事后修成pass。

## 集中差异

1. **规划输入增加程序依据。** 保持已验证的 `head-goal-planning-wire-v2` 输出Schema和原local v1完整校验/转换不变。规划Prompt单独版本化为 `head-goal-plan-grounded-v3`；请求增加 `planning_example_basis`，版本 `head-planning-example-basis-v1`。两个原支持候选各含准确函数接口/函数体、变量声明和作用域、关键代码行、接收/忽略返回值的逐次状态与最终差异，以及engine/template/spec/code/materials摘要。资料来自既有引擎，不新增模型调用、C执行或第三个示例。
2. **职责明确。** 模型仍生成真实学习目标、候选选择、教学顺序和场景purpose，不使用程序大纲。若目标/约定/purpose提及算法步骤、变量或结果，必须服从所选程序依据；不另造实现、局部head赋值或不准确结果。程序提供事实/代码/轨迹/答案，模型负责规划及全部教学自然语言，独立评估者核对语义，资料存在不能自动判pass。
3. **材料对应关系。** 规划mapping增加planning_prompt_version和planning_basis_digest；规划结果仍存local v1，已有prompt_version字段记录新Prompt，请求摘要覆盖完整依据。正文输入增加所选 `planning_basis`（binding和evidence），修复保留在original_input中；两者继续采用原head-goal-course-v1教学Schema和原教学/修复Prompt。候选摘要覆盖新增输入，不能复用旧候选。原代码/轨迹/答案的materials_digest保持。
4. **评估绑定。** 规划pass及最终正文pass必须附 `planning_basis_binding`，准确匹配version、basis_digest、selected_example、example_basis_digest、materials_digest。缺失/错版拒绝，不接受仅有plan/candidate摘要的旧意见。generation_context同时检查规划新Prompt及准确请求摘要，防止把未携带新依据的旧规划当作新规划继续。没有新增公开API字段、教学输出字段或数据库迁移；新增字段均在原私有JSON/本批评估记录中。
5. **新执行提案。** 新包r03、新manifest和 `accept_ADR0052_R03_and_batch_C2`、planning_prompt_version、planning_wire_version另批；旧余额、Key、窗口和C2不继承。本轮真实调用0。将来仍最多3HTTP/600秒（规划1/正文1/有条件普通措辞修复1），不修规划，不探测/重试/回退；语义/协议/事实/答案/安全/unknown问题按包停。简化规划若再遭接口拒绝，保留准确错误并交用户决定Provider路线，不追加字段补丁。

范围仅为现有头插候选A/B。固定模板检查与独立闭式期望核对用于拒绝资料不一致，不构成通用C解析器、执行器或自然语言事实验证器。既有单前台尽力停止、可能迟发/继续计费、本机原件无独立抗回滚保障、金额无可验证硬上限均不改变；真实执行前仍须本批接受C2。

准确请求、来源映射和检查见 [r03准备包](../acceptance/phase-1.5-head-goal-t108-r03/README.md)。最终验收仍是实际应用内新完整私有课程及完整学习/刷新/独立教学评估；本准备不完成T108，不恢复T102，不启动T038或扩主题。
