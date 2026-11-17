# T021：新旧课程与安全边界兼容验收

本项验证目录签核课程、旧 planned/legacy、新 owner 私有草稿在同一用户和同一数据库中的交互。实际行为沿各自原协议；不把课程可读等同于共享、签核或可写正式掌握度。当前任务是兼容验收，后续页面框架为 T022、学习首页为 T023、导师接入为 T028；T020交接中“T021前端/T023导师”的文字编号不准确，以根 task.json 为准。冻结提案保留原字节及其当时任务注记。

| 验收对象 | 实际组合验证 |
| --- | --- |
| 旧课可用与隔离 | 合成目录签核、经过原 ReviewOutcome 的 legacy 正式/拒绝版本、原共享计划/自动审核发布的 bound 与 unbound planned、自由草稿在同一 owner 下建立；dynamic 读取各自允许内容，catalog_only 保留目录与新私有草稿读权限，按旧规则隐藏生成的 legacy/planned；其他 owner 始终不能读取准确对象。 |
| 发布安全 | 草稿 UUID 不能用作目录 release/旧 learning_unit；旧受信 record_reviewed_resource 和 publish_approved_case 也拒绝自由课程/场景身份。无学生 publish、目录发布、后台签核端点。合成旧审核通过不代签实际课程。 |
| 原评分与历史 | 目录和准确 bound planned 经原 HTTP 作答，随后建立/作答/禁用新草稿；模式切换和旧回执重放保持原分数、审核、发布、资源版本及事实行的完整 JSON 字节。旧 unbound planned 可读但新评分仍返回 TEACHING_BINDING_UNVERIFIED，不能借草稿协议重新准入。 |
| 撤回互不污染 | 新缺陷确认暂停准确旧场景版本，历史 manifest 可读但不能绕过正文禁用；旧目录仍可读。反向撤回旧 catalog/planned 后，这两类资源不可读，新草稿保持 owner 可读。原始学生作答保留，撤回反馈不展示答案。 |
| XSS与权限 | 三种脚本/链接/实体样本经真实持久生成硬门和 HTTP 公开投影，Markdown 惰性化、JSON content-type；学生反馈仍 pending，不能自动确认为事实。这里验证 PG/HTTP，不冒充新前端浏览器验收。现有旧学习组件仍使用 Vue 文本插值。 |
| 画像、掌握度、路径 | 用户显式偏好保存后，可靠新题组首次完整作答准入；确认缺陷后有效掌握度回到 unseen/0，路径 is_stale 保持待更新。用户原画像/未知学情和显式偏好字节保留，其他 owner 无掌握度/路径泄漏。 |
| 模型设置 | 真实加密持久化的合成凭据、四档偏好、版本冲突和跨 owner 拒绝，在新课程读写/模式切换后仍符合旧协议；响应与日志不暴露合成 secret，不发出 Provider HTTP。扩展回归另覆盖原配置版本/显式回退的 Mock 路径。 |
| 归档与旧门禁 | 四份 docs/tasks 归档与 b0c9a08 的 Git 字节一致，旧 MVP T033/P1 T040/T041 仍 blocked；46份既有迁移字节不变。30批准规范/5 manifest保持 SHA256；不读取 H 留出样本、不重评旧质量或借用旧预算。 |

新增 `backend/tests/test_free_course_compatibility.py` 有12项 PG/HTTP组合检查；原API、调度、证据、目录/发布/画像/模型设置及归档回归在独立数据库逐组执行。每次运行新建带 run-id 的数据库，核验专用 Docker 容器 `edumind-phase1-t037-pg` 的测试标签和 `127.0.0.1:15437` 绑定；不会加载真实 .env/Provider 配置或执行生成代码。

合成旧 planned 审计本来使用 RESTRICT/append-only。夹具关闭客户端、撤销合成会话，保留专用隔离库的历史事实；不为清理测试而削弱外键/触发器。新组合测试禁止构造真实 Provider，并拒绝所有 AsyncClient 出站；旧审核/画像使用明确的内存 Stub，新调度用 FakeAdapter。合成目录签名和题组核定都标 TEST_ONLY/synthetic，不能用于产品质量结论。

执行与证据：

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-compatibility-t021/run_checks.py --run-id r03 --output /tmp/edumind-p15-t021-r03
backend/.venv/bin/ruff check backend/tests/test_free_course_compatibility.py docs/acceptance/phase-1.5-compatibility-t021/run_checks.py
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/app/services/owned_learning.py backend/app/services/catalog_publication.py backend/app/services/hybrid_learning_publication.py backend/app/services/mastery_updates.py backend/app/services/free_course_evidence.py backend/app/services/model_preferences.py backend/app/services/profile_behavior_updates.py
python3 docs/acceptance/phase-1.5-course-api-t020/build_contract.py --check
python3 scripts/check_catalog_workflow.py
git diff --check
```

results.json 保存各组实际数量及原始日志/XML SHA256，另逐 testcase 保留历史行摘要；baseline-integrity.json绑定 b0c9a08 的50份归档/迁移原件，并记录已有无关README的工作区摘要。原始测试日志位于准确 /tmp 输出目录，历史分数/审核原行在相应隔离数据库保留，可对照复核。

r01目录夹具包ID超过原40字符限制，改为合法37字符；r02混合矩阵使用不足16字符的旧目录幂等键，另有试图删除不可变 planned 历史导致的清理错误。r03使用合法长键，并按原审计保留协议只撤销测试会话。保留了原产品断言、身份/权限、校验和审计约束。真实 Provider0、生产 catalog_only、无 push/merge/部署；不自动领取 T022。

最终r03：**697通过，0失败/错误/跳过**（新增组合12、前序573、补充旧协议112），46组实际隔离PG；Ruff2文件、strict mypy7模块、累计契约/工作流/diff与冻结SHA通过。未修改运行代码、既有迁移或API契约。
