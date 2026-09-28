# MVP-0.3-T012 动画创建与 Job 生命周期验收及交接

`POST /api/learning-units/{unitId}/animations` 仅接受当前 owner 的 ready 学习单元、相同知识点的已审核可信模板和 `intro` 场景版本，参数由模板注册表严格规范化。请求的 `Idempotency-Key` 与完整摘要绑定；相同请求返回原回执，不重新渲染，异摘要返回 `IDEMPOTENCY_CONFLICT`。私有缓存只执行完整性查找，不在 API 进程渲染：命中时同一数据库事务写共享审核媒体、owner 绑定、succeeded Job 与事件并返回 200；未命中写 queued Job 与事件并返回 202。`GET /api/animation-jobs/{jobId}` 直接读 owner 的持久状态与事件水位，运行中租约不会因查询被判失败。

取消路径用同一 Job 行锁与 Worker 发布排序。先取消时写 `cancelled`、失效 token、保存 owner 唯一的取消幂等键并追加事件；迟到发布不能绑定资源。先发布则取消返回 `JOB_STATE_CONFLICT`。取消键同时用数据库唯一约束解决跨 Job 并发复用；最初并发实测出现 owner 锁与 Job 锁逆序死锁，取消路径去掉多余 owner 锁后重测通过。Worker 每秒检查失效租约并对当前 token 命名的容器执行 `docker rm -f`；真实 Docker 运行中取消在 10 秒阈值内结束且没有绑定/孤儿容器。`POST /retry` 仅对 failed/cancelled 原 Job 建立新 queued Job，`retry_of` 指向原 Job，原终态不变；同键重放，异目标冲突。所有写入都经现有 Cookie、同源 Origin、CSRF 与幂等键校验；未知/其他 owner 的 Job 统一 404。

隔离 PostgreSQL 测试库从 0010 升至 [0011](../../backend/alembic/versions/0011_animation_cancel_key.py)，再降回 0010、重新升级均通过；未触碰既有运行库。`EDUMIND_TEST_DATABASE_URL=<isolated-url> EDUMIND_DOCKER_TESTS=1 uv run --frozen pytest -q tests/test_animation_job_api.py tests/test_animation_worker.py` 为 12 通过，覆盖缓存命中双 owner 共享字节但分开授权、队列/快照/幂等/越权/CSRF/参数、取消先赢与发布先赢、真正并发唯一终态、跨 Job 取消键并发、失败与取消的显式重试，以及真实容器及时终止、真实 Worker 发布。全量后端 `pytest -q` 为 524 通过、5 项 Docker 专项跳过；Ruff/Mypy 与 OpenAPI 静态契约通过。未调用 Provider。下一任务 T013 提供 GET SSE 重放与断线恢复；T014 才开放媒体读取。
