# T003 质量处理与学习证据契约提案

状态：用户已批准ADR-0026 A—E及准确附件，T003设计验收完成；未实施业务接口、迁移或真实评分。

## 审批入口与取舍

[ADR-0026](../../ADR/0026-course-quality-and-learning-evidence.md)列出五项具体决定；[contract](contract.md)说明确认、暂停/撤回、准入与重放，[policy](policy.json)记录规则，[OpenAPI](../../api/phase-1.5-quality.openapi.json)提供6个planned反馈/作答/导师接口及内部维护结构，[44条用例](examples.json)描述后续实现验收预期。[manifest](manifest.json)绑定6份规范文件；用户随后回复“批准”，[批准登记](../../ADR/0026-approval-20261022.json)绑定准确提案提交及摘要。冻结文件中Proposed/pending保持批准前原字节，当前接受状态以登记为准。T001/T002冻结文件保持原字节。

学生仍可直接学习草稿、做题并获得暂定比较；仅正式掌握度贡献要求准确答案和单节点核定发生在首次完整作答前，且没有已记录辅助或重复。首版核定由可信本地维护者完成，不以模型pass冒充真值，也不建立全量审核前置。缺核定/映射、多节点或历史独立性未知时只保存课程表现。

确认错误或替换题目/答案/映射/必要依赖时，原始作答保留，受影响贡献撤销后按有效历史重放；不以新题答案评价旧题。旧写路径也必须使用来源分派，不能重新算回已撤销的新证据。新导师每轮1次/90s，共享T002课程40次池；生成活动期间不并行启动导师，提示等待或主动停止，不自动取消生成。导师请求会记录所用上下文题组的辅助状态，包括尚未开始作答的题组。

## 实际检查与边界

命令：

- `backend/.venv/bin/python docs/acceptance/phase-1.5-quality-contract-r01/check_design.py`
- `backend/.venv/bin/python docs/acceptance/phase-1.5-course-contract-r01/check_design.py`
- `backend/.venv/bin/python docs/acceptance/phase-1.5-generation-contract-r01/check_design.py`
- `python3 scripts/check_catalog_workflow.py`
- `git diff --check`

[verification.txt](verification.txt)记录结果。设计检查覆盖OpenAPI结构/引用、schema与公开投影正负例、共享预算一致性、设计用例完整性、链接与摘要；未运行数据库事务/撤销重放、真实HTTP/Provider或浏览器，不等同实现和学习效果通过。

按doc-coauthoring技能进行独立只读读者审查。中断前审查结果未作为证据使用，恢复后重新审查；发现并修复两处遗漏：已ready导师回复在源内容禁用后必须撤回公共正文；旧目录缺stem列时须按原始准确题干计算去重，原件缺失不能猜测首次资格。另自查补齐未开始作答的帮助标记、题干摘要防修答案重置、历史清单只读、幂等回执仅返ID、未知证据来源默认拒绝及旧写路径重放分派。所有这些都是待实现契约，未伪报运行验证。

## 恢复与交接

T003准确A—E已批准，来源与提案摘要已登记，已追加RESUME并重核冻结文件；完成设计验收与独立Task-Completed提交后done。下一项T004为全站主要页面设计，尚未领取；不把本提案当成后续执行授权。

当前分支codex/phase-1.5-t001，用户旧验收报告修改与OpenMAIC参考目录保留且不纳入本任务提交。catalog_only/H封存/Provider实际调用0保持；无生产开放、部署、push或merge。
