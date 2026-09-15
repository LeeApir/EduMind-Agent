# 开源项目参考综合报告

> 分析对象: OpenMAIC & MAIC-UI
> 时间: 2026-06-17
> 目的: 为 EduMind Agent 设计提供参考和借鉴

---

## 一、两个项目一句话定位

| 项目 | 定位 |
|------|------|
| **OpenMAIC** | 输入主题 → 多 Agent 生成互动课堂（幻灯片 + 测验 + 模拟 + PBL），AI 角色实时授课 |
| **MAIC-UI** | 上传 PDF → 生成交互式学习网站（5 种模态），个性化适配 K-12 学生 |

---

## 二、技术栈横向对比

| 维度 | OpenMAIC | MAIC-UI | EduMind |
|------|----------|---------|---------|
| 前端框架 | Next.js 16 + React 19 | Next.js 14 + React 18 | **Vue 3 + Naive UI** |
| UI 库 | Tailwind CSS 4 | Tailwind CSS | Naive UI |
| 后端框架 | — (Next.js 单体) | FastAPI | **FastAPI** |
| Agent 编排 | LangGraph 1.1 | — | **LangGraph** |
| LLM | 多 Provider 可切换 | 智谱/Claude/OpenAI | **讯飞星火 (硬性要求)** |
| 数据库 | 无持久化 DB | SQLite/PG (SQLAlchemy) | PG + Neo4j + Chroma + Redis |
| 任务队列 | — | — | Celery + Redis |
| 视频 | 基础 | — | Manim + TTS + FFmpeg |
| 知识图谱 | — | — | Neo4j (核心差异化) |
| 部署 | Vercel / Docker | Docker Compose | Docker Compose |

**关键结论**: 
- 后端框架 EduMind 与 MAIC-UI 一致 (FastAPI)，MAIC-UI 的后端分层设计可直接参考
- Agent 编排 EduMind 与 OpenMAIC 一致 (LangGraph)，OpenMAIC 的图结构设计可以借鉴
- 前端框架三者各不相同，无法直接复用代码，但组件设计思路可参考

---

## 三、架构模式对比

### 3.1 Agent 编排对比

```
OpenMAIC (LangGraph):
  场景大纲 → 场景内容 → Agent画像 → 场景动作 → 组装
  [串行/并行混合]

EduMind (LangGraph):
  ProfileAgent → PathAgent → {DocAgent, MindmapAgent, QuizAgent, VideoAgent, CodeAgent} → ReviewAgent → 前端
  [画像 → 路径 → 并行生成 → 独立二审]
```

**EduMind 的优势**: 独立的 ReviewAgent 审核层是两个项目都没有的差异化设计。

### 3.2 生成 Pipeline 对比

| 特性 | OpenMAIC | MAIC-UI Heavy Mode | EduMind |
|------|----------|-------------------|---------|
| 阶段数 | 4-5 阶段 | 2 阶段 | 3 阶段 (生成→审核→输出) |
| 并行能力 | 场景级并行 | — | Agent 级并行 |
| 验证机制 | — | 每阶段 3 次精修 | ReviewAgent 二审 (最多 2 次) |
| 降级策略 | — | Fast Generator 兜底 | 拒绝 + 兜底内容 |
| 缓存 | — | 成功结果缓存 | Redis 缓存 + 预渲染视频 |

### 3.3 API 设计对比

```
OpenMAIC API 模式:
  POST /api/generate-classroom → 202 {jobId, pollUrl}
  GET  /api/generate-classroom/:jobId → {status, result}
  优点: 异步非阻塞, 适合长任务
  缺点: 轮询模式, 实时性差

MAIC-UI API 模式:
  POST /api/pdf/upload → 200 {document_id}  (同步处理)
  POST /api/content/personalize → 200 {personalized_content}
  优点: 简单直接
  缺点: 同步阻塞, 大文件处理时体验差

EduMind 推荐:
  结合两者优点:
  - 资源生成用 SSE 流式 (实时反馈)
  - 视频渲染等长任务用 Job + 轮询
  - 画像采集用 WebSocket 双向对话
```

---

## 四、可借鉴的具体内容

### 4.1 从 OpenMAIC 借鉴

| 内容 | 优先级 | 具体做法 |
|------|--------|---------|
| LangGraph 图编排 | 🔴 高 | 研究 OpenMAIC 的 StateGraph 定义，移植到 EduMind 的 8 Agent 编排 |
| 异步 Job 模式 | 🔴 高 | 借鉴 `classroom-job-runner` 的设计，用于 Manim 视频渲染等长任务 |
| Agent 画像设计 | 🟡 中 | 参考 Agent Profile 的数据结构 (name/role/personality/avatar/speakingStyle) |
| 场景动作生成 | 🟡 中 | Agent 动作概念可用于 EduMind 的 AI 教师行为设计 |
| SOP 分阶段 Prompt | 🟡 中 | 用于 ProfileAgent 的对话画像采集流程 |
| DSL 设计 | 🟢 低 | `@maic/dsl` 的领域语言设计思路，可用于 EduMind 的资源标准化 |
| PPTX 导出 | 🟢 低 | `@maic/importer` + `pptxgenjs` 的模式可用于 DocAgent 的导出功能 |

