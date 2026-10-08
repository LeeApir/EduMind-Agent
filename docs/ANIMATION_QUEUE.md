# 动画投递与恢复运行说明（T019–T020）

依据已批准[ADR-0009](ADR/0009-durable-animation-queue.md)。T019交付PG事务outbox和独立publisher/reconciler；T020交付固定Celery消费者、持久尝试账本和独立宿主清理器，取消联动/SSE由T021完成。此文不表示队列阶段验收或生产部署完成。默认`EDUMIND_ANIMATION_DISPATCH=pg_poll`与`catalog_only`继续有效。

## 事务与故障语义

新Job或显式重试按当前服务端路由开关，Job内部保存backend和epoch，celery模式在同一事务保存queued事件与唯一(job_id,epoch)outbox；缓存命中/幂等重放不增加outbox。API仍在commit后返回202，不联系broker。PG领取器只领取pg_poll；T020独立reaper处理两种backend的过期租约。既有Job迁移回填pg_poll/epoch1，公共Job响应不暴露路由字段。

独立`backend/scripts/run_animation_dispatcher.py`每轮短事务领取到期行（SKIP LOCKED），随机token/30秒数据库租约，在锁外发送固定Celery任务。每次传输在隔离子进程执行，总等待4.5秒，进程超时/失败/确认丢失均仅记录BROKER_UNAVAILABLE，退避1/2/4/…/60秒，不增加render attempt。正常发送再以当前未过期token CAS标sent。进程死亡时sending可在租约过期后重新领取；已发送但未领取的queued行60秒后可恢复pending。reconciler每30秒扫描最多100个需修复Job；缺失outbox补建，活跃publisher租约不覆盖，终态/取消/旧epoch置obsolete。broker丢失已发送消息也可从PG重新投递，不承诺恰好一次执行。publisher逐次领取，避免大批顺序发送导致尚未发送的租约预先过期。

消息只有`schema_version=1`、规范UUID的`job_id`、正整数`dispatch_epoch`；唯一固定任务`edumind.render_animation.v1`/队列`edumind.animation.v1`，task ID为outbox ID。消息无owner、路径、源码、DSL、Provider凭据或上下文；严格JSON且不接受额外字段。Celery result backend关闭，API不读AsyncResult。发送子进程只接收PATH/SYSTEMROOT及broker URL环境，不继承Provider、数据库或KEK。错误、URL、任务异常原文不进日志或outbox。

## 固定依赖与隔离运行

