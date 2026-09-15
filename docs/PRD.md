# 启智学伴（EduMind-Agent）产品需求文档

> **项目代号**：EduMind-Agent  
> **中文名**：启智学伴 · 基于多智能体的个性化学习系统  
> **项目形态**：独立产品 / 开源项目
> **文档版本**：v2.1 (2026-09-15)
> **作者**：Lee + Claude / Codex
> **文档目的**：作为开发期间的"产品宪法"与 AI Coding 上下文锚点

**v2.1 修订摘要**：产品进一步从“AI 课件生成器”收敛为“面向学生的个性化学习系统”。学生通过一句自然语言立即开始学习，画像在学习行为中渐进完善；OpenMAIC 式大纲、场景和版本作为系统内部编排，不要求学生编辑或确认。MVP 缩减为单一 OpenAI-compatible Provider、8-10 个线性表知识点、讲解/代码/练习三类资源、单导师专注模式、正式资源按风险审核，以及预渲染/参数化 Manim 模板。

**v2.0 修订摘要**：项目由竞赛方案转为长期独立产品，移除比赛评分、固定交付期限和讯飞星火强制要求；新增可由用户选择的多模型 Provider 系统。任何兼容 Provider 均可承担课堂生成、审核、Embedding、TTS 或其他 AI 能力，讯飞星火与讯飞 TTS 保留为可选适配器。知识图谱、动态学习路径、ReviewAgent、Manim 程序化动画、多角色课堂和多视角辩论继续作为产品核心。

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
10. [产品指标与发布标准](#十产品指标与发布标准)

---

## 一、项目概览

### 1.1 项目背景

通用大模型能够回答知识问题，但通常缺少稳定的学习路径、持续更新的学生画像、可验证的掌握度，以及围绕同一课程长期积累的学习状态。EduMind 以**数据结构课程**为首个垂直领域，面向希望系统学习编程基础的大学生，将对话、知识图谱、多模态资源和学习评估组合为持续适应的学习过程。

### 1.2 产品定位

> **一句话定位**：以多智能体协作 + 知识图谱驱动的数据结构智能学伴，让学生用一句话开始学习，并根据渐进画像与学习表现持续调整讲解、资源和下一步路径。

### 1.3 核心价值主张

| 维度 | 行业现状 | 启智学伴的差异化 |
|---|---|---|
| 学习资源 | 标准化、千人一面 | 学习目标 + 渐进画像驱动的**个性化生成** |
| 知识体系 | 线性 PPT / 视频 | **知识图谱 + 动态学习路径** |
| 学习交互 | 单一 ChatBot 一问一答 | **多角色互动课堂 + 条件触发的多视角辩论** |
| 多模态视频 | 通用视频模型生成（质量差） | **Manim 程序化生成**（事实可控、质量极高） |
| 防幻觉 | 无 | **评审 Agent 二审 + 知识图谱事实约束** |

### 1.4 产品原则

- **模型中立**：业务逻辑依赖能力接口，不绑定单一模型厂商。
- **用户可控**：用户可以选择 Provider、模型和是否使用自带 API Key。
- **学习闭环**：画像、路径、学习单元、课堂互动和评估必须相互反馈。
- **学习过程可控**：学生可以调整难度、节奏和资源形式，要求重新解释、换例子、跳过或补充前置知识。
- **内部编排透明**：大纲、场景和版本由系统维护；学生可以查看学习计划，但无需扮演课件作者。
- **事实可追溯**：知识结构与教材依据提供事实边界，正式资源由 ReviewAgent 独立审核。
- **渐进复杂度**：先交付稳定 Web MVP，再扩展本地模型、更多模态和原生客户端。
- **隐私优先**：API Key 加密存储，敏感学习数据不进入日志或非必要 Provider。

### 1.5 产品目标与非目标

**当前目标**：

1. 让学生输入一句学习需求后立即获得第一段可学习内容，首次使用不要求完成画像问卷或多轮访谈。
2. 将一个知识点组织为可适应、可交互、可评估、可恢复的学习单元。
3. 在学习过程中根据测验、提示、资源选择和显式反馈持续更新掌握度与路径。
4. 允许用户选择云端或本地模型，并清楚了解模型能力、成本和数据去向。

**当前非目标**：

- 不在 MVP 中覆盖所有学科，先验证数据结构课程。
- 不复制 OpenMAIC 的完整通用课堂编辑器和全部 Provider。
- 不要求学生编辑大纲、场景元数据或资源清单；教师创作模式属于 P2。
- 不要求学生在开始学习前完成固定维度画像；画像在学习过程中渐进完善。
- 不在 MVP 中实现完全自由的 Python/Manim 代码执行。
- 不将 iOS 客户端、PPTX 导出和通用视频模型作为首发阻塞项。

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

> 小李是首个设计基准画像，用于保持产品决策、测试数据和验收场景一致；正式产品支持不同基础、目标和学习偏好的大学生。

### 2.2 核心用户故事

#### Story 1：一句话开始学习
> 小李打开网页，只看到一个对话框：“你现在想学习什么？”他输入“数据结构期末快考了，链表插入的指针总是搞混，想先看代码”。系统立即识别学习目标和临时偏好，开始第一段讲解，不要求填写画像或确认课件大纲。完成练习后，系统根据错题和资源选择逐步补充画像，并向小李解释下一步为什么需要复习 C 指针。

#### Story 2：困惑时的多视角辩论
> 小李在学链表时疑惑："什么时候用链表，什么时候用数组？"
> 系统启动**辩论模式**：
> - **🚀 性能派 Agent** 从内存局部性、缓存命中率角度论证数组的优势  
> - **🛠️ 工程派 Agent** 从代码可维护性、动态扩容场景论证链表的优势  
> - **📚 学术派 Agent** 从抽象数据类型定义和教科书定义解释二者本质区别  
> - **🎤 主持人 Agent** 综合三方观点，结合小李"工程实践偏好"画像，给出："**对你的项目场景，我推荐你优先看工程派的解释**"
> 
> 小李点击"我喜欢这种解释"——画像中"认知风格 / 工程偏好"维度强化。

#### Story 3：图谱漫游（路径规划展示）
> 小李在学习页看到一条轻量路径：已掌握“数组”→ 建议复习“C 指针”→ 当前学习“单链表插入”→ 下一步“链表删除”。点击节点即可查看推荐理由；进入节点后先展示讲解，需要时再查看代码、练习或请求 Manim 动画，不自动生成全部资源。

#### Story 4：Manim 算法动画
> 小李点击"看动画"，系统调用 VideoAgent：
> 1. 系统优先匹配已审核的“链表插入”预渲染资源
> 2. 未命中时，将当前节点名称和指针参数注入参数化模板
> 3. 后台完成受限 Manim 渲染并返回进度
> 4. 30-90 秒动画返回前端，字幕默认可用，配音属于增强能力
> 5. P1 才在无模板覆盖时使用 LLM 生成动画 DSL，并执行完整安全审核
>
> 小李看到链表节点的指针变化被像 3Blue1Brown 那样可视化，瞬间理解了。

### 2.3 核心用户旅程

```text
首次进入
  → 在单一对话框输入学习目标与困难
  → 系统建立临时画像并识别知识点
  → 立即展示第一段讲解与推荐理由
  → 进入多角色互动课堂
  → 按需查看代码、动画和练习，或调整难度与节奏
  → 对比/选型问题触发多视角辩论
  → 学习结果更新掌握度、渐进画像和下一步路径
```

大纲、场景依赖和版本仍由系统在后台维护，以支持恢复、复用和审核，但不作为学生开始学习的前置步骤。首次学习允许匿名会话并采用系统默认模型；用户创建账号后可以跨设备同步画像、进度和资源。P1 用户可在设置中选择 Provider。Provider 不可用时，系统保留已生成资源与学习进度，并提示重试或切换模型。

---

## 三、功能需求

### 3.1 功能模块总览

```
┌──────────────────────────────────────────────────────────┐
│                   启智学伴 功能矩阵                         │
├──────────────┬──────────────┬──────────────┬─────────────┤
│ 模块         │ 用户视角      │ 智能体视角    │ 产品优先级   │
├──────────────┼──────────────┼──────────────┼─────────────┤
│ M1 渐进画像  │ 一句话开始+行为反馈│ ProfileAgent │ P0       │
│ M2 学习单元  │ 讲解/代码/练习/动画│ LearningUnitGenerator │ P0 │
│ M3 动态路径  │ 推荐解释+轻量图谱│ PathAgent    │ P0          │
│ M4 互动课堂  │ 专注模式+按需角色│ Tutor + Debate子图 │ P0/P1  │
│ M5 深度辅导  │ 对话窗        │ TutorAgent   │ P1          │
│ M6 学习评估  │ 反馈+看板     │ AssessAgent  │ P0 闭环 / P1 看板 │
│ M7 模型设置  │ 系统默认+高级配置│ ProviderGateway │ P0/P1   │
└──────────────┴──────────────┴──────────────┴─────────────┘
```

### 3.2 模块 M1：渐进式学生画像

**首次输入**：一句自然语言学习需求
**持续输入**：提问、资源选择、答题、提示、跳过、反馈等学习行为
**输出**：允许字段未知、带证据与置信度的渐进画像 JSON
**主智能体**：ProfileAgent

首次请求不得为了补全画像而阻塞学习。ProfileAgent 从一句话中只提取当前任务所需信息；没有证据的字段保持 `unknown`，不允许模型臆测。后续在真实学习行为中增量更新，并记录 `source`、`confidence` 和更新时间。

#### 画像维度（渐进完善）

| 维度 | 字段名 | 数据类型 | 示例 |
|---|---|---|---|
| 1. 专业背景 | `professional_background` | object | `{grade: "大二", major: "计算机", history: [...]}` |
| 2. 知识基础 | `knowledge_base` | object | `{mastered: ["数组"], weak: ["指针"], unknown: [...]}` |
| 3. 认知风格 | `cognitive_style` | object | `{visual: 0.8, deductive: 0.3, analytical: 0.4}` |
| 4. 学习目标 | `learning_goals` | object | `{short_term: "期末通过", long_term: "项目能力"}` |
| 5. 易错点偏好 | `error_preferences` | array | `[{topic: "指针", confusion_with: "引用"}]` |
| 6. 工程偏好 | `engineering_preference` | object | `{theory_vs_practice: 0.2, code_first: true}` |

MVP 首次只要求 `learning_goals` 至少包含当前知识点或困难；其余维度均可为空。画像卡片默认作为可查看、可纠正的学习设置，不要求学生完成全部字段。

#### 扩展维度（P1）

| 维度 | 字段名 | 价值 |
|---|---|---|
| 注意力时长 | `attention_span_minutes` | 单次任务时长上限，影响视频长度生成 |
| 学习时段偏好 | `preferred_time_slots` | 推送时机决策 |
| 社交学习偏好 | `social_learning` | 是否启用辩论模式的频率 |

#### 验收标准

- [ ] 用户输入一句话即可开始学习，画像补全不阻塞首次内容生成
- [ ] 临时画像与持久画像 JSON 严格符合 schema，未知字段允许为空且不得臆测
- [ ] 每个推断字段记录证据来源和置信度，学习过程中自动增量更新
- [ ] 前端展示画像卡片，支持手动编辑修正

### 3.3 模块 M2：个性化学习单元生成

M2 围绕一个知识点组装可适应、可重试、可恢复的**学习单元（Learning Unit）**。系统内部借鉴 OpenMAIC 的“先大纲、后场景、再动作与组装”，但学生只需表达学习目标并控制难度、节奏和资源形式，不需要编辑或确认课件结构。

#### 学习单元组成

| 资源类型 | Agent | 输出格式 | 关键约束 |
|---|---|---|---|
| 课程讲解 | `LearningUnitGenerator` | Markdown | P0，短段落、示例和必要公式，支持“更简单/更深入/换个例子” |
| 代码示例 | `LearningUnitGenerator` | JSON | P0，首发一种语言，包含预期输出和关键步骤说明 |
| 小型练习 | `LearningUnitGenerator` | JSON | P0，每个单元 3 道左右，结果用于更新掌握度 |
| **Manim 算法动画** | `VideoAgent` | mp4 URL + 字幕 | P0 增强项，优先预渲染或参数化模板，按需播放 |
| 知识点思维导图 | `MindmapAgent` | JSON 树 | P1，不阻塞核心学习闭环 |

每个学习单元在系统内部包含 `learning_objectives`、`prerequisites`、`outline`、`scenes`、`profile_snapshot`、`review_summary` 和 `version` 等元数据。学生界面只展示学习计划、当前进度和可执行学习动作。

#### 分阶段生成流程

```text
0. 上下文准备
   用户目标 + 6 维画像 + 当前掌握度 + 图谱节点 + 教材/RAG 依据
   ↓
1. 内部学习计划生成
   输出学习目标、场景顺序、资源建议和预计时长；不阻塞首段讲解
   ↓
2. 快速首屏生成
   流式返回第一段讲解；学生可立即开始，不需要确认大纲
   ↓
3. 资源渐进生成
   代码和练习按场景生成；Manim 仅在用户请求或教学策略需要时加载
   ↓
4. 分级质量审核
   正式讲解/代码/练习经过 ReviewAgent；普通对话使用轻量规则
   ↓
5. 学习动作与角色适配
   TutorAgent 默认以专注模式讲解，按需调用其他角色或辩论
   ↓
6. 学习单元组装
   合并资源、审核记录、学习动作和掌握度证据，生成可恢复快照
```

系统可以在后台生成并调整大纲，但不得要求学生冻结版本。高成本视频不随学习单元自动全量生成；修改学习目标后只使受影响场景失效，已审核且依赖未变化的资源继续复用。

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
  "tts_voice": "provider-specific-voice-id"
}
```

- 角色名称、头像、说话风格和音色对同一学习单元保持稳定。
- 角色画像只决定表达与互动方式，不得改变知识事实。
- P0 使用固定导师模板 + 少量画像参数；学生可选择专注或互动模式，但不编辑角色画像。

#### 学生学习控制与内部版本

- 学习单元由多个 `scene` 组成，每个场景具有独立 ID、输入快照、生成状态和审核状态。
- 学生可以执行“更简单”“更深入”“换个例子”“先看代码”“播放动画”“跳过”和“补充前置知识”。
- “重新解释当前场景”不得重建整个学习单元，也不得覆盖其他已完成场景。
- 重新生成创建新版本，保留旧版本以便对比和回退。
- 版本和依赖由系统内部维护；教师级大纲编辑、排序和场景元数据修改延后到 P2。

#### 异步任务与进度恢复

MVP 的讲解、代码和练习直接流式生成；只有未命中缓存的 Manim 渲染等长任务使用异步 Job：

```text
queued → planning → generating → reviewing → ready
                      ↓ on demand
                  rendering → completed / failed / canceled
