# MVP-0.3-T014 已审核动画媒体读取验收与交接

`GET /api/animation-media/{mediaId}/mp4|srt` 从 Cookie 取得 owner，先关联已成功 Job、相同 owner/单元/场景版本的正式资源绑定、ready 学习单元、已审核场景和 passed 媒体；单有共享 `animation_media` 行或猜中 ID 均不授权。路径只由服务端固定缓存根目录、数据库摘要与 `.mp4/.srt` 扩展名构造，HTTP 仅接受 UUID；打开时拒绝符号链接，核对普通文件、大小与 SHA-256，并用同一文件描述符传输。授权存在但文件缺失或损坏返回 503 `MEDIA_UNAVAILABLE`，其他 owner/无绑定/未知对象统一 404，错误不泄露内部路径。

MP4 支持完整读取、单段闭区间、开放末尾和后缀 Range；越界/多段/无效范围返回 416 和 `Content-Range: bytes */size`。部分响应为 206，带准确 Content-Range/Length 与 `Accept-Ranges: bytes`。SRT 为固定 `application/x-subrip`，两类响应均设置 `nosniff`、`private, no-store`、安全文件名；默认 inline，`download=true` 为 attachment。媒体失败不改变文字学习单元读取。

隔离 PostgreSQL 上 `EDUMIND_TEST_DATABASE_URL=<isolated-url> uv run --frozen pytest -q tests/test_animation_media_api.py tests/test_mvp03_openapi_contract.py` 为 9 通过，覆盖完整/范围/越界读取、owner 隔离、无绑定媒体、路径参数无效、符号链接、损坏/缺失字节和文字回退。真实 Docker Job 产出的 36 秒 Manim MP4 经本地 Uvicorn API 由 headless Chromium 加载播放，浏览器观察 `readyState=4`、`currentTime=1.216558`、`duration=36`、`error=null`，同源 SRT 读取 200；服务由 webapp-testing 的 `with_server.py` 管理，测试脚本位于临时目录而非产品仓库。未调用 Provider，未提交生成媒体。下一任务 T015 将这些端点接入按需播放器。
