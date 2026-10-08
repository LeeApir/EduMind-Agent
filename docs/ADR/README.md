# 架构决定索引

本索引汇总已有批准记录，不新增批准。产品范围以 [PRD](../PRD.md) 为准；现行接口见 [OpenAPI](../api/openapi.yaml)，实现与限制摘要见 [架构说明](../ARCHITECTURE.md)。

| ADR | 当前状态 | 已确定内容 | 仍待决定 |
| --- | --- | --- | --- |
| [0001：匿名身份与持久化](0001-anonymous-identity-and-persistence-boundary.md) | 部分批准 | HttpOnly Cookie + CSRF；P0 同源及既定会话边界 | 匿名数据留存/删除、P0 以外会话策略、账户合并、跨站点部署 |
| [0002：流式首屏与正式资源](0002-streaming-first-screen-and-resource-review.md) | 部分批准，未整体 Accepted | PRD 正式资源审核门禁；MVP 0.2-T030 最小恢复语义；后续计时口径与收尾决定 | 审核拒绝/不可用时临时内容呈现、事件保留与重放、取消成本/时限；同操作重启与可靠中断识别未获该有限批准 |
| [0003：学习证据、掌握度与路径版本](0003-learning-evidence-mastery-and-path-versioning.md) | Accepted（MVP 0.2） | 只追加证据、确定性评分、画像/路径版本、事务与并发边界 | 文档未列待审批项；新增行为如改变这些边界需后续 ADR |

## MVP 0.3 设计记录

[ADR-0004：可信动画 Job](0004-trusted-animation-jobs.md) 已获用户批准 A–D，状态 Accepted；容器资源限制、租约/取消/重启、缓存授权及事件游标成为 T004 与后续实现边界。T001 验收基线见 [范围与测量计划](../acceptance/mvp-0.3-acceptance-plan.md)，已完成并不授予真实采样预算。

[ADR-0005：课堂会话与场景版本](0005-classroom-session-and-scene-version.md) 已获用户批准 A–D，状态 Accepted；MVP 0.3已实现持久化课堂/控制与版本边界。目录模式只开放批准课程的学习控制和预设演示，动态互动仍关闭。

[ADR-0007：课程目录版](0007-curated-course-catalog.md) 为当前已批准交付范围：10节点、固定C示例/练习、两个动画模板、进度推荐及导出，新增受信人工签核来源和撤回边界。Lee已实际签核linear-course v0.1.0的准确digest，见[签核记录](../acceptance/mvp-0.3-catalog-human-signoff-20261003.json)。[目录版退出报告](../acceptance/mvp-0.3-catalog-exit-20261003.md)复用T045/T046独立证据；T033仍blocked，动态生成/重解释/实时AI暂缓。此退出不批准部署或Phase 1。

## 性能与历史证据

[收尾决定](../acceptance/mvp-0.2-closeout-decision.md) 保留 HTTP 首字节与完整首段的 PRD 目标，将独立教学首 token≤2 秒转为非阻塞优化。原失败结果不变；Pro 质量/闭环和 Flash 性能不能合并为同一配置全项通过。

历史验收报告中的“当前”“下一步”只描述记录时点。活动阶段与任务状态读取根目录 [task.json](../../task.json)；[阶段归档](../tasks/README.md) 只读，执行日志只追加。

## MVP 0.3 后续入口

- T001：冻结范围、验收映射、测量方式和预算。
- T002：制定可信模板渲染与持久化 Job 安全边界。
- T003：制定课堂会话、场景版本及学习控制边界；明确暂停、跳过、资源选择和旧版本恢复的后端职责。
- T004：在相关决定批准后固定 API/SSE 契约，包括 Job 事件重放。

上列T001–T004为历史设计入口，当前均已完成，接口以[OpenAPI](../api/openapi.yaml)及活动任务账本为准。Markdown导出不要求学生先运行多视角；目录版仅记录已查看的预设演示。

## Phase 1 规划入口

2026-10-03用户选择Phase 1功能开发，并授权原样归档MVP 0.3及替换根账本，见[PRD §0.1](../PRD.md)。42项计划任务从`PHASE-1-T001`开始；T002/003确定Provider身份、凭据与API，T018确定队列迁移边界，T022确定DSL安全契约，T030确定扩展图谱与按需存储选型，T035确定动态恢复与独立验收门禁。T001范围与验收规则见[Phase 1验收计划](../acceptance/phase-1-acceptance-plan.md)；相关设计任务状态以活动账本为准，新ADR尚未批准，不将阶段选择或T001完成等同于架构批准。

历史ADR-0007及T033失败记录保留，目录基线不会因任务切换自动开放动态模型入口。部署、付费验证和后续阶段分别按明确授权执行。

## Phase 1决定

[ADR-0010：受约束动画DSL、审核与来源隔离](0010-constrained-animation-dsl.md)为PHASE-1-T022的Accepted方案，用户于2026-10-04批准A–D及准确附件，见[批准登记](0010-dsl-approval-20261004.json)：九动作/资源上限、独立审核/固定编译/沙箱、owner私有DSL缓存/撤回、有界API生成与无凭据队列及模板降级。未实施DSL或开放动态入口。

[ADR-0009：持久化动画队列、恢复与迁移](0009-durable-animation-queue.md)为PHASE-1-T018的Accepted方案，用户于2026-10-04批准A–D，提案digest及原话见[批准登记](0009-queue-approval-20261004.json)：PG唯一状态源/最小消息、事务outbox与Redis丢失恢复、Worker租约/取消/媒体发布、增量切换与回滚。尚未实施Redis/Celery，后续按T019–T021验证；批准不授予真实Provider预算或部署。

[ADR-0008：Provider身份、凭据与出站数据边界](0008-provider-credentials-and-egress-boundary.md)为PHASE-1-T002的Accepted方案，用户于2026-10-04明确批准A–D，具体提案digest及原话见[批准登记](0008-provider-approval-20261004.json)。批准2h匿名凭据留存、加密轮换、临时Key与发送/回退边界；按T002至T005批次实现，实际Provider调用仍须独立授权。

[ADR-0011：独立动态验收](0011-independent-dynamic-acceptance.md) 为 T035 待批准提案。固定历史/新例、分组准入、预算计数器及测试开放边界；设计批准不等于调用授权或正式开放。
