# MVP 0.3归档与Phase 1任务切换

2026-10-03用户明确选择“还是继续Phase 1 功能开发”，本次完成原样归档及新阶段任务细化，不领取功能任务。

## 归档与范围

源提交：`30fcd4e1f9384359a72b451bb40243a2095691cf`。其根`task.json`逐字节复制到[归档](../tasks/mvp-0.3.json)，SHA256为`0edbd007af6313235f94caaa536b8d60c4084f1472cfdaee9e0a2a41c3791a4f`。46项任务保留45 done与T033 blocked，全部历史结果、阻塞原因和预算说明原样保留。

[活动账本](../../task.json)为42项Phase 1任务，初始全部todo，无started_at/completed_at或验证通过记录。每项包含依赖、范围、2–5条验收条件、待实施的验证接口及完成提交标记。

| 任务 | 结果范围 |
|---|---|
| T001 | 范围、验收、预算规则 |
| T002–T017 | Provider安全/API/BYOK、兼容与Ollama、连接与四档设置、三类原生适配 |
| T018–T021 | 队列ADR、可靠投递、Worker恢复、取消与SSE |
| T022–T029 | DSL安全契约、校验、编译、审核、生成降级、隔离渲染与界面 |
| T030–T034 | 约30节点、按需图查询后端、路径与可用性展示 |
| T035–T041 | 独立动态门禁、队列/DSL/目录回归、另行授权的真实接入/质量/性能 |
| T042 | 阶段退出及交接 |

任务前缀均为`PHASE-1-`。阶段范围以[PRD v2.3 §0.1](../PRD.md)及§9.1为准。Neo4j按实际需求决定；新重大API/数据/安全决定须通过相应设计任务，不能把本次规划视为新ADR已获批准。部署与试用、真并行辩论/RAG/学习报告及额外语音/多模态产品入口未纳入本次范围。

目录模式仍为已交付基线。新动态配置须独立验收，不能修改旧T033或使用目录成绩替代模型质量；历史2033/2500不自动转为新阶段付费额度。本次Provider新增0。

## 兼容性维护

`check_catalog_workflow.py`核验活动阶段依赖并从归档读取MVP 0.3约束；`verify_legacy_archives.py`在阶段切换后对比归档与原Git账本。没有归档或归档被改分时仍失败关闭。原冻结工作树审计器`verify_catalog_exit.py`保持历史用途，不因任务切换重新运行旧实验。

## 实际验证

- `cd backend && .venv/bin/python -m pytest -q tests/test_legacy_archives.py`：7 passed；包括新阶段归档读取、归档篡改拒绝和缺失归档拒绝。
- `backend/.venv/bin/ruff check scripts/check_catalog_workflow.py scripts/verify_legacy_archives.py backend/tests/test_legacy_archives.py`：通过。
- `python3 scripts/check_catalog_workflow.py`：活动Phase 1依赖与MVP 0.3目录范围通过，T033 blocked。
- `python3 scripts/verify_legacy_archives.py`：236原件、64实验代码和169证据Git归档核验通过。
- 内联Python对比`git show 30fcd4e:task.json`和新归档原始字节：完全相同；42唯一ID、全部todo、无环/无悬空依赖、退出任务覆盖全部42项、首项唯一可领取、2–5验收条件及本轮改动文档本地链接检查通过。
- `git diff --check`：通过。未启动数据库、Worker、浏览器或真实Provider测试。

## 交接

归档、根账本、PRD/AGENTS/README/ADR索引、校验兼容和日志一起创建治理提交。下一任务为`PHASE-1-T001`，本轮没有领取或完成Phase 1业务任务，不写伪造的Task-Completed标记。新测试文件路径属于计划接口，须在相应任务完成前建立并执行。未push、merge或部署。
