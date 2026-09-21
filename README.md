# EduMind Agent

启智学伴：面向数据结构学习的个性化学习系统。

## 后端（MVP 0.1）

后端固定使用 Python 3.11，并由 `uv.lock` 固定依赖版本。首次安装依赖：

```bash
cd backend
uv sync --python 3.11 --all-groups
```

启动 API（健康检查不需要 Provider 凭据）：

```bash
cd backend
uv run --python 3.11 uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

运行测试：

```bash
cd backend
uv run --python 3.11 pytest
```

## Web（MVP 0.1）

首次安装并启动学习入口：

```bash
pnpm --dir web install --frozen-lockfile
pnpm --dir web dev
```

生产构建：

```bash
pnpm --dir web build
```

## Compose 开发启动

需要 Docker Compose（OrbStack 兼容）。先准备本地环境文件，真实 Provider 凭据只保留在该未提交文件中：

```bash
cp .env.example .env
# 编辑 .env，至少替换 EDUMIND_POSTGRES_PASSWORD；需要生成时再填写 Provider 三项
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:5173/
```

PostgreSQL 仅在 Compose 内部网络开放；API、Web 分别暴露为 8000、5173。Compose 会先等待数据库与 API 健康检查，API 启动时自动执行 `alembic upgrade head`。仅检查健康状态时不需要 Provider 凭据；实际学习生成需要在 `.env` 设置三项 `EDUMIND_PROVIDER_*`。开发停止但保留数据卷：

```bash
docker compose down
```

不要使用 `docker compose down -v`，除非明确要删除本地开发数据。配置检查与重新构建：

```bash
docker compose config --quiet
docker compose build
```

## 本地数据备份与恢复

Compose 使用命名卷 `edumind_postgres_data` 保存 PostgreSQL 数据。日常重启使用
`docker compose restart`，或停止后重新 `docker compose up -d`；两者都会保留该卷。
在升级镜像或迁移前，建议先导出逻辑备份：

```bash
docker compose exec -T postgres pg_dump -U edumind -d edumind_dev > edumind_dev-backup.sql
```

恢复到已经启动的本地数据库时：

```bash
docker compose exec -T postgres psql -U edumind -d edumind_dev < edumind_dev-backup.sql
```

`docker compose down` 不会删除数据卷；`docker compose down -v` 会删除它，只应在明确放弃本地数据后使用。当前 Compose 配置没有自动备份、跨主机复制或生产级灾备；备份文件可能包含学习数据，应保存在受保护位置且不得提交到 Git。

## MVP 0.1 浏览器 E2E

首次运行先安装锁文件中的开发依赖和 Playwright 对应的 Chromium：

```bash
cd backend
uv sync --python 3.11 --all-groups
uv run playwright install chromium
cd ..
pnpm --dir web install --frozen-lockfile
```

随后用单个命令执行浏览器 E2E；命令会在 `127.0.0.1:4173` 临时启动 Vite，结束后自动停止：

```bash
pnpm --dir web e2e
```

该套件使用浏览器路由级 mock API，稳定覆盖一句话开始、临时首段、正式讲解/代码/三道练习、Provider 故障、审核拒绝和 SSE 异常后的持久化操作恢复，不会调用或计费真实 Provider。后端 Provider、审核门禁、幂等和恢复逻辑由 `backend/tests/test_learning_sessions.py` 的隔离 PostgreSQL 测试覆盖。真实 Provider 和首段 P95 性能不由 mock 结果替代，必须按 T035 单独验收。