```

- 长任务 `POST` 创建 Job 并返回 `job_id`；SSE 推送阶段和进度。
- P0 使用 PostgreSQL 保存任务状态；引入 Redis/Celery 后可迁移热状态和队列。
- 每个阶段使用幂等键，重试不得产生重复资源。
- 单场景失败不影响用户查看已完成场景，可单独重试。

#### 导出能力

| 优先级 | 格式 | 内容 |
|---|---|---|
| P0 | Markdown | 学习笔记、知识点总结和错题摘要 |
| P0 | MP4 + SRT | 已生成的 Manim 动画、可选配音和字幕 |
| P1 | 学习报告 | 掌握度变化、路径和复习建议 |
| P2 | JSON / ZIP / PPTX / 离线 HTML | 教师创作、迁移和离线课件 |

导出必须使用已通过 ReviewAgent 的资源版本，并记录生成模型、时间和内容版本。

#### 分级审核机制

审核强度由内容风险和是否持久化决定，避免普通对话每轮都产生第二次模型调用：

| 内容 | P0 审核方式 |
|---|---|
| 普通课堂对话、追问和提示 | schema、长度、敏感内容、引用范围等轻量规则；高风险时升级 |
| 保存为学习单元的讲解、代码和练习 | 独立 `ReviewAgent` 审核，失败后定向修正 |
| Manim 动画 DSL | schema + 动作白名单 + 静态安全规则 + `ReviewAgent` |
| 多视角辩论总结 | `ReviewAgent` 交叉核验后由 Moderator 输出 |

```text
临时对话 → 轻量规则 ──→ 直接流式返回 / 升级审核

