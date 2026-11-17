# T111 审核与验收标准

每次独立审核只签准确候选或准确规划。审核者写明方法、材料、发现及影响。程序可检查身份、结构及绑定。事实语义和教学质量需要逐项判断。

## 规划审核

核对原目标与引文、先备自述、唯一例 C、两项教学目标、场景形式与顺序。逐项核对 `head`、`p`、`caller_head`、返回值和 NULL 判定来自同版代码。验收独立手算接收与忽略返回路径的差异。通过记录 `plan-review.json`，字段 `verdict=pass`、`plan_digest`、`planning_basis_binding`、`independent_evaluator`。需要澄清或无法通过则 STOP。

## 全文审核

- 全文与目标一致。解释头插保存旧首地址、返回新首地址、局部指针作用域、接收返回值才更新调用者入口。自述先备不能写成已测掌握。
- 逐帧从代码独立推导状态与行号。主演示 13 帧，两次分配成功，f02/f08 判空为假。说明掩码关闭及实际 malloc 失败均未演示，静态代码在 p 为 NULL 时返回旧 head。区分成功假设、分配器能力和程序投影，解释动态节点生命周期与清理边界。
- 接收结果为 `[9,-2,5]`。忽略对照入口仍为 i0，结果为 `[5]`，t0/t1 均不可达。用 `head_evidence_v1.discard_return_comparison` 支持忽略返回的段落。逐项核对引用支持陈述，区分展示帧、独立对照与代码语言语义。
- 逐题使用迁移代码独立推导答案。核对题干无泄漏、无带答案的格式示例、题目与解析匹配。检查全文、总结及演示替代文本语义一致。
- 修订后复评整课。逐个核对允许位置的原职责、原有必要解释、引用证据、近似复制邻段、全文一致性和不可改材料。任何阻断保留准确路径、原句、影响及证据。

首稿或恢复稿通过时写 `final-review.json`。若需修订，写 `repair-review.json`。两种记录均绑定 `candidate_digest`、`parent_digest`、`planning_basis_binding`、`evidence_digest` 和非空 `independent_evaluator`。修订审核用 `verdict=needs_revision`，须记录 `checks.full_lesson=true`，`blocking_findings` 与 `findings` 为同一份完整清单，1–8 项，每项包含唯一 `id`、`path`、`quote`、`issue`、`area`、`repairable=true` 和 `teaching_responsibility`。允许类别 `fact`、`citation`、`teaching_expression`。位置仅限 `["paragraphs",i]`、`["learning_summary"]`、`["failure_scope"]`。发现任何不能进入清单的阻断时保存 stop 审核，写 STOP。

最终审核用 `verdict=pass`、`blocking_findings=[]`。下列 `checks` 都须显式为 true：`full_lesson`、`fact_citations`、`paragraph_responsibilities`、`no_neighbour_copy`、`no_omitted_explanation`、`code_trace_answers`、`no_answer_hints`、`display_scope`、`return_contrast`、`whole_lesson_consistency`。经过一次修订仍有阻断时，保存复评和原件后 STOP。只有通过的最终记录可进入准入。

## 应用验收

用真实浏览器按原会话进入同一私有课程 v2。记录首稿结构、首次教学、格式恢复、模型修订、最终教学和应用验收。比对实际源标识、父稿、规划、材料、证据摘要与原件。逐帧比对 13 帧与可见状态／高亮，实际操作播放、暂停、前后步和重置。检查提交前公开场景无答案或解析，提交四题有效错答及正确答案，核对服务器反馈和绑定，验证刷新恢复同一版本、题组、反馈与输入且未重复提交。冻结范围出现改动时记录差异与失败，不在该批继续调用或用手改成果替代。
