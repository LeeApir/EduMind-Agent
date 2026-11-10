# T121 队列课程统一结果

2026-11-10 完成零调用准备。真实首稿、独立教学审核和队列课程浏览器验收待准确授权。

| 操作完成后 | 有效元素（队头到队尾） | 队头 | 队尾 | 本步出队 |
| --- | --- | --- | --- | --- |
| 初始化 | `[]` | 无 | 无 | 无 |
| `enqueue(3)` | `[3]` | 3 | 3 | 无 |
| `enqueue(8)` | `[3,8]` | 3 | 8 | 无 |
| `dequeue()` | `[8]` | 8 | 8 | 3 |
| `enqueue(5)` | `[8,5]` | 8 | 5 | 无 |

共用 CLI 的队列主题提供检查、准备、发送、严格重放、准入及停止。固定提纲流程从原栈代码提取，沿用 T120 的传输、封存和已有私有仓储。队列适配只提供专属目标、提纲、程序材料、教学检查和播放投影。原栈首稿请求与历史文件逐字节相等。真实队列批次使用新的专用库和私有封存目录，MockTransport 夹具限于独立测试库。

| 复核 | 实际结果 |
| --- | --- |
| `pytest -q backend/tests/test_queue_course_trial.py backend/tests/test_course_trial_transport.py backend/tests/test_head_course_deepseek_wire.py` | 23 项通过。Clang C11 断言独立核对五帧、FIFO、前移、判空判满及迁移数据。隔离 PostgreSQL 验证错批次、错审核、异常响应保全、重复发送拒绝，以及私有 v2、四题反馈、答案隔离和版本回读 |
| `pnpm typecheck` 与 `pnpm exec vitest run tests/course-visualization.spec.ts tests/head-course-status.spec.ts` | 13 项通过，覆盖五帧队头、队尾、出队结果和逐行高亮。定向 ESLint 无错误，保留 4 条原模板换行警告 |
| `scripts.check_course_trial_replay` 在当前代码的临时本机应用执行 | T118、T119 原冻结读取器均通过。实际 Chromium 同一访客验收 13 帧和 5 帧、播放、四题反馈及刷新。7 个隔离库反例被拒绝，43 个原封存文件摘要一致。[回归明细](replay-regression.json) |
| 本机队列开发入口及批准门禁 | API 健康、Web 200，普通生成 POST 409。没有本批封存目录时执行共用 `send --topic queue`，在提示密钥前即拒绝。没有创建真实生成操作 |
| 静态检查与冻结 | Ruff、工作流、Git 差异检查和 `scripts.course_trial inspect --topic queue` 通过。历史冻结目录的 Git 差异为空 |

Provider 调用 **0**。下一步需批准准确执行包、30 分钟窗口、单次 DeepSeek 首稿及 C2 例外。真实首稿通过独立审核后，才进入实际私有课程和浏览器验收。[准确执行包](README.md)
