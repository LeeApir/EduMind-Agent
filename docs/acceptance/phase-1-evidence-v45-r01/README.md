# v4.5独立四例诊断包（零调用冻结）

实施基线fdce381。固定deepseek-flash/low/8192总输出（含思考）/60秒/温度0.0。学生envelope、原目标快照、共享计划、参考材料及输出Schema均保留原文；仅切换到已实施v4.5 Prompt/政策及相应身份、依赖摘要绑定，不把旧政策材料伪装为新结果。旧3/5 ADMISSION_FAILED不恢复，旧2槽预算不复用。

顺序与判据：
1. reachable-safety：先验证原越界过强断言；必须具体检出长度3访问a[4]并保留严重code_safety/reject。检查所有附带finding、counterexample及impact；不得由UB推出固定返回数值、必不等于某数或必崩溃。代码/步骤矛盾可以具体检出，但不能捏造新错误。
2. fact-contradiction：保留18与实际16的具体fact拒绝；逐项查全部引用，原a15/F不支持数值16，不能靠有效a1抵消辅助偏差。允许引用真实代码及错误声明的对应片段，不按ID硬编码封禁。
3. gap-and-safety：教学缺口与越界并存，严重安全拒绝不能全部降为待人工；其他缺口和全部断言/引用均须准确。
4. trace-complete：完整正确对照应pass，五check齐全，findings/unchecked/unresolved空，无附带误报。

每条三项同时核对：完整性、全部断言（包括每条finding与impact，不能只看主缺陷）、全部引用（包括辅助锚点，不能只查ID成员资格）。任一失败即停止并持久halt，保留原回答和失败原因，不删除字段/改写结论后冒充通过。自动类别/路由门禁不等于语义质量；服务端仍没有一般自然语言蕴含证明器。

逐条执行。下一槽必须有实际proposal/receipt摘要绑定的Lee确认，且completeness_checked/all_assertions_checked/all_citations_checked全部true、issues=[]；这些是本地诊断确认字段，不改变Provider输出Schema。任何未解决问题不能签continue；不得由模型结果预签人工记录。最后一条也要独立签核才视为小型诊断完成，随后仅进行T040正式验收准入复核；正式调用和预算不在本包授权范围。

准确最多4请求、9.010508元保守预留，每槽1次，费用由proposal/token-cost-proof冻结。无重试/修正/回退/额外探测，首败不退回额度重用。新私有账本/批准/标签独立，原始失败与确认均保留，不自动开放dynamic，catalog_only保持。

准备：backend/.venv/bin/python scripts/prepare_evidence_v45.py --write。执行：backend/.venv/bin/python scripts/run_evidence_v45.py --run-one。当前真实批准/标签/账本均未创建，Provider0。原模型历史问题回归材料位于evidence-repair-proposal-r01/regression-cases.json；不改历史分数。
