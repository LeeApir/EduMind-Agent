# MVP-0.3-T022 学习控制与场景版本界面验收

## 交付

- 学习页按场景版本呈现已审核资源，不再把新旧讲解、代码和练习混合；历史版本可只读查看，选择保存在当前浏览器会话。旧练习仍使用原资源 ID 读取原提交回执。
- 学习控制接通持久化课堂 `controls` API：暂停、继续、跳过和讲解/代码/练习切换使用 revision、CSRF、幂等键。连接结果不明时保留原请求供恢复；跳过后读取服务端场景状态，不在客户端臆造掌握度。
- 当前正式场景支持“更简单”“更深入”“换个例子”。流式候选明确标为临时内容，审核通过且收到 `scene_ready` 后才读取新正式版本；拒绝时撤回候选并保留原资源。页面刷新、历史版本选择和课堂控制切换不会被迟到内容覆盖。
- [ClassroomPanel.vue](../../web/src/components/ClassroomPanel.vue) 在外部控制刷新课堂时结束旧发言的临时显示，并丢弃旧 generation 的迟到 token。

## 验证

- `cd web && pnpm exec vitest run`：17 文件、105 项通过。覆盖控制请求重试/跳过、重解释发布和撤回、历史版本、刷新与迟到选择、课堂旧 token 丢弃。
- `cd web && pnpm build`：TypeScript 检查与 Vite 构建通过。
- 对本任务改动文件执行 `pnpm exec eslint ...`：0 错误、0 警告；`git diff --check` 通过。全仓 `pnpm lint` 0 错误，尚有其他既有组件的 67 条样式警告。
- `cd web && UV_CACHE_DIR=/private/tmp/edumind-uv-cache pnpm e2e`：路由 mock 的 Chromium 流程通过，覆盖资源切换、重解释成功、旧版选择与刷新恢复、审核失败保留正式版；截图 `/tmp/edumind-mvp03-t022-controls.png`。浏览器 mock 与后端已有 T021/T035 的真实数据库测试分层验证；本任务未调用真实 Provider。

## 后续

按根 `task.json` 领取下一个依赖已完成的 MVP 0.3 任务；T022 的前端使用已批准的 ADR-0005、OpenAPI 和 T021/T035 接口。
