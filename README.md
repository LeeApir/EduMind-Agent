# EduMind Agent

启智学伴：面向数据结构学习的个性化学习系统。

当前交付：**MVP 0.3 课程目录版**，范围依据 [PRD v2.2 §0](docs/PRD.md) 与 [ADR-0007](docs/ADR/0007-curated-course-catalog.md)。从10节固定课程选择节点，阅读讲解/完整C示例、完成每节3道固定练习，查看进度与路径推荐；保留两个链表动画模板、预设数组 vs 链表演示及 Markdown/MP4/SRT 导出。核心学习流程无需 Provider key，模型调用为0。

`linear-course v0.1.0` 已由 Lee 实际审阅并签核具体摘要；[签核记录](docs/acceptance/mvp-0.3-catalog-human-signoff-20261003.json)与[受信发布清单](data/course_catalog/release-allowlist.json)独立保存。当前通过的是目录版阶段退出，见[退出报告](docs/acceptance/mvp-0.3-catalog-exit-20261003.md)；课程只在隔离测试库核验登记/撤回，尚未部署。

**动态生成、重解释、实时AI互动及动态辩论仍暂缓**；服务端默认 `catalog_only`，在构建模型依赖前拒绝动态入口。T033 保持 blocked，原模型质量/延迟成绩不变，目录静态性能不作为动态生成通过。固定题由服务端确定性计分，首次完整作答形成掌握度证据，重复练习有反馈但不刷掌握度；做完课程不等于已掌握。

任务状态以根目录 [task.json](task.json) 为准，目录版退出后保持此账本，不自动进入 Phase 1。MVP 0.2 的38项任务已[原样归档](docs/tasks/mvp-0.2.json)，其[收尾决定](docs/acceptance/mvp-0.2-closeout-decision.md)保留 Pro 质量/闭环与 Flash 性能的证据边界。架构状态和待决项见 [ADR 索引](docs/ADR/README.md)。

## 后端

后端固定使用 Python 3.11，并由 `uv.lock` 固定依赖版本。首次安装依赖：

```bash
cd backend
uv sync --frozen --python 3.11 --all-groups
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

需要 Docker Compose（OrbStack 兼容）。这是本地开发栈；目录版启动、签核登记、Worker和撤回步骤见[部署说明](docs/DEPLOYMENT.md)。先准备本地私有环境文件：

```bash
cp .env.example .env
# 编辑 .env，替换 EDUMIND_POSTGRES_PASSWORD；目录版不填 Provider 凭据
EDUMIND_PRODUCT_MODE=catalog_only EDUMIND_PROVIDER_BASE_URL= \
EDUMIND_PROVIDER_API_KEY= EDUMIND_PROVIDER_MODEL= docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:5173/
```

PostgreSQL 仅向宿主回环地址的 15432 端口开放，供独立动画 Worker 连接；API、Web 分别仅在回环地址暴露 8000、5173。端口可用 `EDUMIND_POSTGRES_PORT`、`EDUMIND_API_PORT`、`EDUMIND_WEB_PORT` 覆盖。Compose 会先等待数据库与 API 健康检查，API 启动时自动执行 `alembic upgrade head`。目录学习不需要 Provider 凭据。健康检查不证明课程已登记；API不会自动导入课程，须受信操作者在部署另行获授权后登记已签核版本。没有批准课程时目录为空，不能用自由生成补齐。

MVP 0.3 动画 Worker 是宿主机上的独立进程，需要可用的 Docker CLI、已拉取的固定 Manim 镜像和仅含本地数据库 URL 的私有 `.env.worker`（不要提交）。先创建可写媒体目录 `mkdir -p data/videos/cache/approved`；Compose 以只读方式把同一目录挂给 API，Worker 在宿主机写入经审核媒体。`.env.worker` 中将 `EDUMIND_DATABASE_URL` 指向 `127.0.0.1:15432/edumind_dev`，然后另开终端运行：

```bash
cd backend
uv run --env-file ../.env.worker python scripts/run_animation_worker.py
```

Worker 不接收 Provider 密钥；渲染时启动的固定 Manim 容器不挂 Docker socket、数据库或媒体库。只启动 API 而不启动 Worker 时，缓存命中仍可读，但新动画 Job 会保持排队。Worker 重启先回收过期租约，最多自动尝试两次；取消或旧尝试的迟到结果不能重新发布。隔离 Compose 重启实测见 [T031 验收记录](docs/acceptance/mvp-0.3-t031-compose-recovery.md)。

两个模板的合法边界、缓存播放和按需渲染单机验收结果见 [T032 动画报告](docs/acceptance/mvp-0.3-t032-animation-performance.md)；报告记录指标、首次测量失败和环境限制；每槽原始数据保存在本地材料。

仅保留用于历史动态开发的仓库示例配置使用 DeepSeek Responses API、`https://api.deepseek.com` 和 `deepseek-flash`；实际模型以服务端配置及验收记录为准，示例不代表该模型通过所有质量指标。API Key 只留在服务端 `.env`，不要提交或放入浏览器。支持的传输与安全边界见 [Provider 说明](docs/PROVIDERS.md)。

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

