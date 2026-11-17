# 渐进生成与恢复契约 v1（提案）

本契约落实[ADR-0025](../../ADR/0025-progressive-course-generation.md)，继承[已批准T001](../../ADR/0024-approval-20261021.json)的身份、版本、owner、旧数据兼容和程序硬门。所有接口planned，尚无真实调用或部署。

## 1. 输入、计划与首场景

创建POST沿T001仅收goal/teaching_language/code_language；默认按15分钟学习规模规划，计划允许1–8场景，不固定为三块，不强制凑满8。15分钟是内容编排目标，不是生成耗时保证；用户原文有时长要求则保留为目标，超出首版规模时返回澄清建议，不静默截掉原要求。不新增未设计的时长控件或不支持语言。

计划最小字段见[policy](policy.json)，完整结构见补充OpenAPI的内部PlanCandidate/PlanScene/PlanObjective（不是学生响应正文）：标题、目标及真实请求来源、共享术语/示例/约定、顺序场景标题/目的/预期表达类型、依赖前序场景。模型只给临时scene_key及来源片段，服务分配逻辑UUID、owner、版本与摘要。source_key必须来自服务端提供的真实请求片段白名单，excerpt须是该片段原文子串，服务绑定准确请求ID；objective id/term/scene_key唯一，场景objective_ids引用本计划目标，依赖必须存在且先于自身，无环；图谱关联可空。原始目标及全部有据输入保留，计划来源和用户要求分离。

真正冲突、超范围或缺必需材料时，规划返回needs_clarification及1–3条问题（每条1–300字符），写入终态awaiting_clarification，不调用场景生成。未知画像/无节点/多节点本身不构成澄清理由。用户补充通过新操作clarify，保存新请求快照，累计预算不重置；不让旧操作无限等待。计划结构/引用失败可用受限格式修复，语义覆盖意见不作为草稿的必经审核门。

计划合法后，先提交含所有scene_version_id=null的清单及outline_ready事件，默认自动生成第一个场景，用户无需确认。每个场景的一次主要调用合并生成受约束正文/代码/题目及动作/可视化描述，代码只作文本，答案只存私有投影。计划/内容schema和引用经本地验证，服务分离存储与公开投影；单场景可以混合多种表达形式，仍是一个可学场景。

首场景必须是计划第1场景且无必要前置，完整正文和本场景必需交互描述均通过硬门。相同事务保存场景版本、全清单新版本、CAS head、步骤完成及事件后，才可发scene_ready和一次first_scene_ready。后续场景继续追加清单；空大纲/可视化占位/HTTP首字节/流片段不算首场景可学。first_scene_ready按课程逻辑唯一，历史重放保持同event_id，不因新连接或修订再发。

## 2. 三类独立状态

| 对象 | 状态与含义 |
| --- | --- |
| 操作 | queued、running、cancel_requested为活动态；succeeded、partially_succeeded、awaiting_clarification、failed、cancelled、timed_out为终态 |
| 操作内场景步骤 | pending、blocked_dependency、running、ready、failed、invalidated、cancelled；ready只表示本操作准确绑定已提交，不等于签核 |
| 用户学习进度 | 后续业务单独保存，不由生成ready或succeeded推导完成/掌握度 |

状态转移以policy为规范。失败场景标failed，必要后代blocked_dependency，继续生成无依赖的后续场景；流程串行拓扑排序（同层按计划顺序）。如果没有可执行步骤则结束。正常耗尽：全计划场景可学且未禁用→succeeded；至少一场景可学但不完整→partially_succeeded；全无可学→failed。取消/超时/未知结果优先使用其真实终态/原因，不因已存在内容改写为成功，ready_count仍保留。规划澄清仅在没有新可学场景时发生；旧课修订需澄清时旧版照常读。

course的head清单完整性与operation终态分开：旧head可能完整而本次修订失败，原课程仍有内容。confirmed缺陷使有效可学数减少，但不改写历史manifest的complete布尔；读取返回当前限制，UI不能把历史complete当可用保证。

GET操作返回原目标绑定、kind、状态、base/head版本、每场景步骤、固定原因码、last_event_id及预算使用/剩余额度；不返回内部审核、答案、密钥、lease token。失败原因使用固定码SCHEMA_INVALID、DEPENDENCY_UNAVAILABLE、PROVIDER_REJECTED、OUTCOME_UNKNOWN、BUDGET_EXHAUSTED、DEADLINE_EXCEEDED、LEASE_LOST、CANCELLED等，不回显异常正文。

