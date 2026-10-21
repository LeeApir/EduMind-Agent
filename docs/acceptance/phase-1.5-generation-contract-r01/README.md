# T002 渐进生成契约提案与交接

状态：用户已批准ADR-0025 A—E及准确附件，T002设计验收完成；不是调度/API实现或运行质量验收。

## 决定与准确附件

[ADR-0025](../../ADR/0025-progressive-course-generation.md)解释五项决定；[contract](contract.md)为执行规范，[policy](policy.json)冻结状态和数值，[OpenAPI补充](../../api/phase-1.5-generation.openapi.json)提供5个操作/影响预览接口及1个T001场景投影扩展，[34条用例](examples.json)覆盖主要边界。[manifest](manifest.json)绑定6份准确文件，用户随后回复“批准”，[批准登记](../../ADR/0025-approval-20261021.json)绑定准确提案提交及摘要；冻结文件中的Proposed/pending保持批准前原字节，当前状态以批准登记为准。T001批准附件原字节不改。

建议重点确认：1–8场景；单操作13次尝试/600秒；课程累计40次；token与并发上限；未知发送保留预算和隔离槽直至可信结算；普通修订整体就绪才切head。请求次数上限不是实际Provider预算或费用批准。本轮真实请求0。

## 实际核对

- `backend/.venv/bin/python docs/acceptance/phase-1.5-generation-contract-r01/check_design.py`
- `backend/.venv/bin/python docs/acceptance/phase-1.5-course-contract-r01/check_design.py`
- `python3 scripts/check_catalog_workflow.py`
- `git diff --check`

[verification.txt](verification.txt)记录实际结果。本检查只验证OpenAPI结构、schema/引用、预算代数、状态可达与终态、请求/事件/正文正负例、文档用例、链接及摘要；不模拟PG锁、真实Provider、HTTP服务或浏览器，不能据此宣称调度和质量已通过。

初OpenAPI结构检查因当前FastAPI工具不接受3.1 type数组报错，已用语义等价anyOf表达可空字段，保持完整JSON Schema校验，未删除检查。独立读者指出网关错误不证明远端终止、无instruction的预览不能理解意图、正文schema允许空/纯代码三项矛盾，已修复并扩展负例。根代理另补未知结果槽隔离、事件条件字段与现有错误封套；尚未运行并发和故障注入，留待实现任务。

## 审批后的恢复

T002准确A—E已批准、来源已登记，已追加RESUME并重核冻结文件，完成设计验收与独立Task-Completed提交后done。下一项为T003，按用户执行授权和依赖继续；不自动将本提案当作T003评分/缺陷确认批准。

分支复用codex/phase-1.5-t001。用户旧验收报告修改和OpenMAIC参考目录保持，不纳入本任务提交。运行仍catalog_only、H封存，无真实调用、部署、push或merge。