正式资源 → ReviewAgent ──┬─→ 通过 → 保存为可发布版本
                          ├─→ 需修正 → 携带问题清单定向重生成（最多 2 次）
                          └─→ 严重错误 → 拒绝发布 + 提供兜底内容
```

`ReviewAgent` 检查事实依据、难度匹配、易错点覆盖、结构化输出合法性，以及代码和 Manim 脚本安全性。知识图谱用于约束核心概念及关系，教材/RAG 资料用于补充图谱之外的事实，不能以“术语不在图谱中”作为唯一错误依据。

#### Manim 视频生成流水线（EduMind 差异化）

```text
1. 系统确定动画目标与场景状态（如“链表节点插入”）
   ↓
2. 查询预渲染缓存
   ├─ 命中 → 直接返回 MP4 + SRT
   ↓
3. 查询参数化模板
   ├─ 命中 → 注入节点、数值和讲解参数后进入渲染
   ↓
4. P1 完整生成：用户选择的 LLM 通过 VideoAgent 生成结构化分镜与动画 DSL
   ↓
5. 模板编译器将白名单动作转换为受限 Manim Python 代码
   ↓
6. 静态规则扫描 + ReviewAgent 事实/安全审核 + 语法预检
   ↓
7. 隔离的 Manim Worker 渲染无声动画
   ↓
8. 可选 TTS + FFmpeg 合成，保存资源并回写 Job 状态
```

该流水线与 OpenMAIC **不相同**：OpenMAIC 的视频能力主要调用生成式视频 Provider 获得媒体片段，并支持把课堂时间线渲染/导出为视频；EduMind 使用动画 DSL、模板编译器与 Manim 确定性渲染数据结构和算法过程，重点是步骤准确、可复现、可审查。两者共享分阶段、异步 Job、场景复用和导出思想，但不共享视频底层实现。

P0 不开放任意主题的 LLM 动画生成，只提供链表插入、链表删除和指针移动等 2-3 个预渲染/参数化模板。P1 完整生成仅开放 `create_node`、`connect`、`disconnect`、`move_pointer`、`highlight`、`compare`、`swap`、`visit` 和 `show_complexity` 等动画动作。模型不得直接提交任意 Python；DSL 校验或渲染失败时自动降级到已验证模板。

缓存优先级固定为“预渲染资源 → 参数化模板 → P1 完整 DSL 生成”。缓存键包含知识点、模板版本、参数和语言；同一输入必须复用已审核资源。

#### 验收标准

- [ ] 用户输入一句话后可直接进入学习，不出现强制画像或大纲确认步骤
- [ ] 讲解、代码和练习可组成一个完整学习单元，并能按需读取
- [ ] 学生可调整难度、换例子、切换资源、跳过或重新解释当前场景
- [ ] 内部场景版本可恢复；重新解释不覆盖其他已完成场景
- [ ] Manim 长任务可查询、取消和失败重试；普通资源不依赖异步队列
- [ ] 结构化输出 schema 通过率 ≥ 98%，人工构造错误集上的 ReviewAgent 严重错误召回率 ≥ 90%
- [ ] P0 支持 Markdown 学习笔记以及 MP4/SRT 导出
- [ ] 2-3 个 Manim 模板可稳定复用，缓存命中时 2 秒内开始播放

### 3.4 模块 M3：知识图谱驱动的动态学习路径

M3 不只是展示知识图谱，而是负责“规划—学习—评估—再规划”的个性化闭环。路径中的每个节点对应一个 M2 学习单元，节点掌握度和画像变化会驱动下一步推荐。

#### 知识图谱与学习状态

- **节点数**：P0 为 8-10 个，优先覆盖数组、指针、单链表、链表插入/删除/遍历、栈和队列；P1 扩展到约 30 个节点。
- **关系类型**：`DEPENDS_ON`（前置依赖）、`SIMILAR_TO`（相似/易混概念）、`EXTENDS`（进阶扩展）。
- **用户节点状态**：`unseen`、`learning`、`weak`、`mastered`。
- **掌握度**：0-1 连续分值，P0 由测验、提示次数、重新解释和复习结果共同更新；P1 再纳入代码运行证据。

#### 统一节点 schema

```yaml
id: ds.list.linked
name: 单链表
chapter: 线性表
difficulty: 2
description: "..."
ai_context: "教学时强调指针的‘箭头’比喻"
prerequisites: [ds.list.array, c.pointer]
related_misconceptions: ["指针 vs 引用"]
```

用户掌握度属于用户业务数据，保存在 PostgreSQL。P0 的公共知识结构使用版本化 YAML 或 PostgreSQL 关系表；PathAgent 组合知识结构与掌握度。P1 节点和关系复杂度增长后再迁移到 Neo4j，迁移不得改变外部 API。

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
目标节点 → PathAgent 初始规划 → 学习 M2 单元 → 测验/提示/行为反馈
    ↑                                                ↓
    └──────── 画像与掌握度更新 ← AssessAgent ←──────┘
```

