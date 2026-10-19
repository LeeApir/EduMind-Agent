# 架构决定索引

本索引汇总已有批准记录，不新增批准。产品范围以 [PRD](../PRD.md) 为准；现行接口见 [OpenAPI](../api/openapi.yaml)，实现与限制摘要见 [架构说明](../ARCHITECTURE.md)。

## 当前新提案：OM式生成与混合审核

2026-10-15用户选择参照OM重构生成、保留自动审核，并将无法可靠判断的内容交人工。[ADR-0015](0015-shared-plan-and-hybrid-review.md) A–D及[准确附件](../acceptance/phase-1-om-redesign/proposal-manifest.json)已按本次用户要求补齐契约/兼容并获A–D批准：共享计划/三个场景/受约束动作，语义审核及人工路由，计划与案件持久化/维护CLI/原子发布/API状态，以及分层验收和仅新链路的诊断补充。T043只交付设计，T044–T054按依赖零调用实施；准确批准见[登记](0015-approval-20261015.json)，真实预算0、catalog_only保持，T040旧路线及历史失败不恢复。

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

2026-10-08：[ADR-0011 批准记录](0011-dynamic-approval-20261008.json)将具体提案 A–D、样本标签和新增准入规则批准为 Accepted。原提案/manifest保留批准时字节（其中 Proposed/pending 是历史状态），状态以本批准记录为准。实际轮次目标/模型及调用额度尚未批准，仍为 0；不开放测试或生产动态入口。

2026-10-09：[ADR-0012：30节点知识结构、存储与课程资格](0012-expanded-knowledge-graph.md)为T030的Proposed方案，待批准A–D及准确附件。推荐复用YAML/PostgreSQL；默认10节点seed/签核目录保持，独立扩展图；元数据不等于课程资格。未完成T030、未开放动态或授权真实模型。

2026-10-09：用户明确回复“批准”，[ADR-0012批准登记](0012-graph-approval-20261009.json)将A–D与准确manifest附件批准为Accepted。原提案/报告/manifest保留Proposed历史字节，当前状态以本登记为准；按T031–T033实施，真实Provider授权0、动态入口未开放。

2026-10-15：[ADR-0013：逐条声明审核与确定性汇总](0013-claim-level-resource-review.md)为T040连续漏项后的Proposed设计稿，仅设计授权；声明提取/独立覆盖/逐条及整体检查/本地汇总均未实施，真实请求0。内部原型实施、动态子请求冻结规则补充与真实预算需分别决定；不改变ADR-0011、原失败/验收标签或catalog_only。

2026-10-15 后续：用户“继续”授权并完成[零调用原型](../acceptance/phase-1-t040-claim-review-prototype/README.md)，只在scripts实验层使用合成tape；不代表ADR-0013真实派生/生产接入条款Accepted。61原型+148相关回归通过，真实Provider0，动态预算补充与质量门禁仍待决定。

2026-10-15：[ADR-0014：T040有界子请求冻结与预算](0014-bounded-derived-review-requests.md)为Proposed补充，A–D待批准；[准确提案清单](../acceptance/phase-1-t040-derived-budget-proposal/manifest.json)只绑定规则/基线供设计审阅。批准仅授予独立机制实现与零Provider测试；不授权247次理论调用、任何金额、正式质量/DSL/T041或生产开放，旧v1与旧台账不改。

2026-10-15 后续：用户“yes”批准ADR-0014 A–D及准确manifest，状态以[批准登记](0014-derived-budget-approval-20261015.json)为Accepted，原Proposed提案保留历史字节。[独立预算机制](../acceptance/phase-1-t040-derived-budget-kernel/README.md)完成零调用实现与269项离线验证；未接入真实HTTP/出站鉴权，真实请求及费用授权仍0，T040质量门禁继续blocked。

2026-10-15 后续：完成[派生发送组合离线验证](../acceptance/phase-1-t040-derived-calibration-draft/README.md)，311项离线通过，补齐模型可复制的块/身份摘要；两例最多38次草案仍DRAFT_NOT_EXECUTABLE，Token/费用证明、真实审批/当前凭据同意和事实签核组合待补，真实Provider0，未新增架构或付费批准。