Compose 使用命名卷 `edumind_postgres_data` 保存 PostgreSQL 数据，动画媒体默认保存在宿主 `data/videos/cache`（可通过 `EDUMIND_MEDIA_CACHE_HOST_PATH` 改为绝对路径）。该目录须由 Worker 用户可写、API 可读；不要让 API 写入或直接公开为静态目录。日常重启使用
`docker compose restart`，或停止后重新 `docker compose up -d`；两者都会保留该卷。
在升级镜像或迁移前，建议先导出逻辑备份，并同时复制媒体缓存的 `approved/entries` 与 `approved/objects`（其余临时尝试目录不作为恢复数据）：

```bash
docker compose exec -T postgres pg_dump -U edumind -d edumind_dev > edumind_dev-backup.sql
tar -C data/videos/cache -cf edumind-media-backup.tar approved/entries approved/objects
```

恢复到已经启动的本地数据库时：

```bash
docker compose exec -T postgres psql -U edumind -d edumind_dev < edumind_dev-backup.sql
tar -C data/videos/cache -xf edumind-media-backup.tar
```

数据库和媒体须按同一时间点成对备份/恢复；恢复后核对 API owner 授权及 MP4/SRT 摘要。`docker compose down` 不会删除数据卷或宿主媒体；`docker compose down -v` 会删除数据库卷，只应在明确放弃本地数据后使用。当前 Compose 配置没有自动备份、跨主机复制或生产级灾备；备份文件可能包含学习数据，应保存在受保护位置且不得提交到 Git。

## 浏览器 E2E

首次运行先安装锁文件中的开发依赖和 Playwright 对应的 Chromium：

```bash
cd backend
uv sync --frozen --python 3.11 --all-groups
uv run playwright install chromium
cd ..
pnpm --dir web install --frozen-lockfile
```

随后用单个命令执行浏览器 E2E；命令会在 `127.0.0.1:4173` 临时启动 Vite，结束后自动停止：

```bash
pnpm --dir web e2e
```

这是历史动态流程的回归套件，不能替代目录版真实集成证据。干净 checkout 的目录版离线预检运行 `python3 scripts/check_catalog_workflow.py` 和 `python3 scripts/verify_catalog_release.py`，结果边界见[已提交版本验证](docs/acceptance/mvp-0.3-clean-checkout-20261003.md)。`verify_catalog_exit.py` 是依赖原 `.env` 和历史实验文件的冻结工作树审计器，不能作为干净 checkout 的检查入口。该历史套件使用浏览器路由级 mock API，稳定覆盖一句话开始、正式资源、课堂模式与多视角、练习、文件下载、Provider 故障、审核拒绝和 SSE 异常恢复，不会调用或计费真实 Provider。隔离 PostgreSQL 后端测试负责审核、owner、幂等和持久恢复。真实前后端集成需要另外运行 `web/tests/e2e/real_stage_flow.py`：先迁移隔离测试库、准备已审核的真实模板媒体缓存，再设置 `EDUMIND_TEST_DATABASE_URL` 和 `EDUMIND_DATABASE_URL` 指向该库，从 `backend/` 执行 `uv run python ../web/tests/e2e/real_stage_flow.py`。这条流程使用确定性 mock Provider，不能替代真实模型质量或首段 P95 验收；真实模型证据由 T033 单独记录。

## MVP 0.2 历史验证入口（当前暂缓付费测试）

以下命令仅保留历史复现说明；目录版退出不执行，不恢复旧付费授权。T033仍blocked，任何新的Provider测试须另行明确授权。

后端数据库测试必须设置 `EDUMIND_TEST_DATABASE_URL` 为已经迁移的隔离 PostgreSQL
URL；未设置会跳过 DB 测试，不能视为全量通过。测试数据库会写入合成夹具，不可指向生产库。
闭环与容器恢复证据见 [自动化闭环报告](docs/acceptance/mvp-0.2-closed-loop.md)。

历史动态验收和质量成绩见[收尾决定](docs/acceptance/mvp-0.2-closeout-decision.md)与[质量报告](docs/acceptance/mvp-0.2-resource-quality.md)。当前目录版不启用这些付费流程。验收目录只保留阶段报告、关键动画/恢复报告与签核依据；原始日志、冻结协议、逐槽结果和诊断已移至被 Git 忽略的本地材料，读取及历史恢复方式见[材料索引](docs/acceptance/README.md)。回归测试所需工具和原样夹具分别保留在 `scripts/acceptance_support/`、`backend/tests/fixtures/acceptance/` 和 `web/tests/fixtures/`。
