# MVP-0.3-T015 按需动画播放器验收与交接

Web 的已审核学习页只在知识点为链表插入/删除时显示可选动画卡片；页面加载、刷新或切换节点均不自动创建新 Job。学生点击“打开动画”后，客户端先在 `sessionStorage` 保存本次请求键与模板参数，再调用创建接口；响应丢失时只以原键重放。拿到 Job ID 后，刷新先 GET 快照，再通过原生 EventSource 用 `after=last_event_id` 首次订阅，自动重连时由浏览器发送 `Last-Event-ID`。客户端按 Job 内序号去重，终态关闭连接；取消与显式重试分别保存自己的幂等键。节点/单元切换递增 generation，旧请求和事件不能覆盖当前页。

卡片展示缓存就绪、排队、进度、失败、取消和重试。成功后用带 Cookie 的 owner 媒体接口播放 MP4；字幕从 SRT 读取并在浏览器内转换为 WebVTT Blob track。媒体或网络出错只在卡片中提示，文字讲解、代码和练习仍可继续。断网时 EventSource 自行重连，恢复网络会主动重读旧 Job 快照，不发新的创建 POST。为原生 EventSource 无法设置初始请求头的限制，T015 对 T013 增补了可选 `after` 查询参数和 OpenAPI 描述；重连头优先。

`pnpm exec vitest run` 覆盖 77 项前端测试，包括 5 项组件测试和 2 项 HTTP 客户端测试；`pnpm build` 包含 Vue 类型检查并通过；ESLint 新文件无错误。后端隔离 PostgreSQL 的 SSE/契约测试覆盖查询游标与头优先。浏览器脚本 [animation_flow.py](../../web/tests/e2e/animation_flow.py) 在一次性 PostgreSQL、真实 Vite/Uvicorn、受限 Docker 和 headless Chromium 中验证：首次进入不创建、点击只发 1 次创建 POST、36 秒 MP4 播放且 SRT track 加载、刷新无新增 Job、另一个 Job 取消后显式重试、断网期间渲染完成并在恢复后自动播放。测试不调用 Provider，也不提交生成媒体。MVP 0.3 其余课堂/导出/阶段集成任务仍按根 `task.json` 继续。
