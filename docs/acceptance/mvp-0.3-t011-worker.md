# MVP-0.3-T011 持久化动画 Worker 验收与交接

[独立 Worker](../../backend/scripts/run_animation_worker.py) 以 PostgreSQL 为队列，不挂在 API 请求或 lifespan 中。领取用 `SELECT FOR UPDATE SKIP LOCKED` 短事务；每次写入 attempt、随机 token、数据库时间计算的 30 秒租约和 running 事件。渲染交给已审核模板的受限 Docker 执行器；Worker 每 10 秒续租。发布前重新核对缓存身份、模板版本、媒体摘要和字幕，只有当前未过期的 attempt/token 可在同一事务中写入共享 `animation_media`、owner 范围 `animation_resource_bindings`、succeeded 状态和事件。失败仅写稳定错误码与事件，不修改学习单元或正式资源。

进程中断后，新 Worker 先回收过期租约：首轮回 queued，第二轮记 `RENDER_INTERRUPTED`；旧 token 不能续租或发布。容器入口在 130 秒后自行退出，作为宿主 Worker 异常终止时的遗留容器清理兜底；宿主执行器仍按 ADR 的 120 秒硬超时处理。T012 将实现用户取消与发布互斥及运行中容器的及时终止；T013/T014 提供 Job/SSE 和媒体 owner 接口。这里的共享缓存只是私有存储，不能直接给客户端路径。

在独立 PostgreSQL 测试库运行 `EDUMIND_TEST_DATABASE_URL=<isolated-url> EDUMIND_DOCKER_TESTS=1 uv run --frozen pytest -q tests/test_animation_worker.py`：6 通过，覆盖并发领取、双 owner 共享媒体但分别绑定、重复发布拒绝、全新引擎恢复过期租约、旧 attempt 拒绝、第二次中断失败、损坏媒体拒绝、渲染失败保持已有学习纲要、进程内真实 Job，以及另起 Python Worker 进程读取持久 Job 后完成 Docker 渲染。实际 `AnimationJob`、媒体和绑定均为 succeeded/passed/同一 media ID，事件水位一致。全量后端在同库 `pytest -q` 为 519 通过、4 项 Docker 专项跳过；本任务未调用 Provider。下一步 T012 实现取消与发布竞争，随后才开放正式 API。