- 连续答错：降低当前节点掌握度，回退到缺失的前置节点或切换讲解资源。
- 达到掌握阈值：标记完成并推荐下一个可达节点。
- 用户手动跳过：保留风险提示，不伪造掌握状态。
- 路径变化：保存新版本，并向用户说明变化原因。
- `SIMILAR_TO` 节点同时出现且用户提出选型问题时，可触发 M4 多视角辩论。

#### 学习路径可视化（P0 轻量，P1 G6）

- 节点配色：**绿（已掌握）/ 橙（学习中）/ 红（薄弱或目标）/ 灰（未学习）**。
- 边样式：实线（前置依赖）/ 虚线（相似易混）/ 粗线（当前推荐路径）。
- 交互：点击节点查看推荐理由、掌握证据和 M2 学习单元；支持用户设为目标或申请重新规划。
- 路径调整时只高亮变化节点，避免整图跳动造成认知负担。

#### 验收标准

- [ ] 8-10 个线性表相关知识节点及关系完成建模，并可从版本化种子数据加载
- [ ] 每个用户拥有独立掌握度和节点状态，不污染公共图谱
- [ ] 路径规划普通请求 P95 ≤ 200ms（不含 LLM 生成）
- [ ] 每次推荐均返回前置关系、画像或学习证据中的至少一项解释
- [ ] 测验、提示和显式反馈能更新掌握度，并在必要时产生新路径版本
- [ ] 轻量路径视图能够显示当前节点、前置节点、下一节点及推荐理由

### 3.5 模块 M4：多角色互动课堂与多视角辩论

M4 将专注学习、按需角色互动与复杂问题的多视角推理组合在同一学习会话中。默认只有启智导师发言；基础同学、进阶同学和辩论角色只有在学生主动开启或确有教学价值时出现，避免打断学习。

#### 两层角色模型

| 层级 | 角色 | 目标 | 实现原则 |
|---|---|---|---|
| 专注模式（P0 默认） | 启智导师 | 主讲、提问、反馈和资源切换 | 单 TutorAgent，优先保证连续性和低延迟 |
| 互动模式（P0 可选） | 启智导师、基础同学、进阶同学 | 按需呈现典型误区、代码与边界 | TutorAgent 统一编排，不持续并行调用 |
| 辩论模式（P0 演示 / P1 完整） | 性能派、工程派、学术派、主持人 | 对多方案独立分析、权衡并形成个性化结论 | P0 单次结构化生成一个预设场景；P1 升级为三 Agent 真并行 |

课堂角色是稳定的产品人物，辩论角色是临时的推理职责。学生可以在设置中选择“专注”或“互动”；P1 再增加互动频率。二者共享当前学习单元、渐进画像和路径上下文，但分别维护角色记忆。

#### 多角色互动课堂

```text
进入 M2 学习单元（默认专注模式）
  → TutorAgent 读取内部计划、可用画像和 M3 路径理由
  → 启智导师讲解当前场景
  → 学生主动开启互动，或 TutorAgent 检测到典型误区
  → 基础同学或进阶同学按需出现，不要求两者都发言
  → 真人学生回答、提问、暂停、跳过或切换资源
  → TutorAgent 选择下一动作：继续讲解 / 代码 / 动画 / 测验 / 辩论
```

课堂角色发言必须服务当前学习目标；同一知识点不得让多个角色重复改写相同内容。切换回专注模式后，除启智导师外的角色停止主动发言。P0 采用一个 TutorAgent 编排所有课堂表现。

#### 辩论触发与退出

P0 只实现“数组 vs 链表”一个预设多视角演示，使用一次结构化生成返回三个视角和总结。P1 满足任一条件时进入完整辩论模式：

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

- 专注模式只突出启智导师和学生当前内容；互动模式才显示其他课堂角色。
- 进入辩论后切换为圆桌布局，显示性能、工程、学术三个视角及主持人。
- 当前发言者头像放大并高亮；三方观点完成后由主持人显示共识、分歧和最终建议。
- 退出辩论时恢复原课堂场景、进度和资源状态。

#### 验收标准

- [ ] 默认专注模式只有启智导师主动发言，学生可随时开启或关闭互动模式
- [ ] 互动模式支持基础同学或进阶同学按需出现，返回专注模式后不丢失进度
- [ ] 课堂角色不要求每个角色独立持续调用模型，普通场景首字节 P95 ≤ 3s
- [ ] P0 完成“数组 vs 链表”结构化多视角演示；P1 三个视角 Agent 真并行输出
- [ ] 主持人显式引用问题条件、图谱依据和画像字段，并区分事实与偏好
- [ ] 用户反馈能更新 `cognitive_style.preference_persona`，影响后续表达方式

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

测验结果、提示次数、重新解释和显式反馈驱动 M3 掌握度更新，属于 P0 基础闭环；代码运行证据、完整数据看板、视频行为分析和遗忘曲线提醒属于增强项。

| 数据维度 | 采集方式 | 用途 |
|---|---|---|
| 资源停留时长 | 前端埋点 | 判断兴趣点 |
| 答题正确率 / 错误模式 | 后端记录 | 更新 `error_preferences` |
| 视频回放 / 暂停 | 前端埋点 | 判断难点 |
| 辩论倾向选择 | 用户反馈 | 强化认知风格 |
| 提问频次 | 后端记录 | 困惑度评估 |

**P0 验收**：测验、提示和显式反馈可更新掌握度、薄弱点与路径版本。
**P1 增强**：基于学习记录提供数据看板和遗忘曲线复习提醒。

### 3.8 模块 M7：模型与能力提供商

M7 为所有 Agent 和多模态能力提供统一 Provider Gateway。业务模块只依赖内部能力接口，但 P0 只实现一个由服务端配置的 OpenAI-compatible Provider，并提供系统默认模型，让学生无需配置即可开始学习。BYOK、本地模型和多 Provider 设置属于后续产品化能力。

#### Provider 类型与优先级

| 优先级 | Provider 类型 | 覆盖范围 |
|---|---|---|
| P0 | OpenAI-compatible | OpenAI 及兼容 Chat Completions/Responses 风格接口的云端或自托管服务 |
| P1 | Ollama / 本地 OpenAI-compatible | 本地文本生成与 Embedding |
| P1 | 用户 BYOK 与模型设置 | 用户连接自己的兼容服务并选择任务模型 |
| P1 | Anthropic 原生适配器 | Claude 文本、流式和工具调用 |
| P1 | Google Gemini 原生适配器 | Gemini 文本、多模态和结构化输出 |
| P1 | 讯飞星火原生适配器 | 星火文本生成；不再作为强制依赖 |
| P1 | TTS / ASR 适配器 | 讯飞、OpenAI-compatible、Azure 或本地语音服务 |
| P2 | 图片 / 通用视频 Provider | 作为补充媒体，不替代 Manim 算法动画 |

#### 模型能力注册

每个模型注册 `streaming`、`structured_output`、`tool_calling`、`vision`、`embedding`、`tts`、`asr` 等能力，以及上下文长度、并发限制和可选成本信息。Agent 提交能力需求，由 Provider Gateway 校验后路由：

