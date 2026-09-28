# MVP-0.3-T013 动画 Job SSE 验收与交接

`GET /api/animation-jobs/{jobId}/events` 使用现有 Cookie 鉴权，在响应开始前校验 owner 与 `Last-Event-ID`，随后从 PostgreSQL `animation_job_events` 只回放游标之后的已提交事件。事件以 Job 内单调整数为 `id`，数据仅含白名单阶段、进度、稳定错误码、媒体 ID、尝试序号及 Job ID。终态事件发完立即关闭；已经消费终态水位的重连立即返回空流。超前或非法游标返回 `EVENT_CURSOR_INVALID` 409；事件缺口返回 `EVENT_CURSOR_EXPIRED` 410，客户端可先 GET Job 快照取最新水位再订阅。当前不自动删事件，410 只在数据缺口时出现。

每轮查询重新检查 owner Job 和数据库会话到期时间，Cookie 过期即结束现有连接。每进程非阻塞上限 32 条流，轮询间隔 1.5 秒，空闲注释心跳约 15 秒，单条流最多 5 分钟，随后由 EventSource 按游标重连；断开订阅只释放流资源，不修改 Job 或触发渲染。会话、事件查询都使用短期数据库 session，发送数据时不占用连接。

在独立 PostgreSQL 测试库运行 `EDUMIND_TEST_DATABASE_URL=<isolated-url> uv run --frozen pytest -q tests/test_animation_events_api.py`：5 通过，覆盖已提交事件重放、实时 running/progress/failed 推送、游标去重、终态关闭、客户端重启后恢复、跨 owner 404、非法/超前 409、事件缺口 410、主动关闭订阅后 Job/attempt/事件不变、会话过期结束连接和连接容量拒绝。未调用 Provider，未触发额外渲染。下一任务 T014 提供经 owner 授权的 MP4/SRT 读取；T015 再接入浏览器播放器。
