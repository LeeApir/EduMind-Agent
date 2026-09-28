# EduMind Agent 架构约束

本文件记录已拆分任务的架构决定及其边界。产品范围和验收标准仍以 [PRD](PRD.md) 为准；重大的 API、数据模型和安全变更必须新增 ADR。

审批状态和待决项见 [ADR 索引](ADR/README.md)。本文区分当前实现与阶段计划，不替代批准记录。

## 身份与学习状态（ADR-0001 部分批准）

匿名学生可以直接开始学习。服务端通过不透明、受保护的会话 Cookie 认证匿名用户，并将临时画像、学习会话、学习单元、场景进度和正式资源引用按匿名 `user_id` 持久化至 PostgreSQL。每个查询和写入均从认证上下文取得所有者，不接受客户端声称的用户 ID。

服务重启后，进程内流式连接可以中断，但已提交到 PostgreSQL 的学习快照必须由同一浏览器 Cookie 恢复。未审核或未提交的流式内容不得成为正式资源。注册把当前匿名记录升级为账号并轮换会话令牌，不复制学习数据。

完整决策、替代方案和待审批项见 [ADR-0001](ADR/0001-anonymous-identity-and-persistence-boundary.md)。

## 流式首屏与正式资源（ADR-0002 部分批准）

首段讲解以受轻量规则约束的临时 SSE token 尽快显示，但不属于正式资源。完整候选必须经 schema 校验和 ReviewAgent 后，才以原子提交的不可变版本发布，并发出 `scene_ready`。断线恢复操作状态和已审核版本，不保证回放临时 token；相同幂等键不得重复创建学习单元或资源版本。

HTTP 首字节 P95≤2 秒、完整教学首段 P95≤10 秒与独立教学首 token 分开测量；首 token≤2 秒已转为非阻塞优化，历史失败保留。起止点与证据适用范围见 [收尾决定](acceptance/mvp-0.2-closeout-decision.md)，后续采样由 MVP 0.3-T001 冻结。设计提案、已批准的最小恢复语义和待决项见 [ADR-0002](ADR/0002-streaming-first-screen-and-resource-review.md)。

## API 与 SSE 契约（MVP 0.1）

最小 API 契约在 [OpenAPI](api/openapi.yaml) 中维护。创建学习会话必须带 `Idempotency-Key`；POST SSE 断线后先读取持久化操作状态，再按需重新附着后续事件，且不承诺回放临时 token。资源读取端点只返回当前用户拥有、审核通过的不可变版本；当前契约不包含 Manim Job；持久化动画 Job 属于 MVP 0.3 待实施范围，Provider 设置属于 P1。

已知操作优先 GET 查询；运行中等待，失败/取消仅恢复终态，相同幂等键不重启生成。用户明确重新生成才换键。当前没有可靠的进程中断识别，真正中断的操作可能持续显示运行中；不能用一次查询判定失败。事件订阅只接收连接后的事件，不承诺持久化 token 重放。

## 学习证据、掌握度与路径（MVP 0.2）

测验、提示、重新解释和显式反馈作为 owner-scoped、只追加的学习证据持久化。已发布题目由服务端确定性评分；客户端和 LLM 都不能直接写入正确性、掌握分或节点状态。更正通过补偿证据完成，不覆盖原事实。这里的“重新解释”指请求动作的证据记录；生成、审核和恢复场景新版本的服务属于 MVP 0.3-T021，尚未实施。

掌握度和节点状态是使用版本化规则生成的可重建投影，每次变化保留不可变 revision。画像和路径每次有效更新都创建不可变版本；路径同时固定图谱版本、画像版本、掌握度水位和规划规则版本。规则和阈值由服务端版本化配置决定，不由 LLM 临时选择。

影响掌握度的命令在一个 PostgreSQL 事务中追加证据、创建 mastery revision、替换当前投影并标记待重规划。路径以已提交输入在独立短事务中重算；Provider 画像推断也不占用证据事务。幂等记录、版本水位与待重规划标记均存于 PostgreSQL，因此并发、重复提交和服务重启后可安全恢复。

