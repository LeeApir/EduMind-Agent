# MVP-0.3-T027 已审核 Markdown 笔记验收

## 交付

- 按已批准的 MVP 0.3 OpenAPI 提供只读 `GET /api/learning-units/{id}/notes.md`。会话与 owner 限制沿用现有认证；该请求不写数据，CSRF 头只适用于写请求。PRD §7.3 的早期 POST 路径已同步为 GET。
- 每个场景取当前已发布场景版本中的最新已审核讲解资源，完整写入“讲解”，并逐字摘取首段作为“知识点总结”。仅在实际有本人错题时，从本人测验回执及其准确匹配的已审核练习资源版本提取题干；同题最新回执已答对时不再列为错题。可附上最新已发布多视角结果的主持人总结。导出不调用 Provider 或渲染器。
- 文件内记录导出时间以及讲解、错题练习和可选多视角结果的模型、发布时间、场景与资源版本。原始作答、答案键、证据 ID、临时 token、未发布及审核拒绝内容均不进入正文。原始 HTML 转义，Markdown 链接失活；文件名只由学习单元 UUID 构成；响应为 UTF-8 Markdown、`attachment`、`nosniff` 和私有禁缓存。

## 验证

- `backend/tests/test_markdown_notes_api.py` 使用隔离 PostgreSQL 和 FastAPI 测试客户端，覆盖新旧已审核版本选择、未审核过滤、owner 隔离、练习版本与错题归属、答对后移除、可选已审核多视角总结、无额外 Provider 调用、下载字节与安全文件名、无资源 404，以及只读 GET 行为。
- 隔离 PostgreSQL 上后端全量 `uv run pytest -q`：649 通过、5 跳过；错题跨资源版本边界调整后，导出与 OpenAPI 专项 11 通过。`uv run ruff check app tests`、`uv run mypy app`（95 个源文件）和 `git diff --check` 通过。无真实 Provider 调用。

## 后续

T028 负责已生成 MP4/SRT 下载；本任务不触发媒体生成。按用户此次只要求 T027 的范围，完成本地提交后停止，不领取 T028。
