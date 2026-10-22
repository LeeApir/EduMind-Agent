# 草稿质量、作答与掌握度契约 v1（提案）

依据[ADR-0026](../../ADR/0026-course-quality-and-learning-evidence.md)，继承[课程身份批准](../../ADR/0024-approval-20261021.json)和[渐进生成批准](../../ADR/0025-approval-20261021.json)。以下均为拟实施规则，当前无新运行入口。

## 1. 质量分层与可信确认

| 来源/状态 | 程序处理 | 不能推导 |
| --- | --- | --- |
| schema、owner、版本、清洗、执行安全硬门失败 | 拒绝候选、读取或操作；已可见版本新发现硬失败时追加禁用事实 | 不能用草稿、模型pass或人工确认豁免 |
| 学生feedback或模型opinion | 保存准确位置/描述/来源，状态pending；可显示“有待核实反馈” | 不变成confirmed，不强制隐藏整课、不自动重生成 |
| 已确认语义缺陷 | 受信维护命令保存准确绑定、原文依据/反例/影响及范围；追加禁用和依赖传播，触发派生证据失效 | 模型严重度、用户重复举报、另一模型赞同本身不是确认依据 |
| 不成立/无法判断 | 维护者记录not_confirmed及理由；保留原反馈和未知项 | 不能把不确定结果改成原模型pass或已签核 |

反馈定位到course_version、scene_id、scene_version_id及anchor_id，可选exercise_id/exercise_version_id；路径必须真实存在于该清单，正文引用由服务取准确快照，客户端引用文本只当描述。description 1–2000字符、去空白非空。服务分配反馈ID，客户端不能传verdict、严重度确认、owner或处置命令。旧版本反馈不应用到任意最新版；同摘要复用若需传播，必须通过服务已保存的依赖/来源关系定位，不按相似措辞全库撤回。

语义确认的可信主体是有本地维护权限的操作者（当前维护者Lee），不是Web用户角色。拟建本地CLI命令接受具体course/version/scene/exercise绑定和JSON证据文件，先dry-run输出影响清单，执行时绑定impact_digest和幂等decision_key；不增加HTTP确认/签核接口。证据记录author、来源类型、准确内容/答案摘要、引用片段与解释、确认时间。代码类反例可以是人工静态推演/独立既有受限离线证据，不能借确认运行任意模型代码；现有固定C许可不自动转用。模型可以辅助描述，不能充当唯一语义证据或确认主体。机械硬失败保存rule_id/version及可复现机器结果，程序可以直接确认该机械违规。

## 2. 禁用、撤回与依赖传播

确认按最小可验证范围处理：题目/答案缺陷暂停该题组的提交与答案反馈；正文或必需动作缺陷暂停整个场景；课程级原始目标/共享约定错误才按依据影响全课。题目缺陷可以仍保留同场景无关讲解/代码，返回明确的不可用题块，不展示已知错误答案。场景级禁用返回CONTENT_UNAVAILABLE，不通过旧版本GET绕过。

服务以准确场景版本依赖边及内容引用计算必要后代，保守暂停这些后代场景；不能仅凭课程同节点或字符串相似扩散。对同一缺陷影响多个准确题组/场景创建同一decision下逐项事实，每项保留原因与上游。原始版本/反馈/作答不改写，禁用事实追加。普通意见和普通优化无禁用效果。

确认事务锁owner→course→必要operation→按node_id排序的mastery锁，复核影响摘要/基线，再一并：写确认/禁用事实、给相关在途生成/导师输出设置失效围栏、撤销相关答案/映射核定与贡献、重算受影响掌握度/派生画像并置路径replan_required、保存owner可读处置摘要。不在该事务调用Provider；任何失败回滚、不返回确认成功，CLI报告失败待重试，不能只撤课程却保留仍生效的错误分数。原始错误意见不因此消失。

修订不会解除旧禁用。T002新候选全部硬门就绪且替换集合完整后，允许切换到新内容；新场景不继承旧答案核定。旧版仍保持禁用，准确新版本只有自己的核定资格。确认被推翻时追加decision_correction并保持旧贡献已撤销，不自动复活旧答案或评分；恢复正文须维护者重新核对准确版本/硬门并追加restore事实，依赖仍禁用时不得恢复；不会静默重评或重新授予掌握度。复核不要求重走全课语义审核。

## 3. 练习身份、公开投影与原始作答

首版保持现有短文本题型，以一个exercise_id代表2–4题的题组；question_id在组内唯一且跨同题修订稳定。exercise_version_id绑定准确scene_version_id、题干/输入类型/答案/解释/评分规则摘要。复制到新plan的未改题组保持逻辑exercise_id与assessment_digest；真实变更分配新exercise_version_id，不把旧答案覆写。课程与场景可包含零或多个题组；计划不固定练习数量，正文/动作仍受T002总字节上限。

