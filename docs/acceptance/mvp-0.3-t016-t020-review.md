# MVP 0.3 T016–T020 代码复核与修复

复核了课堂持久化、模式切换、发言 API 和前端衔接。修复两处 T017 行为缺陷及一处 T016 跨平台测试误判：

- 创建和模式切换命令现在保存提交时的不可变课堂快照。同键同摘要重试返回原回执，即使课堂随后切换了模式；新幂等键对已有课堂的创建请求也保存其回执。`0014_classroom_receipts` 增加 `result_snapshot` 和独立的 `create` 操作类型。
- 建立课堂前要求 intro 场景确有本 owner、本学习单元、审核通过且 `published_at` 非空的正式资源，不能只凭场景审核状态创建。
- POSIX `flock` 允许空锁文件，测试只在 Windows 要求单字节；动态导入 Windows 锁模块使当前平台的严格类型检查通过。

迁移前的操作没有原始回执数据，无法无损补写。此类旧幂等键重试明确返回 `409 IDEMPOTENCY_RESULT_UNAVAILABLE`，不会把当前课堂状态误报成原回执；客户端可 GET 当前课堂快照。OpenAPI 已同步该错误和资源发布门禁。

在独立 PostgreSQL 数据库验证 Alembic 0014 升级、降级、再升级。课堂/文件锁/OpenAPI 定向测试 35 项通过；后端全量 606 通过、5 跳过。前端 96 项测试与构建通过；Ruff、严格 Mypy 和 `git diff --check` 通过。测试使用 mock Provider，没有真实模型调用。工作分支为 `codex/mvp-0.3-t015`，不推送或合并；后续 T021 可从当前本地提交继续。

验证命令（在 `backend/` 目录运行；`EDUMIND_DATABASE_URL` 和 `EDUMIND_TEST_DATABASE_URL` 均指向独立测试库）：

```text
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade 0013_classroom_operations
.venv/bin/alembic upgrade head
.venv/bin/pytest -q tests/test_classroom_mode_api.py tests/test_classroom_speech_api.py tests/test_classroom_persistence.py tests/test_file_lock.py tests/test_mvp03_openapi_contract.py
.venv/bin/pytest -q --tb=no
.venv/bin/ruff check app/services/classroom.py app/services/file_lock.py app/api/classroom.py app/models/classroom.py tests/test_classroom_mode_api.py tests/test_classroom_speech_api.py tests/test_file_lock.py alembic/versions/0014_classroom_operation_receipts.py
.venv/bin/mypy app
git diff --check
cd ../web && pnpm exec vitest run
pnpm build
```
