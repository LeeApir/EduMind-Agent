# ADR-0005：课堂会话、场景版本与学习控制

- 状态：Proposed，待用户批准；未实施
- 日期：2026-09-28
- 关联任务：MVP-0.3-T003（接口细化 T004；实现 T016–T026）
- 依据：[PRD](../PRD.md) §3.3、§3.5；[ADR-0002](0002-streaming-first-screen-and-resource-review.md)、[ADR-0003](0003-learning-evidence-mastery-and-path-versioning.md)

## 边界与已有事实

课堂是现有 owner 的学习单元内的持久进度，不创建第二套用户或掌握度来源。现有 `learning_units`、`learning_scenes`、`generated_resources` 提供场景与正式资源版本，`learning_evidence` 已记录重解释请求与显式反馈；MVP 0.2 的操作状态恢复只保证已提交快照，不保证临时 token 重放。这里的场景新版本生成与模式/消息持久化是新增能力，不能因为已有请求证据就声称已经实现。

以下 A–D 为具体待批准的新数据/API语义。P0仅一个 TutorAgent 编排：默认专注、按需互动，以及数组 vs 链表一次结构化多视角演示。无真并行子图、开放深度辅导、自动生成全量视频或模型设置。

## 决定 A：持久课堂游标与归属

每个学习单元至多一个当前课堂会话。记录 `owner_id`、`learning_unit_id`、固定的 `scene_key` 与当前已发布 `scene_version`、`mode`（focus/interactive）、`revision`、全局单调 `message_cursor`、独立的 `scene_progress`、`enabled_roles`、当前 `generation_id`、暂停标志及可选 `detour`（数组 vs 链表演示返回点）。数据库复合owner/单元约束和服务端鉴权双重保护，不接受客户端 owner_id。首次学习单元发布后可延迟创建课堂；没有课堂会话时正常学习路径仍可用。课堂记录和已有学习会话不同，前者是课堂进度，后者是学习目标/资源操作身份。

消息只追加，保存服务端 `message_id`/单调message_cursor、角色（tutor/beginner/advanced/student/system及演示角色）、创建时的模式revision/场景版本、公开内容或审核后引用、可见状态。仅已提交消息可重放；临时 token 不跨重启保证重放。角色上下文按 `(owner,learning_unit,role,scene_key,scene_version)` 保存**去敏摘要与有限条最近消息引用**，不复制无界对话或完整私有画像。学习单元改变/场景新版本发布时建立新上下文引用，旧消息保留审计但不能作为当前版本事实。

GET 快照在一致读中返回revision/message_cursor/scene_progress/场景版本/模式/enabled_roles/generation_id/暂停/返回点和已提交消息页。游标请求仅返回大于message_cursor的已提交消息，超前409，过期410后以快照message_cursor继续。普通课堂 POST 流用 fetch+ReadableStream；持久动画Job的EventSource契约见ADR-0004，不把课堂临时token伪装成可重放事件。重连先GET课堂快照；快照返回当前最大message_cursor，页面重启后以正式资源与持久消息恢复，不自动重发未完成Provider调用。

## 决定 B：模式切换、迟到输出与多视角返回

所有课堂写命令携带owner范围幂等键、规范化请求摘要及 `If-Match`课堂revision。先查询幂等记录：同键同摘要返回原回执且不再执行、不受后来revision变化影响，异摘要409；未命中时才在行锁下检查当前revision并递增。旧revision返回409 `CLASSROOM_VERSION_CONFLICT`和当前revision，客户端刷新后由用户决定重试，不静默覆盖。

切回focus、关闭某角色或离开场景时，先提交新revision/角色启用集合并标记旧generation_id为superseded；旧流允许结束传输，但服务端不得将旧角色后续token/终态写入当前会话、也不得产生当前场景正式资源。客户端在每个事件检查会话revision/scene_version/generation_id/角色启用状态，丢弃旧输出。停止Provider调用是尽力而为；不把用户界面关闭解释为费用已立即停止。新focus只显示导师的主动发言，已发布的历史可在历史视图读取但不主动继续。切回interactive不自动补发或启动旧角色。

演示是课堂中的暂时detour，不是永久第三种默认模式：进入时保存 `(scene_key,scene_version,scene_progress,mode,enabled_roles,paused)`，独立结构化生成三个视角与主持人总结，经schema/ReviewAgent审核后整体发布；失败不显示部分正式结果。退出以原返回点恢复，若原场景已更新则按新当前版本恢复并提示版本变动；全局message_cursor保持递增，detour退出不回拨，不强制回滚旧资源。只允许一个有效detour，重复进入同键回放，新的进入冲突返回409。多视角卡片不自动成为学习事实，用户显式反馈才可能更新画像偏好。

## 决定 C：学习控制与场景新版本

