# EduMind Agent

> 启智学伴 · 基于多智能体的个性化学习系统
> 独立产品 / 开源项目
> 以数据结构课程为首个垂直领域

`docs/PRD.md` v2.1 是产品范围、优先级和验收标准的唯一事实来源。实现与本文冲突时，以 PRD 和已通过的 ADR 为准。

## 产品主线

EduMind 将学生画像、知识图谱、学习单元、多角色互动课堂和学习评估连接成闭环：

```text
一句话目标 → 临时画像 → 首段讲解 → 代码/练习/按需动画
                  ↑                    ↓
                  └── 渐进画像与路径 ← 掌握度反馈
```

首发聚焦 Web 和数据结构课程，不以 iOS、PPTX、通用视频模型或全学科覆盖阻塞 MVP。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Naive UI + Pinia；P0 使用轻量路径视图 |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 (async)；复杂子图再引入 LangGraph |
| P0 数据 | PostgreSQL + 版本化 YAML 知识结构 + 本地媒体缓存 |
| P1 数据 | 按需引入 Neo4j、Chroma/pgvector、Redis + Celery |
| 模型 | Provider Gateway；P0 仅接一个服务端 OpenAI-compatible Provider |
| P1 Provider | Ollama、BYOK、Anthropic、Google Gemini、讯飞星火、TTS/ASR |
| 视频 | P0 预渲染/参数化 Manim 模板；P1 动画 DSL + 隔离 Worker + 可选 TTS |
| iOS | SwiftUI（P2，可选，不阻塞 Web MVP） |
| 部署 | Docker + docker-compose |
| 包管理 | pnpm（前端） |

依赖版本必须由锁文件固定；不要在实现文档中使用无法复现的 `latest` 作为实际版本。

## 目录结构

```text
EduMind-Agent/
├── docs/                    # PRD、架构、ADR、Provider、API、Prompt、路线图
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI 路由
│   │   ├── agents/          # LangGraph Agent 与子图
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/        # 业务逻辑与 Provider Gateway
│   │   ├── core/            # 配置、鉴权、中间件、密钥保护
│   │   └── workers/         # P1 Celery + 完整 Manim Worker
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── web/                     # Vue 3 Web 客户端
├── ios/                     # P2 SwiftUI 客户端
├── data/
│   ├── knowledge_graph.yaml # P0 8-10 节点种子结构
│   └── videos/cache/        # 预渲染动画（不提交生成媒体）
└── docker-compose.yml
```

## 核心架构

- **ProfileAgent**：从一句话建立临时画像，通过答题和反馈渐进更新；未知字段不得臆测。
- **LearningUnitGenerator**：P0 一次结构化生成讲解、单语言代码和约 3 道练习；内部计划不要求学生确认。
- **ReviewAgent**：审核正式学习资源、Manim DSL 和辩论总结；普通对话只使用轻量规则并按风险升级。
- **PathAgent**：组合版本化知识结构与 PostgreSQL 掌握度，输出当前、前置、下一节点及推荐理由。
- **TutorAgent**：默认专注模式只有启智导师；基础/进阶同学按需出现并可由学生关闭。
- **Debate**：P0 只做“数组 vs 链表”结构化演示；P1 再升级三视角真并行子图。
- **VideoAgent**：按“预渲染缓存 → 参数化模板 → P1 完整 DSL”选择 Manim 路径。
- **Provider Gateway**：业务模块不依赖厂商 SDK；P0 内部任务档位可以映射同一系统模型。

## 开发阶段

| 阶段 | 重点 |
|---|---|
| MVP 0.1 | 一句话开始、单 Provider、临时画像、讲解/代码/练习、流式首屏 |
| MVP 0.2 | 8-10 节点知识结构、渐进画像、掌握度与下一步推荐、正式资源审核 |
| MVP 0.3 | 2-3 个 Manim 模板、专注/互动模式、一个多视角演示、Markdown 笔记 |
| Phase 1 | Ollama/BYOK、多 Provider、完整 Manim DSL、持久化队列、扩展图谱 |
| Phase 2 | 真并行辩论、更多角色策略、RAG、学习报告、更多课程 |
| Phase 3 | iOS、PPTX/离线 HTML、更多课程、模板市场；由真实使用数据决定 |