```text
任务临时覆盖 → 用户任务档位 → 用户默认设置 → 系统默认 Provider
```

P0 在内部保留任务档位接口，但所有档位可映射到同一个系统默认模型。P1 设置页再开放四个任务档位，避免用户逐个配置所有 Agent：

- **快速模型**：意图识别、摘要、初步大纲。
- **默认模型**：画像、课堂对话和普通资源生成。
- **高质量模型**：正式学习单元、复杂代码和动画分镜。
- **审核模型**：ReviewAgent 独立审查；允许与生成模型不同。

高级设置允许按 Agent 覆盖，但不是 MVP 必需能力。

#### API Key 与隐私

- P0 仅支持系统托管凭据，通过服务端环境变量或密钥管理注入，不进入学生浏览器。
- P1 支持用户持久化 BYOK、会话临时 Key 和本地模型连接。
- 持久化 Key 必须使用服务端主密钥加密，API 和日志永不返回明文。
- 临时 Key 只保存在当前会话内存，任务结束或会话过期后销毁。
- 调用前向用户展示 Provider、模型、预计发送的数据类型和是否为本地服务。
- 学生画像、教材原文等敏感上下文遵循最小发送原则；日志仅记录 Provider/模型 ID、耗时、Token 和错误码。

#### 失败处理

- 请求失败时优先对同一 Provider 限次重试，不进行无限轮询。
- 切换到其他 Provider 前必须遵守用户允许的回退策略。
- 不同 Provider 的结构化输出统一转为内部 schema，失败时返回可理解的能力不兼容说明。
- Provider 不可用不影响已生成资源、课堂进度和 Job 状态。

#### 验收标准

- [ ] P0 接通一个服务端配置的 OpenAI-compatible Provider，业务模块只依赖内部接口
- [ ] 新用户无需理解或配置 Provider 即可完成端到端学习闭环
- [ ] 系统托管 API Key 不进入数据库、日志、错误响应或前端状态
- [ ] 能力不匹配、限流和 Provider 故障均返回统一错误码并支持安全重试
- [ ] P1 增加 Ollama、BYOK、连接测试、模型列表和任务档位时不需要修改 M1-M6

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
   │  │ 内部计划 → 首段讲解 → 渐进生成       │     │
   │  │ LearningUnitGenerator / Video      │     │
   │  │             ↓                      │     │
   │  │        ReviewAgent                 │     │
   │  │             ↓                      │     │
   │  │      组装 / 版本 / 学习反馈          │     │
   │  └────────────────────────────────────┘     │
   │  ┌────────────────────────────────────┐     │
   ├─→│ Classroom 子图：                    │     │
   │  │ TutorAgent 默认专注，按需互动         │     │
   │  │       ↓ P0 预设 / P1 条件触发        │     │
   │  │ Debate: Performance / Engineering / │     │
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
    plan_version: int           # 系统内部学习计划版本
    current_scene_id: str
    classroom_mode: str        # "focus" | "interactive" | "debate"
    model_routes: dict         # fast/default/quality/review 任务档位
    intermediate_results: dict # 各 Agent 输出累积
    review_history: list       # 反思链历史
    final_output: dict
    metadata: dict             # job_id、token 用量、耗时等
```

### 4.3 反思机制设计

**按风险分层反思**：

1. **生成内反思（Agent-level）**
   - 生成 Agent 输出后自评："我刚生成的内容是否覆盖了用户的易错点？"
   - 自评不通过 → 重新生成（最多 2 次）

2. **跨 Agent 反思（System-level）**
   - ReviewAgent 审查将被持久化的正式讲解、代码、练习、Manim DSL 和辩论总结
   - 审查不通过 → 退回原 Agent + 反馈具体问题点

普通课堂对话默认只执行轻量规则；命中高风险类型、需要持久化或用户要求核验时再升级到 ReviewAgent。

**辩论 Agent 内的反思**（创新点）：
- 主持人在综合三方观点时**反思每个观点的合理性**，可对极端观点提出质疑
- 体现"多智能体协商而非堆叠"

---

## 五、数据模型

### 5.1 用户表（PostgreSQL）

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE,             -- 匿名用户为空
    password_hash VARCHAR(255),            -- 匿名用户为空
    is_guest BOOLEAN DEFAULT TRUE,
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
    initial_query TEXT,
    
    professional_background JSONB,
    knowledge_base JSONB,
    cognitive_style JSONB,
    learning_goals JSONB,
    error_preferences JSONB,
    engineering_preference JSONB,
    extended_dimensions JSONB,
    evidence JSONB,             -- 字段来源、置信度和更新时间
    
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
    outline JSONB,              -- 系统内部学习计划，不要求学生编辑
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
    scene_type VARCHAR(30),   -- P0: explanation/quiz/video/code；P1: mindmap/debate
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
    job_type VARCHAR(30),       -- P0 主要为 manim；P1 扩展 tts/export 等长任务
    status VARCHAR(30),         -- queued/running/completed/failed/canceled
    stage VARCHAR(40),
    progress INT DEFAULT 0,
    idempotency_key VARCHAR(100) UNIQUE,
    error JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 5.4 知识结构（P0 YAML/PostgreSQL，P1 Neo4j）

P0 仅维护 8-10 个知识点，使用 `data/knowledge_graph.yaml` 作为版本化事实源，并在启动时载入 PostgreSQL 或内存关系结构。外部查询通过统一 Repository 接口完成，不依赖 Neo4j 方言。扩展到约 30 个以上节点并需要复杂图查询时，再迁移到以下 Neo4j 模型：

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
    evidence JSONB,           -- P0 测验/提示/反馈；P1 代码运行与更多行为
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

### 5.7 Redis 键设计（P1）

| Key 模式 | 用途 | TTL |
|---|---|---|
| `cache:llm:{hash}` | 大模型响应缓存 | 24h |
| `session:{user_id}` | 用户会话 | 7d |
| `job:{job_id}` | 学习单元 / 场景 / 视频 / 导出任务热状态 | 24h |
| `queue:video` | 视频生成队列（Celery） | - |

### 5.8 向量检索 Collection（P1）

- `kp_embeddings`：知识点描述的向量
- `resource_embeddings`：已生成资源的向量（用于相似检索）

### 5.9 Provider 连接与模型偏好（P1，PostgreSQL）

```sql
CREATE TABLE provider_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider_type VARCHAR(40),       -- openai-compatible/ollama/anthropic/...
    display_name VARCHAR(80),
    base_url VARCHAR(500),
    encrypted_api_key BYTEA,         -- 服务端主密钥加密；本地无 Key 时为空
    is_local BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    settings JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE model_preferences (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    task_profile VARCHAR(20),        -- fast/default/quality/review
    provider_connection_id UUID REFERENCES provider_connections(id),
    model_id VARCHAR(160),
    fallback_policy JSONB,
    PRIMARY KEY (user_id, task_profile)
);
```

会话临时 Key 不写入上述表；系统托管 Provider 使用独立的服务端配置和密钥管理，不与用户凭据混存。

---

## 六、技术架构

### 6.1 系统架构图

```
┌────────────────────────────────────────────────────────────────┐
│                          客户端层                                │
│  ┌─────────────────────────┐    ┌─────────────────────────┐    │
│  │  Web (Vue3 + Vite + TS)  │    │  iOS App (P2，可选)       │    │
│  │  - Naive UI              │    │  - MarkdownUI            │    │
│  │  - 轻量学习路径视图       │    │  - AVKit (视频)          │    │
│  │  - GSAP (课堂/圆桌切换)   │    │  - URLSession.bytes(SSE) │    │
│  │  - P1 Provider 设置      │    │  - 不阻塞 Web 首发       │    │
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
│  │  Profile / Path / LearningUnit / Classroom / Debate       │ │
│  │  Tutor / Assess / Review                                  │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────┬──────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                    Provider Gateway                            │
│  能力检查 │ 模型路由 │ 凭据解密 │ 重试/回退 │ 用量统计          │
└─────────────────────┬──────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                      AI 与媒体能力层                             │
│  OpenAI-compatible（P0）│ Ollama/其他 Provider（P1）           │
│  参数化 Manim 模板（P0）│ 完整 DSL / TTS / FFmpeg（P1）       │
└─────────────────────┬──────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                      数据存储层                                  │
│  PostgreSQL（P0 业务/画像/路径/Job）│ YAML 图谱 │ 本地媒体       │
│  Neo4j / Chroma / Redis（P1 按规模和需求引入）                  │
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
| 学习路径 | 简单 SVG（P0），AntV G6（P1） | P0 只展示当前、前置和下一节点 |
| Markdown | **md-editor-v3** + **KaTeX** | 公式渲染 |
| 动画 | **GSAP** | 多角色课堂与辩论圆桌模式切换 |
| 流式 | **fetch ReadableStream + EventSource (SSE)** | POST 对话流与 GET Job 事件流分别适配 |
| 构建 | **pnpm** | 单仓库性能最佳 |

