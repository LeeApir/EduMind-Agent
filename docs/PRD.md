# 启智学伴（EduMind-Agent）产品需求文档

> **项目代号**：EduMind-Agent  
> **中文名**：启智学伴 · 基于多智能体的个性化学习系统  
> **赛题归属**：第十五届中国软件杯 A3 赛题（科大讯飞出题）  
> **文档版本**：v1.1 (2026-09-14)  
> **作者**：Solo Dev + AI Coding (Cursor / Codex)  
> **文档目的**：作为开发期间的"产品宪法"与 AI Coding 上下文锚点

**v1.1 修订摘要**：参考 OpenMAIC 的课堂资源生成流程，将 M2 重构为可编辑、可重试、可导出的分阶段生成流水线；将 M3 重构为知识图谱驱动的“规划—学习—评估—再规划”闭环；将 M4 重构为“多角色互动课堂 + 条件触发的多视角辩论”。EduMind 仍以讯飞星火、知识图谱、ReviewAgent 和 Manim 程序化动画作为核心差异化，不复制 OpenMAIC 的产品形态或实现。

---

## 目录

1. [项目概览](#一项目概览)
2. [用户与场景](#二用户与场景)
3. [功能需求](#三功能需求)
4. [多智能体设计](#四多智能体设计)
5. [数据模型](#五数据模型)
6. [技术架构](#六技术架构)
7. [API 契约](#七api-契约)
8. [非功能需求](#八非功能需求)
9. [开发计划](#九开发计划)
10. [评分对应表](#十评分对应表)

---

## 一、项目概览

### 1.1 项目背景

第十五届中国软件杯 A3 赛题要求参赛团队构建**多智能体协同的个性化学习系统**，借助大模型与多模态生成技术，实现"因材施教"的数字化落地。本项目以**数据结构课程**为切入点，面向"基础薄弱、偏好工程实践"的本科生，构建端到端的智能学伴系统。

### 1.2 产品定位

> **一句话定位**：以多智能体协作 + 知识图谱驱动的数据结构智能学伴，根据学生画像规划学习路径，将知识点生成可编辑、可交互、可评估的学习单元，并在多角色课堂中通过多视角辩论解释复杂概念。

### 1.3 核心价值主张

| 维度 | 行业现状 | 启智学伴的差异化 |
|---|---|---|
| 学习资源 | 标准化、千人一面 | 6+ 维画像驱动的**个性化生成** |
| 知识体系 | 线性 PPT / 视频 | **知识图谱 + 动态学习路径** |
| 学习交互 | 单一 ChatBot 一问一答 | **多角色互动课堂 + 条件触发的多视角辩论** |
| 多模态视频 | 通用视频模型生成（质量差） | **Manim 程序化生成**（事实可控、质量极高） |
| 防幻觉 | 无 | **评审 Agent 二审 + 知识图谱事实约束** |

### 1.4 技术关键词覆盖（赛题硬性要求）

- ✅ 多智能体协同（LangGraph + LearningUnit / Classroom / Debate 子图）
- ✅ 大模型应用（讯飞星火 v4.0 / Pro 作为底座）
- ✅ 多模态生成（Manim 视频 + 讯飞 TTS 配音 + 思维导图 + 图谱可视化）
- ✅ AI 辅助编程（Cursor 全程使用，记录工作流证据）
- ✅ 个性化画像（6+ 维，对话式构建，随学随新）
- ✅ 学习路径规划（图谱遍历 + 画像加权 + 实时调整）
- ✅ 防幻觉机制（ReviewAgent + 图谱约束）

### 1.5 获奖策略

| 评分项 | 占比 | 应对策略 |
|---|---|---|
| 创新价值与实用性 | 35% | 多角色互动课堂中的多视角辩论 + Manim 程序化视频范式 + 知识图谱驱动的动态路径闭环 |
| 功能实现及技术要求 | 45% | 5+ 资源类型完整、SSE 流式输出、防幻觉双层校验、12 周可演示里程碑制 |
| 配套文档丰富度 | 10% | 含架构图 / 时序图 / ER 图 / 数据流图 / Agent 协作图 |
| 演示视频 / PPT | 10% | 7 分钟剧本驱动（小李故事），含"幕后视角"切换镜头 |

---

## 二、用户与场景

### 2.1 目标用户画像

**主角**：**小李 · 大二计算机专业**

| 维度 | 描述 |
|---|---|
| 年级 / 专业 | 大二 · 计算机科学与技术 |
| 知识基础 | 数据结构基础薄弱，C 语言基本掌握 |
| 认知风格 | 偏视觉、偏感性、偏归纳推理 |
| 学习目标 | 短期：通过期末考；长期：能独立做项目 |
| 易错点偏好 | 指针操作易混、递归边界判断不清 |
| 工程偏好 | **偏工程实践，对纯理论推导兴趣不高** |
| 学习时段 | 晚上 8-11 点 / 单次专注约 25 分钟 |

> 所有 Demo 数据、演示视频脚本、Mock 用户都围绕**小李**展开。这是**故事化演示**的核心。

### 2.2 核心用户故事

#### Story 1：第一次使用（5 分钟内完成画像建立）
> 小李打开网页，没有看到繁琐的注册表单。系统说："Hi，我是你的学伴，能告诉我你正在学什么课程，遇到了什么困难吗？"小李在自然对话中提到"数据结构期末快考了，链表搞不懂指针，更想看代码不想看公式"。系统在对话结束时弹出一张画像卡片，列出了 6 维特征——小李第一次感觉"这个 AI 真的懂我"。

#### Story 2：困惑时的辩论圆桌（核心创新展示）
> 小李在学链表时疑惑："什么时候用链表，什么时候用数组？"
> 系统启动**辩论模式**：
> - **🚀 性能派 Agent** 从内存局部性、缓存命中率角度论证数组的优势  
> - **🛠️ 工程派 Agent** 从代码可维护性、动态扩容场景论证链表的优势  
> - **📚 学术派 Agent** 从抽象数据类型定义和教科书定义解释二者本质区别  
> - **🎤 主持人 Agent** 综合三方观点，结合小李"工程实践偏好"画像，给出："**对你的项目场景，我推荐你优先看工程派的解释**"
> 
> 小李点击"我喜欢这种解释"——画像中"认知风格 / 工程偏好"维度强化。

#### Story 3：图谱漫游（路径规划展示）
> 小李在主界面看到一张**知识图谱可视化**：绿色节点是已掌握的（如"数组"），红色高亮是当前学习区（"单链表"），灰色虚线是依赖路径上未学的（"双链表 → 循环链表 → 树"）。点击"循环链表"节点，系统自动调用资源生成 Agent 推送讲解文档 + Manim 动画 + 3 道针对小李易错点的题目。

#### Story 4：Manim 算法动画（多模态加分）
> 小李点击"看动画"，系统调用 VideoAgent：
> 1. 大模型基于"链表节点插入"知识点生成 Manim Python 代码
> 2. ReviewAgent 检查代码安全性
> 3. Manim Worker 在 Docker 中渲染
> 4. 讯飞 TTS 生成配音（节奏匹配画面）
> 5. 30-60 秒 1080P 动画返回前端
>
> 小李看到链表节点的指针变化被像 3Blue1Brown 那样可视化，瞬间理解了。

### 2.3 演示视频脚本（7 分钟内）

| 时段 | 内容 | 关键画面 |
|---|---|---|
| 0:00-0:30 | 开场：教育痛点 + 项目愿景 | 痛点字幕 + 系统 Logo |
| 0:30-1:30 | Story 1 画像构建 | 对话流式输出 + 画像卡片浮现 |
| 1:30-2:30 | Story 3 图谱漫游 + 路径规划 | AntV G6 知识图谱交互 |
| 2:30-4:00 | **Story 2 辩论圆桌（核心高潮）** | 圆桌 3 Agent 同时流式输出 + 主持人总结 |
| 4:00-5:00 | Story 4 Manim 动画生成 | 进度条 → 1080P 算法动画 |
| 5:00-5:30 | 5 类资源完整生成展示 | 文档 / 导图 / 题 / 视频 / 代码 一字排开 |
| 5:30-6:30 | **"幕后视角"切换：多智能体协作流程图** | LangGraph 节点实时点亮 + 消息流动 |
| 6:30-7:00 | 多端展示（H5 + iOS） + 技术创新总结 | 双端同步演示 |

---

## 三、功能需求

### 3.1 功能模块总览

```
┌──────────────────────────────────────────────────────────┐
│                   启智学伴 功能矩阵                         │
├──────────────┬──────────────┬──────────────┬─────────────┤
│ 模块         │ 用户视角      │ 智能体视角    │ 验收级别     │
├──────────────┼──────────────┼──────────────┼─────────────┤
│ M1 画像构建  │ 对话窗        │ ProfileAgent │ ⭐⭐⭐ 必做 │
│ M2 学习单元  │ 大纲/场景/导出│ 5 Agent + ReviewAgent │ ⭐⭐⭐ 必做 │
│ M3 动态路径  │ 图谱+推荐解释  │ PathAgent    │ ⭐⭐⭐ 必做 │
│ M4 互动课堂  │ 课堂+辩论模式  │ Tutor + Debate子图 │ ⭐⭐⭐ 必做（王炸）│
│ M5 深度辅导  │ 对话窗        │ TutorAgent   │ ⭐⭐ 增强项 │
│ M6 学习评估  │ 反馈+看板     │ AssessAgent  │ ⭐⭐⭐ 基础闭环 / ⭐ 增强 │
└──────────────┴──────────────┴──────────────┴─────────────┘
```

### 3.2 模块 M1：对话式画像构建

**输入**：自然语言对话（多轮）  
**输出**：6+ 维度画像 JSON  
**主智能体**：ProfileAgent（基于 LangGraph 状态机）

#### 6 个核心维度（必做）

| 维度 | 字段名 | 数据类型 | 示例 |
|---|---|---|---|
| 1. 专业背景 | `professional_background` | object | `{grade: "大二", major: "计算机", history: [...]}` |
| 2. 知识基础 | `knowledge_base` | object | `{mastered: ["数组"], weak: ["指针"], unknown: [...]}` |
| 3. 认知风格 | `cognitive_style` | object | `{visual: 0.8, deductive: 0.3, analytical: 0.4}` |
| 4. 学习目标 | `learning_goals` | object | `{short_term: "期末通过", long_term: "项目能力"}` |
| 5. 易错点偏好 | `error_preferences` | array | `[{topic: "指针", confusion_with: "引用"}]` |
| 6. 工程偏好 | `engineering_preference` | object | `{theory_vs_practice: 0.2, code_first: true}` |

#### 扩展维度（创新加分）

| 维度 | 字段名 | 价值 |
|---|---|---|
| 注意力时长 | `attention_span_minutes` | 单次任务时长上限，影响视频长度生成 |
| 学习时段偏好 | `preferred_time_slots` | 推送时机决策 |
| 社交学习偏好 | `social_learning` | 是否启用辩论模式的频率 |

#### 验收标准

- [ ] 5 轮内对话完成画像构建（不需要表单）
- [ ] 画像 JSON 严格符合 schema（用 Pydantic 校验）
- [ ] 学习过程中**自动增量更新**（如做错题后更新 `error_preferences`）
- [ ] 前端展示画像卡片，支持手动编辑修正

### 3.3 模块 M2：多智能体学习单元生成

M2 不再把 5 类资源视为彼此孤立的生成卡片，而是围绕一个知识点组装为可编辑、可重试、可导出的**学习单元（Learning Unit）**。借鉴 OpenMAIC 的“先大纲、后场景、再动作与组装”思路，但保留 EduMind 的知识图谱约束和 ReviewAgent 独立二审。

#### 学习单元组成

| 资源类型 | Agent | 输出格式 | 关键约束 |
|---|---|---|---|
| 课程讲解文档 | `DocAgent` | Markdown | 含学习目标、KaTeX 公式、代码块、分级标题 |
| 知识点思维导图 | `MindmapAgent` | JSON 树 | 兼容 Markmap / G6 渲染 |
| 多类型练习题 | `QuizAgent` | JSON 题库 | 选择 / 填空 / 编程 / 应用题 4 类，标注 Bloom 层级 |
| **Manim 算法动画** | `VideoAgent` | mp4 URL + 字幕 | 程序化生成、事实可控、讯飞 TTS 配音 |
| 可运行代码案例 | `CodeAgent` | JSON | Python/C++ 双语言 + 测试用例 + 安全审查 |

每个学习单元还包含 `learning_objectives`、`prerequisites`、`outline`、`scenes`、`agent_profiles`、`review_summary`、`version` 和 `export_manifest` 等元数据。

#### 分阶段生成流程

```text
0. 上下文准备
   用户目标 + 6 维画像 + 当前掌握度 + 图谱节点 + 教材/RAG 依据
   ↓
1. 大纲生成（OutlineAgent）
   输出学习目标、场景顺序、资源类型、预计时长
   ↓
2. 生成前编辑
   用户可增删、排序、改写场景；确认后冻结大纲版本
   ↓
3. 场景级生成
   Doc / Mindmap / Quiz / Code 可按依赖并行生成，Video 进入异步队列
   ↓
4. 质量审核
   每个场景独立经过 ReviewAgent；失败场景最多定向修正 2 次
   ↓
5. 学习动作与角色适配
   TutorAgent 根据角色画像生成讲解、提问、提示和场景切换动作
   ↓
6. 学习单元组装
   合并资源、审核记录、角色动作和导出清单，生成可恢复的版本快照
```

大纲确认前不启动高成本视频渲染。修改大纲后只使受影响场景失效，已通过审核且依赖未变化的场景可继续复用。

#### AI 角色画像

课堂角色画像由预设模板与学生画像共同生成，保持跨场景一致：

```json
{
  "id": "teacher_qizhi",
  "name": "启智导师",
  "role": "teacher",
  "personality": "耐心、严谨、鼓励学生先推理",
  "teaching_style": "工程案例优先，必要时补充理论",
  "speaking_style": "短句、分步、每轮只追问一个问题",
  "avatar": "teacher-default",
  "tts_voice": "xunfei-voice-id"
}
```

- 角色名称、头像、说话风格和音色对同一学习单元保持稳定。
- 角色画像只决定表达与互动方式，不得改变知识事实。
- P0 使用固定角色模板 + 少量画像参数；P1 再支持用户编辑角色。

#### 场景级编辑与重新生成

- 学习单元由多个 `scene` 组成，每个场景具有独立 ID、输入快照、生成状态和审核状态。
- 用户可以编辑单个场景的标题、目标、内容要求和资源类型。
- “重新生成当前场景”不得重建整个学习单元，也不得覆盖其他已确认场景。
- 重新生成创建新版本，保留旧版本以便对比和回退。
- 场景依赖发生变化时，系统明确提示哪些下游场景需要重新审核。

#### 异步任务与进度恢复

学习单元完整生成、Manim 渲染、TTS 和导出均使用持久化 Job，不占用普通请求连接：

```text
queued → planning → awaiting_outline_confirmation → generating
       → reviewing → rendering → assembling → completed
                   ↘ failed / canceled
```

- `POST` 创建 Job，返回 `job_id`；SSE 推送步骤、进度和局部结果。
- Job 状态写入 PostgreSQL/Redis，服务重启后可恢复或安全重试。
- 每个阶段使用幂等键，重试不得产生重复资源。
- 单场景失败不影响用户查看已完成场景，可单独重试。

#### 导出能力

| 优先级 | 格式 | 内容 |
|---|---|---|
| P0 | Markdown + JSON | 讲解文档、题目、导图、代码和完整结构化数据 |
| P0 | MP4 + SRT | Manim 动画、讯飞配音和字幕 |
| P1 | ZIP 学习包 | 学习单元 JSON、资源文件、版本清单，可离线归档 |
| P2 | PPTX / 离线 HTML | 教师可编辑课件与可交互离线页面 |

导出必须使用已通过 ReviewAgent 的资源版本，并记录生成模型、时间和内容版本。

#### 反思机制（防幻觉关键）

每个生成 Agent 输出后**强制经过 `ReviewAgent`**：

```text
GenerateAgent → ReviewAgent ──┬─→ 通过 → 保存为可发布版本
                              ├─→ 需修正 → 携带问题清单定向重生成（最多 2 次）
                              └─→ 严重错误 → 拒绝发布 + 提供兜底内容
```

`ReviewAgent` 检查事实依据、难度匹配、易错点覆盖、结构化输出合法性，以及代码和 Manim 脚本安全性。知识图谱用于约束核心概念及关系，教材/RAG 资料用于补充图谱之外的事实，不能以“术语不在图谱中”作为唯一错误依据。

#### Manim 视频生成流水线（EduMind 差异化）

```text
1. 场景大纲确认（如“链表节点插入”）
   ↓
2. VideoAgent 生成结构化分镜（画面、旁白、公式、时长）
   ↓
3. CodeGenAgent 生成受限 Manim Python 代码
   ↓
4. 静态规则扫描 + ReviewAgent 事实/安全审核 + 语法预检
   ↓
5. 隔离的 Manim Worker 渲染无声动画
   ↓
6. 讯飞 TTS 生成旁白，产出时间轴与字幕
   ↓
7. FFmpeg 对齐画面、音频和字幕，输出 MP4 + SRT
   ↓
8. 保存资源、校验时长/分辨率并回写 Job 状态
```

该流水线与 OpenMAIC **不相同**：OpenMAIC 的视频能力主要调用 Seedance、Kling、Veo、MiniMax、Grok 等生成式视频 Provider 获得媒体片段，并支持把课堂时间线渲染/导出为视频；EduMind 使用 Manim 代码确定性渲染数据结构和算法过程，重点是步骤准确、可复现、可审查。可借鉴 OpenMAIC 的分阶段、异步 Job、场景复用和导出设计，但不照搬其视频生成实现。

预生成策略：P0 优先预渲染 5 个核心演示场景到 `/data/videos/cache/`，其余场景按需生成；稳定后再扩展到 30 个知识点。

#### 验收标准

- [ ] 5 类资源均可组成一个完整学习单元，并能单独生成和读取
- [ ] 大纲可在正式生成前编辑、排序和确认
- [ ] 任一场景可独立重新生成、版本回退，不覆盖其他场景
- [ ] Job 可查询、取消、失败重试；服务重启后状态不丢失
- [ ] 结构化输出 schema 通过率 ≥ 98%，人工构造错误集上的 ReviewAgent 严重错误召回率 ≥ 90%
- [ ] P0 支持 Markdown/JSON、MP4/SRT 导出
- [ ] Manim 视频清晰度 1080P，时长 30-90 秒，展示 5 个预渲染核心场景

### 3.4 模块 M3：知识图谱驱动的动态学习路径

M3 不只是展示知识图谱，而是负责“规划—学习—评估—再规划”的个性化闭环。路径中的每个节点对应一个 M2 学习单元，节点掌握度和画像变化会驱动下一步推荐。

#### 知识图谱与学习状态

- **节点数**：P0 约 30 个，覆盖线性表 / 二叉树 / 排序 3 章。
- **关系类型**：`DEPENDS_ON`（前置依赖）、`SIMILAR_TO`（相似/易混概念）、`EXTENDS`（进阶扩展）。
- **用户节点状态**：`unseen`、`learning`、`weak`、`mastered`。
- **掌握度**：0-1 连续分值，由测验、代码运行、提示次数和复习结果共同更新。

#### 节点 schema（Neo4j Label: KnowledgePoint）

```cypher
CREATE (n:KnowledgePoint {
  id: "ds.list.linked",
  name: "单链表",
  chapter: "线性表",
  difficulty: 2,
  description: "...",
  ai_context: "教学时强调指针的'箭头'比喻...",
  prerequisites: ["ds.list.array", "c.pointer"],
  related_misconceptions: ["指针 vs 引用"]
})
```

用户掌握度属于用户业务数据，保存在 PostgreSQL，不直接写入公共知识图谱；Neo4j 负责知识结构，PathAgent 在规划时组合两类数据。

#### 路径规划与解释

输入：学习目标、当前画像、节点掌握度、前置依赖、最近学习表现。  
输出：有序学习节点、每节点推荐资源、预计时长和推荐理由。

```text
路径成本 = α × 依赖距离 + β × 难度跳跃惩罚 + γ × 易错点风险
         + ε × 遗忘风险 - δ × 已掌握程度 - ζ × 目标相关度
```

初始权重使用离线规则配置，不由 LLM 临时决定。每次推荐必须返回可解释依据，例如：

> 推荐先复习“C 指针”，因为“单链表”依赖该节点，且你最近两道指针题均答错；完成后继续学习“单链表插入”。

#### 动态闭环

```text
目标节点 → PathAgent 初始规划 → 学习 M2 单元 → 测验/代码/行为反馈
    ↑                                                ↓
    └──────── 画像与掌握度更新 ← AssessAgent ←──────┘
```

- 连续答错：降低当前节点掌握度，回退到缺失的前置节点或切换讲解资源。
- 达到掌握阈值：标记完成并推荐下一个可达节点。
- 用户手动跳过：保留风险提示，不伪造掌握状态。
- 路径变化：保存新版本，并向用户说明变化原因。
- `SIMILAR_TO` 节点同时出现且用户提出选型问题时，可触发 M4 多视角辩论。

#### 可视化设计（AntV G6）

- 节点配色：**绿（已掌握）/ 橙（学习中）/ 红（薄弱或目标）/ 灰（未学习）**。
- 边样式：实线（前置依赖）/ 虚线（相似易混）/ 粗线（当前推荐路径）。
- 交互：点击节点查看推荐理由、掌握证据和 M2 学习单元；支持用户设为目标或申请重新规划。
- 路径调整时只高亮变化节点，避免整图跳动造成认知负担。

#### 验收标准

- [ ] 30 节点知识图谱完整建模并存入 Neo4j
- [ ] 每个用户拥有独立掌握度和节点状态，不污染公共图谱
- [ ] 路径规划普通请求 P95 ≤ 200ms（不含 LLM 生成）
- [ ] 每次推荐均返回前置关系、画像或学习证据中的至少一项解释
- [ ] 测验/代码结果能更新掌握度，并在必要时产生新路径版本
- [ ] G6 在 100 节点以内保持可流畅交互

### 3.5 模块 M4：多角色互动课堂与多视角辩论（王炸）

M4 将日常学习的多角色陪伴与复杂问题的多视角推理组合在同一学习会话中。课堂角色负责讲解节奏和陪伴；辩论角色只在对比、选型或多解问题中临时启动，承担真正独立的专业推理。

#### 两层角色模型

| 层级 | 角色 | 目标 | 实现原则 |
|---|---|---|---|
| 课堂角色 | 启智导师、基础同学、进阶同学 | 主讲、提出典型误区、补充代码与边界 | TutorAgent 统一编排，按需生成发言，不持续并行调用 |
| 辩论角色 | 性能派、工程派、学术派、主持人 | 对多方案独立分析、权衡并形成个性化结论 | 三个视角 Agent 真并行，Moderator 汇总 |

课堂角色是稳定的产品人物，辩论角色是临时的推理职责。二者共享当前学习单元、学生画像和图谱上下文，但分别维护角色记忆，避免身份和立场混乱。

#### 多角色互动课堂

```text
进入 M2 学习单元
  → TutorAgent 读取大纲、画像和 M3 路径理由
  → 启智导师讲解当前场景
  → 基础同学按需提出典型误区
  → 进阶同学按需补充工程案例或边界条件
  → 真人学生回答、提问、暂停、跳过或切换资源
  → TutorAgent 选择下一动作：继续讲解 / 代码 / 动画 / 测验 / 辩论
```

课堂角色发言必须服务当前学习目标；同一知识点不得让多个角色重复改写相同内容。P0 采用一个 TutorAgent 编排多个角色表现，以控制延迟和 Token 成本。

#### 辩论触发与退出

满足任一条件时进入辩论模式：

1. 用户主动点击“展开多视角讨论”。
2. 问题含“区别、哪个好、怎么选、什么时候用”等对比/选型意图。
3. 问题同时关联两个 `SIMILAR_TO` 节点，且存在多种合理方案。

纯定义、唯一答案计算、简单语法错误、用户要求快速回答时不自动触发。辩论结束后必须回到原课堂场景，由启智导师结合结论继续教学，不能丢失进度。

#### 4 个辩论智能体

| 角色 | 视角 | 核心输出 |
|---|---|---|
| 🚀 性能派 | 时间复杂度、空间占用、缓存友好 | 性能条件、瓶颈与适用规模 |
| 🛠️ 工程派 | 可维护性、扩展性、实际项目 | 工程约束、开发成本与场景建议 |
| 📚 学术派 | 抽象数据类型、形式化定义、算法性质 | 理论边界、成立条件与反例 |
| 🎤 主持人 | 事实核验、观点权衡、画像匹配 | 共同结论、分歧、条件化建议 |

#### 辩论子图与课堂回归

```text
[课堂问题分类]
       ↓ debate
[并发 Fan-out]
  ┌────┼────┐
  ▼    ▼    ▼
性能  工程  学术
  └────┼────┘
       ↓
[ReviewAgent 交叉核验]
       ↓
[Moderator：结合问题条件 + 图谱事实 + 学生画像]
       ↓
[用户反馈：最易理解/最有帮助的视角]
       ↓
[更新画像偏好并返回原课堂场景]
```

主持人必须区分“客观结论”和“基于画像的学习建议”，不得因为用户偏好工程实践而篡改算法事实。

#### 视觉呈现（GSAP / Motion）

- 日常课堂显示导师、基础同学和进阶同学的稳定头像与角色名。
- 进入辩论后切换为圆桌布局，显示性能、工程、学术三个视角及主持人。
- 当前发言者头像放大并高亮；三方观点完成后由主持人显示共识、分歧和最终建议。
- 退出辩论时恢复原课堂场景、进度和资源状态。

#### 验收标准

- [ ] 同一学习会话可在课堂模式与辩论模式之间切换，返回后上下文和进度不丢失
- [ ] 课堂模式至少支持导师讲解、基础同学提问、进阶同学补充和真人学生打断
- [ ] 课堂角色不要求每个角色独立持续调用模型，普通场景首字节 P95 ≤ 3s
- [ ] 辩论模式三个视角 Agent 真并行输出，Moderator 只能在三方完成后总结
- [ ] 主持人显式引用问题条件、图谱依据和画像字段，并区分事实与偏好
- [ ] 用户反馈能更新 `cognitive_style.preference_persona`，影响后续表达方式
- [ ] P0 至少完成 3 个预定义场景：链表 vs 数组、递归 vs 迭代、BFS vs DFS

### 3.6 模块 M5：深度智能辅导（增强项）

M4 已包含 TutorAgent 的基础课堂编排；M5 在此基础上增加苏格拉底式追问、错因诊断和多模态补救教学。

- **追问策略**：不直接给答案，反问引导
  - 用户："这道题怎么做？"
  - 系统："你觉得这道题考的核心知识点是什么？"
- **多模态解答**：自动判断回答类型
  - 概念性 → 文字 + 思维导图
  - 流程性 → 文字 + Manim 动画片段
  - 编程性 → 文字 + 代码示例 + 测试用例

### 3.7 模块 M6：学习反馈与效果评估

测验、代码运行和提示次数驱动 M3 掌握度更新属于 P0 基础闭环；完整数据看板、视频行为分析和遗忘曲线提醒属于增强项。

| 数据维度 | 采集方式 | 用途 |
|---|---|---|
| 资源停留时长 | 前端埋点 | 判断兴趣点 |
| 答题正确率 / 错误模式 | 后端记录 | 更新 `error_preferences` |
| 视频回放 / 暂停 | 前端埋点 | 判断难点 |
| 辩论倾向选择 | 用户反馈 | 强化认知风格 |
| 提问频次 | 后端记录 | 困惑度评估 |

**P0 验收**：测验和代码结果可更新掌握度、薄弱点与路径版本。  
**P1 增强**：基于学习记录提供数据看板和遗忘曲线复习提醒。

---

## 四、多智能体设计

### 4.1 智能体角色与子图清单

```
┌────────────────────────────────────────────────────┐
│                Orchestrator (LangGraph)             │
└──┬──────────────────────────────────────────────┬──┘
   │                                              │
   │  ┌────────────────┐                         │
   ├─→│ ProfileAgent   │ 画像构建/更新           │
   │  └────────────────┘                         │
   │  ┌────────────────┐                         │
   ├─→│ PathAgent      │ 路径规划                │
   │  └────────────────┘                         │
   │  ┌────────────────────────────────────┐     │
   ├─→│ LearningUnit 子图：                 │     │
   │  │ Outline → 用户确认 → Scene 生成     │     │
   │  │ Doc / Mind / Quiz / Video / Code   │     │
   │  │             ↓                      │     │
   │  │        ReviewAgent                 │     │
   │  │             ↓                      │     │
   │  │      组装 / 版本 / 导出             │     │
   │  └────────────────────────────────────┘     │
   │  ┌────────────────────────────────────┐     │
   ├─→│ Classroom 子图：                    │     │
   │  │ TutorAgent 编排导师/基础/进阶角色    │     │
   │  │       ↓ 条件触发                    │     │
   │  │ Debate: Performance / Engineering / │     │
   │  │ Academic → Review → Moderator       │     │
   │  └────────────────────────────────────┘     │
   │  ┌────────────────┐                         │
   └─→│ AssessAgent    │ 学习评估                │
      └────────────────┘
```

### 4.2 协作协议（消息格式标准）

所有 Agent 间消息走 **LangGraph 共享状态**：

```python
class AgentState(TypedDict):
    user_id: str
    profile: dict              # 用户画像
    task_type: str             # "plan" | "generate" | "classroom" | "debate" | ...
    current_knowledge_point: str
    learning_unit_id: str
    outline_version: int
    current_scene_id: str
    classroom_mode: str        # "lesson" | "debate"
    intermediate_results: dict # 各 Agent 输出累积
    review_history: list       # 反思链历史
    final_output: dict
    metadata: dict             # job_id、token 用量、耗时等
```

### 4.3 反思机制设计

**两层反思**：

1. **生成内反思（Agent-level）**
   - 生成 Agent 输出后自评："我刚生成的内容是否覆盖了用户的易错点？"
   - 自评不通过 → 重新生成（最多 2 次）

2. **跨 Agent 反思（System-level）**
   - ReviewAgent 作为独立 Agent 审查所有生成产物
   - 审查不通过 → 退回原 Agent + 反馈具体问题点

**辩论 Agent 内的反思**（创新点）：
- 主持人在综合三方观点时**反思每个观点的合理性**，可对极端观点提出质疑
- 体现"多智能体协商而非堆叠"

---

## 五、数据模型

### 5.1 用户表（PostgreSQL）

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt
    nickname VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP
);
```

### 5.2 学生画像表（PostgreSQL JSONB）

```sql
CREATE TABLE student_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    version INT DEFAULT 1,
    
    professional_background JSONB,
    knowledge_base JSONB,
    cognitive_style JSONB,
    learning_goals JSONB,
    error_preferences JSONB,
    engineering_preference JSONB,
    extended_dimensions JSONB,
    
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, version)
);

CREATE INDEX idx_profile_user ON student_profiles(user_id);
```

### 5.3 学习单元、场景与资源（PostgreSQL + 文件系统）

```sql
CREATE TABLE learning_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    knowledge_point_id VARCHAR(64),
    title VARCHAR(200),
    learning_objectives JSONB,
    outline JSONB,
    outline_version INT DEFAULT 1,
    agent_profiles JSONB,
    status VARCHAR(30),       -- draft/generating/ready/failed/archived
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE learning_scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    learning_unit_id UUID REFERENCES learning_units(id) ON DELETE CASCADE,
    scene_key VARCHAR(64),
    scene_order INT,
    scene_type VARCHAR(30),   -- explanation/mindmap/quiz/video/code/debate
    input_snapshot JSONB,
    version INT DEFAULT 1,
    generation_status VARCHAR(30),
    review_status VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(learning_unit_id, scene_key, version)
);

CREATE TABLE generated_resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    learning_unit_id UUID REFERENCES learning_units(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES learning_scenes(id) ON DELETE CASCADE,
    knowledge_point_id VARCHAR(64),
    resource_type VARCHAR(20),  -- doc/mindmap/quiz/video/code
    
    content JSONB,              -- Markdown 文本 / 题目 / 代码 / 视频元数据
    file_url VARCHAR(500),      -- 视频 / 音频文件路径（如适用）
    
    generated_by VARCHAR(50),   -- Agent 名
    review_score FLOAT,         -- ReviewAgent 评分
    review_comments JSONB,
    version INT DEFAULT 1,
    supersedes_id UUID REFERENCES generated_resources(id),
    metadata JSONB,             -- token 用量、生成耗时等
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    learning_unit_id UUID REFERENCES learning_units(id) ON DELETE CASCADE,
    scene_id UUID REFERENCES learning_scenes(id) ON DELETE CASCADE,
    job_type VARCHAR(30),       -- unit/scene/manim/tts/export
    status VARCHAR(30),         -- queued/running/completed/failed/canceled
    stage VARCHAR(40),
    progress INT DEFAULT 0,
    idempotency_key VARCHAR(100) UNIQUE,
    error JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 5.4 知识图谱（Neo4j）

```cypher
// 节点
(:KnowledgePoint {
    id, name, chapter, difficulty,
    description, ai_context,
    common_misconceptions: [],
    learning_objectives: []
})

// 关系
(a)-[:DEPENDS_ON {weight: 1.0}]->(b)
(a)-[:SIMILAR_TO {comparison_topic: "..."}]->(b)
(a)-[:EXTENDS]->(b)
```

### 5.5 学习记录表（PostgreSQL）

```sql
CREATE TABLE learning_records (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID,
    knowledge_point_id VARCHAR(64),
    action VARCHAR(30),  -- view/answer/replay/debate/...
    duration_seconds INT,
    payload JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_lr_user_time ON learning_records(user_id, created_at DESC);

CREATE TABLE knowledge_mastery (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    knowledge_point_id VARCHAR(64),
    status VARCHAR(20),       -- unseen/learning/weak/mastered
    mastery_score FLOAT DEFAULT 0,
    evidence JSONB,           -- 测验、代码运行、提示次数、复习结果
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, knowledge_point_id)
);
```

### 5.6 互动课堂与辩论会话表（PostgreSQL）

```sql
CREATE TABLE classroom_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    learning_unit_id UUID REFERENCES learning_units(id),
    current_scene_id UUID REFERENCES learning_scenes(id),
    mode VARCHAR(20),          -- lesson/debate
    progress JSONB,
    role_memory JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE debate_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    classroom_session_id UUID REFERENCES classroom_sessions(id),
    topic VARCHAR(200),  -- 如 "链表 vs 数组"
    
    performance_view TEXT,
    engineering_view TEXT,
    academic_view TEXT,
    moderator_conclusion TEXT,
    
    user_preference VARCHAR(20),  -- 用户最终选择哪一派
    profile_delta JSONB,          -- 本次辩论对画像的更新
    
    created_at TIMESTAMP DEFAULT NOW()
);
```

`classroom_session_id` 关联所在互动课堂会话；辩论前后保存 `scene_id`、课堂进度和消息游标，确保退出辩论后恢复原学习场景。

### 5.7 Redis 键设计

| Key 模式 | 用途 | TTL |
|---|---|---|
| `cache:llm:{hash}` | 大模型响应缓存 | 24h |
| `session:{user_id}` | 用户会话 | 7d |
| `job:{job_id}` | 学习单元 / 场景 / 视频 / 导出任务热状态 | 24h |
| `queue:video` | 视频生成队列（Celery） | - |

### 5.8 Chroma Collection

- `kp_embeddings`：知识点描述的向量
- `resource_embeddings`：已生成资源的向量（用于相似检索）

---

## 六、技术架构

### 6.1 系统架构图

```
┌────────────────────────────────────────────────────────────────┐
│                          客户端层                                │
│  ┌─────────────────────────┐    ┌─────────────────────────┐    │
│  │  Web (Vue3 + Vite + TS)  │    │  iOS App (SwiftUI)       │    │
│  │  - Naive UI              │    │  - MarkdownUI            │    │
│  │  - AntV G6 (知识图谱)    │    │  - AVKit (视频)          │    │
│  │  - GSAP (课堂/圆桌切换)   │    │  - URLSession.bytes(SSE) │    │
│  │  - md-editor-v3          │    │  - 原型级（C 方案）      │    │
│  └─────────────────────────┘    └─────────────────────────┘    │
└─────────────────────┬───────────────────────────┬──────────────┘
                      │ HTTPS REST + SSE           │
                      └─────────┬─────────────────┘
                                ▼
┌────────────────────────────────────────────────────────────────┐
│                     API 网关层 (FastAPI)                         │
│  - JWT 认证          - SSE 流式             - OpenAPI 自动文档   │
│  - 限流              - CORS                 - Pydantic 校验      │
└─────────────────────┬──────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                  智能体编排层 (LangGraph)                        │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Orchestrator StateGraph                                  │ │
│  │  ProfileAgent / PathAgent / ResourceGen子图 /             │ │
│  │  Debate子图 / TutorAgent / AssessAgent / ReviewAgent      │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────┬──────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                      AI 能力层                                   │
│  讯飞星火 v4.0     讯飞 TTS    Manim Worker     Embedding 模型   │
└─────────────────────┬──────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                      数据存储层                                  │
│  PostgreSQL  │  Neo4j  │  Chroma  │  Redis  │  本地文件系统     │
│  业务数据     │  图谱    │  向量库   │  缓存+队列│  视频/音频     │
└────────────────────────────────────────────────────────────────┘
                      ↑
              docker-compose 一键编排
```

### 6.2 技术栈

#### Web 前端
| 类别 | 选型 | 理由 |
|---|---|---|
| 框架 | **Vue 3 + Vite + TypeScript** | AI Coding 配合好 / 中文社区强 |
| UI 库 | **Naive UI** | 现代深色风、AI 产品感 |
| 状态管理 | **Pinia** | Vue 3 官方推荐 |
| 知识图谱 | **AntV G6** | 中文文档、性能好 |
| Markdown | **md-editor-v3** + **KaTeX** | 公式渲染 |
| 动画 | **GSAP** | 多角色课堂与辩论圆桌模式切换 |
| 流式 | **fetch ReadableStream + EventSource (SSE)** | POST 对话流与 GET Job 事件流分别适配 |
| 构建 | **pnpm** | 单仓库性能最佳 |

#### iOS 前端（原型级）
| 类别 | 选型 |
|---|---|
| UI 框架 | SwiftUI |
| Markdown | **MarkdownUI** |
| 网络 | URLSession + AsyncSequence |
| 视频 | AVKit |
| 知识图谱（简化） | SwiftUI Canvas（不做完整 G6 平替） |

#### 后端
| 类别 | 选型 | 版本 |
|---|---|---|
| 语言 | Python | 3.11 |
| Web 框架 | **FastAPI** | latest |
| 智能体编排 | **LangGraph** | latest |
| ORM | SQLAlchemy 2.0 + asyncpg | latest |
| Neo4j 客户端 | py2neo / neo4j-driver | latest |
| 向量库 | chromadb | latest |
| 任务队列 | Celery + Redis | latest |
| 视频 | Manim Community | v0.18+ |
| 配音 | 讯飞 SDK | latest |
| 大模型 | 讯飞星火 SDK (sparkai) | latest |

#### 部署
- Docker + docker-compose（开发/演示）
- 本地服务器或云服务器（演示视频可录本地）

### 6.3 部署架构（docker-compose.yml）

```yaml
services:
  postgres:    # 业务数据
  neo4j:       # 知识图谱
  redis:       # 缓存 + Celery broker
  chroma:      # 向量库
  api:         # FastAPI
  worker:      # Celery worker (含 Manim 渲染)
  web:         # Vue dev server / nginx 静态
```

---

## 七、API 契约

### 7.1 认证 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/auth/register` | 邮箱注册 |
| POST | `/api/auth/login` | 邮箱密码登录，返回 JWT |
| GET | `/api/auth/me` | 获取当前用户信息 |
| POST | `/api/auth/logout` | 登出 |

### 7.2 画像 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/profile/dialog` (SSE) | 对话式画像构建（流式） |
| GET | `/api/profile/me` | 获取当前画像 |
| PATCH | `/api/profile/me` | 手动修正画像 |
| GET | `/api/profile/me/history` | 画像版本历史 |

### 7.3 学习单元生成、异步任务与导出 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/learning-units/outlines` | 基于目标、画像和图谱生成学习单元大纲 |
| PATCH | `/api/learning-units/{id}/outline` | 编辑、排序大纲并创建新版本 |
| POST | `/api/learning-units/{id}/confirm` | 确认大纲并创建正式生成 Job |
| GET | `/api/learning-units/{id}` | 获取学习单元、场景和当前版本 |
| POST | `/api/learning-units/{id}/scenes/{scene_id}/regenerate` | 单场景重新生成，不覆盖其他场景 |
| GET | `/api/resource/{id}` | 获取已生成资源 |
| GET | `/api/resource/list` | 列出我的资源（分页+筛选） |
| POST | `/api/learning-units/{id}/exports` | 创建 Markdown/JSON/MP4/ZIP 导出 Job |
| GET | `/api/jobs/{job_id}` | 查询异步任务状态、阶段和错误 |
| GET | `/api/jobs/{job_id}/events` (SSE) | 接收进度、局部结果和完成事件 |
| DELETE | `/api/jobs/{job_id}` | 取消尚未完成的任务 |
| POST | `/api/jobs/{job_id}/retry` | 从可恢复阶段幂等重试失败任务 |

### 7.4 知识图谱与路径 API

| Method | Path | 描述 |
|---|---|---|
| GET | `/api/graph` | 完整图谱（节点+关系） |
| GET | `/api/graph/node/{id}` | 单节点详情 |
| POST | `/api/path/plan` | 规划学习路径 |
| GET | `/api/path/current` | 当前推荐路径 |
| POST | `/api/path/replan` | 根据最新掌握度重新规划并返回变化理由 |
| GET | `/api/mastery` | 获取用户节点掌握度和证据摘要 |

### 7.5 互动课堂与辩论 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/classroom/sessions` | 创建或恢复互动课堂会话 |
| POST | `/api/classroom/{id}/messages` | 用户提问/回答；使用 fetch 流式返回课堂角色发言 |
| POST | `/api/classroom/{id}/actions` | 暂停、继续、跳过、切换资源 |
| POST | `/api/classroom/{id}/debates` | 在当前场景启动辩论 Job |
| GET | `/api/classroom/{id}/events` (SSE) | 接收课堂动作、角色发言和辩论输出 |
| POST | `/api/debate/{id}/feedback` | 用户反馈倾向 |
| GET | `/api/debate/history` | 我的辩论历史 |

### 7.6 辅导 / 评估 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/tutor/ask` (SSE) | 苏格拉底辅导 |
| POST | `/api/assess/log` | 行为埋点 |
| GET | `/api/assess/dashboard` | 学习评估看板 |

### 7.7 SSE 事件协议

```
event: agent_start      # Agent 开始工作
data: {"agent": "DocAgent", "task": "..."}

event: stage_changed    # Job/学习单元切换阶段
data: {"job_id": "...", "stage": "reviewing", "progress": 60}

event: scene_ready      # 单个场景已审核，可提前查看
data: {"scene_id": "...", "version": 2, "resource_ids": [...]}

event: classroom_action # 课堂角色或场景动作
data: {"session_id": "...", "role": "teacher_qizhi", "action": "speak"}

event: token            # 流式 token 输出
data: {"agent": "DocAgent", "delta": "..."}

event: agent_done       # Agent 完成
data: {"agent": "DocAgent", "result": {...}}

event: review_pass      # 反思通过
data: {"score": 0.92}

event: review_reject    # 反思拒绝
data: {"reason": "...", "retry": true}

event: progress         # 长任务进度（视频生成）
data: {"task_id": "...", "percent": 45, "stage": "rendering"}

event: error
data: {"code": "...", "message": "..."}

event: done             # 全部完成
data: {"final": {...}}
```

---

## 八、非功能需求

### 8.1 性能

| 指标 | 目标 |
|---|---|
| 大纲生成首字节响应 | P95 ≤ 2s |
| 非视频场景生成完成 | P95 ≤ 20s，并允许逐场景提前展示 |
| 预渲染视频命中 | P95 ≤ 2s 可播放 |
| 按需 Manim 视频生成 | 目标 P95 ≤ 90s，持续推送阶段进度 |
| 知识图谱加载 | ≤ 500ms |
| 课堂普通发言首字节 | P95 ≤ 3s |
| 辩论三 Agent 并发首字节 | P95 ≤ 3s |
| API 普通查询 | P99 ≤ 200ms |

### 8.2 防幻觉

1. **知识图谱事实约束**：核心概念、前置关系和易混关系优先以图谱为准；图谱未覆盖的事实必须由教材/RAG 依据补充
2. **ReviewAgent 二审**：所有生成产物经过反思
3. **置信度标注**：对模型不确定的内容标注 `[需确认]` 标签
4. **RAG 增强**：基于自建知识库（教材摘录）作为生成依据
5. **敏感词过滤**：黑名单 + 二次大模型审核

### 8.3 安全

| 维度 | 措施 |
|---|---|
| 用户密码 | bcrypt + salt |
| API 鉴权 | JWT (RS256)，2h 过期，refresh token |
| 速率限制 | Redis 计数器，单用户 60 req/min |
| 代码生成安全 | Manim 代码沙箱化，禁用危险 API |
| SQL 注入 | SQLAlchemy 参数化查询 |
| XSS | 前端 Markdown 渲染默认转义 |
| CSRF | Token Header 模式，无 cookie |

### 8.4 可观测性

- 后端：FastAPI middleware 记录请求 / Token 用量 / Agent 调用链
- 日志：结构化 JSON（Loguru），按用户/Agent 维度可查询
- 演示用看板：简易仪表盘展示总 Token 消耗、各 Agent 调用次数（PPT 用）

---

## 九、开发计划

### 9.1 12 周 Sprint 总览

| Sprint | 周数 | 主题 | 关键交付 | 是否可演示 |
|---|---|---|---|---|
| **S0** | W1 | 环境搭建 + 知识库 | docker-compose 跑起、星火 API 接通、Manim hello world、30 节点图谱 v0 | 内部 |
| **S1** | W2-3 | 后端骨架 + 认证 + 画像 | 邮箱登录可用、对话画像 SSE 跑通、画像存盘 | ✅ MVP1 |
| **S2** | W4-5 | 知识图谱 + 动态路径 | Neo4j 30 节点、掌握度、推荐解释、再规划闭环 | ✅ MVP2 |
| **S3** | W6 | 分阶段学习单元生成 | 大纲编辑、4 类资源、场景重生成、Job、ReviewAgent | ✅ MVP3 |
| **S4** | W7 | Manim 视频流水线 | VideoAgent + Worker + TTS 全链路 | ✅ MVP4（多模态加分核心） |
| **S5** | W8-9 | **互动课堂 + 辩论子图（王炸）** | 课堂角色编排、4 个辩论 Agent、模式切换、画像反馈 | ✅ MVP5（创新加分核心） |
| **S6** | W10 | iOS 原型 + UI 美化 | SwiftUI 浏览端 + Web UI 打磨 | ✅ 多端展示 |
| **S7** | W11 | 评估 + 深度辅导 + 优化 | M5/M6 增强项、性能优化、防幻觉强化 | 全功能 |
| **S8** | W12 | 文档 / PPT / 视频 | 提交包完整 | 🎬 提交 |

### 9.2 Sprint 详细任务

#### S0 (W1) - 启动周
- [ ] 申请讯飞星火 API key + TTS API key
- [ ] 项目仓库初始化（前端 + 后端 + iOS 三个子目录）
- [ ] docker-compose.yml 编写（5 服务）
- [ ] 知识图谱 v0：30 节点 YAML 定稿（手工 + AI 辅助）
- [ ] Manim 本地装好，渲染"链表节点"hello world
- [ ] 星火流式对话 demo
- [ ] PRD 评审 + ADR-001（架构决策记录） 写下

#### S1 (W2-3) - 骨架 + 画像
- [ ] FastAPI 项目脚手架（含 OpenAPI 自动文档）
- [ ] 数据库迁移工具（Alembic）+ 初始 schema
- [ ] JWT 认证模块 + 邮箱注册登录
- [ ] Vue3 项目脚手架 + Naive UI 接入
- [ ] 登录注册页面 + 路由守卫
- [ ] ProfileAgent（LangGraph 状态机）
- [ ] 对话画像 SSE 接口
- [ ] 前端对话窗口（流式输出）
- [ ] 画像卡片展示组件

#### S2 (W4-5) - 图谱 + 路径
- [ ] Neo4j 30 节点种子数据导入脚本
- [ ] 知识图谱 API（GET /api/graph）
- [ ] PathAgent + 路径权重算法
- [ ] 用户节点掌握度模型 + 学习证据记录
- [ ] 路径推荐理由 + 路径版本变化说明
- [ ] 测验/代码结果触发掌握度更新和重新规划
- [ ] AntV G6 前端组件（含交互）
- [ ] 节点详情面板
- [ ] 路径高亮动画

#### S3 (W6) - 分阶段学习单元生成
- [ ] OutlineAgent + 学习单元/场景 schema
- [ ] 大纲编辑、排序、确认界面
- [ ] DocAgent（Markdown 输出）
- [ ] MindmapAgent（JSON 树）+ Markmap 渲染
- [ ] QuizAgent（4 题型）+ 答题前端
- [ ] CodeAgent + 代码高亮展示
- [ ] **ReviewAgent**（关键反思层）
- [ ] 持久化 Job 状态 + SSE 进度恢复
- [ ] 单场景重新生成 + 版本回退
- [ ] Markdown/JSON 导出

#### S4 (W7) - Manim 视频
- [ ] VideoAgent 脚本生成
- [ ] CodeGenAgent → Manim 代码
- [ ] Manim Worker（Celery + Docker）
- [ ] 讯飞 TTS 配音流水线
- [ ] FFmpeg 合成
- [ ] 前端视频播放 + 进度条
- [ ] MP4/SRT 导出
- [ ] 5 个核心演示动画预渲染（稳定后扩展到 30 节点）

#### S5 (W8-9) - 多角色互动课堂 + 辩论子图
- [ ] TutorAgent 课堂状态机与场景动作
- [ ] 启智导师 / 基础同学 / 进阶同学角色画像
- [ ] 课堂提问、暂停、跳过、资源切换与会话恢复
- [ ] 4 个辩论 Agent 角色 prompt 设计
- [ ] 对比/选型意图识别 + 手动触发
- [ ] 并发 fan-out 实现（asyncio.gather）
- [ ] ReviewAgent 交叉核验 + Moderator 综合
- [ ] 课堂/圆桌模式切换动画（GSAP）
- [ ] 三方流式输出展示
- [ ] 辩论返回原课堂场景 + 用户反馈回路
- [ ] 3 个 P0 预设辩论场景测试通过

#### S6 (W10) - iOS + UI
- [ ] SwiftUI 项目初始化
- [ ] 登录 + 资源浏览页
- [ ] Markdown / 视频展示
- [ ] 简化对话窗（不做生成）
- [ ] Web UI 全面打磨（深色模式、动效、空状态）

#### S7 (W11) - 增强能力 + 优化
- [ ] TutorAgent 苏格拉底追问与错因诊断增强
- [ ] AssessAgent + 看板页面
- [ ] 行为埋点
- [ ] 性能优化（缓存命中率、SSE 流稳定性）
- [ ] 防幻觉测试 + 完善

#### S8 (W12) - 交付
- [ ] 系统开发说明书（80+ 页）
- [ ] 测试说明书
- [ ] 演示 PPT（30+ 页）
- [ ] 7 分钟演示视频
- [ ] 项目 README + 部署文档
- [ ] AI Coding 使用说明（含 Cursor 截图）

### 9.3 AI Coding 工作流（Cursor）

#### 工作流 SOP

```
1. 每个 Sprint 开始：
   - 阅读本 PRD 对应章节
   - 在 docs/sprint-N/tasks.md 写本周任务清单
   - Cursor Plan Mode 讨论关键设计

2. 每个任务：
   - Cursor Agent Mode 实现
   - 实现完跑测试
   - git commit（让 Cursor 写 message）

3. 每个 Sprint 结束：
   - 录 1-2 分钟演示视频片段
   - 更新 docs/CHANGELOG.md
   - ADR 记录关键架构变更

4. 每周日：
   - 整理本周 AI Coding 用量
   - 截图保留 3-5 个"AI 生成精彩瞬间"
```

#### 关键文档（与 PRD 配套）

| 文件 | 用途 |
|---|---|
| `docs/PRD.md` | 本文（产品宪法） |
| `docs/ADR/*.md` | 架构决策记录 |
| `docs/sprint-N/tasks.md` | 每周任务 |
| `docs/api/openapi.yaml` | API 契约 |
| `docs/agents/prompts/*.md` | 各 Agent 提示词 |
| `docs/CHANGELOG.md` | 变更日志 |
| `docs/AI-CODING.md` | AI Coding 使用说明（赛题要求） |

### 9.4 风险与应对

| 风险 | 概率 | 应对 |
|---|---|---|
| 讯飞星火限流 | 中 | 申请多个 API key 轮询，关键调用做缓存 |
| Manim 渲染超时 | 高 | P0 预生成 5 个核心动画，按需任务支持超时、重试与降级 |
| 知识图谱不完整 | 中 | S0 末完成 v0，S2 持续完善 |
| 多角色课堂与辩论模式切换工作量大 | 高 | P0 由 TutorAgent 统一编排课堂角色；动画来不及时降级为分栏对话 |
| iOS 工作量爆炸 | 高 | C 方案严格执行，只做浏览，不做生成 |
| 文档撰写时间不够 | 中 | 每周 commit 时同步写 changelog，最后只整合不撰写 |

---

## 十、评分对应表

### 10.1 35% 创新价值与实用性

| 创新点 | 对应模块 | 文档章节 |
|---|---|---|
| 多角色课堂中的多视角辩论 | M4 | §3.5 |
| Manim 程序化视频生成范式 | M2 VideoAgent | §3.3 |
| 知识图谱驱动的动态路径规划 | M3 | §3.4 |
| 跨 Agent 反思机制 | ReviewAgent | §4.3 |
| 6+扩展画像维度（注意力时长等） | M1 | §3.2 |
| AI Coding 工作流的工程化记录 | docs/AI-CODING.md | §9.3 |

### 10.2 45% 功能实现及技术要求

| 赛题硬性要求 | 我们的实现 | 文档章节 |
|---|---|---|
| 6 维画像 | 6 必做 + 3 扩展 | §3.2 |
| 5 类资源生成 | 5 类完整 + ReviewAgent | §3.3 |
| 多智能体协同 | 专职 Agent + LearningUnit / Classroom / Debate 子图协作 | §四 |
| 多模态生成 | Markdown / 思维导图 / 题库 / 代码 / Manim 视频 / TTS 配音 | §3.3 |
| 学习路径规划 | Neo4j + 加权算法 + 实时调整 | §3.4 |
| 防幻觉机制 | ReviewAgent + 图谱约束 + RAG | §8.2 |
| 流式输出 | AI 生成、课堂和辩论过程统一 SSE 事件协议 | §7.7 |
| 现代 AI 产品交互 | Naive UI + 流式 + 圆桌动画 | §6.2 |
| 必须使用讯飞工具 | 星火大模型 + TTS | §6.2 |

### 10.3 10% 配套文档丰富度

- ✅ 系统架构图
- ✅ 多智能体协作时序图
- ✅ ER 图（数据模型）
- ✅ API 契约（OpenAPI）
- ✅ 部署架构图
- ✅ 用户故事 + 演示脚本
- ✅ ADR 架构决策记录
- ✅ AI Coding 使用记录

### 10.4 10% 演示视频 / PPT 效果

- ✅ 7 分钟剧本（§2.3）
- ✅ 故事化主角（小李）
- ✅ "幕后视角"切换镜头
- ✅ 多端同步演示
- ✅ 关键创新点对应章节明确

---

## 附录 A：项目目录结构

```
EduMind-Agent/
├── docs/
│   ├── PRD.md                    ← 本文档
│   ├── ADR/
│   ├── api/openapi.yaml
│   ├── agents/prompts/
│   ├── sprint-N/tasks.md
│   ├── CHANGELOG.md
│   └── AI-CODING.md
├── backend/
│   ├── app/
│   │   ├── api/                  ← FastAPI 路由
│   │   ├── agents/               ← LangGraph Agent
│   │   ├── models/               ← SQLAlchemy
│   │   ├── services/             ← 业务逻辑
│   │   ├── core/                 ← 配置/JWT/中间件
│   │   └── workers/              ← Celery + Manim
│   ├── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── web/
│   ├── src/
│   │   ├── views/
│   │   ├── components/
│   │   ├── stores/               ← Pinia
│   │   ├── api/                  ← axios + SSE 封装
│   │   └── composables/
│   ├── package.json
│   └── vite.config.ts
├── ios/
│   └── EduMindAgent/             ← SwiftUI 项目
├── data/
│   ├── knowledge_graph.yaml      ← 30 节点种子
│   ├── videos/cache/             ← 预渲染动画
│   └── seeds/                    ← Demo 数据（小李等）
├── docker-compose.yml
├── .env.example
└── README.md
```

## 附录 B：知识图谱节点清单（30 节点）

### 线性表章（10 节点）
1. 数组（array）
2. 链表概念（linked-list-concept）
3. 单链表（single-linked-list）
4. 双向链表（doubly-linked-list）
5. 循环链表（circular-linked-list）
6. 栈（stack）
7. 顺序栈（array-stack）
8. 链栈（linked-stack）
9. 队列（queue）
10. 循环队列（circular-queue）

### 二叉树章（10 节点）
11. 树的基本概念（tree-concept）
12. 二叉树（binary-tree）
13. 二叉树遍历（traversal）
14. 前序遍历（preorder）
15. 中序遍历（inorder）
16. 后序遍历（postorder）
17. 层序遍历（level-order）
18. 二叉搜索树（bst）
19. 平衡二叉树（avl）
20. 完全二叉树（complete-bt）

### 排序章（10 节点）
21. 排序基本概念（sort-concept）
22. 冒泡排序（bubble-sort）
23. 选择排序（selection-sort）
24. 插入排序（insertion-sort）
25. 希尔排序（shell-sort）
26. 快速排序（quick-sort）
27. 归并排序（merge-sort）
28. 堆排序（heap-sort）
29. 计数排序（counting-sort）
30. 排序算法对比（sort-comparison）

### 关键 SIMILAR_TO 关系（辩论场景预设）
- 数组 ↔ 单链表（"链表 vs 数组"）
- 顺序栈 ↔ 链栈（"实现选择"）
- 邻接矩阵 ↔ 邻接表（图章节扩展）
- 快排 ↔ 归并排序（"原地 vs 稳定"）
- 递归遍历 ↔ 迭代遍历（"递归 vs 迭代"）

---

## 附录 C：演示主角小李的种子画像

```json
{
  "user_id": "demo-xiaoli",
  "nickname": "小李",
  "professional_background": {
    "grade": "大二",
    "major": "计算机科学与技术",
    "school_type": "普通本科",
    "course_history": ["C 程序设计 (B+)", "高等数学 (B)"]
  },
  "knowledge_base": {
    "mastered": ["数组", "C 基本语法"],
    "weak": ["指针", "递归"],
    "unknown": ["链表", "树", "图", "排序算法"]
  },
  "cognitive_style": {
    "visual_vs_textual": 0.8,
    "deductive_vs_inductive": 0.3,
    "preference_persona": null
  },
  "learning_goals": {
    "short_term": "通过数据结构期末考",
    "long_term": "能独立完成 Web 项目",
    "exam_oriented": true,
    "project_oriented": true
  },
  "error_preferences": [
    {"topic": "指针", "confusion_with": "引用"},
    {"topic": "递归", "issue": "边界条件判断"}
  ],
  "engineering_preference": {
    "theory_vs_practice": 0.2,
    "code_first": true,
    "preferred_languages": ["C", "Python"]
  },
  "extended_dimensions": {
    "attention_span_minutes": 25,
    "preferred_time_slots": ["20:00-23:00"],
    "social_learning": 0.5
  }
}
```

---

> **文档维护规则**  
> - 每个 Sprint 结束时更新章节"开发计划进度"  
> - 重大架构变更走 ADR，不直接改本文档  
> - 本文档是 AI Coding 的核心上下文，每次开新会话先读本文
