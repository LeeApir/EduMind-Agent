# 架构决定索引

本索引汇总已有批准记录，不新增批准。产品范围以 [PRD](../PRD.md) 为准；现行接口见 [OpenAPI](../api/openapi.yaml)，实现与限制摘要见 [架构说明](../ARCHITECTURE.md)。

| ADR | 当前状态 | 已确定内容 | 仍待决定 |
| --- | --- | --- | --- |
| [0001：匿名身份与持久化](0001-anonymous-identity-and-persistence-boundary.md) | 部分批准 | HttpOnly Cookie + CSRF；P0 同源及既定会话边界 | 匿名数据留存/删除、P0 以外会话策略、账户合并、跨站点部署 |
| [0002：流式首屏与正式资源](0002-streaming-first-screen-and-resource-review.md) | 部分批准，未整体 Accepted | PRD 正式资源审核门禁；MVP 0.2-T030 最小恢复语义；后续计时口径与收尾决定 | 审核拒绝/不可用时临时内容呈现、事件保留与重放、取消成本/时限；同操作重启与可靠中断识别未获该有限批准 |
| [0003：学习证据、掌握度与路径版本](0003-learning-evidence-mastery-and-path-versioning.md) | Accepted（MVP 0.2） | 只追加证据、确定性评分、画像/路径版本、事务与并发边界 | 文档未列待审批项；新增行为如改变这些边界需后续 ADR |

## MVP 0.3 设计记录

[ADR-0004：可信动画 Job](0004-trusted-animation-jobs.md) 已获用户批准 A–D，状态 Accepted；容器资源限制、租约/取消/重启、缓存授权及事件游标成为 T004 与后续实现边界。T001 验收基线见 [范围与测量计划](../acceptance/mvp-0.3-acceptance-plan.md)，已完成并不授予真实采样预算。

[ADR-0005：课堂会话与场景版本](0005-classroom-session-and-scene-version.md) 已获用户批准 A–D，状态 Accepted；尚未实施，不改变现有操作恢复或已发布课堂API。

## 性能与历史证据

[收尾决定](../acceptance/mvp-0.2-closeout-decision.md) 保留 HTTP 首字节与完整首段的 PRD 目标，将独立教学首 token≤2 秒转为非阻塞优化。原失败结果不变；Pro 质量/闭环和 Flash 性能不能合并为同一配置全项通过。

历史验收报告中的“当前”“下一步”只描述记录时点。活动阶段与任务状态读取根目录 [task.json](../../task.json)；[阶段归档](../tasks/README.md) 只读，执行日志只追加。

## MVP 0.3 后续入口

- T001：冻结范围、验收映射、测量方式和预算。
- T002：制定可信模板渲染与持久化 Job 安全边界。
- T003：制定课堂会话、场景版本及学习控制边界；明确暂停、跳过、资源选择和旧版本恢复的后端职责。
- T004：在相关决定批准后固定 API/SSE 契约，包括 Job 事件重放。

T001 已完成验收口径冻结；T002 已完成并批准，T003 已获批准，T004 按依赖顺序继续。Markdown 导出不要求学生先运行多视角；T027 对 T024 的开发依赖保留用于可选结果适配。ADR-0004 只批准动画设计边界，当前实现仍以已发布 OpenAPI 为准；课堂与场景边界需另行决定。
