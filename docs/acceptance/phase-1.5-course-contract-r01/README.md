# T001 契约提案与交接

状态：设计已准备，等待具体批准；不是实现验收、不是Task-Completed。

## 审批入口

请阅读[ADR-0024](../../ADR/0024-free-course-identity-and-owner-access.md)的A—D。推荐采用独立新表、新版本清单、owner私有草稿访问和独立API；[契约](contract.md)、[OpenAPI](../../api/phase-1.5-free-course.openapi.json)及[25条正负例](examples.json)是规范附件，[manifest](manifest.json)绑定准确字节。当前没有批准登记，不假定“开始开发”批准尚未呈现的具体方案。

主要影响：旧签核和旧失败原样保留；新课程可无节点；首场景先学、整课以清单逐步追加；无公开分享；有数据的数据库回退保留新表，不能直接drop。T002/T003的状态、预算、修订及评分资格仍须另行细化。

## 实际验证

- 命令：`backend/.venv/bin/python docs/acceptance/phase-1.5-course-contract-r01/check_design.py`。
- 命令：`python3 scripts/check_catalog_workflow.py`。
- 命令：`git diff --check`。
- 结果见[verification.txt](verification.txt)。离线检查覆盖本地引用、JSON Schema结构、6个planned操作、请求结构正负例、25条设计用例、链接及冻结摘要；不验证运行中的路由、PG约束、Provider、权限执行或模型质量。空白目标的语义拒绝、跨表约束等是后续实现验收项，不能用本检查代替。

按doc-coauthoring进行独立只读读者审查，七项问题（无节点、reject与硬门、guest/owner、历史禁用、旧失败、新旧兼容与回退、T002/T003边界）均可准确回答。审查发现“不可用错误响应返回受影响ID”与OpenAPI封套冲突，已统一为仅固定原因、ID由请求路径绑定，并与现有main.py错误封套对齐retryable:false。该审查不代替用户契约批准。

## 后续恢复

仅T001已获本次执行授权；具体契约待批准，T001保持blocked。收到针对准确manifest的A—D批准后，登记来源并重核摘要、追加RESUME、完成验收与Task-Completed提交；不得冒充已批准提前实现或领取T002。下一任务是T002，但须用户执行授权及依赖满足。

本轮Provider调用0，实际仍catalog_only；H与旧归档账本不改。用户已有旧验收报告改动、OpenMAIC参考目录未纳入本任务提交。交付仅本地设计治理提交，无push/merge/部署。
