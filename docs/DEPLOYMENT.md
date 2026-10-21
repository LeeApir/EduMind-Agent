# 课程目录版部署说明

## 阶段切换不代表部署授权（2026-10-21）

P1已按[收敛交付范围](acceptance/phase-1-closeout-20261021/README.md)结束；Phase 1.5只完成活动账本切换，尚未启动开发、部署或试用。继续默认catalog_only及原签核清单，不得以旧冻结包、诊断成绩或本说明中的历史命令自动启用dynamic、追加真实Provider调用或导入未签核课程。T040质量和T041旧链性能均blocked；新链性能按新契约独立验收。

当前交付范围以 [PRD §0](PRD.md) 和 [ADR-0007](ADR/0007-curated-course-catalog.md) 为准。以下是未来获授权后的本地运行说明，本次T034只核对文档，未执行部署、迁移、课程导入或撤回。当前Compose使用Vite开发服务器和回环端口，不是公网生产部署方案。

## 配置与启动

后端依赖使用 `backend/uv.lock`，前端使用 `web/pnpm-lock.yaml`。安装和Compose启动见[README](../README.md)。私有 `.env` 只配置本地数据库密码；目录版显式设置 `EDUMIND_PRODUCT_MODE=catalog_only` 并将三项 `EDUMIND_PROVIDER_*` 连接凭据置空。缺少或无效产品模式也关闭动态能力；`dynamic` 只保留给另行授权的历史开发回归，不用于目录交付。

Compose的API启动先执行 `alembic upgrade head`；目录版退出时迁移链到 `0017_catalog_immutability`；Phase 1 开发链现增量到 `0025_animation_dsl_media`（目标部署仍需另行核验）。API、Web、PostgreSQL只绑定 `127.0.0.1` 的8000、5173、15432，可用配置覆盖端口。数据目录和媒体只读挂给API；学生无上传课程或在线发布接口。健康检查只表示服务活着，不表示已登记课程。

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