#### iOS 前端（P2，可选）
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
| Web 框架 | **FastAPI** | 由锁文件固定 |
| 智能体编排 | 简单服务编排（P0），LangGraph（P1 复杂子图） | 由锁文件固定 |
| ORM | SQLAlchemy 2.0 + asyncpg | 由锁文件固定 |
| 知识结构 | YAML + PostgreSQL（P0），Neo4j（P1） | 由种子数据与锁文件固定 |
| 向量检索 | P1 再选择 Chroma 或 pgvector | 不阻塞 MVP |
| 任务队列 | PostgreSQL Job（P0），Celery + Redis（P1） | 按长任务规模引入 |
| 视频 | Manim Community | v0.18+ |
| Provider 网关 | 自定义统一接口 + httpx | 项目锁文件固定 |
| P0 模型 | 单一 OpenAI-compatible Provider | 项目锁文件固定 |
| P1 模型 | Ollama + 多 Provider | 项目锁文件固定 |
| P1 原生适配 | Anthropic / Google Gemini / 讯飞星火 | 按适配器固定版本 |
| 语音 | 可插拔 TTS / ASR Provider | 按适配器固定版本 |
| 凭据保护 | 应用层信封加密 + 服务端主密钥 | 不在数据库保存明文 |

#### 部署
- Docker + docker-compose（开发与自托管）
- 本地服务器或云服务器；本地 Provider 通过服务端白名单地址访问

### 6.3 部署架构（docker-compose.yml）

```yaml
services:
  postgres:    # 业务数据
  api:         # FastAPI
  web:         # Vue dev server / nginx 静态

  # P1 按需启用
  neo4j:       # 大规模知识图谱
  redis:       # 缓存 + Celery broker
  chroma:      # 向量库（或改用 pgvector）
  worker:      # Celery worker（完整 Manim / TTS / 导出）
```

---

## 七、API 契约

### 7.1 认证 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/auth/guest` | 创建匿名学习会话，不阻塞首次学习 |
| POST | `/api/auth/register` | 将匿名会话升级为账号并保留学习数据 |
| POST | `/api/auth/login` | 邮箱密码登录，返回 JWT |
| GET | `/api/auth/me` | 获取当前用户信息 |
| POST | `/api/auth/logout` | 登出 |

### 7.2 画像 API

| Method | Path | 描述 |
|---|---|---|
| GET | `/api/profile/me` | 获取当前画像 |
| PATCH | `/api/profile/me` | 手动修正画像 |
| GET | `/api/profile/me/history` | 画像版本历史 |
| POST | `/api/profile/events` | 记录答题、资源偏好和显式反馈，异步更新画像 |

### 7.3 学习单元生成、异步任务与导出 API

| Method | Path | 描述 |
|---|---|---|
| POST | `/api/learning-sessions` (SSE) | 输入一句学习需求，创建会话、临时画像和内部学习计划，并流式返回首段内容 |
| GET | `/api/learning-units/{id}` | 获取学生可见学习计划、场景、资源和当前进度 |
| POST | `/api/learning-units/{id}/scenes/{scene_id}/adjust` (SSE) | 更简单、更深入、换例子、重新解释或补充前置知识 |
| POST | `/api/learning-units/{id}/scenes/{scene_id}/actions` | 跳过、标记已会、切换资源或请求动画 |
| GET | `/api/resource/{id}` | 获取已生成资源 |
| GET | `/api/resource/list` | 列出我的资源（分页+筛选） |
| POST | `/api/learning-units/{id}/notes/export` | 导出 Markdown 学习笔记与错题摘要 |
| POST | `/api/learning-units/{id}/scenes/{scene_id}/animation` | 获取缓存动画或创建 Manim 渲染 Job |
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
| POST | `/api/classroom/sessions/{id}/resume` | 恢复已有互动课堂会话 |
| POST | `/api/classroom/{id}/messages` | 用户提问/回答；使用 fetch 流式返回课堂角色发言 |
| PUT | `/api/classroom/{id}/mode` | 在专注与互动模式之间切换 |
| POST | `/api/classroom/{id}/debates` | P0 启动预设多视角演示；P1 启动并行辩论 Job |
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
event: agent_start      # 生成器或 Agent 开始工作
data: {"agent": "LearningUnitGenerator", "task": "..."}

event: stage_changed    # Job/学习单元切换阶段
data: {"job_id": "...", "stage": "reviewing", "progress": 60}

event: scene_ready      # 单个场景已审核，可提前查看
data: {"scene_id": "...", "version": 2, "resource_ids": [...]}

event: classroom_action # 课堂角色或场景动作
data: {"session_id": "...", "role": "teacher_qizhi", "action": "speak"}

event: token            # 流式返回首段讲解或课堂回复
data: {"agent": "TutorAgent", "delta": "..."}

event: agent_done       # Agent 完成
data: {"agent": "LearningUnitGenerator", "result": {...}}

event: review_pass      # 正式资源审核通过
data: {"score": 0.92}

event: review_reject    # 反思拒绝
data: {"reason": "...", "retry": true}

event: progress         # 长任务进度（视频生成）
data: {"task_id": "...", "percent": 45, "stage": "rendering"}

event: error
data: {"code": "PROVIDER_RATE_LIMITED", "message": "...", "retryable": true}

