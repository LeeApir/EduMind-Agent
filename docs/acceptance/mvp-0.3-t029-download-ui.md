# MVP-0.3-T029 学习页下载入口验收

## 交付

- 学习页提供只读 Markdown 笔记下载，明确内容来自本单元当前已审核版本。查看历史场景时禁用该入口，避免把当前版笔记误称为历史版。
- 动画面板仅在成功 Job 携带已审核媒体 ID 时显示 MP4/SRT 下载。视频和字幕都使用同一媒体 ID，服务端 `Content-Disposition` 的安全文件名用于保存。排队、审核中和生成失败时不显示下载操作。
- 下载失败可直接重试同一 GET，不重新生成学习单元或动画；服务端确认已绑定媒体缺失时提示并提供显式的“重新请求动画”。场景切换后迟到的响应不保存文件；同一节点、同一版本的不同场景使用各自的 Job 恢复键。
- 下载按钮可通过键盘操作；窄屏下操作区域自动换行。

## 验证

- `pnpm exec vitest run`：121 passed。覆盖安全文件名、下载失败重试、缺失媒体显式恢复、同版本跨场景隔离。
- `pnpm build`（含 Vue 类型检查）、改动文件 ESLint、E2E Python Ruff、`git diff --check` 通过。
- `UV_CACHE_DIR=/private/tmp/edumind-uv-cache pnpm e2e`：Chromium 路由模拟测试通过。375px 视口使用键盘 Enter 下载三种文件，逐一比较浏览器保存的字节与响应体、文件名；切换历史场景后验证笔记禁用、动画下载隐藏，期间无学习/动画 POST。
- `web/tests/e2e/real_export_flow.py`：在独立 PostgreSQL 迁移到 Alembic head 后，运行真实 FastAPI、Vite 和 Chromium。测试只种入 owner 已审核讲解及绑定媒体，不调用模型或渲染器；浏览器实际下载 Markdown、MP4、SRT，核对服务端文件名、讲解版本及 MP4/SRT 原始字节，期间无学习/动画 POST。两次独立运行通过，确认脚本可重复执行。此验证使用测试媒体字节；真实 Manim 渲染与完整旅程由 T030 验收。

## 交接

T030 应覆盖专注、互动、多视角、返回、真实模板动画与导出的完整旅程，并确认普通学习不依赖可选动画或演示。T029 无已知阻塞；本任务不 push、不 merge。