Phase 1 T020增加固定Celery消费者与独立宿主控制器，运行接口、共享token锁目录、账本迁移和故障恢复边界见[动画队列说明](ANIMATION_QUEUE.md#t020消费者与宿主恢复)。消费者复用现有模板/容器限制，PG仍是任务事实来源；Worker父进程或子进程死亡后由独立控制器回收过期租约与残留容器。默认pg_poll及catalog_only不变，未执行生产切换。启用Celery时必须分别监管publisher、消费者和控制器；不能只启动Redis/消费者而遗漏宿主清理。

## Phase 1 审核 DSL 的隔离渲染（T027）

`app.workers.dsl_render.render_dsl_job` 是已持久化 DSL 候选的内部渲染步骤。T028 接续 Job 创建、调度及正式媒体发布；T027 不提供学生调用入口，也不将渲染成功直接标记为 Job 成功。目录模式与真实 Provider 零预算保持有效。

Worker 先在 PostgreSQL 校验当前 owner、目标/场景版本、独立审核 binding、当前明确登记的政策及永久撤回状态，重新编译 canonical DSL，并匹配 Job 的缓存键、源摘要、编译器、Review、字幕、镜像、字体和渲染器摘要。容器启动前再次完整重编译比对；源文件或执行器变化立即拒绝。政策摘要包含固定执行器、媒体校验器及 Worker，升级后须显式登记新政策，旧候选不能自动沿用。

DSL当前使用T037固定字体镜像，构建和准确摘要见[DSL运行时](../backend/docker/dsl/README.md)；模板仍使用原Manim摘要。容器以 UID/GID 10001 运行，禁网、根文件系统只读、丢弃全部 capabilities、禁止提权，CPU 2、内存 1 GiB、pids 128，渲染及产物校验总限时 120 秒。唯一只读挂载是本次私有输入目录，含受信编译结果、精确字幕、摘要清单和固定执行/字体核验文件；不挂载仓库、宿主缓存、凭据或 Docker socket。`/tmp` 和 `/output` 各使用 256 MiB tmpfs，输出空间有内核硬配额，单个 MP4/SRT 最多 64 MiB。宿主只编译 DSL 为文本；Python 语法检查和 Manim 执行在容器内进行。容器 Python 3.14 与宿主 Python 3.11 的 AST 格式差异由各自完整静态检查处理，源摘要及节点数仍须一致。

`.ready` 只提示可取回文件。宿主验证实际 MP4/SRT 字节及精确字幕，并把取回的 MP4 字节送入同一受限容器中的固定 PyAV 校验器重新解码：单视频流、1280×720、15 fps（T037修订后，旧480p仅为历史记录）、30–90 秒、帧数与 DSL 时间线吻合。通过后只留下本地候选 MP4/SRT；授予媒体访问还须由 T028 在发布事务中重新核验当前资格。

容器名、宿主 token 锁和持久尝试账本沿用 T020，心跳持续到发布回调结束；失败/取消清理容器和私有目录，保留固定错误码与 PG 终态，过期租约由既有 reaper 回收，最多两次尝试。旧 token、渲染期间候选撤回或政策变化不能接受产物。异步取消还会等待已启动渲染线程返回并回收迟到的本地产物。退出码、不可确认的宿主清理或输出校验失败均拒绝发布；容器自动删除导致无法取得 OOM 状态时保留一般容器失败码，不能假称确定的 OOM 原因。

验收用独立测试数据库和实际 Docker；Mock 审核仅用于构造内部测试候选，不能充当真实模型教学质量验收。真实媒体、禁网/根目录及输入只读、输出配额 ENOSPC、超时、容器退出、租约恢复、撤回/替换与取消的证据在 `local-materials/phase-1-t027/checks/`。故障脚本由测试操作者固定注入，不接受模型 Python；未执行生产部署或动态开放。

## 撤回与恢复

受信操作者通过 `revoke_catalog(db, release_id)` 并commit撤回；没有学生撤回或管理后台。撤回不删除既有进度证据，不改历史评分；恢复教学须建立新的批准版本，不能修改已撤回release。

数据库和媒体 `approved/entries`、`approved/objects` 同时间点成对备份/恢复，保留版本、签核和allowlist。具体命令见[README备份说明](../README.md#本地数据备份与恢复)及[容器恢复证据](acceptance/mvp-0.3-t031-compose-recovery.md)。恢复后核验批准版本、owner隔离、媒体摘要和撤回状态。`docker compose down`保留数据，`down -v`会删卷；当前没有自动备份、跨主机复制或生产灾备。

## 已知限制与部署前工作

固定10节点/30题、单语言C、两个参数化模板、预设对比演示；动态生成、模型画像推断、重解释、实时AI及动态辩论暂缓。匿名身份、同源Cookie/CSRF及Markdown清洗保留；账户合并、长期数据留存与跨站点策略仍待决定。

性能证据适用于本机单并发、固定浏览器/镜像和冻结工作树；“冷首屏”是新owner/浏览器/单元，API/DB进程仍热。不能据此承诺公网、高并发或全进程冷启动性能。详细门槛、原始结果及失败记录见[退出报告](acceptance/mvp-0.3-catalog-exit-20261003.md)。

T034验收工作树中仍保留未提交的旧T033代码和证据；它们未纳入T034提交。当时的hash核验只证明冻结工作树一致。之后已对交付提交 `c7831d1` 建立干净checkout，锁定依赖新安装、生产Web构建、目录离线回归、新隔离库迁移及构建产物浏览器冒烟通过，见[已提交版本验证](acceptance/mvp-0.3-clean-checkout-20261003.md)。旧退出脚本依赖原 `.env` 和历史实验，不能直接在该checkout通过，原失败及冻结文件保留。此次不重跑媒体渲染/性能矩阵、不构建新部署镜像；未来部署前仍需固定实际发布源码、迁移/依赖/镜像及签核配置，补目标环境验证，不得自动启用动态能力、重开Provider测试或启动Phase 1。

## T028 DSL Job开发实现

[DSL Job v1](agents/animation-dsl-jobs-v1.md)新增API准备/SSE和owner私有Job/media来源；默认catalog_only拒绝动态路由，服务端DSL模型预算默认拒绝。临时凭据仅API内存，Worker无Provider权限，显式pg_poll/celery切换仍用旧运维函数名route_queued_template_jobs并兼容DSL资格。私有DSL缓存部署目录必须持久保存且只由API/Worker维护；显式GC以同namespace/key锁及非锁定PG引用检查保留正式文件，旧孤儿最短24h。0024/0025有保留新来源时拒绝降级；生产迁移/清理/部署未执行。T028验收为隔离PG、Redis、实际Linux容器和mock模型，不能替代真实模型画面/开放验收。
