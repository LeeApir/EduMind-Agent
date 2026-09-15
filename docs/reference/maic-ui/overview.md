# MAIC-UI — 项目概览

> Making Interactive Courseware with Generative UI
>
> 仓库: https://github.com/THU-MAIC/MAIC-UI
> 论文: arxiv:2604.25806
> 定位: AI 驱动的交互式教学界面生成系统

## 一句话定位

**将 PDF 教材转化为可操作、可交互、可反馈的个性化学习网站——不只是生成内容，更生成学习过程。**

## 核心价值

| 维度 | 说明 |
|------|------|
| 从内容到交互 | 不止生成静态课件，还生成学习过程中的交互界面 |
| 降低制作门槛 | 教师无需编程/设计技能即可生产教学资源 |
| 真实课堂验证 | 53 名高中生 3 个月课堂部署，提升学习主动性 |
| 多模态学习 | 沉浸式文本、幻灯片+旁白、音频对话、思维导图、测验评估 |
| 稳定可落地 | 面向课堂稳定性设计，非 demo 原型 |

## 技术栈

| 层次 | 选型 |
|------|------|
| 前端 | Next.js 14 + React 18 + TypeScript + Tailwind CSS |
| 后端 | Python 3 + FastAPI + SQLAlchemy 2.0 |
| 数据库 | SQLite (开发) / PostgreSQL (生产) |
| AI 集成 | 智谱 GLM / Anthropic Claude / OpenAI (可切换) |
| PDF 处理 | PyPDF2 + pdfplumber |
| 部署 | Docker + docker-compose + nginx |

## 五个学习模态

```
PDF 上传 → 内容分析 → 个性化 → 多模态生成

模态 1: 沉浸式文本 (Immersive Text)
  - 交互式课本，嵌入测验 + AI 插图

模态 2: 幻灯片 + 旁白 (Slides & Narration)
  - 演示风格 + AI 语音旁白

模态 3: 音频课程 (Audio Lessons)
  - 模拟师生对话 + 口语化讲解

模态 4: 思维导图 (Mind Maps)
  - 层级知识可视化 + 可展开节点

模态 5: 测验评估 (Assessments)
  - Bloom 分类法 + 多题型 + 进度跟踪
```

## 与 EduMind 的关联

**中度相关。** MAIC-UI 的后端架构（FastAPI 分层）和教育场景的 AI 生成模式对 EduMind 有直接参考价值。但其核心是"PDF → 网站转换"，而 EduMind 是"知识图谱驱动的个性化学习路径"——定位不同，可借鉴但不可复制。

## 关键差异

| 维度 | MAIC-UI | EduMind |
|------|---------|---------|
| 输入 | PDF 教材 | 知识图谱节点 + 对话画像 |
| 输出 | 交互式网页 | 5 类资源 + 学习路径 |
| 用户 | 教师 + 学生 | 学生为主 |
| Agent | 无显式多 Agent | 8 Agent + LangGraph |
| 知识图谱 | 无 | Neo4j 核心组件 |
