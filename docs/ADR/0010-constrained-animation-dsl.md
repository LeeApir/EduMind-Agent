# ADR-0010：受约束动画 DSL、审核与来源隔离

- 状态：**Accepted**（2026-10-04，用户批准A–D及附件）；不是已实施或正式验收通过。
- 日期：2026-10-04；任务：PHASE-1-T022，实施T023–T029，验证T037/T040/T041。
- 依据：[PRD](../PRD.md) §0.1/§3.3/§8.2/§8.3、[Phase 1验收计划](../acceptance/phase-1-acceptance-plan.md)。
- 继承：[ADR-0004](0004-trusted-animation-jobs.md) 沙箱/媒体/owner、[ADR-0007](0007-curated-course-catalog.md) 目录门禁、[ADR-0008](0008-provider-credentials-and-egress-boundary.md) 出站/凭据/回退、[ADR-0009](0009-durable-animation-queue.md) PG/outbox/epoch/租约/取消/清理。
- 具体提案附件：[DSL v1契约与schema/示例](../agents/animation-dsl-v1/README.md)、[审核Prompt](../agents/prompts/animation-dsl-review-v1.md)、[生成Prompt](../agents/prompts/animation-dsl-generate-v1.md)。A–D批准包含这些附件的准确digest，不只批准标题；[原始提案清单](../agents/animation-dsl-v1/proposal-manifest.json)保存本文件及7项附件SHA256，清单本身的digest登记在活动账本/日志，批准后保留原始清单作历史依据。

- 批准记录：[用户批准登记](0010-dsl-approval-20261004.json)，准确原始提案清单SHA256为 `25d44d3a80967fe1f95a6fbe8a81168145aa43902e00801b627b5861b5e94c3f`。附件与清单中的Proposed/提案保留批准前原文，当前批准状态以本登记为准；审核/渲染仍待实施验证。

## 现状、目标与替代方案

现有`animation_templates.py`只接受两个已审核链表模板及最多8个节点整数参数；模板缓存包含源/审核/镜像/字体/渲染/字幕版本且共享字节需独立owner绑定。`animation_renderer.py`对固定源做AST黑名单/有限导入检查后在受限Docker执行；其中有限os/json例外是旧模板的受信配置，不可视为模型源码权限。`container_runner.py`当前只认6/7条固定6s字幕；`review_agent.py`当前审核讲解/代码/练习，不会因为一般Review存在就已支持DSL。Job/媒体数据库没有DSL候选、动态来源/撤回字段。ADR-0009刚获批准，Redis/Celery尚未实施。

PRD要求九种动作及缓存/模板/完整DSL优先级。直接生成Python、宿主执行、“仅让LLM看代码就放心执行”均不能达到安全边界；无限动画语言/任意素材超出Phase 1。选择有限JSON动作+逐步模拟+受信确定性编译+独立审核+容器渲染。v1针对≤8节点的小规模数据结构过程；不声称覆盖所有约30图谱节点或替代完整程序执行。

## A. 版本化数据语言与资源上限（推荐）

1. 冻结附件`animation-dsl/1`的精确根字段、九动作、对象ID/引用、状态与字幕语义；所有对象拒绝额外字段/未知动作，schema使用本地内部引用，模型不得传Python、模块、路径、URL、导入、表达式/控制流或自定义schema。允许的文本只作显示字面量，不作程序指令；不能因为caption含一段代码就执行它。
2. 字节≤64KiB、深度≤12、节点累计≤8、指针≤4、边累计≤16、动作≤120、节点值-999…999；固定8×3整数网格且格位不重叠。strict int拒绝bool/float，拒绝重复JSON key/非有限数/非法UTF-8/控制与双向字符。边可指向NULL，不允许自环；swap只换值，compare根据当前值计算。悬空/前向/错误类型引用、删除后ID复用、重复活边、同节点compare/swap等整体拒绝。
3. 所有步骤200ms量化串行，总计划时长30–90s；字幕逐步1 cue对应1动作，文本和时间直接从可信轨迹生成，不使用模型外部SRT。资源上限不是模型建议值，运行时必须强制执行；节点过多或DSL不满足目标时明确拒绝/合适模板降级，不能静默扩容或削弱PRD验收。
4. [结构有效九动作示例](../agents/animation-dsl-v1/valid-all-actions.json)与[拒绝候选](../agents/animation-dsl-v1/invalid-examples.json)区分schema、引用/资源、事实审核；文本/复杂度schema合法也可事实错误。这些材料没有正式内容签核/真实渲染，不用于充当T037/T040正式通过。

## B. schema、Review、编译与隔离各自职责（推荐）

