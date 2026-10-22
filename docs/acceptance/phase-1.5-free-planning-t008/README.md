# T008：自由目标课程规划交接

实现私有自由规划器与结果持久化，直接使用课程原始目标、准确请求链和创建请求采用的画像证据；未知字段保持未知，自述不升级为已掌握。不依赖单节点解析、图谱命中或旧三场景规划门禁。尚无公开API、Worker接线或运行开放。

## 规划与准入

版本化Prompt `free-course-plan-v1` 与 `free-course-planning-response-v1` schema支持1–8场景、默认15分钟、共享示例/术语/表示约定及前向依赖。PlanCandidate结构与已批准ADR0025附件一致。用户要求引用真实请求来源键及原文子串，模型建议来源为空；服务端生成UUID/摘要，模型不得提交owner、节点或签核权限。未知学情、多个知识点或无匹配本身不能成为澄清理由。

响应仅在要求冲突、必要材料缺失、范围不支持时表达澄清，带1–3问题和真实来源键；否则返回计划。确定性检查覆盖结构、空白/大小、重复ID/术语、准确引用、依赖顺序与目标覆盖。来源匹配和覆盖是结构保证，不证明要求理解、事实正确、个性化或澄清理由真实；这些仍须独立质量验收，合成Mock结果不计真实质量分子。

Gateway一次调用，不重试或静默回退。发送前必须提供authorize_send回调，绑定请求摘要；本任务仅Mock回调，未建立真实预算预约。Provider拒绝、schema失败、超时/未知发送分别保存固定失败码，不伪造成功，不保存厂商异常文本；取消传播而不假装完成。有限的无效结构响应只保留私有诊断。128000字节输入和16384字节响应上限是安全限额，不代表token/费用估计。超限拒绝，不截断目标或教学内容。

## 持久化与并发

load_inputs通过既有仓储重验准确请求摘要并沿父请求读取来源，不替换为当前最新画像。persist_outcome不调用网络；按owner→course→operation加锁，重验真实输入、调用摘要与返回正文摘要，拒绝跨owner、伪造输入及返回后字典修改。围栏/取消/PG时钟租约与期限/expected_head同时约束写入。

ready结果保存私有候选与逻辑场景，不切head、不生成正文或大纲事件，不等于课程完成。澄清或失败原子写审计及操作状态，不创建计划。审计绑定请求/操作/调用键/epoch/输入和响应；同键同结果返回原ID，异结果拒绝。候选、收据、审计、操作更新在同一保存点，外层事务由调用者commit/rollback。append-only约束保持历史，用户删除沿既有级联策略。

0036前向迁移新增结果审计表和操作reason_code/clarification_questions；0034/0035原字节不改。有规划结果或非空澄清/原因时拒绝downgrade，不删除历史以强行回退。T014/T015尚须提供持久attempt、计数/token/费用预约、租约续期、未知发送隔离、容量回收和恢复；目前的写围栏与回调不能视作完整Worker/预算授权。T013负责学习清单/事件接线，公开投影仍按后续任务实现。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-free-planning-t008/run_checks.py --run-id r02 --output /tmp/edumind-p15-t008-r02
backend/.venv/bin/ruff check backend/app/agents/free_course_planning.py backend/app/services/free_course_planning.py backend/app/models/free_course_planning.py backend/app/models/free_course_writes.py backend/app/models/__init__.py backend/app/services/learning_stage_gateway.py backend/alembic/versions/0036_free_course_planning.py backend/tests/test_free_course_planning.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-free-planning-t008/run_checks.py
(cd backend && .venv/bin/mypy app/agents/free_course_planning.py app/services/free_course_planning.py app/models/free_course_planning.py app/models/free_course_writes.py app/models/__init__.py app/services/learning_stage_gateway.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

专用test-only PostgreSQL、127.0.0.1:15437，八个新隔离数据库：新规划59、仓储44、迁移57、旧路径22，共182 passed，0失败/错误/跳过。包含空库升降、旧数据摘要、并发/围栏/取消/过期、持久幂等、回滚及审计不可变。Provider异常/超时/取消由Mock验证，无真实调用。凭据只在进程内存，不读.env。原始日志/XML位于/tmp/edumind-p15-t008-r02；计数、来源及证据摘要见results.json，过程见verification.txt。重跑须使用新run-id及输出目录。

自查补充了返回候选字典变动检测，最终r02重新验证全部182项；r01此前181项通过。30份既有批准规范及5份manifest摘要不变，0034/0035不改。无真实教学质量、性能或业务E2E结论。catalog_only、H封存、旧失败及用户无关改动保持，无push/merge/部署。

下一T009：非阻塞知识点关联，仍todo，未领取。
