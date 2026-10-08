# EduMind Agent 架构约束

本文件记录已拆分任务的架构决定及其边界。产品范围和验收标准仍以 [PRD](PRD.md) 为准；重大的 API、数据模型和安全变更必须新增 ADR。

审批状态和待决项见 [ADR 索引](ADR/README.md)。本文区分当前实现与阶段计划，不替代批准记录。

## Phase 1队列决定（ADR-0009已批准）

[ADR-0009](ADR/0009-durable-animation-queue.md)确定保留PostgreSQL为Job/owner/租约/媒体/SSE唯一事实源，以同事务outbox和Redis/Celery投递已审核动画的Job ID/epoch；重复投递由数据库条件领取与版本隔离处理。凭据、临时handle、学习上下文和待模型审核阶段不进入队列。30s租约/10s心跳/最多两次领取、取消与发布行锁排序及既有媒体隔离继承ADR-0004，具体切换/回滚与失败矩阵见提案。

该方案已获用户批准A–D，具体提案digest及原话见[批准登记](ADR/0009-queue-approval-20261004.json)；T019已交付锁定的Celery/Redis运输依赖、Job路由增量迁移、事务outbox、独立publisher/reconciler及兼容PG领取过滤，运行说明见[ANIMATION_QUEUE](ANIMATION_QUEUE.md)。默认仍pg_poll；T020已交付固定消费者/持久尝试账本/独立宿主清理器，T021已接入取消同事务清理与outbox失效、队列路由下PG事件恢复。公开API路径、响应状态和PG事件游标保留；OpenAPI中的`x-queue-migration`只记录已批准内部迁移计划，公开接口不暴露内部投递字段。T019–T021按本批准逐项实施并验证，T036须提供真实故障恢复；目录与2h匿名会话继续按既有批准，不新增Redis会话/LLM缓存或模型队列。

## Phase 1 DSL决定（ADR-0010已批准）

[ADR-0010](ADR/0010-constrained-animation-dsl.md)及[DSL v1契约/schema/示例](agents/animation-dsl-v1/README.md)确定九动作有限JSON、逐步状态模拟、独立审核与确定性编译/AST、同等隔离容器；模型不能提交Python。资源上限为64KiB/深度12/8节点/4指针/16累计边/120动作/30–90s，具体引用/字幕/严格解码见附件。

DSL自由文本采用owner私有缓存及准确生成/审核来源，候选/规则/课程撤回实时阻断新发布与读取；API内有界模型准备操作不进Celery，只有已审核无凭据渲染Job进入ADR-0009队列。失败只一次降级到同目标已审核模板，无适用模板则不可用。方案已获用户批准A–D及附件，见[批准登记](ADR/0010-dsl-approval-20261004.json)；T023已实现本地严格校验/冻结轨迹，T024实现确定性编译与受限静态检查，T025实现独立审核与不可变候选/资格目录，其余按任务逐项实施；OpenAPI扩展只标已批准计划，T025增加T024编译前置，T023等逐项实施并验证。真实Provider预算0、catalog_only与T035独立开放门禁不变。

T024的`animation_dsl_compiler`仅通过AST构造固定Manim `DSLScene.construct`，按可信轨迹逐动作更新对象；ID映射由编译器分配`m0…`，自由文字只进入Constant。实际最小属性集为`move_to`、`add/remove/play/wait`和已核对来源的`animate.set_color`（group）/`animate.set_fill`（box）；交换仅Transform两个值Text，访问标记单独保留，compare结果下一动作移除，字幕覆盖duration+hold。只允许固定Text/RoundedRectangle/Arrow/VGroup/FadeIn/FadeOut/Transform及Scene导入，构造器/坐标/色表/字体/时长参数逐项核验，未知节点/接收者/参数拒绝。

`animation_dsl_static.py`作为stdlib可信子进程解析源码，不import/run生成模块，`-I`且空环境，不继承Provider/PG/KEK。父进程复核当前源码/政策与加载时摘要，子进程再次核对传入的静态源码/政策摘要，版本漂移即拒绝，需重新加载新版本。先限制256KiB，再核验≤20000 AST节点；CPU1s、栈8MiB、零文件输出及32描述符，Linux额外384MiB DATA/AS上限，macOS不声称内存rlimit已生效。父进程0.9s截止并强制kill/wait，为1s总预算留清理余量。后端Python3.11与固定渲染镜像实测Python3.14均拒绝额外type_params；其他解释器版本不可确认即拒绝。AST摘要包含实际解释器结构，编译身份另绑定Python版本、实际源码/静态政策/schema/轨迹/SRT、固定镜像/字体/布局/帧率；跨解释器不转授旧摘要。

编译成功结果仍须通过T025独立审核并绑定本次完整编译/轨迹摘要；T027再核对同版本重新编译与静态检查，并在受限容器验证字体/导入/真实MP4与字幕，T037补实际画面。T024未执行生成Scene、渲染或开放新请求/动态能力；静态失败只有固定内部码`DSL_COMPILE_REJECTED`/`DSL_RESOURCE_LIMIT`/`DSL_COMPILE_UNAVAILABLE`，不回显源码、异常或路径。

T025通过`animation_dsl_review`和服务端`SelectedDSLReviewGateway`将完整DSL/可信轨迹/≤8KiB版本化参考交给T012实际review档位，单次60秒、不隐式回退；生成Python不发送或执行。严格审核输出与动作索引/安全文字检查失败返回`DSL_REVIEW_UNAVAILABLE`，与事实reject分开。`0023_animation_dsl_reviews`建立owner/单元/场景版本复合外键、pass绑定与内容摘要插入复核、不可变候选/审核/政策，以及追加撤回记录；失败仅存固定类别/索引/摘要，不存未审核文字。已有审核数据的迁移降级拒绝，正常owner学习数据删除可级联。当前政策须受信维护代码显式登记，读/存不自动复活；资格检查刷新当前课程/场景/参考/图谱及政策，锁顺序遵守ADR-0010。详见[运行审核材料](../data/animation_dsl/review-v1/README.md)。T026生成/修正、T027实际渲染和T028 Job/媒体发布仍待交付，尚无新HTTP或媒体，也未开放动态入口。


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

[OpenAPI 0.3.0](api/openapi.yaml) 固定动画Job、媒体/导出及课堂/场景接口，当前交付范围与验证见[目录版退出报告](acceptance/mvp-0.3-catalog-exit-20261003.md)；目录模式下动态课堂与重解释仍关闭。POST课堂流使用fetch；GET持久动画Job事件使用EventSource及游标重放。