## 3. PG持久调度与原子边界

新增表均owner/course复合绑定，独立于旧LearningOperation/AnimationJob：

| 表 | 最小职责与约束 |
| --- | --- |
| free_course_operations | id、owner/course、kind、request快照、base_head_version可null、state、deadline_at、config/policy快照、lease_epoch/token/expires_at、cancel_requested_at、created_at；活动态owner唯一及course唯一的部分索引 |
| free_course_steps | owner/course/operation、step_key、scene_id可null、state、准确输入及依赖摘要、attempt计数、next_attempt_at、结果引用；unique(operation,step_key) |
| free_course_attempts | owner/course/operation/step、attempt_id、用途primary/transport_retry/format_repair、预留input/output、sent_at可null、结果及用量或unknown；只追加预约/结算事实，不改为未发生 |
| free_course_events | owner/course/operation、operation内连续递增seq、event_type、公开payload、created_at；unique(operation,seq)，first_scene_ready按course部分唯一；正文/答案/秘密不入事件 |
| free_course_receipts | owner+规范路由+Idempotency-Key唯一，规范请求摘要及原HTTP收据；有课程即同域引用；重放不调度 |
| free_course_capacity | 固定全局槽位1–2、owner/course/operation、expires_at、epoch、state=held/quarantined、pending_attempt_id可null；同操作最多占1，数据库事务竞争，quarantined不得仅按expires_at释放 |

创建事务：认证/CSRF/模式/输入校验后，在owner锁及课程锁范围内重查幂等；冲突/额度不足不创建课程、操作或收据；owner已有活动操作则409 OPERATION_ACTIVE，全局worker槽不足允许queued等待。创建课程（首次）、请求快照、queued操作、首步骤、queued事件及201/202收据一并提交。Worker只读取已提交queued/running记录；API不在事务内调用Provider。PG轮询间隔1s，FOR UPDATE SKIP LOCKED领取，定期扫描过期租约/取消/截止时间，重启后继续扫描，不依赖HTTP存活或内存队列。不承诺1秒性能。

锁顺序固定owner→course→operation→step→capacity→attempt/event/receipt；worker亦按此序重新锁定并复核，不一边持有capacity行再回锁course。Provider网络调用在事务外。获取租约递增epoch、随机token、有效45s，每10s短事务续租。完成写入重检token/epoch/租约未过期、截止、取消、head基线及依赖摘要；任一失败禁止切head及写ready，未公开候选可留作审计但不能复用成合法结果。

每次外部调用前原子锁定course计数/operation预算，预约最坏token并记录attempt及sent标志后才发送；预约提交后进程崩溃可能未真正发送，仍按不确定已尝试保守记数。无sent预约可以安全释放token预留，但调用次数一经进入sent不退；已发送且未知token消耗按预留上限占用，不能填0。Gateway/SDK内部重试关闭，所有发送必须通过该预约。没有可用凭据/模型能力时不启动发送，不静默换Provider。

过期租约：没有sent未结算调用且步骤结果已提交，按持久结果继续；没有sent调用且无结果，可重领步骤；存在sent未结算调用，终止操作failed/OUTCOME_UNKNOWN，不自动再次调用。对应容量槽进入quarantined，owner/course存在未结算发送时拒绝新生成操作409 OUTCOME_UNRESOLVED；不能因终态或租约超时就释放槽并发起下一次调用。只有收到准确attempt的完整响应/明确未执行或停止的Provider回执，或维护者依据同等可信证据追加核销事实后释放；仅本地timeout不证明远端已停。人工无证据不准释放，无法核销时可持续阻塞并告知用户。旧worker即使晚收到成功也因epoch失效不能发布；晚到用量可追加结算，仍不自动继续。外部调用恰好一次无法保证，本方案保守不重发。

## 4. 预算、重试与时钟

准确数值见[policy](policy.json)，均是拟议产品安全上限，当前真实请求授权仍为0。每个explicit操作新建自身上限，但全部共享course终身累计上限（无自动按日重置），避免连续resume/clarify/revise放大成本；创建新课也须遵守将来获准执行包的全局请求/费用封顶，不能用新course绕预算。首版不提供客户端扩额接口。