暂停/继续只改变课堂播放与自动下一动作，不撤销已提交学习证据，也不取消显式请求的动画Job；暂停后不得自动启动下一次发言/资源生成。跳过当前场景要追加ADR-0003允许的 `explicit_feedback` 证据并推进scene_progress，不能直接标记 mastered；message_cursor只在持久消息追加时增加。补前置知识沿既有图谱/路径进入推荐节点，保存课堂返回点；不可由客户端声明掌握度或私自修改路径。资源选择只记录用户确实选择的资源类别，动画仅经明确点击创建Job。

“更简单/更深入/换例子”接受后先追加 `reexplanation_requested` 证据（幂等、owner、基版本），再生成候选 `learning_scenes` 新version与对应资源；候选在schema/ReviewAgent通过之前只以临时流显示，不覆盖当前正式版本。发布用 `(owner,unit,scene_key,base_version)` CAS：只有基版本仍为当前版本且课堂仍在对应scene时，将新已审核scene/resource作为当前，并递增课堂revision；若同时追加正式课堂消息则单独递增message_cursor；旧版本不可改。并发重解释有一方成功，另一方返回409 `SCENE_VERSION_CONFLICT`且候选不可发布。Provider失败或审核失败不回滚请求证据，也不改变已发布scene；该证据仅证明学生提出重解释需求，可影响困惑/画像/路径待重算标记，不证明新解释已成功。原幂等键恢复原操作与证据，不重复追加；用户明确再次请求须新键。刷新、断线或重启仅恢复已提交的旧/新正式版本及操作终态，不宣称候选临时token可恢复。旧版本可在历史中只读，但不重新设为当前；旧资源仍可按owner/审核状态读取。

路径/画像依ADR-0003使用已提交证据与版本重算；重解释、跳过、资源选择不自动增减掌握分。补前置或模式切换不隐式调用Provider重新推断画像。若画像/路径异步更新，课堂记录只引用操作开始时固定的版本水位；后续下一次动作读最新已提交版本，需记录输入水位避免混用。

## 决定 D：审核与反馈

普通课堂发言使用服务端轻量规则：输入/输出长度、角色权限、越权指令、危险内容和知识节点事实边界；命中高风险（安全/隐私风险、与知识图谱事实冲突、代码执行建议或拟持久化总结）升级ReviewAgent。普通发言允许先流式展示标记为临时的token，仅限轻量规则通过的低风险内容；任何需升级审核的内容在审核通过前不可作为正式消息/资源。审核拒绝或ReviewAgent不可用时不得发布，流中已展示的临时token须发出`content_retracted`事件、标记失效并清除当前视图，保留去敏审核事件；无法可靠清除时停止显示后续内容并显示明确失效状态。此临时显示及撤回语义是本ADR待批准新决定，不声称ADR-0002整体已批准。未审核临时token不能进入Markdown笔记。正式场景资源和多视角主持人总结始终schema+ReviewAgent通过后发布，不能仅凭轻量规则。

“我喜欢这个视角”只接受已发布且本owner可读的演示结果ID+视角枚举，作为ADR-0003 `explicit_feedback` 追加证据，绑定当时scene/结果版本；同一owner/结果/反馈动作幂等。画像 `cognitive_style.preference_persona` 可随版本化合并规则及证据置信度更新，不能将偏好当事实或直接改掌握度。反馈不改历史主持人总结，仅影响之后的表达选择；只有显式反馈才作此更新，不从停留/回放/浏览自动推断偏好。

## 场景审查

| 场景 | 必须结果 |
| --- | --- |
| 关闭互动角色时旧流仍到达 | 旧revision不可写当前消息/资源；UI丢旧事件 |
| focus→interactive→focus与刷新 | 默认导师、按需角色、模式/游标持久化，旧消息可查但不主动发言 |
| 断线/重启后重连 | 快照与持久消息可恢复，临时token不冒充重放；未完成操作遵ADR-0002 |
| 两个重解释并发、审核拒绝、旧版本读取 | 一个CAS发布或均无发布；旧正式资源可读；证据不丢 |
| 多视角中场景版本更新后退出 | 原进度优先，新版本提示；不会回滚到过期当前指针 |
| 暂停、跳过、补前置、资源选择 | 不产生虚构测验/掌握证据，不自动创建动画Job |
| 同键复发、异参数、跨owner读取/反馈 | 一次效果、409冲突、跨owner404 |

T004固定请求/响应、错误码与SSE事件；T016/T021验证持久化/并发，T019/T024验证审核门禁，T020/T022/T025验证UI迟到输出，T026验证偏好证据，T031验证重启。当前仅设计审查，无实现测试。任何改变现有画像/路径/掌握度事务语义须先修订ADR-0003。用户批准此ADR才可继续实现与T004契约。