1. 本地严格解码/schema/逐步模拟生成可信帧，检查所有动作后才允许进入下一步；编译器固定映射到版本化受信渲染原语/Scene库，不使用候选可执行字符串，候选ID不作为变量名。输入文本用AST Constant，编译源受≤256KiB/≤20000 AST节点/≤1s预检限制。相同规范数据+源版本+runtime编译字节/轨迹/SRT一致，跨硬件MP4逐字节一致不作为保证。
2. 本地编译与AST检查通过后，ReviewAgent使用独立review档位审完整候选+可信帧+最小版本化教材/场景参考（参考≤8KiB，缺失/超限不可用，不截断装作已核对）。审核模型不执行源码；生成模型不能给自己签核。准确检查指针/边更新、compare/swap、字幕、复杂度、知识点与目标。生成quality档位，所有出站/重试/修正需ADR-0008授权/版本/SSRF/预算；没有Provider权限时不发请求。
3. 审核Prompt/严格输出版本`animation-dsl-review-v1`，pass只能空issues；revise/reject须具体位置与问题，最多16条。最多2次定向修正，每次全量重新校验、编译与独立审核，所有新hash重新签核；reject终止，审核失败/截断/不可用单列DSL_REVIEW_UNAVAILABLE，不因不可用自动修正/换厂商。schema/AST是强制拒绝门，Review pass不能覆盖它们。T025新增T024依赖，以保证最终审核凭证绑定实际编译摘要；不降低原验收。
4. 最终不可变正式**候选**不是正式媒体。T025通过Alembic建立owner/单元/场景版本复合约束的候选与审核记录：规范DSL/轨迹hash、schema/validator/compiler/policy/Prompt源码hash、compiled_source hash、graph与scene/reference digest、受限生成/审核来源、pass审核版本及安全issue类别；任何候选变更新ID/hash/审核记录。失败候选只保留固定错误/索引/摘要，不持久未审核自由文本、原始Provider错误或完整对话。审核pass候选可随owner学习数据保留；不新增匿名数据TTL或延长2h凭据。没有pass不得创建可渲染DSL Job。
5. T027重新校验候选与版本、重编译并核对批准hash，再检查AST。DSL生成业务源只开放最小白名单结构/符号/调用接收者/参数形状；禁止任意导入、dunder/reflection、os/json/I/O、eval/exec、循环/控制代码。旧模板黑名单不是DSL准入。语法/导入预检若需执行只在相同受限容器内由固定runner完成，宿主不import/run生成模块。
6. 固定runner/Manim的合法内部媒体I/O与生成业务源权限分开；沿用ADR-0004/0009的CPU2/RAM1GiB/pids128/120s/禁网/只读根/尝试挂载/256MiB硬配额。容器无Provider/KEK/DB/Redis/socket，不下载素材，无宿主回退。实际MP4解码/时长30–90s/15fps、字幕N条与可信轨迹逐项一致、路径/文件/摘要/配额检查均通过，再持有有效lease及当前审核资格同事务正式发布。T037人工检查实际步骤；LLM审核和AST不能替代它。

