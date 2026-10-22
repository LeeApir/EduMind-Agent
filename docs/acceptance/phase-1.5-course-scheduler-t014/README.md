# T014：持久渐进生成调度与共享预算

私有 `Scheduler` 将 T008–T013 的规划、单场景生成、机械准入和可学习提交接成 PostgreSQL 持久队列；新增 0041 迁移。仅使用注入的 Mock transport 验证，不注册生产 Provider、HTTP/API、Celery 消费任务或部署入口，仍为 `catalog_only`。

## 运行及事务边界

`enqueue` 在同一事务保存课程/请求、固定 policy 的 queued 操作、规划步骤、queued 事件及幂等收据；policy 在创建时冻结，不修改既有不可变操作绑定。已有收据先重放，不创建步骤或重复预约；存在未知发送时拒绝新操作。普通仓储的空 policy 创建摘要保持旧格式，升级前收据不因新参数失效。

复用现有 PostgreSQL/异步 session 的轮询队列方式，按批准契约每秒扫描，不改变旧动画 Redis/Celery 队列。`claim` 按 owner→course→operation→step→capacity→attempt/event 的顺序处理；owner 与单个空容量槽使用 SKIP LOCKED，实例共享固定槽位 1、2，同操作最多一个槽。并行实例可各领取一项，单实例 `work` 循环串行消费。租约 45 秒、10 秒短事务心跳，领取递增 epoch/token；PG 保存初始 600 秒截止时间，排队、退避、重启均不延长。

大纲先提交；按准确计划顺序选择前置均 ready 的场景，同一操作串行生成。场景检查和提交沿 T011–T013，已就绪场景逐个可读；依赖失败保留 blocked_dependency，独立后续仍继续。内容完整后才另写 succeeded/done；有局部失败和可读内容时 partially_succeeded，无可读结果时 failed。规划澄清保存 awaiting_clarification 和准确问题，无场景调用。

无网络调用持有数据库事务或锁。`prepare` 原子保存不可变 attempt 及最坏 token/费用预约，提交后 `deliver` 再用唯一 dispatch 事实取得一次发送资格并提交，随后出站。重复消费在已有发送尚未完成时无操作，不重复发送或判失败；完整响应以不可变 settlement 保存后才进入原子场景提交。步骤提交失败可保留已结算响应供同 epoch 重试本地事务，不重调 Provider。

## 额度和重试

运行 policy 是批准 T002 的准确副本。硬上限：单操作 13 次（规划 1、最多 8 场景、传输池 2、格式池 2），每步骤每类额外尝试最多 1；单课终身 40 次。操作输入/输出 200000/48000，课程 600000/144000，单调用输入≤32000、输出≤8000。计数从不可变已发送预约派生，失败或 not_executed 也保留发送次数，换操作不清零课程累计。准确 token 用量结算到实际值，缺失/部分未知保留全部预约，不填 0；可信未执行回执才结算为 0 token。

只接受服务端注入的 `SendPolicy`/Adapter；默认请求额度 0，不准发送。必须提供有据的输入上界、包括隐藏推理的总输出约束、固定费率和执行包标识/请求与金额上限；按包加 PG 事务锁检查跨课程、跨 owner 累计预约，保守不退已预约费用。测试费率/计数器纯合成；没有生产 tokenizer、已核验厂商执行证据适配器或真实费用执行包的实现/验收声明。未来真实执行仍须准确预算授权和接线，不可据本任务启动真实调用。Adapter 必须禁用 SDK 隐式重试，传入 `retry_safe=False`，不提供自动换 Provider。

传输自动重试仅可信证据证明未执行/已停止，且无有效正文的 429/502/503/504。单凭网关状态不重试；超时、断连和普通异常为 OUTCOME_UNKNOWN。退避至少 2 秒，Retry-After 只接受 0–30 秒 ASCII 整数，非法值停止，剩余截止不足不重试。格式修复仅 schema/本地引用错误，保留完整原要求、固定错误码与不可信旧候选；无语义改写循环。transport 的硬拒绝/401/403 不进入格式修复。完整请求/响应保存在 owner 私有审计，不进入事件或日志。

## 中断、隔离与迟到响应

PG 扫描不依赖浏览器存活。没有发送的过期租约可重新领取，已 ready 场景及累计计数保留；已有完整结算但未发布的旧 epoch 响应不改写成新 epoch 发布，终止 LEASE_LOST，禁止重新发送或伪造合法来源。

只要有未结算 sent，过期/截止或明确未知结果即 failed/OUTCOME_UNKNOWN；容量槽进入 quarantined，不能因本地计时结束释放，owner 不能通过新课程绕过。迟到的准确完整响应/可信停止或未执行证据可追加 settlement、释放对应隔离槽，但旧操作保持终态、内容不发布、不自动继续；未知 token 即使远端已结束仍按预约保留。输入/输出超过预约、矛盾证据和不一致重复结算均拒绝。证据由可信 transport 提供，模型 JSON 不能自签回执。

`cancel_requested` 的终止、学生继续/新操作、恢复复制计划与补章等完整协议留 T015；普通修订留 T016。T014 不开放取消/恢复入口，不把租约扫描当作学生主动恢复。已有精确版本、已签核课程、旧审核/评分及 H 封存保持。

## 验证与交接

最终命令及结果见 [verification.txt](verification.txt)，测试与源文件摘要见 [results.json](results.json)。实际 test-only PG 为既有标签容器、127.0.0.1:15437，每组新隔离数据库；原始日志/XML 保留在 `/tmp/edumind-p15-t014-r08`，重跑须新 run-id/目录。没有读取 `.env`、真实凭据或原封存教学内容。

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-course-scheduler-t014/run_checks.py --run-id r08 --output /tmp/edumind-p15-t014-r08
backend/.venv/bin/ruff check backend/app/services/free_course_scheduler.py backend/app/services/free_course_snapshots.py backend/app/models/free_course_scheduler.py backend/app/models/__init__.py backend/app/models/free_course_progress.py backend/alembic/versions/0041_free_course_scheduler.py backend/tests/test_free_course_scheduler.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-course-scheduler-t014/run_checks.py
(cd backend && .venv/bin/mypy app/services/free_course_scheduler.py app/services/free_course_snapshots.py app/models/free_course_scheduler.py app/models/__init__.py app/models/free_course_progress.py app/services/free_scene_availability.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

39 项新增测试覆盖实际多连接领取/发送前可见、重复投递、全课程逐章完成、完整 13 次池、课程累计 40 次、共享费用/请求额度、未知用量、预算耗尽保留可学内容、持久退避、非法重试头、硬拒绝、格式失败有界、Worker 重建/过期重领、未知发送隔离、迟到结算拒发布、途中过截止、预约/事件回滚、私有 owner 围栏及旧收据兼容。前置 359 项和旧图谱/路径 47 项一起回归；不计真实教学质量、性能、HTTP/SSE、浏览器或实际厂商端到端通过。

0034–0040 历史迁移和 30 份批准规范/5 份 manifest 原字节不变。0041 扩展规划步骤、增加预约/dispatch/结算及固定容量；非空预约/规划或占用容量时拒绝 downgrade，旧行与签核回归保持。任务只做本地提交，无 push/merge/部署。下一 T015 仍 todo，待执行授权。
