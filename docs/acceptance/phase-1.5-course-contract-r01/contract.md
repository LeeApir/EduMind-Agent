# 自由课程最小数据与访问契约 v1（提案）

依据[ADR-0024](../../ADR/0024-free-course-identity-and-owner-access.md)。规范中的“必须”约束后续实现，不表示运行端点存在。用户只需批准具体A—D，不重复确认A—F产品方向。

## 1. 课程身份与来源

`course_id`、`scene_id`、版本行ID由服务端分配UUID。课程属于现有`users.id`；客户端和模型不能指定owner、签核、摘要或持久化版本。逻辑场景ID跨修订稳定，顺序和依赖属于计划版本，不能把数组下标当身份；删除后再添加的新场景使用新ID。

课程保存不可变的原始目标、教学语言与代码语言。后续目标/偏好调整创建只追加请求快照，保留原目标；模型计划是建议来源，不能覆盖原始要求。请求快照保存原文、用户补充、有据画像ID/版本或null及实际采用证据快照、非秘密Provider配置引用和协议版本。未知画像保持null；自述不自动成为掌握度。服务验证画像属于同owner。模型不提交来源hash。

计划保存请求快照ID、目标条目、共享术语/示例/表示约定、场景顺序/目的/预期表达方式与依赖。每个目标标明 `user_requirement` 或 `planner_suggestion`；前者引用真实请求快照及原文片段，禁止虚构引用。合法结构不代表覆盖质量已经验证；完整原始目标始终保留供生成和验收。具体规划内容schema、场景规模和调用限额由T002冻结。

## 2. 最小持久化模型

下列新表均包含`user_id`；所有跨表引用以包含user_id/course_id的复合外键限制同owner/同课程。所有时间使用数据库UTC。版本为服务分配的正整数，在各自对象内单调递增，不要求不同对象版本数相等。

| 新表 | 最小字段与约束 |
| --- | --- |
| free_courses | id、user_id、original_goal、teaching_language、code_language（无代码可null）、head_version_id可null、created_at；unique(user_id,id) |
| free_course_requests | id、user_id、course_id、version、parent_request_id可null、original/adjustment类型、request_text、profile_id/version可null、evidence_snapshot、nonsecret_config_snapshot、schema_version、digest、created_at；unique(owner,course,version) |
| free_course_plans | id、user_id、course_id、version、request_id、schema_version、plan_json、digest、created_at；unique(owner,course,version)；正文插入后不可更新 |
| free_course_scenes | id、user_id、course_id、created_at；逻辑身份，不含可变正文 |
| free_course_scene_versions | id、user_id、course_id、scene_id、version、plan_id、content_json、actions_json、dependency_bindings、schema_version、content_digest、created_at；unique(owner,course,scene,version)；正文只追加 |
| free_course_versions | id、user_id、course_id、version、plan_id、manifest_json、digest、created_at；unique(owner,course,version)；清单只追加 |
| free_course_node_links | user_id、course_id、course_version_id、scene_id可null、node_id、graph_version、relation、source、evidence_refs；同一清单/场景/节点唯一（含null场景去重） |

清单包含按计划顺序的全部scene_id，以及每个条目的准确scene_version_id或null。null表示无可学版本；等待/失败等生成细节由T002定义，不伪造空内容版本。首场景与后续追加均创建新清单，内容正文无需复制。head只能指向同课程清单；建表时可延迟建立循环外键，迁移结束必须完整。服务/PG约束同时拒绝清单引用别课场景或与绑定plan不一致的场景版本；复用正文时也须建立属于新计划的版本绑定，不能绕过依赖验证。

`dependency_bindings`保存准确上游scene_version_id及digest，按计划有向无环依赖验证；任何就绪条目的必要上游在同一清单中必须就绪且版本一致。内容、动作、题目与可视化都绑定同场景版本；动作只能引用本版本内容锚点及允许的组件，不执行模型HTML/JS或代码。完整可学正文通过schema、引用/身份、依赖与清洗检查后才可被清单引用。部分流式片段只用于进度，不当成可学正文。

节点关联允许空集合，不造占位节点；node_id必须存在于指定版本知识结构。`relation`为target/supporting，`source`为user_selected/planner_suggestion，证据引用须可追溯；映射不等于已掌握或可靠评分资格。关联随清单不可变；改映射产生新清单。没有节点不阻断创建/学习，正式掌握度准入留给T003。