event: done             # 全部完成
data: {"final": {...}}
```

### 7.8 Provider 与模型设置 API（P1）

| Method | Path | 描述 |
|---|---|---|
| GET | `/api/providers/catalog` | 获取系统支持的 Provider 类型与能力声明 |
| POST | `/api/providers/connections` | 新增用户 Provider 连接；Key 加密后存储 |
| PATCH | `/api/providers/connections/{id}` | 修改连接名称、地址、凭据或启用状态 |
| DELETE | `/api/providers/connections/{id}` | 删除连接及加密凭据 |
| POST | `/api/providers/connections/{id}/test` | 测试连通性、鉴权和基础能力 |
| GET | `/api/providers/connections/{id}/models` | 获取或刷新可用模型列表 |
| GET | `/api/model-preferences` | 获取 fast/default/quality/review 模型设置 |
| PUT | `/api/model-preferences/{task_profile}` | 设置任务档位的 Provider、模型与回退策略 |

API 响应仅返回凭据是否已配置及脱敏标识，任何接口均不得返回完整 API Key。

---

## 八、非功能需求

### 8.1 性能

| 指标 | 目标 |
|---|---|
| 一句话请求首字节响应 | P95 ≤ 2s |
| 第一段可学习内容 | P95 ≤ 10s，后续资源渐进展示 |
| 预渲染视频命中 | P95 ≤ 2s 可播放 |
| 按需 Manim 视频生成 | 目标 P95 ≤ 90s，持续推送阶段进度 |
| P0 轻量路径加载 | ≤ 500ms |
| 课堂普通发言首字节 | P95 ≤ 3s |
| 辩论三 Agent 并发首字节 | P95 ≤ 3s |
| API 普通查询 | P99 ≤ 200ms |

模型相关延迟按 Provider 和模型分别统计，上述生成指标以项目维护的基准模型与正常网络为测量条件；Provider 自身排队或限流必须在监控中单独标识。

### 8.2 防幻觉

1. **知识图谱事实约束**：核心概念、前置关系和易混关系优先以图谱为准；图谱未覆盖的事实必须由教材/RAG 依据补充
2. **分级审核**：正式讲解、代码、练习、Manim DSL 和辩论总结经过 ReviewAgent；普通对话使用轻量规则并按风险升级
3. **置信度标注**：对模型不确定的内容标注 `[需确认]` 标签
4. **RAG 增强（P1）**：基于自建知识库（教材摘录）作为生成依据
5. **敏感词过滤**：黑名单 + 二次大模型审核

### 8.3 安全

| 维度 | 措施 |
|---|---|
| 用户密码 | bcrypt + salt |
| API 鉴权 | JWT (RS256)，2h 过期，refresh token |
| 速率限制 | P0 应用中间件；P1 多实例部署改用 Redis 计数器 |
| API Key | P0 服务端环境变量/密钥管理；P1 BYOK 加密存储、响应脱敏、日志禁止记录明文 |
| 自定义 Base URL | 默认 HTTPS；阻止云端部署访问回环、链路本地和云元数据地址，防止 SSRF |
| Provider 数据最小化 | 仅发送完成当前任务所需的画像字段、教材片段和消息历史 |
| 代码生成安全 | Manim 代码沙箱化，禁用危险 API |
| SQL 注入 | SQLAlchemy 参数化查询 |
| XSS | 前端 Markdown 渲染默认转义 |
| CSRF | Token Header 模式，无 cookie |

### 8.4 可观测性

- 后端：FastAPI middleware 记录请求、Provider/模型 ID、Token 用量、Agent 调用链和 Job 阶段
- 日志：结构化 JSON（Loguru），按用户、Agent、Provider、模型和错误码查询；不记录 API Key 与完整教材/画像内容
- 运营看板：请求成功率、首字节延迟、Token/成本、Provider 限流率、Review 重试率和 Manim 渲染失败率

---

## 九、开发计划

### 9.1 阶段路线图

路线图不绑定固定比赛日期，每个阶段满足退出标准后再进入下一阶段。

| 阶段 | 主题 | 关键交付 | 退出标准 |
|---|---|---|---|
| **MVP 0.1** | 一句话进入学习 | Vue/FastAPI/PostgreSQL、单一 OpenAI-compatible Provider、临时画像、讲解/代码/练习、流式首屏 | 输入一句话后 10 秒内看到首段内容，并能完成一个知识点学习 |
| **MVP 0.2** | 学习闭环 | 8-10 节点知识结构、渐进画像、测验评分、掌握度和可解释下一步推荐、正式资源审核 | 用户完成“输入→学习→练习→掌握度更新→下一步推荐” |
| **MVP 0.3** | 核心差异化 | 2-3 个 Manim 预渲染/参数化模板、专注/互动模式、数组 vs 链表多视角演示、Markdown 笔记 | 动画和多视角能力可用，但不阻塞普通学习链路 |
| **Phase 1** | 产品化基础 | Ollama/BYOK、多 Provider、持久化队列、完整 Manim DSL、约 30 节点图谱、Neo4j（如有必要） | 更多模型与动态动画接入不改变业务模块，长任务可恢复 |
| **Phase 2** | 深度学习体验 | 真并行辩论、更多角色策略、RAG、学习报告、更多课程 | 达到 §十发布标准并完成小规模真实用户测试 |
| **Phase 3** | 扩展能力 | iOS、PPTX/离线 HTML、更多课程、模板市场 | 由真实使用数据决定，不阻塞 Web 产品迭代 |

### 9.2 P0 MVP 任务

#### 工程与模型层

- [ ] FastAPI、Vue 3、PostgreSQL 的可复现开发环境
- [ ] Provider Gateway 最小接口、统一错误码和流式适配
- [ ] 一个由服务端配置的 OpenAI-compatible Provider
- [ ] 系统托管凭据不进入浏览器、数据库和日志
- [ ] Manim Job 使用 PostgreSQL 保存状态并支持查询、取消和重试

#### 核心学习闭环

- [ ] 一句话建立临时画像并立即开始学习
- [ ] 学习行为渐进更新画像，字段包含证据与置信度
- [ ] 8-10 节点 YAML/PostgreSQL 知识结构与轻量路径视图
- [ ] LearningUnitGenerator 生成讲解、单语言代码和 3 道左右练习
- [ ] 正式资源 ReviewAgent；普通对话轻量审核
- [ ] 测验结果更新掌握度并触发下一步推荐

#### 互动与多模态

- [ ] TutorAgent 默认专注模式，学生可切换按需互动模式
- [ ] “数组 vs 链表”单次结构化多视角演示
- [ ] 2-3 个链表类 Manim 预渲染/参数化模板与缓存
- [ ] Markdown 学习笔记、已生成 MP4/SRT 导出

### 9.3 工程工作流

1. 每项功能从用户故事和验收标准开始，拆分为可独立验证的任务。
2. API、数据模型或安全边界变化必须先写 ADR，再修改实现。
3. 每次提交运行对应单元测试；合并前运行类型检查、Lint 和关键 E2E。
4. Prompt、模型能力映射和 Review 规则均版本化，生成结果记录所用版本。
5. 每个阶段维护变更日志、部署说明和已知限制，不为文档页数设置目标。

| 文件 | 用途 |
|---|---|
| `docs/PRD.md` | 产品目标、范围和验收标准 |
| `docs/ARCHITECTURE.md` | 系统边界、数据流和组件关系 |
| `docs/ADR/*.md` | 架构决策及替代方案 |
| `docs/api/openapi.yaml` | API 契约 |
| `docs/agents/prompts/*.md` | Agent Prompt 与输出 schema |
| `docs/PROVIDERS.md` | Provider 接入、能力映射和安全说明 |
| `docs/ROADMAP.md` | 迭代任务、负责人和状态 |
| `docs/CHANGELOG.md` | 用户可见变化 |

### 9.4 风险与应对

| 风险 | 概率 | 应对 |
|---|---|---|
| Provider 接口差异大 | 高 | P0 只实现一个 OpenAI-compatible Provider；业务层只依赖内部 schema |
| API Key 泄漏 | 中 | P0 使用服务端托管凭据与日志脱敏；P1 BYOK 使用信封加密和删除能力 |
| 自定义 Base URL 引入 SSRF | 中 | HTTPS 默认、地址解析校验、云元数据/内网阻断、管理员白名单 |
| 模型输出质量差异大 | 高 | 能力注册、结构化校验、独立 Review 模型、基准测试集 |
| Manim 渲染超时或代码风险 | 高 | P0 仅使用预渲染/参数化模板；P1 才开放完整 DSL 和隔离渲染 |
| 知识结构不完整 | 中 | P0 人工审核 8-10 个种子节点和关系，逐步扩展 |
| 多角色输出冗余和成本过高 | 高 | 默认专注模式；其他角色按需出现；真并行辩论延后到 P1 |
| 功能范围持续膨胀 | 高 | 严格执行 P0/P1/P2，iOS 和高级导出不阻塞 Web MVP |

---

## 十、产品指标与发布标准

以下数值是 MVP 初始目标，需要在真实用户测试后校准，不能通过测试数据造高指标。

### 10.1 激活与完成

| 指标 | MVP 目标 |
|---|---|
| 一句话请求后成功进入学习的比例 | ≥ 80% |
| 输入学习需求到看到首段内容的 P95 | ≤ 10 秒 |
| 推荐路径后开始首个知识点的比例 | ≥ 60% |
| 已开始学习单元的完成率 | ≥ 50% |

### 10.2 质量与可靠性

| 指标 | MVP 目标 |
|---|---|
| 结构化输出 schema 通过率 | ≥ 98% |
| 基准错误集上的 ReviewAgent 严重错误召回率 | ≥ 90% |
| 正式讲解/代码/练习生成成功率 | ≥ 95% |
| 预渲染/参数化 Manim 模板可用率 | ≥ 98% |
| SSE 断线后可恢复率 | ≥ 99% |
| API Key 明文泄漏 | 0 起事件 |

### 10.3 学习效果与用户价值

| 指标 | 测量方式 |
|---|---|
| 掌握度提升 | 同一知识点学习前后测验对比 |
| 路径解释有效性 | 用户是否理解并接受推荐理由 |
| 资源有用性 | 文档、代码、动画、辩论的单项反馈 |
| 个性化感知 | 用户是否认为难度、示例和节奏符合自身情况 |
| 重新解释有效性 | 用户要求换例子或降难度后是否继续学习并答对练习 |
| 次周留存 | 用户是否回来继续路径中的下一知识点 |

### 10.4 Web MVP 发布门槛

- [ ] 新用户无需阅读开发文档即可完成核心用户旅程
- [ ] 单一 OpenAI-compatible 系统默认模型可完成一次端到端学习闭环
- [ ] 用户输入一句话即可开始，画像和内部大纲均不构成前置步骤
- [ ] 画像、路径、学习单元、课堂进度和 Job 在服务重启后可恢复
- [ ] 正式学习资源经过 schema 和 ReviewAgent；普通对话通过轻量规则并可按风险升级
- [ ] 2-3 个 Manim 预渲染/参数化模板稳定可用，不执行模型生成的任意 Python
- [ ] 专注模式、学习控制、Provider 失败、SSE 重连和重新解释具有自动化测试
- [ ] README、部署说明、安全说明和已知限制完整

---

## 附录 A：项目目录结构

```
EduMind-Agent/
├── docs/
│   ├── PRD.md                    ← 本文档
│   ├── ARCHITECTURE.md
│   ├── ADR/
│   ├── api/openapi.yaml
│   ├── agents/prompts/
│   ├── PROVIDERS.md
│   ├── ROADMAP.md
│   └── CHANGELOG.md
├── backend/
│   ├── app/
│   │   ├── api/                  ← FastAPI 路由
│   │   ├── agents/               ← LangGraph Agent
│   │   ├── models/               ← SQLAlchemy
│   │   ├── services/             ← 业务逻辑与 Provider Gateway
│   │   ├── core/                 ← 配置/JWT/中间件
│   │   └── workers/              ← P1 Celery + 完整 Manim Worker
│   ├── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── web/
│   ├── src/
│   │   ├── views/
│   │   ├── components/
│   │   ├── stores/               ← Pinia
│   │   ├── api/                  ← fetch + SSE 封装
│   │   └── composables/
│   ├── package.json
│   └── vite.config.ts
├── ios/
│   └── EduMindAgent/             ← P2 SwiftUI 客户端
├── data/
│   ├── knowledge_graph.yaml      ← P0 8-10 节点种子，可渐进扩展
│   ├── videos/cache/             ← 预渲染动画
│   └── seeds/                    ← 测试与基准画像数据
├── docker-compose.yml
├── .env.example
└── README.md
```

## 附录 B：知识结构路线图

### P0 种子节点（10 个）

1. C 指针（c-pointer）
2. 数组（array）
3. 链表概念（linked-list-concept）
4. 单链表（single-linked-list）
5. 链表遍历（linked-list-traversal）
6. 链表插入（linked-list-insertion）
7. 链表删除（linked-list-deletion）
8. 栈（stack）
9. 队列（queue）
10. 循环队列（circular-queue）

P0 只要求这组节点形成可学习闭环，不要求使用 Neo4j。每个节点必须包含前置关系、学习目标、常见误区、讲解依据和掌握度计算规则。

### P1 扩展候选

- 双向链表、循环链表、顺序栈、链栈
- 树的基本概念、二叉树、遍历、二叉搜索树、平衡二叉树
- 冒泡、选择、插入、快速、归并、堆排序及排序算法对比
- 图的表示、BFS、DFS 及更多课程节点

### 关键 SIMILAR_TO 关系（辩论场景预设）
- 数组 ↔ 单链表（"链表 vs 数组"）
- 顺序栈 ↔ 链栈（"实现选择"）
- 邻接矩阵 ↔ 邻接表（图章节扩展）
- 快排 ↔ 归并排序（"原地 vs 稳定"）
- 递归遍历 ↔ 迭代遍历（"递归 vs 迭代"）

---

## 附录 C：基准用户“小李”的种子画像

```json
{
  "user_id": "benchmark-xiaoli",
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
