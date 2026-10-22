# T007：课程及场景快照仓储交接

交付私有SnapshotRepository、规范JSON/分域摘要、持久收据和写入围栏，以及0035前向迁移。依据ADR-0024/0025已批准的准确身份/幂等/取消/租约边界；没有HTTP路由、Provider调用、轮询Worker或生产开放。

## 仓储行为

- create_course保存原始目标原文、语言、准确owner画像版本及采用证据快照；未知字段保持null。配置只接受明确非秘密键及平面标量，拒绝api_key等额外键/嵌套配置。服务端UUID、只追加请求/计划/正文/清单，不让客户端指定签核或digest。
- 原始JSON可用parse_json拒绝任意层重复键、非有限数和无效Unicode；canonical采用UTF-8、sort_keys、紧凑分隔、ensure_ascii=False及allow_nan=False。摘要以kind/schema_version/payload分域，模型不提供摘要。读取准确快照重验摘要；返回深拷贝，不允许经返回对象改历史。
- 模型临时scene_key映射为服务UUID，保留原candidate，校验场景顺序和依赖。新计划复用当前head中保留scene_key的逻辑scene_id；删除后重新添加不会从更早历史捞旧ID。正文复制/重新绑定及完整修订流程留给T016。
- store_plan/store_scene是私有候选持久化，不宣称完整教学schema/动作清洗已通过。T008/T010–T012实现真实候选生成/确定性准入；T013以后才连接可学习公开投影。get_scene_snapshot是内部准确原始快照（可能有私有答案），不能直接序列化为HTTP响应，T017/T020必须经过实时可见性与答案投影。
- get_course/get_request/get_plan/get_version/get_scene_snapshot均限定owner+course；显式历史不回退到最新版，未就绪场景返回固定SCENE_NOT_READY。当前head每次查询刷新，避免长Session身份缓存遗漏其他事务更新。
- 写入按owner→course→operation加锁。每个操作的epoch/token/lease/deadline/cancel标记持久化；清单切head用SQL同时检查expected_head、当前围栏、PG时钟期限。取消先获得锁则旧写入失败；提交先获锁则提交结果保留。私有旧候选不能借新epoch/继任operation发布，已进入准确旧清单的内容可继续按历史绑定保留。
- head切换、清单、节点关联和收据在同一事务/保存点，收据保存失败全部回滚；调用者负责外层commit/rollback，仓储不内部提交。owner/路由/key持久唯一，同键异请求拒绝，同键重放只取已保存标识；重放不会重新调度或写新版本。repo:plan/scene/manifest为内部幂等命名空间，/api/free-courses预留准确创建标识收据，不表示端点已实现。

## 持久化与迁移

0035新增批准范围内的free_course_operations和free_course_receipts基础表，及候选origin_operation_id/origin_lease_epoch，防止取消/过期候选换围栏重用。旧0034行来源列保持null，不回填为有效新候选。operation静态绑定/期限不可修改，收据只追加，用户删除沿既有级联。活动owner/course唯一。

本任务只建立操作存储及写入/取消围栏原语。steps/attempts/events/capacity、计数/token/费用预约、未知发送隔离和恢复/完整状态转换由T014/T015补齐；acquire_write_fence不能当作生产Worker领取能力。没有Worker读取新表，也没有出站路径；queued记录是测试/内部存储，不能据此宣称已经可生成。

修复T006节点CHECK换行错误：0034历史DDL曾将少数连字符名称变成含空格的字符串；0035保留原迁移不改，替换为准确允许集合，覆盖两个已批准图谱40个节点。新清单关联同事务保护改用DB生成creation_txid（顶层事务ID），解决SAVEPOINT下行xmin为子事务ID而误拒绝；旧行creation_txid保持null、禁止追加历史关联。清单摘要包含节点关联，映射变化不能保留同一manifest摘要。

含0034自由课程/请求/计划/场景/清单/节点关联的真实隔离库已upgrade0035，除新增内部列外原始行摘要一致。若既有不合法拼写行导致新CHECK校验失败，迁移整体回滚、请求人工处理，不静默改写历史映射。有操作/收据/节点关联时0035拒绝downgrade；回退仍优先关闭入口并保留数据。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-snapshot-repository-t007/run_checks.py --run-id r05 --output /tmp/edumind-p15-t007-r05
backend/.venv/bin/ruff check backend/app/models/free_course.py backend/app/models/free_course_writes.py backend/app/models/__init__.py backend/app/services/free_course_snapshots.py backend/alembic/versions/0035_free_course_repository.py backend/tests/test_free_course_snapshots.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-snapshot-repository-t007/run_checks.py
(cd backend && .venv/bin/mypy app/services/free_course_snapshots.py app/models/free_course.py app/models/free_course_writes.py app/models/__init__.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

新仓储44项、迁移57项、旧路径16项共117 passed，0skip；专用test-only PG/127.0.0.1:15437六个新隔离库，凭据只在子进程内存，不读.env。原始日志/XML在/tmp/edumind-p15-t007-r05，计数、来源与证据摘要见[results.json](results.json)；过程与边界见[verification.txt](verification.txt)。每次运行须使用新的run-id/输出目录，不覆盖既有数据库。

下一T008：自由目标规划，尚未领取。API/模式门禁/正式作答/可见性禁用仍按各自任务实施，当前无对外新增功能或真实质量/性能成绩。catalog_only、H封存、旧失败和用户无关改动保持，不push/merge/部署。
