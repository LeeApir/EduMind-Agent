# MVP 0.2 T030：学习请求身份恢复

## 根因与批准边界

入口的 retryLearning 调用 resetAttempt，丢弃原 operation ID 并换幂等键。
网络失败并不意味着服务端停止；新键绕开原操作的幂等记录，可再次调用 Provider。
入口的异步 SSE 回调、错误恢复和完成状态也没有统一绑定请求代次，旧响应能修改新目标页面。

后端 GET 曾无条件将 active 状态写为 failed/INTERRUPTED；既有测试只种入 reviewing 记录，并不能证明重启。
2026-09-27 用户批准 GET 只读、同键失败仅回放、明确新生成才换键；不新增中断检测。
审核发布、Provider 网关、owner 过滤和数据库 schema 均未改变。

## 行为变化

- “重试恢复原请求”保留提交时的目标、操作 ID 和幂等键，输入框未提交的草稿不会改变原请求。
- 有操作 ID 只查询；published 读取原单元，运行中提示等待，failed/canceled 展示终态。
- 状态或资源读取暂时失败可再次恢复，不创建新操作。
- 未取得操作 ID 时，以原目标和原幂等键 POST。服务端只回放原记录，不重复调用 Provider。
- “重新生成（新请求）”及新的目标提交创建新身份。
- 请求代次检查覆盖会话建立之后、SSE 回调、操作查询、资源读取、成功和异常路径。
  新目标可在旧请求未完成时提交；旧请求可能继续运行，但不能污染新页面。
- 未扩展“重新解释场景”的版本 API；此处重新生成仍是既有整次学习请求。

## 回归入口

web/tests/learningRecovery.spec.ts：10 项入口回归，覆盖六类要求及未知操作 ID、
失败 done 重放、迟到流成功/异常、迟到查询和资源读取。
backend/tests/test_learning_sessions.py：8 种状态的 GET/同键 POST 保持状态及零 Provider 调用；
失败真实路由（FakeAdapter）同键重放、新键新操作；既有 published 重放回归。
外部 owner 查询保持 404，原记录及 attempt 不变。
web/tests/e2e/learning_flow.py：浏览器验证失败恢复无第二次 POST，
明确重新生成换键，丢失流响应后恢复原已发布资源仅一次 POST。

## 实际验证

所有命令从项目根或以下注明目录执行。无真实 .env 加载、无真实模型请求。
隔离数据库使用既有 edumind-mvp02-quiz-20260925（127.0.0.1:32769），仅合成测试数据。

- backend：EDUMIND_TEST_DATABASE_URL=<隔离 PostgreSQL URL> uv run --frozen pytest -q。
- backend：uv run --frozen ruff check app tests；uv run --frozen mypy app。
- pnpm --dir web test --run；pnpm --dir web typecheck；pnpm --dir web lint；pnpm --dir web build。
- backend：uv run --frozen python ../web/tests/e2e/run.py。
- git diff --check；提交前检查明确暂存路径与 diff。

结果：后端 396 项通过，无跳过，7 条既有弃用警告；Ruff 通过、Mypy 55 源文件通过。
前端 65 项/10 文件通过；类型检查和 Vite 构建通过；ESLint 0 错误/67 条既有样式警告。
浏览器 route-mock E2E 通过，diff 检查通过。详细结果同时记录在根 task.json 和 process.txt。
webapp-testing 技能指导了浏览器生命周期、network-idle 探测及交互验证；
浏览器全部 API route-mock，不能替代真实 Provider 浏览器验收。

## 剩余限制

- 不识别进程中断：未写终态的操作可能持续显示运行中，需用户明确选择新生成。
- 请求身份保存在当前页面内存，未新增跨刷新未完成操作恢复；既有已发布单元恢复保留。
- 不取消旧目标的服务端调用，不提供费用追回或账单级 exactly-once 承诺。
- 浏览器 mock 场景仍含既有 401/404 console 消息；前端 lint 仍有既有样式警告。
- 不归档当前阶段、不进入 MVP 0.3、不 push/merge。