公开题块在T001/T002 ExerciseBlock基础上增加exercise_version_id和items（每题question_id、question、input_type=short_text），question顶层仍为组说明；不返answer_key、solution、核定原文或私有digest。展示每题输入、可提交部分作答，答案长度≤500字符，不接收客户端score/node_id/qualified。一次POST必须包含至少一个非空作答，最多4题，重复ID、组外ID和未知字段422，绑定不符404或409。提交新作答仅接受当前head清单，历史清单只读；head已变返回409 STALE_COURSE_VERSION，不自动移植作答到新题。空白项按未作答保存。

POST提交只进行确定性校验/保存，返回201 attempt_id；GET作答返回原始学生输入、最新反馈有效状态。未完整填满组内题目为incomplete，score=null且不展示答案/逐题对错，避免部分提交先偷看其他答案；继续作答使用新key形成新attempt，不更新旧行。首次完整提交才允许按当前私有答案作全组比较并展示当前版本的解释；此前已主动求助/看答案仍可练习，但不作为独立测量。

反馈分开表示reliability=provisional/verified/withdrawn、completeness、comparison_score与mastery_effect。默认provisional仅指“与AI参考答案的暂定比较”，不能宣称正确性已独立核实；逐题对错同样标暂定。不调用模型判卷。去NFKC、casefold和折叠空白的字符串比较沿用quiz-exact-text-v1，不能据此声称理解同义解法/证明代码正确。无可靠答案也可保存作答和显示暂定解释；没有合法私有答案时反馈unavailable/score=null，不伪造0分。

历史作答保留原始学生文本。题组/答案已禁用或撤回核定时，GET与重复POST的后续读取只返回withdrawn/null比较和原因，不再显示错误参考答案/解释。原始打分/旧回执保存在私有审计，不能用幂等重放泄漏失效“正确”结论。POST收据只含attempt_id，因此可以稳定重放；读取投影随最新可见性事实变化。无论题目正文能否读取，owner仍可读自己的原始作答（始终转义），不含被禁用的模型正文；其他owner统一404。

## 4. 可靠答案与单节点核定

只有可信维护者针对准确题组完成两份独立条目才可准入：answer_attestation验证题目可判定、完整答案/解释、确定性评分适用性；mapping_attestation验证该组确实测量指定版本的一个知识节点及对应课程关联，不仅是词命中。每份有authority、rule_version、版本/digest、来源/可复核理由与核定时间；可以同一人执行，但不得把模型输出原样当独立依据。格式/身份/摘要由程序重算，权限与事实依据不能由客户端自报。

首版只提供维护者核定，不引入自动语义验证器或任意代码执行。确有多个测量节点的题组不得复制同一分数到多个节点，保留课程表现，待将来独立拆题批准。缺节点关联或可靠映射不阻断学习/作答，只阻断正式贡献。课程级关联不代替题组映射，用户自选节点也不直接成为可靠证据。

核定只针对自己的准确版本，不能让整课变成已签核或进入catalog。题干/答案/关联/实际教学上下文/必要上游发生变更则原核定不适用于新版本；已确认缺陷撤销受影响旧核定。维护命令无模型调用、不改变原始正文，不提供学生端“确认答案”按钮。

## 5. 首次独立作答与正式贡献

必须同时满足：

1. 提交时该准确课程/场景/题组可读可提交，全部必要依赖有效；answer与mapping核定均在本次首次完整作答提交事务前有效。
2. 该owner此前未对同题组assessment_digest完成过作答，也未请求答案/提示/相关导师帮助；本次所有题都有非空输入。这里的独立仅指系统可观测记录，不声称证明外部未求助；无法确定既有帮助绑定时保守不准入。暂定/已看答案作答不能后来追认；后续重做只作练习。
3. assessment_digest对题干/答案作NFKC/casefold/空白归一化，忽略展示ID、排序与解释，沿用现有catalog question_set_digest识别规则；另记录仅对题干集合规范化的question_stem_digest，同题干修正答案/换ID仍不重置已作答/辅助资格。题干须包含独立作答所需条件，核定不能接受靠隐含版本上下文才可判定的题。两种摘要任一已有完整/帮助记录就不得当新独立测量。同owner跨新课程/新ID/重排序去重，并检查已有目录同digest的完整成绩。旧目录无stem列时，从原作答所绑定的准确保留题干快照/资源版本确定性计算stem及完整性（不能用当前最新版），匹配任一摘要的历史完整作答或帮助记录都阻断新资格；原件缺失或无法判定时返回PRIOR_ASSESSMENT_UNKNOWN、只留课程表现，不猜测未作答，也不改旧成绩。生成练习去重不会追溯删掉旧目录成绩或改变其原资格。
4. 服务端按准确核定节点和确定性规则生成分数，写正式证据；不从路径current、模型打分或客户端取节点/score。