摘要沿用规范JSON字节（UTF-8、sort_keys、紧凑分隔、ensure_ascii=False、allow_nan=False），拒绝重复键/非有限数/无效Unicode；对象带kind/schema_version域标签，不包含自身digest。正文及来源快照须可恢复，不能只留摘要。不可变内容由PG写保护和服务双重约束；head及可见性事实另存，禁止就地改历史正文。删除现有用户沿用既有用户删除级联政策，不引入新保留期限。

## 3. 清单与可见性

每次追加可学场景或替换版本，在同一事务内校验全部绑定、插入清单并以expected_head_version CAS切head。版本创建/切换与任务操作、幂等收据的原子关系在T002补齐。版本列表是准确历史，不按各scene的max(version)临时组装课程；显式版本不存在就404，不自动替代成最新版。

可见性与签核是独立维度：所有新课程的`course_kind=ai_draft`、`endorsement=unendorsed`，服务端只读常量；没有客户端晋级字段。head清单可以部分就绪，`complete`仅指全部计划场景有可学版本，不表示语义正确、已签核或已学完。具体生成/学习进度另行返回，不复用endorsement。

普通模型意见/reject不能自行改变可见性为“已确认错误”；结构/安全失败内容不得进入可学版本。已确认缺陷通过只追加、owner/课程/场景版本精确绑定的禁用事实阻断正文访问；历史清单和head都须实时检查禁用事实，不能用旧版本绕过。其确认权限、证据和依赖传播由T003批准后建立；该契约未完成时禁止实现新链开放。响应仅给固定不可用原因，不额外返回受影响ID列表（请求路径已绑定准确对象），不泄露内部审核正文；旧历史作答的可访问范围由T003约定。

## 4. owner访问与发布边界

- 使用现有`edumind_session`数据库会话和服务端user_id；写请求验证现有CSRF/Origin，不从header/body相信用户ID。匿名身份有效但不是跨设备账号；新guest不会继承其他guest内容。
- 所有列表、详情、历史、场景及后续事件/媒体/作答/操作接口先验证owner。无会话401；CSRF失败403；不存在/其他owner统一404。嵌套ID必须同owner、同course、同清单；仅知道UUID不授予权限。
- 普通草稿读取不要求人工签核或语义pass。无公开分享链接、跨owner复制、维护者绕过或目录发布接口。管理诊断仍遵循现有独立维护工具权限，不扩展成学生API权限。
- 普通响应不返回owner_id、内部Prompt/模型推理、配置秘密、审核原文或练习答案。练习只返回题干和允许的输入结构；反馈/答案展示及题目证据由T003单独冻结，不能直接序列化存储content_json。
- 所有私有读取 `Cache-Control: no-store`，错误响应无他人内容。文本经白名单渲染与清洗，URL/媒体另过现有安全规则；草稿标识不能代替XSS/执行隔离。
- `catalog_only`中GET可以读取自己已有的合法新历史；新建/生成写操作拒绝409 `FREE_COURSE_DISABLED`，不调用Provider。未来开放使用独立显式配置并经验收批准，不自动把旧`dynamic`模式映射成新入口。

## 5. 新读写API提案

完整类型见[独立OpenAPI](../../api/phase-1.5-free-course.openapi.json)，文件标记planned。当前主[OpenAPI](../../api/openapi.yaml)继续记录既有接口，本提案不改变其运行状态。T021合并时才按已实现内容登记。

| 方法与路径 | 语义 |
| --- | --- |
| POST /api/free-courses | 保存目标并创建课程/持久操作；201返回course_id、operation_id；大纲自动继续。操作调度与预算须先批准T002；不进行同步模型生成 |
| GET /api/free-courses | 仅列owner课程，游标分页，按created_at/id稳定倒序 |
| GET /api/free-courses/{course_id} | 原目标、课程类型及准确head快照；无head时head=null；无正文拼接 |
| GET /api/free-courses/{course_id}/versions | owner范围清单分页；只列版本标识、创建时间，读取详情用下条 |
| GET /api/free-courses/{course_id}/versions/{version} | 准确历史清单，不修改学习位置、不触发生成 |
| GET /api/free-courses/{course_id}/versions/{version}/scenes/{scene_id} | 仅返回该清单中绑定且当前允许读取的准确场景；条目未就绪409，禁用409，未列入404 |