阶段由 `docs/PRD.md` 的退出标准驱动，不绑定固定比赛日期。

## 实现约束

### 模型与凭据

- 不得把任何单一模型设为业务层硬依赖；讯飞星火只是可选 Provider。
- P0 只实现一个由服务端配置的 OpenAI-compatible Provider；Ollama、BYOK 和模型设置属于 P1。
- P0 API Key 只来自服务端环境变量/密钥管理；不得进入数据库、日志、错误响应、Git 或前端状态。
- 自定义 Base URL 必须防 SSRF；云端部署阻止回环、链路本地、私网和云元数据地址。本地模型只能通过显式白名单放行。
- Provider 切换和自动回退必须遵守用户设置；禁止静默把敏感上下文发送给另一个厂商。

### API 与异步任务

- 普通查询和修改使用 REST；模型生成、课堂和辩论输出使用统一 SSE 事件协议。
- POST 流式响应使用 `fetch` + `ReadableStream`；持久化 Job 事件使用 GET `EventSource`。
- 讲解、代码和练习直接流式生成；只有未命中缓存的 Manim 等长任务进入异步 Job。
- P0 Job 状态写入 PostgreSQL，不得只保存在进程内存；Redis/Celery 属于 P1。

### 生成与安全

- 所有正式生成资源必须经过 schema 校验和 ReviewAgent；审核失败内容不得发布。
- P0 只运行已审核的预渲染/参数化 Manim 模板；P1 模型输出必须是受约束动画 DSL。
- 模板编译后的代码仍须经过 AST/静态规则、容器隔离、CPU/内存/时间限制和禁网处理。
- 禁止生成或执行 `os.system()`、`eval()`、`exec()`、任意文件访问、网络访问和未授权导入。
- 前端 Markdown、HTML 和模型输出必须清洗并默认转义，防止 XSS。

### 数据与工程

- 数据库迁移统一使用 Alembic；禁止手工修改生产 schema。
- P0 公共知识结构存版本化 YAML/PostgreSQL，用户掌握度和路径版本存 PostgreSQL；P1 可迁移 Neo4j。
- Prompt、模型能力映射、动画 DSL 和 Review 规则必须版本化。
- 新功能必须包含与风险相称的测试；核心路径至少覆盖单元测试、Provider 失败、SSE 重连和关键 E2E。
- 变更产品范围、API、安全边界或持久化模型时，同步更新 PRD、ADR/OpenAPI 和相关文档。

## 任务驱动开发协议

### 文件与任务边界

- `docs/PRD.md` 定义产品范围；根目录 `task.json` 是开发任务状态的唯一事实来源；`process.txt` 是只追加的执行日志。任务文件中的开发状态不是产品中的异步 Job 状态。
- 先细化当前阶段；后续阶段保留 PRD 目标，阶段验收后再拆任务。不得自行扩展产品范围或降低验收标准。
- 一个任务对应一个可独立验证、可审查的结果，包含 ID、依赖、范围、验收标准和验证步骤。复杂任务先拆分；实现、必要测试、迁移和相关文档应一起交付。
- `status` 只允许 `todo`、`in_progress`、`blocked`、`done`，不另维护容易失步的完成布尔值。验证步骤中的命令属于待建立的工程接口，任务完成前必须存在且实际执行。

### 领取、执行与恢复

