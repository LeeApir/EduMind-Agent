# T015：取消、显式恢复与只读断点查询

新增私有 `Recovery` 服务，接入 T014 持久扫描和发送围栏。0042 仅新增 owner/course 绑定、只追加的 `free_course_operation_sources` 关系表，保存新操作的准确来源；旧操作表不加列，0034–0041 原字节保持。

## 停止及竞争

`cancel` 先按 owner→course→operation→step 持锁，幂等重放优先；当前非终态操作置 cancel_requested，记录 PG 时间、递增 epoch 并撤销 token/租约，pending 步骤标 cancelled。同事务保存 cancel_requested 事件、符合批准 Operation schema 的完整状态收据，HTTP 语义固定 200；实际 HTTP/CSRF 控制器尚未接线。已终态取消保持原 succeeded/failed 等状态，无额外事件/预约；同键重放仍返回当时的原收据。

下一轮持久扫描将 cancel_requested 收尾为 cancelled/done，pending/running 步骤标 cancelled；ready、failed、blocked_dependency 事实保留。没有未结算发送则释放槽；有 sent 未结算则隔离槽，次数不退、未知 token 仍按 T014 最坏预约。扫描支持 catalog_only 中停止旧的非调度自由课程操作，不把它们自动升级到新调度 policy。

取消先获得锁时，旧候选和迟到响应不能切 head 或写 ready；ready 先完成事务时，取消等待后保留该准确场景/版本。发送期间每秒只读检查持久状态/epoch，失效时尝试取消本地发送任务。该本地信号不证明远端停止、不退款、不释放未知槽；transport 若不理会本地取消后返回完整可信响应，仅追加结算，绝不调用发布路径。进程中断后仍由 PG 扫描恢复，不能依靠本地任务存在与否判断远端是否结束。

可信结算若在未知终态前先取得同一锁，终态复核未结算事实后释放槽，避免把已结算尝试永久隔离；重复可信结算也遵守同样的释放规则。取消最终状态及旧 head 不因此被重新激活。

## 显式继续是新操作

`start(kind=resume|clarify)` 必须明确给出 source_operation_id、expected_head（可显式 null），owner/course/来源/当前基线一致，来源为当前终态操作；活动冲突、未知发送、已耗尽课程额度、陈旧来源及陈旧版本拒绝，错误时课程/请求/操作/收据不留部分提交。同键同体只重放，改体冲突；新操作是 queued，保存 202 身份收据和来源关系，操作自己的 600 秒及尝试池重新开始，课程终身 40 次/token 累计不清零。真实 Provider/费用执行授权仍为 0。

已有 head 的 resume 复用同一不可变请求与计划，不重命名旧候选来源、不复制或替换 ready 版本；只为缺失/失败及必要后代建立新 pending 步骤，准确保留已有 ready 的 scene_version_id。依赖可使用旧的准确 ready 场景，新章逐个追加；没有缺章则 NOTHING_TO_RESUME。已有绑定却无法证实可学习、或缺章后代存在不应被替换的 ready 绑定时拒绝。历史操作的失败/取消和旧预算保持，学习进度显示最近步骤，不回写旧状态。没有 head 的显式 resume 从新规划步骤开始，旧预约不复用。

clarify 仅接受 awaiting_clarification、显式当前 null head、1–4000 字非空补充；在本事务追加 adjustment 请求、parent_request 和准确 profile/evidence/config 快照，再创建新规划操作。原目标和原请求仍在来源链中，补充原文不会被自动写成已证实画像。当前 T014 的澄清发生在大纲提交前；修改已有大纲/局部重解释及影响确认属于 T016。

## 刷新只读

`read_operation` 使用 PostgreSQL REPEATABLE READ / READ ONLY 事务返回批准 Operation/Step/Budget 视图：kind、状态、base/head、deadline、固定原因、澄清问题、步骤、序号、已用/剩余预算及 usage_unknown。不返回内部候选、私有答案、原文、配置、lease token 或凭据。刷新不领取租约、不写幂等收据、不自动 resume、不预约或发送，返回对象可由调用者安全修改副本。

以上均为私有服务，未开放 REST/SSE、前端按钮或生产 Worker；owner 验证已在服务执行，HTTP CSRF/mode/路由及重连控制仍留后续 API 任务。T016 修订/已确认缺陷处理、前端提示、实际厂商停止证据/计费适配和真实运行开放没有因本任务自动交付。

## 实际验证及交接

最终 r04：474 项通过，0 失败/错误/跳过，其中新恢复 29、前置自由课程 398、旧图谱/路径 47。实际 test-only PG 使用既有标签容器及 127.0.0.1:15437，每组新隔离库；Provider 全为 Mock。44 份原始日志/XML 在 `/tmp/edumind-p15-t015-r04`，摘要及源文件摘要见 [results.json](results.json)，执行记录见 [verification.txt](verification.txt)。重跑使用新的 run-id 和输出目录。

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-course-recovery-t015/run_checks.py --run-id r04 --output /tmp/edumind-p15-t015-r04
backend/.venv/bin/ruff check backend/app/models/free_course_recovery.py backend/app/models/__init__.py backend/app/services/free_course_recovery.py backend/app/services/free_course_scheduler.py backend/app/services/free_course_snapshots.py backend/app/services/free_scene_availability.py backend/alembic/versions/0042_free_course_recovery.py backend/tests/test_free_course_recovery.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-course-recovery-t015/run_checks.py
(cd backend && .venv/bin/mypy app/models/free_course_recovery.py app/models/__init__.py app/services/free_course_recovery.py app/services/free_course_scheduler.py app/services/free_course_snapshots.py app/services/free_scene_availability.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

新测试覆盖 queued/running/terminal 取消、两种实际多连接锁竞争、立即围栏与跨连接提交可见性、整条取消事务回滚、在途尽力中断、忽略本地取消的迟到可信结算、结算先于未知终态的容量竞争、无 head 及缺章恢复、原 ready ID/首章唯一里程碑保持、并发重复恢复/改体冲突、陈旧来源与严格基线、schema 收据、澄清请求与未知画像、只读多次刷新无写入、历史失败保留、来源不可变和有数据拒绝 downgrade、旧 policy 停止。

早期 r01/r02 的失败来自两个夹具未对齐形式/枚举及漏改第二处正文夹具；r03 新行为与前置前三组通过，但旧 0037 升级夹具因 ORM 引用新列而报错。改用独立来源表后，r04 保持所有旧夹具/断言通过，未放宽硬门或修改旧迁移。30 份批准规范/5 份 manifest、旧签核/评分和 H 封存保持，不追认真实质量/性能或浏览器 E2E。无 `.env`/真实凭据读取、生产迁移、push/merge/部署。下一 T016 未领取，待授权。
