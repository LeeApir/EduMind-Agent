# DSL 动画准备操作与渲染 Job v1

T028实现[ADR-0010 C/D](../ADR/0010-constrained-animation-dsl.md)的开发接口。精确契约见[OpenAPI](../api/openapi.yaml)。目录交付基线继续使用 `catalog_only`；该文档及代码提交不代表动态入口、真实模型预算或部署开放，T037画面验收和T040/T041独立配置验收仍待完成。

## 调用与恢复

`POST /api/learning-units/{unit_id}/animations/generate` 需要有效owner原会话、CSRF、Idempotency-Key和非秘密 `X-Animation-Operation-ID` UUIDv4。body仅有 `scene_id/scene_version/goal_kind/parameters`。固定目标策略接受数组比较/交换/遍历、链表概念比较/遍历、插入/删除；`trace_insert/trace_delete`只表示可降级的详细轨迹表现，不扩展DSL动作。最多8个严格整数，值域−999到999；插入最多7项，索引必须符合操作。拒绝bool、未知字段、DSL、Python、owner或Provider URL。

POST使用fetch/ReadableStream；`agent_start`返回安全准备快照，`stage_changed`表示generating/reviewing/compiled，`done`包含终态快照。handed_off只表示已交付渲染Job；渲染进度/断点恢复走既有Job GET EventSource，不延长普通学习请求。模型只在当前API操作任务内执行，不进入Celery；最多3次生成候选和3次独立审核，修正只在已审核前一候选后发生。默认DSL预算授权器拒绝每次出口；真实授权必须另行落实服务端预算，并通过开放门禁。缓存/合法参数化模板不使用模型出口。

PG准备操作绑定owner、目标、规范意图、摘要、不可变原session hash/expiry、≤180秒绝对deadline和服务端随机holder token。相关UUID不代表执行权限，holder不回传。最多2个owner活跃操作；同键同摘要只观察或重放，异摘要409，另一会话不能接管。`GET /api/animation-preparations/{operation_id}`只返回id/stage/deadline及可选job_id/source/error_code；到期CAS收尾，不后台重放。API重启后旧操作只能观察到截止，新生成使用新键。

原执行POST断线先取消模型actor/清理该purpose=generation操作的临时凭据，再独立屏蔽ASGI取消完成PG CAS。观察连接断线不取消holder。显式准备cancel需要原session、CSRF和独立幂等键。取消与handoff争同准备行锁：先取消为零Job；先handoff保留Job引用，此后使用Job cancel。原session撤销或到期也停止模型出口和迟到handoff。

临时quality/review handle只放请求头和内存。预上传使用相同operation UUID、purpose=generation和精确connection/config/model绑定。同连接/model/purpose可由一次lease覆盖有界生成、修正和独立审核调用；不同审核模型需独立精确handle。缺审核凭据或选择变化不能改用其他模型。每次调用重查实际配置/能力/目标，handoff事务再锁定owner路线、连接及模型快照；无handle/密文/未审核文字进入准备记录、Job或队列。

## 缓存与发布

优先复用当前模型来源匹配的已审核candidate，然后检查合法模板，只有不适用才生成DSL。模型来源、采样、Prompt/政策/编译/图谱/参考/目标版本和owner namespace进入内容身份；Key版本不进入键。alias未知revision显式保留unknown，不能自动发现厂商后台替换模型权重。缓存命中仍复核当前来源、审核资格及实际不可变文件。

`0024_animation_preparations`固定准备身份/计数/终态；`0025_animation_dsl_media`回填旧Job/media为template，新增owner/candidate/目标复合外键及template/dsl互斥CHECK。旧模板响应保持原字段；准备来源Job额外包含render_kind/generation_id和准确candidate/fallback来源。DSL模板身份为NULL，不用假模板ID。保留准备、DSL或fallback来源时降级拒绝；无数据隔离库实际up/down/up用于验证迁移。

获审核candidate与Job、首事件、outbox和准备结果在同一PG事务提交。Worker只消费无凭据Job ID/dispatch_epoch，支持pg_poll/celery及显式队列切换。领取、渲染、发布、重试、媒体和导出读取都核验完整当前版本。发布锁序Job→课程/scene→candidate→policy→owner缓存协调锁→key锁→媒体/绑定；新handoff的Job尚未对其他事务可见，不反向锁既有Job。

实际Linux Manim隔离容器与固定PyAV完整解码验证完成后，私有不可覆盖字节与正式PG媒体/绑定/succeeded同lease提交。文件不完整、摘要改变、候选/政策/课程撤回均拒绝。成功Job保留历史终态，未来读取即时不可用。MP4 Range、SRT和下载沿用owner授权；DSL响应头 `X-Animation-Generated-By=reviewed-manim-dsl`，省略模板ID/version，`X-Animation-Source-Versions`为受限ASCII JSON来源版本，不含Key/handle/完整URL。

显式维护函数 `collect_private_dsl_orphans`沿用24h孤儿规则，先取得同owner namespace/key协调锁，再非锁定读取正式引用与活跃意图。正式媒体即使撤回仍保留；活跃同key不删，owner存在待渲染任务时保守保留未知对象；损坏描述符不授权删除未知对象。只清理未引用旧缓存产物，不自动删除学习数据或candidate。不同owner无字节/文本缓存共享。

## 失败与验证

生成失败仅当原请求头 `X-Animation-Allow-Template-Fallback=true` 且目标/参数有合法模板时降级，准备快照和Job保留明确来源及固定原因。会话/目标失效无回退。DSL渲染异常或worker失联按PG租约最多两次领取；最终失败仍保存原DSL Job。一项原请求授权仅在不可变原session还有效、目标仍合格且合法模板适用时创建独立template Job，唯一(original_job_id,render_kind)。原failed事件可带fallback_job_id/fallback_source，新queued事件带fallback_of/source/reason_code；模板失败不循环。更晚的新guest/session/Key不能延长旧授权。正式DSL可用率仍将原槽记失败，模板体验可用单列。

验证入口：`test_dsl_animation_jobs.py`（真实PG/真实Docker媒体、外键、撤回/发布和迁移），`test_dsl_animation_api.py`（真实PG、mock出口、SSE/幂等/断线/预算/契约），`test_dsl_selected_flow.py`（persistent/temporary、同/不同审核模型、一次lease与独立修正），`test_dsl_animation_failure.py`（两次领取、唯一回退、原session/撤回门禁、队列切换），`test_dsl_animation_gc.py`（真实PG、24h、协调锁）。旧模板/Job/媒体/事件/outbox/容器测试共同回归。Mock/字节夹具不作为教学质量或真实Provider成绩；T028真实Provider调用数为0。