POST仅接受原目标、教学语言、代码语言；支持zh-CN与可空C语言，沿首发数据结构/C范围，不接受Provider地址、owner或任意node_id。未知字段422。原目标1–4000 Unicode字符，去空白后非空，原文仍原样存；语言默认zh-CN/C。限制是新API输入上限提案，T002不能把它误当生成规模预算。需要无代码可显式code_language=null。

创建要求Idempotency-Key（1–128 ASCII可打印字符）及CSRF。作用域owner+路由+key；同键同规范请求返回原201收据，不新增调用；同键异请求409 `IDEMPOTENCY_CONFLICT`。无键422。禁止从GET或刷新隐式重发POST。运行模式拒绝不创建课程/收据、不调用Provider。重复提交是否恢复租约仍由T002定义；重放原operation_id不代表重启操作。

错误响应沿用现有`{code,message,retryable:false}`封套，422统一`VALIDATION_ERROR`，不回显输入正文。

分页limit默认20、范围1–100；cursor是服务签发的owner/查询绑定不透明游标，无效或跨owner游标422，不包含目标正文。历史分页固定到首次查询时的上界，避免持续追加导致漏/重复；不扩大读取权限。具体签发算法属实现细节。

T002的调整/恢复/取消/事件端点、T003的作答/反馈/导师端点不在此声明可用；必须继续使用course/准确版本与owner绑定，不得借用旧unit_id接口。写入冲突不得隐式覆盖，后续修订接受expected_head_version并返回409冲突。

## 6. 新旧兼容矩阵

| 来源/动作 | 读取 | 写入与资格 |
| --- | --- | --- |
| 旧签核目录课程 | 原catalog及learning-units API、原签核快照 | 原enrollment/课堂/测验语义，不改签核或审核结果 |
| 旧legacy无计划单元 | 原owner/发布门禁及intro布局 | 保持旧接口规则，不套新草稿可见性 |
| 旧planned三场景/人工案件 | 原publication快照、准确版本/撤回规则 | 旧人工决定不能转新课程资格；旧拒绝不洗为pass |
| 旧未发布/失败/待审动态单元 | 原规则，不能因owner而经新API公开 | 不回填为可学新课程；需要将来独立迁移提案 |
| 新free-course-v1 | 仅新API，owner可学程序硬门合格草稿 | 不写旧current_publication_id，不自动进catalog或旧评分 |
| 新课程ID传旧API/反向 | 404，无fallback、UUID碰撞也不跨命名空间查询 | 不自动转换，不复用旧intro别名或固定三场景 |
| 混合学习记录导航 | 后续记录任务按origin_type+对象ID+版本分派 | 旧记录原样，不把浏览完成当掌握度 |

## 7. 迁移与恢复提案

T006使用Alembic新增表/索引/复合外键及不可变写保护；新空库和含旧curated/legacy/planned/待审与作答记录的隔离PG库均须实际upgrade验证。迁移前后按稳定排序对旧正文、状态、发布引用、审核/人工签核、节点绑定及掌握度证据作摘要比对；旧记录数与引用保持，生产不手改schema。无旧数据回填、无Provider调用、默认入口关闭。

发布回退优先关闭新入口、回退应用，保留新表及数据，旧应用忽略新表。空新表可在隔离验证中downgrade；已存在课程/请求/版本时downgrade必须显式拒绝，避免静默删学生数据。生产需要迁移级恢复时使用已验证备份/前向修复，不承诺有数据直接drop。T006实际验证跨owner FK、重复版本、清单越界、跨计划绑定、不可变保护和事务回滚；T021/T035再验证HTTP兼容及owner拒绝，不把本设计例子当运行验收。

## 8. 审查与任务边界

[正负例](examples.json)逐条记录预期，包含无节点、多个节点、匿名owner、跨owner、旧失败、显式旧版本、安全禁用与幂等冲突。它们是契约用例，尚不是后端通过证据。

T001本轮只设计；T002/T003/T005保留各自审批。本包未定义生成次数、时限、重试、缺陷确认细则和正式评分阈值。缺失这些契约不允许靠默认值开放新链。批准时登记准确manifest；修改任何规范附件均需重算manifest并重新确认修改部分。