- 单操作最多13次已发送尝试：主规划最多1次、每个需新生成场景最多1次（最多8）、传输重试额外总2次、格式修复额外总2次；每步骤每类最多1次。格式修复调用遭遇可重试传输错误也必须使用同一传输池，合计仍≤13。无语义自我改写循环，无全量语义审核调用，无隐藏工具循环。
- 单操作输入token累计≤200000、输出累计≤48000；单调用输入≤32000、输出限额≤8000。服务先按实际Prompt用确定性可用计数器保守计算（不能可靠计数则以经验证上界，仍无法界定则拒绝），非秘密模型能力上限更小取更小。发起时预约max_output_tokens；准确用量到达后结算释放未用token，未知用量不释放。Provider隐藏推理如不能约束/纳入总输出上限，则该配置不能准入此策略。
- 单课累计最多40次发送、输入≤600000、输出≤144000。旧阶段余额/次数不继承。额度耗尽终止BUDGET_EXHAUSTED，保留已就绪版本。单次请求和token上限不等于费用授权；真实执行包还须具备可核对费率/金额封顶，无法证明剩余费用足够最大预约则拒绝发送。
- deadline_at=操作创建PG时钟+600s，含排队、重试退避、租约恢复，持久保存且不随重启重置。单调用timeout=min(120s,剩余deadline)。PG时间判断持久期限，进程monotonic用于单次等待，不能用浏览器时钟延长。超时发终态timed_out，已有内容留存。
- 自动传输重试仅限明确HTTP429/502/503/504、未有有效正文，且该Provider经验证的契约/响应证据能确认本次未执行或已停止；仅收到网关502/504不满足此条件，否则OUTCOME_UNKNOWN并隔离槽，最多每步骤1次/全操作2次；退避2s，Retry-After仅接受表示0–30秒的整数，HTTP日期或其他值停止自动重试，超界或剩余时钟不足停止；两者取较大。请求超时、连接在发送后断开、SDK结果不明、JSON语义不正确不属自动传输重试。401/403/不支持能力/SSRF/硬安全失败立即停。
- 格式修复仅schema/本地引用结构可定位错误，输入保留原要求和固定错误列表，不追加新教学目标；每步骤1次/全操作2次。修复后仍不合格则该步骤failed；硬安全失败不可通过修复绕过。已确认错误修订须显式新操作，由T003定义确认，不靠模型严重度触发整课重生成。

active操作owner最多1、course最多1、实例共享PG全局活动worker槽2；用户POST可排队但每owner只能有一项活动操作。无空worker槽可留queued到deadline，不能取得租约再不计时等。全局槽是执行并发限制，API排队不占槽；deadline扫尾不需要调用槽。

## 5. 取消、澄清与主动调整

取消是owner+CSRF+幂等POST，非模型调用，允许catalog_only中停止既有操作。事务置cancel_requested、递增epoch、撤销旧token并持久事件；未开始步骤标cancelled。已提交ready保留；在途Provider尝试尽力中止但仍计入，不能保证不收费。立即围栏后由扫尾在下一轮转cancelled；无在途发送可释放槽，在途/结果未知则按§3隔离槽到可靠结算；已终态取消为同状态的200无副作用，不改写succeeded/failed。取消先持锁则晚写不得发布；ready先提交则取消保留该准确版本。

学生点击“调整大纲”先取消当前活动操作，界面须等终态；输入草稿只保存在前端或已有草稿机制，不触发新调用。提交adjust_outline需明确影响摘要和新生成成本上限确认，然后新键/新操作、expected_head_version CAS；旧基线已变化409。不是在生成中偷改同一计划。恢复/补生成使用resume，澄清用clarify，正文局部调整用revise_scene；全部新操作、共享课程累计预算，旧收据不改写为新操作。客户端必须显示“将开始新的生成操作”，不靠刷新/重连提交。

resume只允许基于自己课程终态操作及当前head，保留已就绪准确内容，生成缺失/失败及其依赖后代；没有可恢复项409。clarify要求source_operation处于awaiting_clarification且仍是当前基线，非空补充1–4000字。source_operation、course、base版本必须同owner；省略基线不能自动取最新。head=null时expected_head_version=null；其余正整数。新调用不复用旧操作预约。

## 6. 局部修订与依赖传播

revise_scene绑定准确基线清单、scene_id及instruction；简单重解释仍是本任务局部修订，导师纯问答另属T003。服务计算目标场景及有向依赖后代集合，不由客户端删减；在发起请求前可用GET影响预览（只按kind/基线/scene计算结构依赖，不接收或判断自然语言instruction），POST绑定同基线与确认后的影响集合摘要。复核变化则409，不扩大范围偷花费。

