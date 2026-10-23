# 私有只读记录契约 r01

## A. 课程记录索引

`GET /api/free-courses/{course_id}/records?kind=attempt|operation|feedback|tutor&limit=20&before_id=UUID`，kind必填；limit默认20、1–50；before_id可选。按(created_at DESC,id DESC)稳定键集分页，多取一条判断next_before_id。四类各自读取对应已有owner/course表，不做全表跨类型大查询。包括所有既有状态/版本，不只成功记录；operation包含tutor_turn操作，UI按kind分类避免将同一导师记录算两次。根目录现有courses/versions接口继续承担课程与版本列表。

返回items仅record_id和created_at，以及顶层course_id、kind、next_before_id。record_id是现有attempt_id/operation_id/feedback_id/turn_id；不能把record_id当作scene或版本。页面按需读取原GET，展示准确版本和当前反馈。索引不返回旧缓存反馈、正文、请求key、Prompt或答案。读历史不触发POST，版本不存在不替换最新；operation.head_version是读取时当前head，不能当作该操作发布结果。

先检验course属于当前owner；cursor须在该kind、同owner、同course的表中存在，否则统一404 NOT_FOUND。跨course/kind/owner游标不返回任何条目。查询始终重带owner/course条件，不能仅靠cursor约束。查询/读取无副作用，catalog_only可用。422只表示参数格式/上限失败，401缺会话，其他owner或不存在统一404，响应no-store。无新CSRF要求（GET不写），不提升guest权限。

## B. 掌握度修订来源

`GET /api/mastery/nodes/{node_id}/revisions?limit=20&before_revision=正整数`，limit同上；node_id沿既有slug规则。按revision DESC分页；仅当前owner此node的已有revision，无记录返回空列表。node无需存在于当前graph，保留历史节点。before_revision是排他数值上界，不查询其他owner是否有该revision。返回node_id、items和next_before_revision。

每项revision、previous_score、score、status、rule_version、created_at、evidence_summary（字符串数组）、recomputed_from_revision（同owner同node原revision号或null）及source。分数是历史快照而非当前有效贡献；当前GET /api/mastery仍唯一最新投影。历史条目不因撤销而删除，也不重新算旧答案。

source包含protocol（free-course-v1/free-course-correction-v1/legacy/unavailable）、evidence_id（UUID或null）、reference（引用对象或null）。free-course-v1沿准确LearningEvidence.free_course_attempt_id读取同owner attempt及其manifest绑定，reference包含course_id/course_version/scene_id/scene_version_id/exercise_id/exercise_version_id/attempt_id。correction沿corrects_evidence_id取得原free-course-v1事实并用同一绑定引用被撤销旧作答，不把新题绑定塞进原记录。仅从真实已存事实连接，不猜当前head。所有连接必须重新校验同owner，若缺原件/有无法可靠连接的旧记录则protocol=unavailable、reference=null，不造来源或回退最新。legacy来源只允许从原LearningEvidence投影resource_id/resource_version/learning_unit_id的可空引用；不开放原payload、学生原始输入或模型反馈。未知非空source_protocol不冒充legacy；按unavailable关闭引用。

recomputed_from_id连接同owner/node revision，缺失时返回null，附evidence_summary原服务端已有安全摘要，不伪称来源已证实。页面以原作答GET的最新mastery_effect/reliability显示撤销，失效答案和解释仍由原GET关闭；历史score不得包装为当前分数。后台核定证据文件及权限不对学生开放。

## C. 实现及验收门槛

无新表/迁移；利用现有排序和owner约束，limit硬上限，禁止返回非白名单列。两个接口独立task/提交。实际新建隔离PG库与合成事实（不算真实签核），HTTP验证两owner隔离、课程/类型游标隔离、同时间戳排序与翻页、零/一/多页、失败/取消/未知记录保留、旧协议资源空引用、空掌握度、真实普通准入及修订/缺陷撤销后的recomputed链和准确旧作答引用、失效GET继续隐藏答案、catalog_only可读、GET不触发模型/写入。明确0skip，补API/旧路径/迁移兼容回归。Ruff/mypy及生成runtime OpenAPI一致检查。若发现新安全/权限或数据决策冲突，停止另提案。

本设计仅做结构/引用/manifest检查，不宣称PG/HTTP/页面已实现。零真实Provider，H封存，生产catalog_only。
