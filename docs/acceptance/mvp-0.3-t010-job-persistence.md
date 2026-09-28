# MVP-0.3-T010 动画 Job 持久化验收与交接

[Alembic 0010](../../backend/alembic/versions/0010_animation_jobs.py) 新增四张表：`animation_jobs` 保存 owner、学习单元/已审核场景版本、公共模板与运行身份、规范化参数摘要、幂等键/摘要、状态、attempt/lease、取消标志和事件水位；`animation_job_events` 用 `(job_id,event_id)` 保存单调、可重放的已提交事件；`animation_media` 保存经审核的共享字节身份但不赋予用户权限；`animation_resource_bindings` 把媒体与 owner、Job、学习单元和场景版本绑定。对既有 `learning_units` 与 `learning_scenes` 增补复合唯一键，供 Job 的复合外键核对 owner 与场景版本。状态、attempt、进度、租约、成功媒体和绑定一致性都有数据库约束。

[预约服务](../../backend/app/services/animation_jobs.py) 先锁 owner 行，再按 `(owner,action_kind,idempotency_key)` 查询。相同请求摘要重放原 Job，不增事件；同键不同摘要返回 `IDEMPOTENCY_CONFLICT`。新请求须指向 owner 的 ready 学习单元、已完成且审核通过的场景及精确已审核模板版本；排队 Job 与 `event_id=1` 的 queued 事件同事务提交。事件追加先锁 Job，递增持久水位；事件载荷只接受阶段、进度、稳定错误码、媒体 ID 和尝试序号，不持久化路径、Cookie、Provider 上下文或临时 token。`after` 游标仅返回更大的事件；超前游标拒绝。该任务只提供持久原语，租约领取、取消/发布竞争、SSE 接口和媒体 owner 授权仍由 T011–T014 实现。

验证只使用新建的临时 PostgreSQL 容器 `edumind-mvp03-t010-pg`（随机回环端口），未迁移现有 MVP 0.2 运行库。空库 `alembic upgrade head` 依次通过 0001–0010；写入 Job/事件后用新引擎重连仍读到相同 ID 和游标。再执行 `alembic downgrade 0009_path_commands`，检查四张表均不存在，然后 `alembic upgrade head` 并重跑集成测试通过。集成回归覆盖同 owner/key 重放、异摘要冲突、并发同键只创建一次、其他 owner 同键可独立创建、跨 owner 事件/媒体绑定外键拒绝、非法状态与缺租约 running 拒绝、事件顺序及超前游标。全量后端在该迁移后的临时库为 515 通过、2 项 Docker 专项跳过。真实 Provider 调用 0 次。

模型/迁移与 [OpenAPI 0.3.0](../api/openapi.yaml)、[ADR-0004](../ADR/0004-trusted-animation-jobs.md) 的状态和游标语义对应。下一任务 T011 必须使用这些行锁、lease token 与 owner 约束完成 Worker 领取和发布，不能以进程内存替代。