Python锁定Celery5.6.3、Kombu5.6.2、redis-py6.4.0，所有传递依赖/hash在uv.lock。Redis7.4.7-alpine的官方manifest摘要为`sha256:02f2cc4882f8bf87c79a220ac958f58c700bdec0dfb9b9ea61b62fb0e8f1bfcf`，compose按摘要引用。配置依据[Celery Redis文档](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)、[Celery配置](https://docs.celeryq.dev/en/stable/userguide/configuration.html)、[Redis ACL](https://redis.io/docs/latest/manual/security/acl/)及[内存策略](https://redis.io/docs/latest/develop/reference/eviction/)。visibility_timeout=300仅是运输重送参数；业务恢复依赖PG。

compose新增可选`animation-queue` profile，Redis只连接私有internal网络、不绑定宿主端口，独立持久卷/AOF/everysec、128MiB/noeviction，容器256MiB；publisher只连接PG与broker，不注入Provider配置。启用前部署者提供私有ACL文件`EDUMIND_REDIS_ACL_FILE`（默认路径local-materials/redis/users.acl并被Git忽略）和publisher专用broker URL，不在命令输出、Git或公开文档放真实密码。ACL必须禁用default用户，为publisher与worker分别设置密码及`~edumind.animation:*`键域，授予实际broker所需命令，拒绝管理/flush命令；文件缺失时Redis不得启动。只启publisher而未启动消费者会持续保留queued并重投。实际生产切换仍须另行授权及完成T036故障矩阵。

本地显式运行接口（仅在迁移完成和私有broker配置存在后）：`cd backend && uv run --frozen python scripts/run_animation_dispatcher.py`；`--once`执行一次巡检/投递。publisher/reconciler是单独进程，API lifespan不启动隐式工作。默认compose不用新profile。

## 操作回滚与验证

管理员先设新Job默认pg_poll、暂停Celery消费者、排空当前lease及容器，再使用内部`route_queued_template_jobs(sessions, ids, backend='pg_poll')`迁移最多100个queued模板Job。它锁Job后锁outbox，改backend/epoch并obsolete旧行；反向切换celery同事务新增outbox。running/终态不改写、审核目标失效拒绝、不把DSL交给旧模板执行器。切换函数没有HTTP入口，不以清空Redis作为正确性条件。实际在途容器与尝试账本迁移由T020/T036核验。

Alembic0021只在开发/隔离数据库验证upgrade/down0020/upgrade；存在活跃celery Job时downgrade明确拒绝，避免删除已接受任务的投递信息。常规功能回滚保持增量schema，不能以downgrade替代运行回滚。专用`scripts/run_queue_storage_tests.py`只接受新隔离DB名；旧合成动画fixture使用测试子进程dynamic、无Provider/KEK/broker配置，实际服务器和compose仍默认catalog_only。Mock、隔离PG、实际broker及真实渲染证据须分别记录；T036负责完整Redis/Celery/渲染故障矩阵。


## T020：消费者与宿主恢复

在同一可信POSIX宿主、同一Docker daemon启动三个独立常驻进程：publisher、消费者、宿主控制器。消费者与控制器都使用本地PG连接及相同的私有媒体目录、`EDUMIND_RENDER_LOCK_ROOT`（默认`data/videos/cache/host-locks`）。锁目录只能由受信运行用户写入，不得为不同进程配置不同目录。控制器不依赖Redis或Worker父进程；由运行环境独立监管和重启。现有compose不自动启动它们，也不向API/publisher挂载Docker socket。

在迁移到0022、预先拉取固定Manim镜像、核对既有容器与账本后，分别运行：

```bash
cd backend
uv run --frozen --env-file ../.env.worker python scripts/run_animation_host_controller.py
uv run --frozen --env-file ../.env.worker python -m app.workers.animation_consumer
```

以上两行需要两个终端或独立进程服务。消费者默认prefork/concurrency1，`--pool=solo`只用于明确的本地隔离演练；固定任务注册表仅有`edumind.render_animation.v1`，late ACK、worker lost重送、prefetch1，仍由PG领取去重。worker环境拒绝Provider/凭据保护配置；`.env.worker`仅提供数据库、worker专用私有broker及共享目录设置，不复制API的密钥环境。控制器只需PG、Docker及目录配置。保持API默认pg_poll与catalog_only，文中命令不表示已启用生产Celery路由。

领取同时记录token/attempt/backend/epoch；心跳10秒、租约30秒，所有续租、进度和发布核对未过期的同一token/attempt/backend/epoch。控制器每5秒回收最多100个过期租约，先持久化清理意图再失效token，最多两次尝试；Celery恢复同事务生成新epoch/outbox。旧消息、重复消息和迟到结果不能增加有效尝试或正式媒体绑定。已有PG轮询Worker也复用同一宿主协调器。

Docker启动/停止按token文件锁跨进程串行，所有账本变更在宿主锁外按Job→尝试行顺序提交。启动前后都复核租约。控制器每轮枚举本应用可见容器，失效token强制移除并重新核验不存在；已写absent后迟到出现的容器也会重新清理。单次PG检查1秒、启动RPC3秒、停止RPC2秒、库存RPC1秒；取消观察1秒。Docker/PG不可确认时只记录固定告警并保留意图，不把检查失败视为不存在。枚举超过100个容器时拒绝确认并告警，需运维排查容量；这不是多宿主调度或无限积压清理方案。

0022为迁移时已有running token补建starting账本；任何无法对应账本的旧容器都要求人工核对/排空，不能按前缀批量删除。存在running Job时0022 downgrade拒绝。运行回滚先停新投递、排空租约/容器再切回pg_poll，保留增量schema。T020隔离测试覆盖实际父进程死亡、prefork子进程死亡、Redis重启、两次租约耗尽、迟到容器重清及单一正式绑定；完整故障矩阵/控制器重启验收留在T036，取消事务与SSE联动留在T021。
