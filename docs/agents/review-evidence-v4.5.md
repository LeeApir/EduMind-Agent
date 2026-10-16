# v4.5：证据强度与逐项引用

2026-10-16按用户批准实施。运行时版本evidence-resource-review-v4.5，常量与新增约束位于app.agents.review_evidence；hybrid_resource_review.INSTRUCTION保留v4.4全部原规则并追加通用约束。learning_policy直接引用同一版本常量，政策摘要随版本变化。原提案和原模型响应作为历史原件保留；当前指令已移除“答案字段F”例子，具体a15/F仅用于回归材料，不作为运行时特殊规则。

引用规则：引用只能支持实际锚定内容所包含的命题，不能借用邻近字段；推导结论须来自引用的前提，不能把计算结果说成某字段原文。按每条finding、condition_or_counterexample与impact的每个断言、每个引用逐项检查，主引用有效不能抵消无关辅助引用。仍仅使用服务端锚点ID/元数据，不计算或编造摘要/偏移，不输出额外证据映射或思考过程。

结论规则：区分确定错误、无法保证和证据不足；无法保证P不推出非P。UB不支持确定数值/必定不等于某值/必崩溃；已证实严重可达安全错误仍须拒绝，不能因运行结果未知全部转人工。

结果Schema仍resource-review-v4，输入仍authoritative-review-input-v1，unit五个check ID、finding类别/严重度、允许verdict和unresolved字符串数组均不变。服务端结构/引用成员检查不会自动证明自然语言蕴含或引用语义；此次没有添加关键词评分器、自动重写旧响应或额外模型judge。Prompt修改的真实效果尚需独立诊断，不凭版本或离线测试宣称有效。

失效：当前服务已将plan.policy_digest与active_policy_digest比较，人工决定和发布前均复核。旧v4.4待审案例遇新摘要会invalidated、操作failed，不能继续批准；旧记录保留、不会自动迁移成新审核或修改已发表目录内容。新增真实隔离PG回归用原v4.4 Prompt/政策创建待审，再切回v4.5验证拒绝决定且没有生成批准记录。没有新增schema迁移。

固定诊断档low/8192总输出/60秒将在新包明确绑定；业务普通请求原有上限未由本次偷偷改变。旧review-remaining-r01仍3/5 ADMISSION_FAILED，后2未发；新包须独立冻结源码/目标/请求/执行器/预算，准确批准后逐条核对完整性、全部断言和全部引用，任何一项失败停。小型诊断通过后才复核T040正式验收准入；不直接开放dynamic，catalog_only保持。

指令正文镜像：prompts/evidence-resource-review-v4.5.txt，与运行常量由测试逐字核对。原a15/F及UB负例见既有evidence-repair-proposal-r01/regression-cases.json，原件不改。