### 4.2 从 MAIC-UI 借鉴

| 内容 | 优先级 | 具体做法 |
|------|--------|---------|
| FastAPI 后端分层 | 🔴 高 | `api/ → services/ → models/` 三层架构直接参考 |
| Prompt 集中管理 | 🔴 高 | `prompts/ai_prompts.py` 的组织方式，按 Agent 拆分 |
| 生成器模式 | 🔴 高 | Fast (轻量) + Heavy (精度) 双模式，对应 EduMind 的快速预览/正式生成 |
| 验证闭环 | 🔴 高 | Heavy Generator 的 `生成→验证→精修→重验证` 对应 ReviewAgent 的二审机制 |
| 用户画像注入 | 🟡 中 | 将 ProfileAgent 的 6 维画像注入每个生成 Prompt |
| 多模态设计 | 🟡 中 | 5 种学习模态的分类法，用于扩展 EduMind 的资源类型 |
| 数据库 Schema | 🟢 低 | Users/Documents/ContentSections/LearningProgress 的 ER 关系 |
| HTML 交互组件 | 🟢 低 | `interactive_components.py` 的组件体系，可用于未来交互式资源 |

---

## 五、EduMind 的差异化优势

两个项目都缺少的能力，正是 EduMind 的核心竞争力：

| 能力 | OpenMAIC | MAIC-UI | EduMind |
|------|----------|---------|---------|
| 知识图谱 | ❌ | ❌ | ✅ Neo4j + 30 节点种子数据 |
| 学习路径规划 | ❌ | ❌ | ✅ PathAgent |
| 独立审核层 | ❌ | ❌ | ✅ ReviewAgent 防幻觉 |
| 视频生成 | 基础 | ❌ | ✅ Manim + TTS 流水线 |
| 代码沙箱 | ❌ | ❌ | ✅ CodeAgent + 安全审查 |
| 辩论机制 | Agent 讨论 | ❌ | ✅ 4 角色辩论子图 |
| 课堂实证 | — | ✅ 53 学生 | 🎯 目标: 竞赛展示 |

---

## 六、给 EduMind 的实操建议

### Sprint 0 (当前) — 立即可做

1. **克隆体验两个项目**
   ```bash
   git clone https://github.com/THU-MAIC/OpenMAIC.git ~/Code/ref-openmaic
   git clone https://github.com/THU-MAIC/MAIC-UI.git ~/Code/ref-maic-ui
   ```

2. **提取 MAIC-UI 的 FastAPI 结构作为后端骨架起点**
   - 复制 `api/ → services/ → models/` 三层架构模式
   - 参考 `core/database.py` 的 DB 初始化模式

3. **研究 OpenMAIC 的 LangGraph 编排代码**
   - 重点关注 `lib/server/classroom-generation/` 目录（需要本地 clone 后查看）
   - 理解 StateGraph 的节点和边定义

### Sprint 1 — 后端骨架搭建时

4. **Prompt 管理**: 在 `backend/app/agents/prompts/` 下按 Agent 拆分，参考 MAIC-UI 的集中管理模式

5. **API 设计**: 
   - 画像采集 → SSE 流式 (参考 OpenMAIC 的 chat route)
   - 资源生成 → POST + poll (参考 OpenMAIC 的 generate-classroom)
   - 视频渲染 → Celery 异步 Job

6. **Agent 画像数据结构**: 参考 OpenMAIC 的 Agent Profile 添加 `name/role/personality/avatar/teachingStyle` 等字段

### Sprint 2-3 — Agent 开发时

7. **ReviewAgent 验证逻辑**: 借鉴 MAIC-UI Heavy Generator 的验证闭环模式

8. **多模态生成模式**: 参考 MAIC-UI 的 5 种模态，设计 EduMind 的资源类型枚举

### 竞赛文档

9. **相关工作章节**: 将本报告的分析写入竞赛文档，展示对领域现状的充分调研

---

## 七、风险与注意

| 风险 | 说明 | 应对 |
|------|------|------|
| **技术栈不兼容** | 两个项目都是 React，EduMind 是 Vue | 只参考后端设计，不尝试复用前端代码 |
| **赛题约束** | 讯飞星火必须用，两个项目都没用 | 设计 Provider 抽象层，讯飞优先但可切换 |
| **过度参考** | 参考 ≠ 照抄，架构差异大 | 保持 EduMind 的核心差异 (知识图谱 + 审核层) |
| **维护活跃度** | OpenMAIC 迭代快 (2-3 周/版本) | 定期关注更新，跟进新功能的架构决策 |

---

## 八、参考资源

- OpenMAIC 仓库: https://github.com/THU-MAIC/OpenMAIC
- OpenMAIC 论文: JCST'26 (doi: 10.1007/s11390-025-6000-0)
- OpenMAIC 在线体验: https://open.maic.chat/
- MAIC-UI 仓库: https://github.com/THU-MAIC/MAIC-UI
- MAIC-UI 论文: arxiv:2604.25806
- MAIC-UI 团队邮箱: tsq25@mails.tsinghua.edu.cn
