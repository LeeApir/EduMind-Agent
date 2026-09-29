# MVP-0.3-T025 多视角展示与课堂返回验收

## 交付

- 学习页新增主动触发的“数组 vs 链表”演示。前端以课堂 revision、CSRF 和幂等键调用 POST SSE；生成及审核期间只显示状态，不渲染候选内容。正式结果仅从 owner 结果 GET 读取，按性能、工程、学术三视角与主持人的客观结论、取舍和学习建议呈现。
- 进入演示时隐藏原学习资源、动画、控制和课堂面板，组件保持挂载；退出后恢复原界面，未提交练习草稿不因切换丢失。返回点、进度、角色、消息游标由服务端事务恢复；若原场景已有新版，向用户提示。
- 会话存储保留待确认操作和退出幂等键；断线后先查持久操作，刷新时凭课堂 `detour.result_id` 读取已发布结果。审核拒绝和 Provider 故障展示明确错误，原课堂保持可用。所有模型文本通过 Vue 插值转义，不插入 HTML。

## 验证

- `cd web && pnpm exec vitest run`：113 项通过；新增 API/组件测试覆盖请求头、SSE 审核门禁、三视角展示、退出、刷新恢复、拒绝、Provider 故障与 XSS。`pnpm build` 通过；改动文件 ESLint 无错误或警告。
- `UV_CACHE_DIR=/private/tmp/edumind-uv-cache pnpm e2e`：Chromium 路由模拟覆盖进入/退出、刷新、失败、XSS 及退出后保留练习草稿，既有学习流程同时通过。
- `web/tests/e2e/real_debate_flow.py` 在隔离 PostgreSQL `edumind_t024_20260929`、实际 Vite 代理与 FastAPI HTTP、mock Provider 上通过浏览器进入、审核发布、刷新读取和退出。无真实 Provider 调用。E2E Python 文件 Ruff 和 `git diff --check` 通过。

## 后续

T026 负责显式视角偏好提交及画像后续表达；本任务只展示正式结果，不根据浏览或停留时间推断偏好。