1. 开始前读取本文件、PRD、`task.json`、最近的 `process.txt` 和 Git 状态，确认分支及已有改动。恢复时优先处理遗留 `in_progress`，不得直接领取新任务或覆盖用户改动。
2. 每次只领取一个依赖全部完成的 `todo`，同一工作区仅一个执行者。按当前阶段、优先级和文件顺序选择，记录 `in_progress`、开始时间与 START 日志。
3. 在 `codex/<task-or-stage>` 功能分支开发；禁止自动向 main/master 提交或合并。可复用明确属于当前任务流的功能分支。
4. 编码并执行验收检查、自查 diff。新行为有测试，缺陷有回归测试；按风险运行 lint、类型检查、构建和相关集成/E2E。纯文档改动检查内容、引用和格式即可。
5. 验证必须记录实际命令、结果和证据路径；未运行、跳过、环境不可用均不等于通过。不得削弱断言、删除失败测试或伪造数据来过关。真实 Provider 验证与 mock 测试分别记录。
6. 验证通过后，准备 `done` 状态、完成时间和 VERIFIED 日志，将代码、测试、必要文档、`task.json`、`process.txt` 一起提交。提交成功并检查提交内容后，才视为 DONE，才允许领取下一任务。
7. 若提交失败或中断，保留工作成果；工作区中的 `done` 不作为完成证据。恢复时检查 Git 历史：没有对应完成提交则恢复 `in_progress`（需要人工则 `blocked`），记录失败原因并重试或求助。

### 本地自动提交

- 用户已授权：每个通过验收的开发任务自动创建本地 commit，无需逐次询问。默认不 push、不 merge、不发布；这些操作需用户另行指示。权限审批仍遵循工具实际要求。
- 提交前检查 `git diff`、`git diff --check`、暂存区 diff 和状态，只使用明确文件路径暂存本任务改动，禁止 `git add .` / `git add -A`。已有无关暂存改动不得带入、撤销或覆盖；无法安全隔离时求助。
- 不提交密钥、真实 `.env`、缓存、生成媒体、日志中的敏感数据或无关改动。不使用 `--no-verify`、强制推送、破坏性 reset 或擅自 amend 历史提交。
- 提交标题为 `type(scope): description`，如 `feat(learning): stream reviewed learning resources`；正文增加 `Task-ID: MVP-0.1-007`。同一任务若确需多个提交，只有最终完成提交包含 `Task-Completed: <id>`。
- `task.json` 以 `commit_lookup` 保存上述完成标记，可通过 `git log --fixed-strings --grep='Task-Completed: <id>'` 查找。不要把当前提交的哈希写进它自身的文件；最终回复报告实际 hash 与验证结果。
- 治理文件维护可使用 `chore(workflow)` 提交，不伪造业务任务完成。任务失败时可以保留日志及未提交修改，但不能创建冒充成功的完成提交。

### 日志与人工求助

- `process.txt` 使用带时区的 ISO 8601 时间，按事件追加：时间、任务 ID、START/VERIFIED/BLOCKED/RESUME/COMMIT_FAILED、改动摘要、验证结果、遗留问题、下一步。历史错误通过新记录纠正，不覆盖历史。
- 同一问题两轮有实质区别的修复仍失败、缺少凭据/权限、需付费或破坏性操作、验收含糊、PRD/ADR 冲突、涉及尚未批准的重大 API/数据/安全决策时，及时标记 `blocked` 并向用户求助。普通实现细节按已有约定自主决定。
- 求助必须给出具体问题、证据、已尝试方案、影响、建议及需要用户决定的事项；未获答案不得自行推测决策或继续依赖该任务的工作。
- `blocked` 只有在阻塞原因确实解除后才能恢复为 `in_progress`，并追加 RESUME。用户提出范围修改时先同步任务与必要的 PRD/ADR。
- 连续开发只推进用户授权的阶段/批次；阶段结束进行集成验收并报告，不自动跨阶段。用户要求暂停、预算耗尽或遇到人工阻塞时保存状态并停止。
- 任务文件用于断点恢复，本身不负责后台调度或自动唤醒；被中断后继续执行仍需运行中的会话或另行配置的调度机制。

## 当前状态

项目处于 MVP 0.1，已完成 PRD v2.1 和参考项目分析，尚未开始主体编码。下一步是搭建 Vue/FastAPI/PostgreSQL 骨架，接通一个服务端 OpenAI-compatible Provider，并跑通“一句话 → 首段讲解 → 代码/练习”的最小链路。
