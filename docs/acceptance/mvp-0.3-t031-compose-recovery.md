# MVP-0.3-T031 容器重启与动画恢复验收

## 结果

使用专用 Compose 项目 `edumind_t031_stage_20260929`、独立 PostgreSQL 卷、宿主临时媒体目录 `/private/tmp/edumind-t031-media-20260929`，未挂载或修改现有开发数据库卷。API 在空库上自动迁移到 Alembic head。宿主独立 Worker 使用相同媒体目录与隔离数据库，模型/Provider 凭据为空，真实执行固定摘要 Manim 容器。

探针 `backend/tests/compose_mvp03_recovery.py` 创建 owner 已审核讲解、画像和课堂；将课堂从专注切为互动、启用基础同学，得到 revision 2。动画分别创建已缓存成功（value=9）、在途（value=11，领取 attempt 1 后模拟 Worker 进程退出）和已取消（value=12）三类 Job。真实重启 PostgreSQL 与 API 后，课堂模式、角色、revision 及已审核 Markdown 不变；成功媒体的 MP4/SRT 下载字节与响应 SHA-256 一致，在途仍为 running，取消仍为 cancelled。等待旧租约过期后启动新的宿主 Worker：事件依次为 queued、running、recovered、running、progress、succeeded，attempt 2 成功渲染并发布新媒体；旧 attempt 1 的发布调用返回 false。取消 Job 保持 attempt 0，事件数不增加，未重复生成；最终重建 API 镜像后再次读取课堂、两组媒体和导出均通过。

首次隔离启动发现两个实际部署问题：Compose 原来没有媒体共享挂载；后端镜像把代码放在 `/app`，而模板源码/注册表按仓库根目录定位，因此动画请求 500。修复后镜像固定在 `/workspace/backend`，版本化 `data/` 挂到 `/workspace/data`，媒体目录单独只读挂给 API；Worker 在宿主写入同一目录。镜像基础 Python/uv 现按摘要固定，启动只安装生产依赖；PostgreSQL 仅向宿主回环端口开放供 Worker 使用，API/Web 也仅绑定回环地址。

## 复现与证据边界

以仓库根目录为起点，先准备独立测试密码、媒体目录和项目名。不要把真实 `.env`、开发卷或已存在的媒体目录用于本测试。以下命令用 `EDUMIND_POSTGRES_PASSWORD`、`EDUMIND_TEST_DATABASE_URL`、`EDUMIND_MEDIA_CACHE_HOST_PATH` 和 `EDUMIND_T031_STATE` 指向同一组独立资源；运行 `docker compose -p <独立项目名> up --build -d postgres api` 后，执行：

```bash
cd backend
uv run python tests/compose_mvp03_recovery.py seed
cd ..
docker compose -p <独立项目名> restart postgres api
cd backend
uv run python tests/compose_mvp03_recovery.py check-restart
# 等待 seed 时领取的 30 秒租约过期，再重启独立 Worker
uv run python scripts/run_animation_worker.py --once
uv run python tests/compose_mvp03_recovery.py check-worker
```

Worker 使用 `EDUMIND_DATABASE_URL` 和 `EDUMIND_ANIMATION_CACHE_ROOT=<独立媒体目录>/approved`；探针使用相同库的 `EDUMIND_TEST_DATABASE_URL`。本次实际输出依次为 `seeded=true`、`recovered=false`、`processed animation job`、`recovered=true`，最终媒体及导出校验为 true。最后使用最终 Compose 文件再次 `up --build -d postgres api` 并重复 `check-worker` 通过。测试后可对该专用项目执行 `docker compose -p <独立项目名> down`；不加 `-v` 保留证据卷，真实用户卷从未参与。

`docker compose config --quiet`、后端 Ruff 和 Mypy（95 文件）通过；隔离 PostgreSQL 针对缓存、Job API、Worker、媒体授权与课堂持久化的测试为 **22 passed、3 skipped、1 warning**。3 个跳过项需 `EDUMIND_DOCKER_TESTS=1`，本任务另以真实隔离 Compose、真实 Worker 与一次固定镜像渲染验证重启路径；批量新渲染可用率与性能仍由 T032 验收。真实 Provider 调用 0 次。README 记录宿主 Worker、媒体权限、数据库与媒体成对备份/恢复；当前没有自动备份或跨主机灾备。
