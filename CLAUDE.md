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
| Phase 2+ | 真并行辩论、RAG、更多课程、iOS 和教师创作模式 |

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

## 当前状态

MVP 0.1 已通过真实 DeepSeek Provider、浏览器主链路和首段性能退出验收。项目进入 MVP 0.2，当前重点是 10 节点知识结构、渐进画像、服务端测验评分、掌握度更新与可解释下一步推荐；活动任务以根目录 `task.json` 为准，已结束阶段快照保存在 `docs/tasks/`。
