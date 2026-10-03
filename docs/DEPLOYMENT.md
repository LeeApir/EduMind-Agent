# 课程目录版部署说明

当前交付范围以 [PRD §0](PRD.md) 和 [ADR-0007](ADR/0007-curated-course-catalog.md) 为准。以下是未来获授权后的本地运行说明，本次T034只核对文档，未执行部署、迁移、课程导入或撤回。当前Compose使用Vite开发服务器和回环端口，不是公网生产部署方案。

## 配置与启动

后端依赖使用 `backend/uv.lock`，前端使用 `web/pnpm-lock.yaml`。安装和Compose启动见[README](../README.md)。私有 `.env` 只配置本地数据库密码；目录版显式设置 `EDUMIND_PRODUCT_MODE=catalog_only` 并将三项 `EDUMIND_PROVIDER_*` 连接凭据置空。缺少或无效产品模式也关闭动态能力；`dynamic` 只保留给另行授权的历史开发回归，不用于目录交付。

Compose的API启动先执行 `alembic upgrade head`；当前迁移链到 `0017_catalog_immutability`。API、Web、PostgreSQL只绑定 `127.0.0.1` 的8000、5173、15432，可用配置覆盖端口。数据目录和媒体只读挂给API；学生无上传课程或在线发布接口。健康检查只表示服务活着，不表示已登记课程。

## 人工签核和受信登记

课程包是 `data/course_catalog/linear-v1`，当前批准版本 `linear-course v0.1.0`，摘要 `92bb0dd4778391e23aae978b8a411b466d8b5988d1cff61cff01654604af21a1`。Lee实际签核记录见[授权原文](acceptance/mvp-0.3-catalog-human-signoff-20261003.json)，受信部署输入是[allowlist](../data/course_catalog/release-allowlist.json)和[独立approval](../data/course_catalog/approvals/linear-course-v0.1.0.json)。原包内pending状态及旧HTML是冻结的审核前快照，不覆盖；当前批准以独立记录为准。

从仓库根目录先做只读预检：

```bash
python3 scripts/verify_catalog_release.py
python3 scripts/verify_catalog_exit.py
```

预检应返回 `HUMAN_APPROVED`、审核人Lee和上述准确摘要。预检不写数据库；API启动也不会自动导入。现有发布入口是受信本地Python服务 `app.services.catalog_publication.publish_catalog`，没有一键生产导入CLI。部署操作者在获得目标数据库写入授权后，从宿主后端环境调用它：使用 `load_package` 读取包，使用 `trusted_release` 读取独立allowlist，将对应approval和受信digest传入，事务成功后显式commit。不得从学生请求或待导入包自动推导可信digest，不能用TEST_ONLY测试批准代替人工签核。

登记后登录匿名会话读取 `GET /api/catalog`，确认版本/10节点；以CSRF及幂等键执行 `POST /api/catalog/sessions` 创建绑定该版本的单元。相同版本不能换内容；更改内容需新版本和新人工签核。同版本相同digest重复登记幂等，撤回后不能以旧签核重新批准。T046仅在独立测试库登记并最终撤回，并没有为开发或生产数据库完成这一步。

## 动画Worker与媒体

API不运行Worker。宿主需Docker CLI和预先拉取的固定Manim镜像 `manimcommunity/manim@sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3`。两模板为 `linked-list-insertion`、`linked-list-deletion`，版本均 `1.0.0`。经静态规则、参数校验和隔离容器处理；禁网、限制CPU/内存/时间，不运行学生或模型任意Python。

创建可写 `data/videos/cache/approved`，Worker与API使用相同物理缓存；API只读，不能用静态文件服务绕过owner/release授权。私有 `.env.worker` 只含本地 `EDUMIND_DATABASE_URL`（Compose默认 `127.0.0.1:15432/edumind_dev`，使用asyncpg URL和实际密码），可显式设置相同的 `EDUMIND_ANIMATION_CACHE_ROOT`；不放Provider密钥。从仓库根目录另开终端：

```bash
cd backend
uv run --env-file ../.env.worker python scripts/run_animation_worker.py
```

没有Worker时缓存媒体仍可读，新渲染会排队。Job写PostgreSQL，Worker重启回收过期租约，最多自动尝试两次；取消或旧尝试迟到结果不能发布。媒体必须经认证API获取MP4/SRT；学习单元撤回后已有资源、笔记、演示、新计分和对应媒体绑定均停止授权。

## 撤回与恢复

受信操作者通过 `revoke_catalog(db, release_id)` 并commit撤回；没有学生撤回或管理后台。撤回不删除既有进度证据，不改历史评分；恢复教学须建立新的批准版本，不能修改已撤回release。

数据库和媒体 `approved/entries`、`approved/objects` 同时间点成对备份/恢复，保留版本、签核和allowlist。具体命令见[README备份说明](../README.md#本地数据备份与恢复)及[容器恢复证据](acceptance/mvp-0.3-t031-compose-recovery.md)。恢复后核验批准版本、owner隔离、媒体摘要和撤回状态。`docker compose down`保留数据，`down -v`会删卷；当前没有自动备份、跨主机复制或生产灾备。

## 已知限制与部署前工作

固定10节点/30题、单语言C、两个参数化模板、预设对比演示；动态生成、模型画像推断、重解释、实时AI及动态辩论暂缓。匿名身份、同源Cookie/CSRF及Markdown清洗保留；账户合并、长期数据留存与跨站点策略仍待决定。

性能证据适用于本机单并发、固定浏览器/镜像和冻结工作树；“冷首屏”是新owner/浏览器/单元，API/DB进程仍热。不能据此承诺公网、高并发或全进程冷启动性能。详细门槛、原始结果及失败记录见[退出报告](acceptance/mvp-0.3-catalog-exit-20261003.md)。

验收工作树中仍保留未提交的旧T033代码和证据；它们未纳入T034提交。现有hash核验只能证明当前冻结工作树一致，未对洁净checkout或新部署镜像增加验收。未来部署前需单独审查并固定实际发布源码、迁移/依赖/镜像及签核配置，补该目标环境所需验证；不得自动启用动态能力、重开Provider测试或启动Phase 1。
