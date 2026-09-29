# MVP-0.3-T020 专注与按需角色课堂界面验收与交接

在 T019 分级审核流式发言与 T017 课堂模式/幂等底座上，为学习页接入真实课堂 UI：默认**专注模式**只显示启智导师，切到**互动模式**才按需出现基础/进阶同学角色与当前发言者标记，可随时关闭互动；接通真实 `/api/learning-units/{unitId}/classroom*` 的 JSON/SSE、错误重试与课堂恢复，页面纯文本插值转义模型内容，与已审核讲解/代码/练习/路径/动画面板共存，支持键盘与移动端。

## 实现

- [classroom.ts](../../web/src/api/classroom.ts)：课堂 API 客户端。`loadClassroom`/`createClassroom`/`setClassroomMode`/`loadClassroomMessages`/`loadClassroomOperation` 复用既有 CSRF + `Idempotency-Key` + `If-Match-Classroom-Revision` 头约定；`streamClassroomSpeech` 复用 `parseSseStream` 逐事件派发 `agent_start/token/review_pass/message_ready/content_retracted/error/done`，捕获 `operationId` 并抛出带错误码的 `ClassroomSpeechError`（401/403/404/409/422/503 映射、连接失败/中断/空流）。
- [ClassroomPanel.vue](../../web/src/components/ClassroomPanel.vue)：课堂主界面。`ensureClassroom`（GET 快照、NOT_FOUND 时以持久化幂等键创建）、`loadTranscript`（`?after=` 分页）、`recoverPending`（按 `operationId` 恢复 published/failed/superseded）、`runSpeech`（generation 计数丢弃迟到事件）、`applyEvent`（token 累积 + content_retracted 收回 + done 提交）、`retrySpeech`（终止错误换新键、连接中断复用同键）、`applyMode`/`toggleMode`/`toggleRole`（CAS revision + generation 升级）。模型内容仅经 `{{ }}` 插值渲染（无 `v-html`），`sessionStorage` 幂等键与 pending 恢复，Enter 发送 / Shift+Enter 换行，`@media (max-width: 600px)` 响应式。
- [App.vue](../../web/src/App.vue)：`<ClassroomPanel>` 与 `PublishedLearningWorkspace`/`LearningPathPanel`/`AnimationPanel`/`ProfileCard` 共存，保留讲解/代码/练习/路径进度；`csrfToken` 复用 `ensureSession`。

## 验证

- [ClassroomPanel.spec.ts](../../web/tests/ClassroomPanel.spec.ts)（12）：NOT_FOUND 创建默认专注课堂、专注不渲染角色控件、互动切模式 + 按需角色开关、流式当前发言者 + done 提交、content_retracted 收回、终止错误换新幂等键、连接中断复用同键、切模式后迟到 token 丢弃、流式与已提交内容 XSS 转义、Enter/Shift+Enter、pending 恢复 published 并清键、单角色关闭仍互动。
- [classroom.spec.ts](../../web/tests/classroom.spec.ts)（7）：SSE 头/体/事件类型、错误事件映射、HTTP 错误码映射、快照/创建/切模式头、消息分页与操作读取、连接失败。
- [classroom_flow.py](../../web/tests/e2e/classroom_flow.py)：headless Chromium 路由 mock 联调——默认专注 → 互动角色开关（`aria-pressed`）→ 键盘提交流式回合 → 按钮提交 → 提交内容 XSS 转义（无 `img`/`script` 元素）→ Provider 故障换新幂等键重试 → 关闭互动 → 移动端无横向溢出。
- 前端 96 项测试通过（16 文件）；ESLint 0 错误；`vue-tsc -b && vite build` 通过。后端课堂测试 **58 项通过**（真实 app + PostgreSQL + FakeAdapter mock Provider：SSE 契约/模式 CAS/持久化/上下文/角色/审核规则），0 Provider 实调。

## 说明

- 浏览器联调沿用 [learning_flow.py](../../web/tests/e2e/learning_flow.py) 的**路由 mock**既有约定，确定性复现课堂 SSE 线格式；「真实后端 mock Provider」由 58 项后端课堂测试（FakeAdapter）覆盖，二者分层印证同一契约。
- 教学正文首 token P95 ≤ 2 秒为非阻塞后续优化，不在本任务范围。

## 下一任务

T020 为 MVP 0.3 课堂链收口。后续按根 `task.json` 继续：持久化动画 Job 与 Markdown/MP4/SRT 导出、场景学习控制、数组 vs 链表多视角演示等剩余任务。
