# MVP 0.2 T031：真实浏览器学习闭环

结论：通过。日期：2026-09-27。前置重试修复 fb273c7 已核对。
本次补充真实浏览器证据，不用旧 TestClient/route-mock 报告代替。

## 环境和模型

Chromium 153.0.8010.12、macOS 15.6.1 arm64、Python 3.11.16；
真实 Chromium → Vite 4181 同源代理 → Uvicorn 8011 → PostgreSQL
edumind_browser_t031（全新数据库，从空库迁移到 0009 head）→ 当前 Provider。
本机单并发，Provider 经当前主机网络访问；不推断公网部署或容量。
无 route mock、TestClient、合成发布资源或答案键读取。

当前模型配置/结构化返回均 deepseek-v4-pro-0813；
文本 SSE 和结构化均沿用 Responses，结构化模式 responses_json_schema。
资源指令 learning-resources-instructions-v8；审核 resource-review-instructions-v2；
画像 profile-instructions-v2 / profile-behavior-instructions-v2。
首段业务提示未改，本任务不做首段 P95 判定。

计费依据：用户此前授权此 key 必要验证直到用量耗尽，无需逐次确认。
本次另设全局 30 实际适配器尝试硬上限，单 Worker，包含重试及审核修正。
总计 30 次（3 次 stream、27 次 structured），全部完成；最终通过轮 10 次。
失败验收轮也计入预算，不重置账本、换模型或扩大预算。费用及剩余额度未知。
真实 .env 只由后端进程加载，没有修改或导出；API key/URL、Cookie/CSRF 值未保存。

## 通过项

- 初次 /auth/session 401 → /auth/guest 201；HttpOnly/Secure 匿名 Cookie 正常。
  学习 POST 存在 CSRF/幂等头，同源代理未放宽 Origin。
- 输入单链表学习目标，按前置知识从 C 指针开始；临时首段和 reviewing 状态真实显示。
- 讲解、代码、练习经实际模型生成、独立审核后发布，三标签可使用。
- 只从 DOM 读取公开题面独立作答 B/T/B：
  指针保存对象地址；*p 可访问并修改对象；*p=12 使 x=12。
  两次使用“再做一次”作答均 3/3，掌握度 0→55%→95%。
- 前端每次练习自动重规划，路径 v1→v2→v3；当前链表概念、下一步单链表。
- 刷新后恢复同一资源、最近测验回执、95% 状态及路径 v3。
  页面真实 GET 的路径快照刷新前后完整相同。
- 在真实响应包含 scene_ready 时，仅丢弃客户端响应；服务端已实际发布。
  Playwright context.set_offline 使恢复 GET 真正断网，上线后点击恢复原请求。
  学习 POST 只有一次，恢复前后全局 Provider 计数 28→28；恢复同一已发布单元。
  没有伪造任何 HTTP 成功响应、审核或资源。

最终完整资源发布约 30664ms；这是单轮总生成时长，不是首 token、首段或 P95。
两次同题满分验证状态闭环，不证明一般学习效果。

## 控制台和失败分类

最终负向 HTTP：初次 session 401、空画像 404、尚无测验回执 404，均为预期。
丢弃发布响应对应 learning-sessions ERR_ABORTED；
离线恢复 GET 对应 ERR_INTERNET_DISCONNECTED，均为本次可控注入。
console 4 个 debug、4 个 error，仅保存类别不保存含 URL 的原文；
这些记录与预期负向请求并存，不宣称 console 零错误。
pageerror 0、意外 HTTP 失败 0。

## 历史失败及修复

- v1/v2：页面整体 networkidle 等待超时，各 0 模型调用；保留报告。
  移除同步远程 Google Fonts 导入，保留本地字体名/回退及样式回归。
  字体不是已证实的唯一超时根因：移除后 v2 仍未空闲；真实 DOM 能渲染。
  最终先探测 networkidle（仍 false），再验证实际 DOM、状态和接口，不把 dev 网络空闲当业务通过。
- v3：真实资源和两次评分完成，但脚本误期望路径 v2；只读 PG 证实实际 v3。
  10 次模型调用，报告仍 failed，不覆盖。
- v4：刷新资源/回执/v3 均通过，但整个路径文本不等。
  原断言包含瞬时 changedIds 和 selectedId，它们不属于持久化契约；
  未留刷新后的全文，不能倒推具体字符差异。10 次调用，仍保留 failed。
- v5：修正为各次 v2/v3、刷新后真实路径快照全字段相同及 UI 持久状态检查，通过。
  不改评分、审核、路径规则或接受标准，不选择生成质量成功样本来覆盖失败。

## 证据和复现

最终：mvp-0.2-real-browser-v5.json。
历史：mvp-0.2-real-browser-v1.json 至 v4.json。
全局账本：mvp-0.2-browser-provider-ledger-v2.json；准备期零调用 v1 也保留。
报告包含公开题面、回执 UI、路径快照、脱敏 HTTP 状态和模型用量，不含答案键。

先建立独立 PostgreSQL 数据库 edumind_browser_t031，并将测试 URL 放入本机
EDUMIND_DATABASE_URL 环境变量（不要输出 URL/凭据）。从 backend：

```text
uv run --frozen alembic upgrade head
uv run --frozen --env-file ../.env python ../docs/acceptance/serve_real_browser.py --confirm-billable --limit 30 --port 8011 --ledger ../docs/acceptance/<fresh-ledger>.json
```

另一个终端，从项目根：

```text
EDUMIND_API_PROXY_TARGET=http://127.0.0.1:8011 pnpm --dir web dev --host 127.0.0.1 --port 4181 --strictPort
```

从 backend（输出路径必须全新，禁止覆盖；题面打印后独立输入 JSON 答案数组）：

```text
uv run --frozen python ../docs/acceptance/run_real_browser.py --confirm-billable --output ../docs/acceptance/<fresh-browser-report>.json --ledger ../docs/acceptance/<fresh-ledger>.json
```

最终停止本次 Uvicorn/Vite；保留隔离库，未动现有 Compose 服务。
webapp-testing 技能用于真实浏览器生命周期、网络空闲探测和交互检查。

## 非计费检查

- 后端隔离库全量 pytest：397 通过，无跳过，7 条既有弃用警告。
- 预算离线回归：拒绝越界、拒绝覆盖、脱敏账本通过。
- Ruff（app/tests/两个验收脚本）和 Mypy（55 源文件）通过。
- 前端 66 项/11 文件通过；类型检查、构建通过；lint 0 错误/67 既有样式警告。
- git diff --check 通过。

任务 B 未完成；本报告不自动授权阶段切换、push、merge 或归档。