目标解释/代码/共享示例变化使对应动作、题目答案、可视化、相关节点映射和必要后代成为新候选；局部请求不能改变全局目标/术语/示例；服务或候选校验发现越界时拒绝OUTLINE_ADJUSTMENT_REQUIRED，不自动升级。学生另选adjust_outline后，按全课重新预览并显式提交。预览requires_outline_adjustment仅表示kind是否为adjust_outline，不声称理解尚未提交的自然语言。候选若不能证明保持原共享约定则失败，不额外调用模型分类器或扩大范围。所有修订生成新计划版本；未受影响场景可复制正文为新plan绑定的场景版本，重算依赖/动作，代码不执行、无额外Provider费用，不能直接引用旧plan行冒充一致。

普通优化：旧head继续可读，修订候选先私有暂存；目标及所有受影响后代全部硬门有效后，同事务切到新清单。任一失败/取消/超时都不发布混合替换子集，旧head保持。本规则特指修订；首次或resume缺章允许逐场景追加（但不替换已有ready场景）。普通修订不会逐场景切head；首版不引入分支合并，head变化即冲突终止。

已确认缺陷：T003的禁用事实先使相应旧版及必要依赖不可访问；修订失败不能撤销禁用，旧清单可保留但不能继续当作正确内容。原作答保留原版本，不套新答案；失效评分/掌握度撤销规则由T003确定并在切换事务联动，未完成不得开放此功能。

## 7. SSE、刷新恢复与可选媒体

API见[补充OpenAPI](../../api/phase-1.5-generation.openapi.json)。GET操作/清单/事件只读，不调用Provider或自动resume。GET EventSource采用现有cookie，读取也验证owner；事件持久序号operation内从1连续递增，SSE id为seq字符串，data含schema_version、operation_id、seq、type、course_version可null及受控payload；事件不流出生成题答案/私有原文。连接15s发注释心跳（无id、不持久化），终态done后关闭。

事件类型：queued、started、clarification_required、outline_ready、scene_started、scene_ready、first_scene_ready、progress、cancel_requested、error、done。先提交PG再发送；scene_ready绑定准确course_version/scene_version_id，客户端GET该版本学习。first_scene_ready是scene_ready的附加里程碑，二者在同事务按序写入。T001旧事件协议保持，不向旧接口伪造新事件。

重连Last-Event-ID或after查询提供非负整数seq；同时提供两者须相等，否则422。从seq之后顺序重放，只能重放同操作。大于最新seq为409 EVENT_CURSOR_AHEAD，负数/非整数422。首版不裁剪事件，直到沿既有user删除策略级联删除；不提供伪造空成功恢复。新连接可以重复收到已投递但未确认事件，客户端按operation_id+seq去重。终态仍重放未读事件及done再关；after已等于终态last_event_id时直接204，不循环重连。无Last-Event-ID默认after=0，可直接读快照last_event_id再接流补后续。

场景至少含一块text完整正文（markdown去空白后非空）；允许text/code/exercise及受约束visualization块，动作引用本版本锚点；show_step要求锚点为visualization且step_index在实际steps范围内，其他动作step_index必须null。元素id在每步骤内唯一，next_id/highlight_ids存在于该步骤，不允许外部引用。首版可视化类型array/linked_list/stack/queue，非可执行JSON步骤，至多50步、每步最多32元素，提供文本替代；schema/action引用详见补充API。不得将任意HTML/JS嵌入步骤。计划正文≤16KiB、单场景持久正文+动作≤64KiB、单操作事件≤256条/单事件≤4KiB；progress最多每步骤一次，不能以token粒度无限写表。超过限额拒绝候选/终止，不静默截内容。

现有已审核缓存媒体可引用现有安全路径；缓存未命中首版不自动启动新的Manim或模型调用，只显示静态步骤/文本替代。用户明确请求Manim时另走经批准的媒体操作及其隔离/预算，未有新课程到媒体资格适配前隐藏操作入口。缺动画不阻断完整文本场景；题目必需图若缺少可理解替代则场景未就绪，不拿“可选媒体”掩盖。

## 8. 验证与退出边界

[正负例](examples.json)是待后续实现验证的契约用例；设计检查不计PG租约、真实HTTP、Provider或性能通过。T006/T013–T021按各自范围实现持久化/状态/修订/API，T035/T036进行组合与浏览器验收；具体分工以根账本为准。本提案获批不启动T003或实现，不把历史失败、H或旧额度转新链。