落库映射：`learning_evidence` 保存 owner 范围幂等键、资源版本、规则版本和结构化事实；`node_mastery_revisions` 与 `node_mastery_current` 分离历史与当前投影；`learning_path_versions` 与 `learning_path_current` 分离路径历史与当前指针/持久化重规划标记。当前指针和补偿引用使用包含 owner（适用时还包含节点/目标）的复合外键，禁止跨用户或跨节点串接。业务写入仍须在事务内检查事实、版本水位和投影一致性，数据库约束不代替命令服务。

完整的证据含义、归属、事务边界、并发策略和重算规则见 [ADR-0003](ADR/0003-learning-evidence-mastery-and-path-versioning.md)。

## 学习闭环 API 契约（MVP 0.2）

[OpenAPI](api/openapi.yaml) 将 MVP 0.2 固定为一组可演进而不泄露所有者的端点：公共 `GET /api/graph` 与 `GET /api/graph/node/{nodeId}` 仅返回版本化知识结构；其他画像、测验、掌握度和路径端点从会话 Cookie 推导 owner。不存在可以由客户端写入的 `user_id`、正确性、分数、掌握状态或规则版本字段。

所有 MVP 0.2 写请求都需要会话 Cookie、同源 CSRF 令牌和 owner-scoped `Idempotency-Key`。画像修正和路径重规划另带显式的当前版本头，并发时返回稳定的 409 而非最后写入者覆盖。测验只接收已发布资源版本的答案，由服务端确定性评分；路径只使用已提交的快照，不调用 Provider。

## MVP 0.3 验收基线

范围、任务映射、计时起止点、固定分母与失败处理见 [T001 验收计划](acceptance/mvp-0.3-acceptance-plan.md)。两个链表模板满足数量下限；动画与多视角按需使用，Markdown 可在没有可选结果时导出。真实采样须另行冻结配置和调用预算，本轮预算为零。动画 Job 的 ADR-0004 已获批准；课堂与场景边界 ADR-0005 也已获批准。设计批准不等于已实施。

## 可信动画 Job（ADR-0004 已批准设计）

[T002 决定](ADR/0004-trusted-animation-jobs.md) 描述 PostgreSQL 短事务领取与租约、取消/发布互斥、可信模板容器隔离及 owner 媒体授权。状态为 Accepted；T005–T009 已实现审核模板、受限渲染与私有缓存，T010 已建立 `animation_jobs`、`animation_job_events`、`animation_media` 和 owner 范围资源绑定的迁移、幂等预约与事件重放。T011 已提供独立 Worker：数据库短事务领取、30 秒租约/10 秒心跳、重启回收、最多两次尝试和当前尝试原子发布；真实 Job 已在独立进程与受限 Docker 容器跑通。T012 已提供受 Cookie/CSRF 保护的创建、快照、取消和显式重试接口；缓存命中在请求事务中绑定 owner，运行中取消由 Worker 停止当前容器，取消与发布共用 Job 行锁排序。T013 已提供 owner 范围 GET SSE，以持久游标回放、会话逐轮核验和有界连接/轮询传递进度。T014 已提供经正式 owner 绑定授权的 MP4 Range/SRT 读取，读取前校验内容摘要，真实 Chromium 可播放。T015 将按需入口、持久 Job 恢复、SSE、取消/重试与 MP4/SRT 播放接入 Web；只在点击后创建，刷新和断网只查询旧 Job。EventSource 首次连接用 `after` 查询游标，自动重连的 `Last-Event-ID` 头优先，不改变现有学习操作的最小恢复边界。

## 课堂会话与场景版本（ADR-0005 已批准设计）

[T003 决定](ADR/0005-classroom-session-and-scene-version.md) 定义owner范围的模式/消息游标、迟到输出隔离、重解释版本CAS、演示返回点与显式偏好反馈。状态Accepted，尚未实施；现有ADR-0003证据/画像/掌握度事务和ADR-0002操作恢复仍有效。由T004落实API契约。

## MVP 0.3 API 契约（T004）

[OpenAPI 0.3.0](api/openapi.yaml) 固定动画Job、媒体/导出及课堂/场景接口，交接见 [T004契约记录](acceptance/mvp-0.3-t004-api-contract.md)。新增端点仍待T012–T028实现，不能把文档路径当作当前服务已提供。POST课堂流使用fetch；GET持久动画Job事件使用EventSource及游标重放。
