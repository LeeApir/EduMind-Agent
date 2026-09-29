# MVP-0.3-T028 已审核媒体下载验收

## 交付

- 复用已实现的 Cookie 保护媒体接口：`GET /api/animation-media/{mediaId}/mp4?download=true` 与同 ID 的 `/srt?download=true`。授权必须有当前 owner 的成功 Job、正式资源绑定和已审核场景；共享缓存字节本身不授予权限。默认 inline 仍供播放，显式下载使用服务端 UUID 文件名。
- MP4/SRT 的响应头共同给出不可变媒体 ID、模板 ID/版本、字幕版本、审核规则版本、来源 `reviewed-manim-template` 和发布时间。各响应的 `X-Animation-Content-SHA256` 是该格式完整字节的内容版本；同一媒体 ID 把视频和对应字幕绑定为一组。P0 模板渲染没有生成模型，因此不虚构模型 ID。
- 下载只打开并校验已发布的内容地址文件，不调用 Provider 或渲染器。不存在或未授权返回 404；已绑定但文件缺失、损坏或变为符号链接时返回 `503 MEDIA_UNAVAILABLE`，提示重新请求动画以恢复，下载请求自身不重渲染。单个格式损坏不影响另一格式的已验证字节。

## 验证

- `backend/tests/test_animation_media_api.py` 在隔离 PostgreSQL 与私有临时缓存中运行，实际读取 MP4/SRT 字节并核对完整文件 SHA-256、同媒体 ID 与版本来源头、UTF-8 字幕、206 Range、显式下载文件名和非法文件名参数。下载期间将渲染器改为失败哨兵，确保零重渲染。
- 同组测试覆盖匿名/跨 owner/未绑定媒体、错误 UUID、越界 Range、符号链接、损坏与缺失文件；`test_mvp03_openapi_contract.py` 校验 200/206 来源头契约。后端全量测试和静态检查的最终结果记录在 `task.json` 与 `process.txt`。
- 隔离 PostgreSQL 上导出/OpenAPI 定向 9 通过，后端全量 `uv run pytest -q` 649 通过、5 跳过；`uv run ruff check app tests`、`uv run mypy app`（95 个源文件）、`git diff --check` 通过。无真实 Provider 调用。

## 后续

T029 接通前端下载入口与恢复提示；本任务只交付服务端下载行为。完成本地提交后停止，不自动领取 T029，也不 push/merge。