依据：[JSON Schema对象规则](https://json-schema.org/understanding-json-schema/reference/object)、[Python AST](https://docs.python.org/3.11/library/ast.html)、[Manim Text](https://docs.manim.community/en/stable/reference/manim.mobject.text.text_mobject.Text.html)、[Docker资源限制](https://docs.docker.com/engine/containers/resource_constraints/)。这些分别用于字段封闭、结构核验、纯文字渲染和硬资源约束，不证明事实准确或隔离自动成立；实际安装版本继续使用锁文件/镜像摘要，而非stable/latest网址版本。

## C. 缓存身份、owner与撤回（推荐）

1. 旧P0模板白名单参数及共享缓存保持原语义；DSL包含自由字幕/标题，默认**owner隔离，不跨owner复用DSL文本或媒体**。新增私有DSL缓存命名空间，由服务端owner UUID派生稳定namespace摘要（不可用客户端输入替换，不含会话hash/Key），绑定仍用owner复合外键；namespace/cache key不回传或作为读权限。不是靠“模型应当不写私人信息”允许共享。仅取最小公共课程上下文/目标生成，不自动发送私人聊天；意外私密文本不外流给其他owner。
2. 确定性键包括namespace、目标知识点/scene version/reference hash/graph version、规范DSL/hash、schema/语义政策/编译器源码及轨迹hash、生成/审核Prompt与规则/模型来源版本、生成采样配置摘要、编译源、Manim/镜像/字体/渲染配置/字幕版本。来源由网关填入实际provider_type/model_id、adapter/capability版本、已知model_revision（未知显式unknown）及目标身份摘要，不采信模型自报，不存Key/密文/DEK/临时handle/Cookie/完整URL/用户连接串。连接ID与config_version作为owner内部审计元数据可记录，凭据版本不进入内容键；清理/换Key不抹改既有正式来源。具体来源字段受固定长度/字符校验。model alias不证明模型权重不可变；unknown revision时缓存只声明当时冻结配置的来源，不能自动发现厂商后台替换，配置/版本或新验收变化必须新namespace版本，不把旧成绩转授新模型。
3. 输入请求映射以owner+target版本+规范意图/参数+冻结模型/策略/runtime身份保存至已审核candidate/media key，同参数且这些版本不变时先找已审核DSL；无需再次模型调用。候选/媒体缓存每次查验当前资格和文件完整性，不以相同参数跳过新规则/模型/目标版本。先查已验证预渲染/参数化模板，只有不适用时进入DSL；失败候选与半媒体从不进入正式缓存。多Job同key沿用唯一约束/不可覆盖发布，不承诺消除重复计算。
4. T025/T028通过版本化政策目录和候选状态撤回记录（候选内容不可变，撤回记录只追加）判断资格；状态passed不等于永久可用。候选、当前compiler/rules/runtime安全准入或课程/scene撤回时，禁止新Job/绑定、queued领取、running正式发布和媒体/导出读取；已成功Job保持历史终态，不删除或改成failed，授权读取返回404/不可用。没有秘密复活、临时绕过审核或把老媒体转为新规则通过。新版本须重新编译/审核并创建新candidate；危险旧版本停用不能只更新缓存键而让老引用继续读。
5. 发布锁顺序为Job→目标课程/scene资格→candidate→政策版本资格→缓存键协调锁→媒体/绑定；撤回只按同资格行顺序锁定目标/candidate/政策，不回锁Job/cache。这样撤回先commit则发布拒绝，发布先commit则未来读取立即按撤回拒绝；不等待异步扫Job才生效。GC遵守ADR-0009缓存锁+非锁定引用/有效意图读取，不反向锁资格/Job；有正式引用的不可变媒体不删。临时产物/未引用孤儿按原24h规则，自动删除学习数据/候选不在本提案。

## D. 请求、队列、失败降级与开放门禁（推荐）

1. 旧`POST /api/learning-units/{id}/animations`模板JSON请求/回执保留。拟由T028增加owner/CSRF/Idempotency-Key保护的`POST /api/learning-units/{id}/animations/generate`（fetch+ReadableStream），请求只包含scene_id、scene_version、固定goal_kind与有界整数参数，不接受DSL/Python/owner/Provider URL。v1 goal_kind由受信知识点策略映射至比较/交换/遍历/链表插入/删除；精确请求schema与SSE字段在T028固定并测试，不扩大九动作/自由代码边界。catalog_only拒绝动态路径，不因保存BYOK或模板请求自动生成；现行OpenAPI只增加Proposed扩展注记，不声称此路由已上线。
2. 模型阶段发生在已授权API进程内，不进入Celery。T028用单独PG准备操作保存owner/目标版本/幂等摘要/固定阶段/服务端随机执行持有者token（观察连接不得接管）/不可变原会话绑定（服务端session哈希及expiry，非Cookie）/绝对deadline（≤180s及会话expiry更早者）/结果Job引用，**无Key/密文/handle/未审核文本**。有效会话/版本/操作绑定按ADR-0008核验每次生成/审核/修正，临时Key只按ADR-0008/现有注册表的精确operation/purpose/connection/model绑定单次领取：只有生成/修正/审核都解析到同一已授权连接/model_id及同一operation purpose时，该lease可覆盖有界流程，审核仍是独立调用；审核若选另一连接/model/purpose，必须事先有独立且精确绑定的有效凭据/handle，不能复用或重领生成handle。缺审核凭据即不可用/合法模板降级，不偷偷改审核模型；不能后台重放；等待期间不持长DB锁。最多2个活跃准备操作/owner，预约时owner行锁串行检查活跃数；到期停止模型出口及迟到候选保存，记录固定失败。
3. 准备操作与渲染Job分开：SSE只给安全阶段/状态与最终Job ID，不流出未审核DSL/字幕；Job仍queued/running/succeeded/failed/cancelled，只有candidate审核/编译通过才可同事务关联它并创建Job+queued事件+celery outbox（缓存命中则succeeded绑定）。准备操作结果引用与Job预约在同事务提交，取消/到期/目标版本变化的操作不能留下可渲染Job。事务顺序准备操作→Job→目标/candidate/政策→附属行；Worker不反向锁准备操作。传输消息仍仅job_id/epoch/schema_version，Worker无模型出口。未命中Manim才是异步渲染Job，不把准备中当queued渲染或承诺模型进程重启恢复。
4. 相同owner+操作类别+幂等键+摘要只回放原准备操作与Job，异摘要409；准备中第二连接查询/观察旧操作，不并发第二生成。T028增加owner GET准备快照/取消接口，用于断线恢复：保存阶段/绝对deadline/Job引用，不承诺暂时token重放；API重启/持有者死亡不能重新生成，deadline到期固定失败，新生成需新键且新授权检查。GET可在到期时CAS收尾，不声称“当前running一定活着”。只有原执行持有者POST连接断开触发当前准备操作自动取消/凭据清理，依据PG持有者token CAS防迟到连接操作；同键观察连接断开只关闭观察，不取消持有者、不重领Key。显式准备取消接口经owner/不可变原session/CSRF/幂等校验后按准备行锁取消；按ADR-0008清理当前有限操作，不继续秘密调用模型；已提交无凭据渲染Job按PG恢复，不因取消准备操作而抹改已交付Job，handoff后使用现有Job cancel。准备取消与handoff共用准备行锁，先取消则零Job，先handoff则返回Job引用及明确使用Job cancel。
5. 生成/校验/编译/审核失败在API阶段有界结束：仅当同目标/参数可以无损映射到**当前已审核**链表模板时降级一次，复用既有模板缓存/Job，标明template/fallback_reason_code/原generation ID，不能执行无效DSL前缀、换知识点或谎称生成成功。schema/安全拒绝可降级但不重新出站；凭据/预算/权限失败先终止Provider，仅已有合法owner课程/模板可零模型降级；会话/owner/课程失效不降级。没有适用模板则ANIMATION_UNAVAILABLE，无媒体与新渲染Job。
6. 渲染阶段失败先按ADR-0009恢复有限两次领取；最终failed且有合法模板替代时，T028在准备操作中不可变originating_session_hash对应原session仍存在、owner匹配且当前DB时间早于原expires_at（不得用后来新guest/同owner新session或更新Key延长）、目标未撤回、原请求明确允许且绑定同session/目标/参数摘要的该降级授权仍有效且唯一(original_job_id, fallback_kind)尚不存在时创建一个新模板Job，保存fallback_of及固定原因；原Job仍failed，事件只加受限fallback Job引用（经T028契约扩展）。不把运行中Job静默换render_kind/覆盖候选/旧终态，不自动循环DSL↔template。缺会话/资格/适用映射则只报告原失败，用户新请求后可取得模板；恢复后明确重试仍新Job/新键。模板也失败即终止，不降级到宿主/远程素材/扩大容器。正式DSL可用率的原槽发生模板降级仍记DSL失败，模板体验可用单列，不能用降级成功抬高DSL质量/可用性分子。
7. T028增量迁移Job/media的render_kind=template|dsl、candidate/fallback来源及owner约束；回填旧记录template，保留模板ID/版本和旧响应。template必须有原模板身份且candidate为空；dsl必须有owner复合外键匹配目标场景的passed candidate，模板身份为空，不用假模板ID隐藏来源。DSL media带owner及candidate来源，template media仍允许共享；数据库CHECK/复合外键强制两类互斥。DSL媒体/导出增加准确generated_by/source_versions，不能冒用reviewed-manim-template头。具体新增公共字段/事件/路由在T028同步OpenAPI及兼容测试；本批准只授予上述目的与边界，超出需补ADR。T025候选/审核迁移与T028准备/引用迁移均须隔离PG实际往返/锁验证。
8. T023本地拒绝矩阵；T024注入/确定性/AST；T025 fake Provider及PG hash/版本/撤回；T026生成/修正/降级；T027真实容器/取消/父子死亡/清理；T028 owner/幂等/断线/撤回/降级竞态；T029明确来源与按需UI。T037≥100合法DSL槽且九动作全覆盖、恶意输入100%拒绝、100模板/100缓存/20未命中及实际画面核对；T040/T041按独立新配置/预算验证模型DSL，不拿契约示例、Fake或目录成绩代替。批准本设计不恢复旧T033，不授予真实Provider额度或动态入口/部署开放；T035及后续新独立验收仍是门禁。

## 批准与后续执行

用户已明确批准A–D整体及链接附件：九动作与小规模资源上限、独立审核/固定编译/容器、owner私有DSL缓存和来源撤回、API内有界生成→无凭据渲染Job及明确模板降级。

准确提案清单及实际用户原话已登记，解除T022设计批准门禁；T023–T029按依赖/优先级逐项实施验证。独立AI读者检查不是人工批准，T035和后续动态开放/真实模型预算仍另行批准。

本任务仅准备文档/schema/示例并执行静态核验，不安装新运行时、不改数据库、不渲染媒体、不调用Provider。未运行的后续验收不记通过。提案变更先更新准确digest，批准后逐任务验证、本地提交，不push/merge/部署。