每个完整题组只形成一次quiz_attempt，不按每题拆成多个加分事件；继续使用mastery-v1数值规则。部分作答不抢占首次完整名额，但求助/揭示答案会永久消耗同题组的独立资格；首个完整作答即使provisional/核定不足/答错，也消费名额。不因撤销第一份贡献而把第二次练习自动晋级。

首版没有独立提示/看答案端点，解释仅在完整作答后读取；若后续新增揭示入口必须先登记暴露事实，不能绕过本准入规则。求助标记和作答/答案揭示共享owner锁，避免并发先拿答案再伪装首次。发起导师请求时，无论题组是否已经开始作答，都把当前场景及选入上下文的上游场景/历史轮次涉及题组记assisted（无意图分类器，不额外模型调用），在Provider请求前持久化；未来同题干/同题组的复制也继承帮助标记，即使导师失败也保留求助记录并告知用户。用户可只读正文，浏览进度、喜欢/跳过、自述和资源选择不直接成为新自由课程正式掌握度事实。

## 6. 准入、撤销与可重放派生状态

新增源标识与审计表，不把新自由课程伪装成旧published resource：

| 载体 | 最小字段/约束 |
| --- | --- |
| free_course_feedback / quality_decisions / visibility_facts | owner/course/准确清单及场景/题组/锚点、描述或依据、来源/authority、digest、decision_key、impact绑定、时间；事实只追加，跨域复合外键 |
| free_course_exercise_versions / attestations | owner/course/scene_version/exercise/version、私有题干答案及规则摘要、assessment_digest、单节点核定（可缺）、authority/依据及撤销事实；正文/核定只追加 |
| free_course_attempts_answers | owner/course/清单/场景/题组版本、答案原文、完整性、提交时反馈快照、首次名额/辅助快照、request_digest/幂等收据；原作答不改写，不能与T002 provider attempts混表 |
| free_course_assessment_exposures | owner+assessment_digest及question_stem_digest、help/solution/first_complete、绑定/时间；只追加，owner锁下确定首次资格 |
| free_course_evidence_admissions / revocations | 准确attempt/attestation/mapping/learning_evidence ID及digest、有效节点/规则、原因/decision/时间；一作答最多一份贡献；撤销只追加且幂等；准入与learning_evidence循环引用使用同owner复合DEFERRABLE外键，提交时必须闭合，不允许临时缺资格记录落库 |
| learning_evidence（增量列与检查） | source_protocol nullable，free_course_attempt_id nullable并同owner外键；新quiz_attempt必须有free-course-v1来源及有效admission；增evidence_correction类型，corrects_evidence_id引用被撤销原证据 |
| free_course_tutor_turns | owner/course/准确清单场景、operation、问题、上下文/配置非秘密摘要、正文版本、引用锚点、状态、可见性、时间；复合绑定及幂等 |

旧learning_evidence的source_protocol保留null，不回填；原目录/legacy/planned资格保持。所有写入和重算入口都必须分派来源：source_protocol=free-course-v1时显式校验有效准入且未撤销，evidence_correction仅作审计触发不计分；未知非空来源默认拒绝。不能沿现有“没有catalog_assessment就eligible”的默认分支接纳新来源。新free_course_attempt_id不能冒用旧resource_id/learning_unit_id。

准入与作答同事务写LearningEvidence、admission、mastery revision/current和path失效；仅有效贡献参与mastery-v1。新证据按数据库created_at/id稳定顺序与旧有效事实合并重放。撤销时追加revocation和evidence_correction、排除被撤销新事实再从全部有效历史重算，不做score相减，不重新评价旧答案，也不改变旧规则对旧证据的资格。新派生节点状态保留recomputed_from与原因指向 correction；原revision不改。无剩余有效事实回到unseen，不能保留旧“已掌握”。

修订分两类：普通优化替换题组/答案/映射/必要依赖时，在T002切新head同事务撤销受影响旧核定和贡献，保留旧作答为历史、不给新题补分；正文无关排版且题组正文/评分规则、必要依赖绑定和映射的规范字节均完全未变时可以保留旧已准入事实，但新版本的未来作答仍需自己核定，重复名额不重置。已确认错误则在禁用确认事务立即撤销，不能等重生成成功才清除污染。确认旧错误只作用于free-course-v1相关事实，不借此全库清理旧课程。

掌握度及引用它的画像/路径不得显示失效贡献：路径replan_required置真，重新规划前标为待更新而非准确当前推荐；画像派生掌握/易错结论按有效证据重建，用户自述和显式偏好保持原文/来源，不删原始观测。所有相关旧写路径也使用来源分派后的同一重放入口，避免后续旧课程作答把撤销的新事实又算回。此为兼容实现要求，T019/T021须实际PG验证，不由本设计证明。

