# ADR-0017 分层审核零调用实施

批准登记：../../ADR/0017-approval-20261019.json；分支 codex/phase-1-t056-t070。

| 任务 | 生效版本 | 实际验证 |
| --- | --- | --- |
| T057 | Prompt v4.6 / input v2 / responsibilities v1 | 88项真实隔离PG＋Mock通过，无跳过 |
| T058 | Prompt v4.7 / input v3 / learner-evidence v1 | 定向45项、组合102项通过，无跳过 |
| T059 | Prompt v4.8 / scope v5 / fixed-check-ids v2 | 最终132项真实隔离PG＋Mock通过，无跳过 |

逐项证据见t057.json、t058.json、t059.json。不同阶段的数量不相加为质量成绩。Provider实际发送均0，模拟响应不证明模型理解分工、无误报或语义可靠；这些仍由后续T040独立新配置/预算验收。

T059新增unit objectives必检项，原五项保持。原结果Schema和finding类别不扩展。原始需求/计划/实际学生内容完整送审，资源负责自身承诺与实际事实/安全；职责待核验不冒充交付或真实未决。未知学情本身不拦截，绑定证据分别保留，不捏造个性化前提。严重reject与资源真实未决不因整课pass消除，原调用/时间/修正边界不变。

独立测试库edumind_t057_t070_20261019用既有Alembic初始化。模型全为Mock；CLI测试中的身份/决定均为测试，不是实际课程签核。旧课程、原失败和停止余额保持。旧已发布快照可读，旧待审/已批未发案不能跨新政策取得发布资格；不修改历史模型结果或自动补新check ID。

最终实际命令（从backend目录，数据库URL仅指独立本地测试库，不能用于生产）：

`EDUMIND_PRODUCT_MODE=dynamic EDUMIND_TEST_DATABASE_URL=<isolated test DB> .venv/bin/pytest -q tests/test_unit_review_responsibilities.py tests/test_learner_evidence_review.py tests/test_shared_learning_plan.py tests/test_resource_review_responsibilities.py tests/test_review_input.py tests/test_hybrid_resource_review.py tests/test_unit_consistency_review.py tests/test_hybrid_review_scope.py tests/test_hybrid_review_check_ids.py tests/test_review_delivery.py tests/test_review_evidence_v45.py tests/test_learning_review_cases.py tests/test_hybrid_learning_publication.py tests/test_hybrid_learning_operations.py tests/test_learning_review_cli.py`

另实际执行全app/tests Ruff、mypy194源文件、流程、diff及236历史归档检查。原ADR0015校验器直接对现工作树运行会因PRD已获准新增规划而失败；失败保留，未改原manifest/脚本或降低断言。改在临时目录逐文件恢复45cfc96批准原件后原脚本通过12文档/12契约，并另对现活动账本的原12任务契约逐项相等检查。临时目录自动清理，不保留多余运行器。

T060节点选择/API契约尚未批准；本实现没有修复或洗白r02的c-pointer错绑数据。T065执行隔离仍待具体设计。catalog_only、T040 blocked、T041/T042门禁及Phase2/3边界不变。
