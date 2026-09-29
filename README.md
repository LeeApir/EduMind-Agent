# EduMind Agent

启智学伴：面向数据结构学习的个性化学习系统。

当前阶段：MVP 0.3 集成验收中，已实现两个链表动画模板、专注/互动课堂、数组与链表多视角演示及 Markdown/MP4/SRT 导出；任务状态以根目录 [task.json](task.json) 为准。MVP 0.2 的 38 项任务已完成并[原样归档](docs/tasks/mvp-0.2.json)；[收尾决定](docs/acceptance/mvp-0.2-closeout-decision.md)保留 Pro 质量/闭环与 Flash 性能的证据边界，独立教学首 token 目标转为非阻塞后续优化。
学习链路连接一句话目标、10 节点知识结构、渐进画像、正式资源审核、服务端测验、
掌握度与可解释推荐。计分题只使用明确格式的客观唯一答案；不让 LLM 判定对错。
阶段状态与失败/修复证据见 [MVP 0.2 验收记录](docs/acceptance/mvp-0.2-stage-acceptance.md)。架构决定的批准状态、待决项及后续入口见 [ADR 索引](docs/ADR/README.md)。

## 后端

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

## Web

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

PostgreSQL 仅在 Compose 内部网络开放；API、Web 分别暴露为 8000、5173。Compose 会先等待数据库与 API 健康检查，API 启动时自动执行 `alembic upgrade head`。仅检查健康状态时不需要 Provider 凭据；实际学习生成需要在 `.env` 设置三项 `EDUMIND_PROVIDER_*`。

仓库示例配置使用 DeepSeek Responses API、`https://api.deepseek.com` 和 `deepseek-flash`；实际模型以服务端配置及验收记录为准，示例不代表该模型通过所有质量指标。API Key 只留在服务端 `.env`，不要提交或放入浏览器。支持的传输与安全边界见 [Provider 说明](docs/PROVIDERS.md)。

最近阶段证据见 [MVP 0.2 收尾决定](docs/acceptance/mvp-0.2-closeout-decision.md)；其中 Pro 质量/闭环与 Flash 性能分别报告。[MVP 0.1 Provider 报告](docs/acceptance/mvp-0.1-provider-acceptance.md) 仅作为历史证据。

开发停止但保留数据卷：

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

## 浏览器 E2E

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

该套件使用浏览器路由级 mock API，稳定覆盖一句话开始、正式资源、课堂模式与多视角、练习、文件下载、Provider 故障、审核拒绝和 SSE 异常恢复，不会调用或计费真实 Provider。隔离 PostgreSQL 后端测试负责审核、owner、幂等和持久恢复。真实前后端集成需要另外运行 `web/tests/e2e/real_stage_flow.py`：先迁移隔离测试库、准备已审核的真实模板媒体缓存，再设置 `EDUMIND_TEST_DATABASE_URL` 和 `EDUMIND_DATABASE_URL` 指向该库，从 `backend/` 执行 `uv run python ../web/tests/e2e/real_stage_flow.py`。这条流程使用确定性 mock Provider，不能替代真实模型质量或首段 P95 验收；真实模型证据由 T033 单独记录。

## MVP 0.2 验证入口

后端数据库测试必须设置 `EDUMIND_TEST_DATABASE_URL` 为已经迁移的隔离 PostgreSQL
URL；未设置会跳过 DB 测试，不能视为全量通过。测试数据库会写入合成夹具，不可指向生产库。
闭环与容器恢复证据见 [自动化闭环报告](docs/acceptance/mvp-0.2-closed-loop.md)。

从 `backend/` 执行真实验收前，设置 `EDUMIND_DATABASE_URL` 指向隔离测试库，
确保 `.env` 中配置当前服务端 Provider，然后使用全新的报告文件名：

Beta严格工具参数路径需显式设置 `EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=beta_tools`；
只支持已配置的官方DeepSeek同源主机，普通文本/SSE仍走原Responses。
当前Beta完整质量验收未通过，4项协议探针通过不代表阶段通过；默认配置不自动切换。
可在以下命令前加 `env EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=beta_tools` 作隔离验证，
无需修改真实`.env`。接口与安全约束见 [Provider说明](docs/PROVIDERS.md)。

```bash
uv run --env-file ../.env python ../docs/acceptance/run_mvp02_acceptance.py \
  --confirm-billable --output ../docs/acceptance/new-stage-report.json
uv run --env-file ../.env python -m tests.resource_quality \
  --mode provider --confirm-billable --output ../docs/acceptance/new-quality-report.json
```

第一个命令按公开题面要求操作者独立输入答案 JSON，最多 30 次模型尝试；
第二个命令最多 86 次请求、禁重试/修正。两者都会计费，必须事先授权；
不要读取答案键或复制标准答案完成验收，不要覆盖历史报告。
旧指令生成的开放题保留原版本，不迁移评分或改写历史证据；应使用新生成的客观题。
真实资源质量见 [质量报告](docs/acceptance/mvp-0.2-resource-quality.md)。

非计费 HTTP 路径性能使用 `run_path_benchmark.py`：先启动连接隔离数据库的
Uvicorn 8001，运行 `uv run python ../docs/acceptance/run_path_benchmark.py --output ../docs/acceptance/new-path-report.json`。
它创建独立用户和合成画像，单并发、每接口 5 次预热与 100 次测量，不证明公网或高并发容量。