## 7. 导师提问、补充解释与预算扩展

新导师只对当前owner的当前head准确course_version/scene_id/scene_version_id提问，历史版本保持只读，不从UI路径猜上下文。可见草稿无需语义pass；私有答案/解释、未就绪/禁用内容、其他用户记录、Prompt/密钥不进入上下文。导师得到原目标、当前公共场景、最多2个准确必要上游的公共片段、有据且相关的画像摘要、至多2轮同场景同版本且全部来源仍有效的可见历史；未知保持未知，自述不升格为掌握。

输入引用在请求和输出提交时再验证，源场景禁用/修订头变化使迟到回答失效，不自动换最新版。已ready导师回复也保存全部上下文依赖绑定；之后任一来源被禁用、答案核定因已确认错误撤回或所用画像证据失效，GET turn必须再次检查并返回invalidated、markdown=null、anchor_refs=[]和固定原因，原用户提问仍可读，旧回复仅私有审计保留，不能靠GET/收据继续展示。普通修订未禁用原来源时，已完成回复可作为准确旧版本历史读取，不冒充新课程解释，也不选入不同版本的新轮次上下文。plain Markdown输出经清洗，最多6000字符，引用只允许上下文锚点；没有引用则可以明确一般解释，不能声称已引用某份证据。回复标记AI解释，不具签核、缺陷确认或正式评分权限。会话不执行工具、不联网/RAG、不调用其他角色、不得运行代码。

纯提问创建tutor_turn持久操作，POST返回202 operation_id/turn_id，再经T002 GET操作/事件及GET turn恢复；本补充扩展Operation.kind=tutor_turn及事件tutor_ready（只含turn_id，不含正文/答案）。该轮最多1次发送、总90s含排队、单调用≤90s、输入≤16000输出≤2000token，不自动传输重试或格式修复。生成操作仍活动时导师请求409 OPERATION_ACTIVE，学生可等完成或主动停止生成再提问，不自动取消、不排第二个活动操作。使用相同PG预约、owner/course活动唯一、全局2槽、未知结果隔离及单课40次/600k输入/144k输出累计池，不能另开聊天无限额度；Provider配置和取消/期限规则与T002同义。预算扩展不修改create/resume/revise原13次/600s，实际调用仍需另行授权。

提交提示可能泄露答案的现象无法靠关键词可靠判定，因此§5保守记录上下文涉及的题组assisted。提交时需确认界面提示“本次上下文涉及的练习将按辅助学习记录”；无确认字段则422，不发送。已有解决方案不可跨版本复用来声称对新题有可靠结论。

“更简单/更深入/换例子”若是独立导师回复，只保存turn，不修改课程；若用户选择更新课程，则走T002明确的revise_scene/adjust_outline影响预览与成本确认，不新增隐式模型调用、不在回答里静默改题。老师回复不是学生事实，不自动更新正式画像、成绩或错误记录。

## 8. API、幂等与兼容

[补充OpenAPI](../../api/phase-1.5-quality.openapi.json)均planned，写入沿现有会话/CSRF/owner+路由+键幂等。反馈和作答是普通REST；导师为持久操作，其GET事件扩展遵循T002序号重放。请求未知字段422、缺会话401、CSRF403、外域/不存在404、基线或不可提交409。所有私有响应no-store，无异常原文。反馈/作答不调用Provider；catalog_only允许读取自己已存在记录及提交问题反馈/取消，禁止新自由课作答和导师发送（409 FREE_COURSE_DISABLED）；默认旧目录入口不受影响。

同键同请求重放原feedback_id/attempt_id/operation_id，不新增贡献或调用；不同请求409。学生原始作答GET即使对应题组禁用仍可读，但反馈只给withdrawn/null，不回显失效答案。越权重放也不得透露原ID。恢复页面只GET，不重发POST。

T001/T002场景公开投影由本补充增加题组版本/输入结构及disabled题块；题组禁用时整块显示reason而非私有题目或答案，不用旧ExerciseBlock绕过。场景级禁用仍409。新增导师事件不在旧API伪装为scene_ready，不改旧课堂/题目评分端点；T020按累计批准合并schema，T021实际兼容验证。暂定作答不进入旧quiz接口逃过新准入。

本提案无教师编辑后台、跨owner分享、新Provider、全量语义审核链、Phase2题库/多角色/RAG/报告或任意代码执行。[用例](examples.json)只是设计材料，不代表真实PG/HTTP/Provider/学习效果验收通过。后续T017–T020各按任务交付，T005仍冻结独立质量与性能口径。
