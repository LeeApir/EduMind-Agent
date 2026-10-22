# T006：自由课程版本数据模型交接

交付：`0034_free_course_snapshots` Alembic迁移、七个ORM及数据库约束。依据已批准ADR-0024/0025/0026，运行入口保持catalog_only；本任务不增加HTTP接口、生成调度、内容生成、缺陷确认命令或评分写入。

## 数据与边界

新增free_courses、free_course_requests、free_course_plans、free_course_scenes、free_course_scene_versions、free_course_versions、free_course_node_links。原目标/语言和历史正文、请求来源、计划、场景、清单及关联只追加；课程只允许head指向更新版本。course_kind=ai_draft与endorsement=unendorsed由数据库约束，完整清单不等于内容签核。已确认缺陷的追加可见性事实及权限在T017实施，本任务不绕过未来实时禁用检查。

所有跨域复合外键绑定owner/course；画像引用绑定准确owner/id/version，为旧student_profiles只增加唯一索引约束，不改旧行。新表复合外键提交时验证，兼容已有用户删除级联；普通直接删除快照被拒绝。新版本插入锁课程并验证正数、单对象递增；并发同版本只有一个提交。head的数据库约束阻止跨课和倒退，expected_head CAS及完整仓储事务属于T007。

持久计划将模型临时scene_key映射成服务分配的scene_id，plan_json.scenes按顺序保存scene_id/depends_on（UUID数组）及其他计划元数据；不是直接保存未处理的PlanCandidate。清单manifest_json.scenes保存同序全部scene_id及准确scene_version_id或null。dependency_bindings保存scene_id/scene_version_id/content_digest，PG校验同计划、全部必需上游和同清单准确版本；同摘要不同版本也不得混用。

节点关联可为零；两个部分唯一索引分别处理课程级null场景和场景级关联。现有两个已批准图谱版本及合法node_id固定为CHECK约束允许集合，不赋予节点课程签核或评分资格；新图谱版本需相应迁移，实际关联依据/图谱服务由T009校验。关联只能和新清单同事务插入（核对清单行xmin），提交后不能给历史清单追加映射；修改需新清单。

当前PG保护身份、引用、计划依赖、历史不可变和草稿类型，不声称在数据库中完成全部教学schema、规范摘要重算、清洗、预算或语义校验。规范JSON/摘要重算与服务写保护由T007实现；正文/动作校验由T010/T011实现。JSONB本身不能识别反序列化前重复键，服务须在入库前拒绝；本任务的合成数据不代表可发布教学资源。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-data-model-t006/run_checks.py --run-id r01 --output /tmp/edumind-p15-t006-r01
backend/.venv/bin/ruff check backend/app/models/free_course.py backend/app/models/learning.py backend/app/models/__init__.py backend/alembic/versions/0034_free_course_snapshots.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-data-model-t006/run_checks.py
(cd backend && .venv/bin/mypy app/models/free_course.py app/models/learning.py app/models/__init__.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

首个命令实际在现有专用PG容器edumind-phase1-t037-pg执行，检查test-only标签和127.0.0.1:15437绑定；新建五个独立测试库，不读.env、不打印连接凭据。每次重跑使用新的编号和输出目录，主迁移测试拒绝非空旧库，不清理或覆盖数据库。新57项、旧16项全部通过，0skip。结果与证据摘要见[results.json](results.json)，原始log/XML位于/tmp/edumind-p15-t006-r01；[verification.txt](verification.txt)记录修复过程及命令。

主迁移用例实际从空库升级全部历史迁移、空新表回退0033，然后插入明确标为synthetic的curated/legacy/planned/待审/失败单元、资源、审核记录/人工决定/发布引用和成绩证据/掌握度；升级前后及测试结束逐表规范排序摘要一致。合成approval字段是数据库兼容夹具，不是真人签核或新内容发布许可。

## 回退与下一任务

空新表可downgrade到0033；任何新表存在数据即拒绝，测试确认revision保留0034。实际回退优先关闭新入口/退应用并保留数据，旧应用忽略新表。生产schema未修改，不承诺有学生数据直接drop。

下一T007实现准确快照仓储、规范JSON/hash、服务写保护、CAS和事务；仍需执行授权。T017/T019以后接可见性事实/贡献撤销；本次无Provider、HTTP/浏览器或真实生成质量验收。旧P1失败、H封存、用户旧报告和OpenMAIC参考目录保留，不push/merge/部署。
