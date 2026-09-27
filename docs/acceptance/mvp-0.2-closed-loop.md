# MVP 0.2 自动化学习闭环验收

任务：MVP-0.2-T024。日期：2026-09-26。执行人：Lee。

## 证据边界

本任务没有真实 Provider 请求，不产生模型费用。真实 Provider 质量证据见
`mvp-0.2-resource-quality.md`；真实完整流程和性能验收属于 T025。

`backend/tests/test_learning_closed_loop.py` 使用真实 PostgreSQL、实际 REST/SSE
路由和发布流程，仅模型输出使用 mock。覆盖一句话输入、正式资源、服务端评分、
掌握度提升、下一节点、手动画像修正、路径过期与重算、连续两次错误回退、
幂等重放、跨 owner 拒绝。通过独立 Python 进程读取同一数据库，核对画像、
路径、掌握度与最新回执恢复。测试会话令牌仅通过 stdin 传递，不输出或提交。

浏览器 `web/tests/e2e/learning_flow.py` 是路由 mock 回归，覆盖测验提交与刷新、
移动端、Provider 失败、审核拒绝、SSE 恢复。不能作为真实后端或模型闭环证据。

Compose 探针使用人工构造、审核通过的资源，不声称完成真实模型生成。实际调用
评分与路径 API，然后重启 PostgreSQL/API，核对资源、测验回执、掌握度和路径
快照。行为模型故意返回不可用，确认该失败不会回滚已提交的测验证据。

## 实际执行

- 隔离 PostgreSQL 上 `uv run pytest -q`：304 passed，无跳过，7 条既有弃用警告。
- `uv run ruff check tests/compose_recovery_check.py tests/learning_recovery_probe.py tests/test_learning_closed_loop.py`：通过。
- `uv run mypy app`：53 个源文件通过。
- 使用 webapp-testing 的 `with_server.py` 启动 4173 Vite，运行
  `uv run python ../web/tests/e2e/learning_flow.py`：通过，服务器自动停止。
  浏览器控制台包含负向场景的 401/404；测试成功不代表没有这些预期响应。
- `docker compose --env-file /dev/null -p edumind-mvp02-acceptance build api`：通过。
- 同一独立项目 `up -d api`，`exec -T api uv run --no-dev alembic upgrade head`，
  `exec -T api uv run --no-dev python tests/compose_recovery_check.py seed`，
  `restart postgres api`，最后运行该探针 `check`：输出 `recovered: true`。

首次 seed 在迁移就绪前失败（users 表尚不存在）；确认迁移完成后重跑成功。
未修改生产 schema、未绕过 Alembic。项目没有加载真实 `.env`，未删除数据库卷。
容器内临时会话文件权限 0600，不作为证据附件。测试数据库仅含验收夹具。

## 限制与下一步

这是自动化回归组合，不是单次浏览器访问真实 Provider 的端到端演示。
T025 仍须独立运行真实 Provider 主链路并测量路径请求，核对 PRD 退出门槛。