2026-10-15 后续：[r09两例运行准备](../acceptance/phase-1-t040-derived-calibration-r09/README.md)完成：供应商整窗契约界、单步审批/凭据文件版本及逐例人工事实门禁，339项离线通过。准确根最多38次/CNY120.149000尚待真实预算批准；非预计消费、非账户硬限额，无模型调用，不改变ADR批准或T040状态。

2026-10-15 实际结果：用户yes批准dff3a06 r09准确根/38次/CNY120.149000后，仅首条声明提取请求实际发送；3932输入/8192总输出（推理8192）、无合格清单，INVALID_OUTPUT停止，余37未发。见[r09结果](../acceptance/phase-1-t040-derived-calibration-r09/results/r09.json)。不误记事实漏检或质量通过、不恢复旧失败；T040仍blocked，none/catalog_only保持。

2026-10-15 后续：用户好接受停止付费盲重试，完成[程序定位/ID选择离线原型与局部审核对照准备](../acceptance/phase-1-t040-span-review-offline/README.md)。新resource-line-spans-v1只用于隔离实验，不替换原已冻结分块或根；100项相关离线通过。四条助手清单待人工范围确认，最多两轮/8次退出规则仅提案，无真实预算/调用，不代表T040或整篇覆盖通过，旧r09停止保持。

2026-10-15 后续：用户确认四条声明忠实原文的范围，独立保存[范围登记](../acceptance/phase-1-t040-span-review-offline/scope-confirmation.json)。[r10固定焦点方案](../acceptance/phase-1-t040-focus-r10/README.md)准备完成：4静态请求/none/2048输出/60秒、保守CNY8.551250、共享最多两轮8次及逐条实际人工事实门禁；新增35+相关238=273离线通过。准确运行预算与退出方案待批准，范围确认不转授调用或预签模型判断；不改变原ADR附件、T040 blocked及目录模式。

2026-10-15 最后一轮准备：r10两条主缺陷检出但附带分类误报，用户要求只再测最后一轮。独立[r11方案](../acceptance/phase-1-t040-focus-r11/README.md)补齐通用分类/实际证据契约及新2错误2正确诊断，19新增+273相关=292离线通过；准确4次/CNY8.516778与新样本范围待批准。复用原两轮8次策略登记，失败后停止当前自动生成/审核路线、不追加第三轮；四条通过也不替代正式T040或跨课程验收。旧源码/评分/停止账本不变，当前真实Provider0，none/catalog_only保持。

2026-10-15 最后一轮实际结束：用户批准7a1467a r11准确范围/最多4次/CNY8.516778后，仅final-01实际1次；具体FIFO/LIFO错误正确检出，但返回misconception未满足冻结fact类别，ADMISSION_FAILED停止，余3未发。见[结果](../acceptance/phase-1-t040-focus-r11/results/r11.json)和[最终退出](../acceptance/phase-1-t040-focus-r11/route-retired.json)：当前路线停止，不追加第三轮/微调重试，2轮累计3次而非8次耗尽；T040 blocked/none/catalog_only保持，旧结果和ADR批准不改，不代表正式质量或跨课程能力通过。

2026-10-19：[ADR-0018](0018-teaching-node-binding.md)已按[准确批准](0018-approval-20261019.json)实施T060–T064：目标/推荐/教学分离及准确发布绑定/评分/API恢复。原Proposed附件保留批准时字节，当前状态以批准记录和根账本为准。T064完成提交8a9b38f；全部零Provider，不代表真实主题质量通过。

2026-10-19：[ADR-0019：固定C样本离线验收](0019-fixed-c-offline-verification.md)为T065具体Proposed方案，A–D及[manifest](../acceptance/phase-1-fixed-c-design-r01/manifest.json)待批准；固定两份封存原件/审阅驱动、独立工具链锁、禁网非特权容器与限额、编译/输出/故障/追踪分列。工具链环境尚未就绪；样本编译/运行0，Provider0。T066–T069不得先行，无宿主直接执行降级或正式发布授权。
