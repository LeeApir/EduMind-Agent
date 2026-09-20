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

PostgreSQL、API、Web 分别暴露为 5432、8000、5173；Compose 会先等待数据库与 API 健康检查，API 启动时自动执行 `alembic upgrade head`。仅检查健康状态时不需要 Provider 凭据；实际学习生成需要在 `.env` 设置三项 `EDUMIND_PROVIDER_*`。开发停止但保留数据卷：

```bash
docker compose down
```

不要使用 `docker compose down -v`，除非明确要删除本地开发数据。配置检查与重新构建：

```bash
docker compose config --quiet
docker compose build
```
