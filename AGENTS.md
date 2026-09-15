# EduMind Agent

> 启智学伴 · 基于多智能体的个性化学习系统
> 第十五届中国软件杯 A3 赛题（科大讯飞出题）
> 以数据结构课程为切入点

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Naive UI + Pinia + AntV G6 + GSAP |
| 后端 | Python 3.11 + FastAPI + LangGraph + SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL (业务) + Neo4j (知识图谱) + Chroma (向量) + Redis (缓存/队列) |
| 任务队列 | Celery + Redis |
| 视频 | Manim Community v0.18+ + 讯飞 TTS + FFmpeg |
| 大模型 | 讯飞星火 v4.0/Pro (sparkai SDK) |
| iOS | SwiftUI (原型级，仅浏览，不做生成) |
| 部署 | Docker + docker-compose |
| 包管理 | pnpm (前端) |

## 目录结构

```
EduMind-Agent/
├── docs/                    # PRD, ADR, API 契约, Agent prompt, Sprint 任务
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI 路由
│   │   ├── agents/          # LangGraph Agent 定义
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/        # 业务逻辑
│   │   ├── core/            # 配置/JWT/中间件
│   │   └── workers/         # Celery + Manim Worker
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── web/                     # Vue 3 前端
├── ios/                     # SwiftUI (C 方案)
├── data/
│   ├── knowledge_graph.yaml # 30 节点种子数据
│   └── videos/cache/        # 预渲染动画
└── docker-compose.yml
```

## 核心架构

8 个主 Agent + LangGraph 编排：

- **ProfileAgent** — 对话式 6 维画像构建
- **DocAgent / MindmapAgent / QuizAgent / VideoAgent / CodeAgent** — 5 类资源生成
- **ReviewAgent** — 独立反思层，防幻觉二审
- **PathAgent** — 知识图谱 + 路径规划
- **Performance / Engineering / Academic / Moderator** — 辩论子图 4 角色
- **TutorAgent** (加分) / **AssessAgent** (加分)

每个生成 Agent 输出必经 ReviewAgent：通过→返回前端 / 需修正→退回重生成(最多2次) / 严重幻觉→拒绝+兜底。

## 开发阶段 (12 周 Sprint)

| Sprint | 主题 |
|---|---|
| S0 (W1) | 环境搭建 + 30 节点知识图谱 v0 |
| S1 (W2-3) | 后端骨架 + JWT + 对话画像 SSE |
| S2 (W4-5) | Neo4j 图谱 + 路径规划 + G6 可视化 |
| S3 (W6) | 4 类资源 Agent + ReviewAgent |
| S4 (W7) | Manim 视频流水线 (VideoAgent + Worker + TTS) |
| S5 (W8-9) | 辩论圆桌 (4 Agent 并发 + GSAP 动画) |
| S6 (W10) | iOS 原型 + Web UI 打磨 |
| S7 (W11) | 辅导/评估加分项 + 性能优化 |
| S8 (W12) | 文档/PPT/演示视频交付 |

## 当前状态

项目处于 S0 启动周。尚未开始编码。

## 约束

- 大模型必须用讯飞星火（赛题硬性要求）
- 所有 API 走 SSE 流式输出
- 代码生成需沙箱安全审查（禁用 `os.system()` / `eval()`）
- 数据库迁移用 Alembic
- 前端 Markdown 渲染必须转义防 XSS
