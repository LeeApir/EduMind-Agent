# MVP 0.3 课程目录版退出报告

> 2026-10-03 整理：下列本地材料路径沿用原仓库相对路径；读取及历史恢复方式见[材料索引](README.md)。旧指标、失败与判定不变。

结论：按PRD v2.2 §0及ADR-0007通过**课程目录版**阶段退出。T034直接依赖T032/T045/T046均done并有完成提交；全46项账本在本任务完成后为45 done、1 blocked。T033保持blocked，动态生成、重解释、实时AI互动及动态辩论暂缓，不宣称原动态MVP验收通过。不自动归档账本或启动Phase 1。

## 交付范围与来源

10节点、30正式资源、30固定题，C示例和确定性计分；首次完整作答形成掌握度证据，重做有反馈但不刷分。交付两个链表动画模板、持久化Job、学习控制、预设数组 vs 链表对比、进度/路径推荐和Markdown/MP4/SRT导出。目录核心流程无需Provider key，默认catalog_only在构造模型依赖前拒绝动态入口。

Lee已实际审阅并批准 `linear-course v0.1.0`，manifest digest `92bb0dd4778391e23aae978b8a411b466d8b5988d1cff61cff01654604af21a1`；[授权原文](mvp-0.3-catalog-human-signoff-20261003.json)、[独立批准记录](../../data/course_catalog/approvals/linear-course-v0.1.0.json)、[allowlist](../../data/course_catalog/release-allowlist.json)一致。确认登记时间2026-10-03T15:30:26+08:00，原审阅起止时间未知。待审核历史快照保留，实际签核及来源hash单独记录。仅隔离测试库核验登记/撤回，未向开发或生产数据库发布。

## 已完成提交与复用验收

| 依据 | 完成提交 | 证据与结论 |
| --- | --- | --- |
| T032模板/动画 | `39c8c2d` | [报告](mvp-0.3-t032-animation-performance.md)：模板100/100，缓存100/100，新渲染20/20；动态早期身份夹具，仅模板/基础能力证据 |
| T036–T044目录实现 | 各自完成提交 | 范围、可信来源、固定内容、单元、关闭动态、测验、预设、Web和导出；逐项完成标记及依赖由离线检查记录 |
| T045目录集成 | `05d5f87` | [工程报告](mvp-0.3-catalog-engineering-20261003.md)：真实PostgreSQL/Worker/Chromium核心旅程，10节点/30资源/30题及恢复/安全/导出，TEST_ONLY批准只验证工程 |
| T046实际签核 | `7944490` | [签核交接](mvp-0.3-catalog-signed-handoff-20261003.md)：真实Lee批准的版本、实际隔离PostgreSQL/HTTPS TestClient流程/撤回6项通过，生产不变 |

T045各项固定分母保留为独立组件，T046仅补实际人工来源，不将测试批准改成人工审核，也不合并旧模型质量成绩。

| 目录版独立指标 | 有效分母/结果 | P95 | 原门槛 |
| --- | --- | --- | --- |
| 模板质量矩阵 | 100/100；20种实际新渲染＋80审核缓存 | 不适用 | ≥98% |
| 10节点冷/暖首屏 | 20/20 | HTTP 0.107111s / 可读正文0.959118s | ≤2s / ≤10s |
| 缓存点击到可播放 | 100/100 | 0.1506s | ≤2s，逐槽≤2s |
| 独立新缓存Worker到播放 | 20/20 | 8.0897s | ≤90s |

原始质量v2（本地材料 `docs/acceptance/mvp-0.3-catalog-20261003-v2-quality.json`）、性能v4（本地材料 `docs/acceptance/mvp-0.3-catalog-20261003-v4-result.json`）、核心旅程v5（本地材料 `docs/acceptance/mvp-0.3-catalog-20261003-v5-core.json`）及各自冻结协议不变。实际签核v3结果（本地材料 `docs/acceptance/mvp-0.3-catalog-signed-v3-result-20261003.json`）证明批准版本的30资源来源摘要、计分/重做、预设恢复、两种真实缓存媒体导出、owner/CSRF和撤回拒绝；它不是新增浏览器/Worker/P95基准。

首次质量失败、测量器/身份/定位器错误、T046测试契约误判均保留在原批次与交接中；未覆盖失败、剔除槽或修改阈值。T045复用了公开的20种不同质量输入，不能表述为100种输入全部新渲染。旧T033漏检、截断和动态质量/P95阻塞不被目录版成绩解除。

## 本轮离线退出核验

`python3 scripts/verify_catalog_exit.py` 只读核验所有done任务的完成标记/提交内done状态与依赖、受信签核、T045固定分母/指标及代码hash、T046冻结代码/协议/结果hash、旧T033任务对象/证据/预算不变及文档引用。结果在退出检查（本地材料 `docs/acceptance/mvp-0.3-catalog-exit-checks-20261003.json`）；该证据在完成提交前保存，提交后另行只读确认T034完成标记。没有启动数据库、浏览器或Worker，没有重跑完整基准，没有Provider请求。

本轮 `cd backend && .venv/bin/python -m pytest -q tests/test_catalog_release_preflight.py tests/test_catalog_acceptance_metrics.py tests/test_catalog_component_gate.py` 为11 passed、无跳过；`backend/.venv/bin/ruff check scripts/verify_catalog_exit.py`、`python3 scripts/check_catalog_workflow.py`、`python3 scripts/verify_catalog_release.py`及文档/diff检查通过。退出核验已找到44个前置done任务的完成提交，235个旧文件保护hash不变。已有工程测试与签核复验细节见各原报告，不重新宣称旧跳过测试通过。Provider累计仍2033/2500，预算和付费授权不因阶段退出恢复。

## 文档、限制与后续边界

[README](../../README.md)、[部署说明](../DEPLOYMENT.md)及[ADR索引](../ADR/README.md)与目录行为同步：明确签核/allowlist/人工登记/撤回、独立宿主Worker、只读API媒体与成对备份。健康检查不证明课程登记，API不自动导入；目前没有在线管理后台或一键生产导入CLI，现有受信服务由获授权的部署操作者调用。

证据适用于本机单并发、固定镜像/Chromium和冻结工作树。冷首屏的API/DB进程仍热，HTTP是必需请求耗时之和；不能外推公网、高并发、全进程冷启动或教学首token目标。固定题完成与已掌握分开显示；暂无开放题、自由课程内容或实时AI。Compose是回环开发栈，公网HTTPS/容量/跨站点会话、数据留存、自动备份及跨主机灾备未验证或待决定。

工作树保留旧T033未提交代码与证据；本任务仅提交文档/治理/退出检查，不夹带这些改动。现有hash证据针对该冻结工作树，未替洁净checkout或部署镜像增加验收；未来部署前须固定并审查实际发布源码和环境，按风险补验证。当前没有部署、push或merge，完成本地T034提交后停止。任何动态能力恢复、付费验证、部署或Phase 1均需新的明确决定。
