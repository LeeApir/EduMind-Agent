# MAIC-UI — 架构设计

## 整体架构

MAIC-UI 采用 **前后端分离** 架构，通过 Docker Compose 编排三个服务：

```
┌─────────────────────────────────────────────────┐
│                nginx (8927)                       │
│              反向代理 / 统一入口                    │
└──────┬──────────────────────────┬───────────────┘
       │                          │
┌──────▼──────┐          ┌───────▼────────┐
│  Frontend    │          │   Backend       │
│  Next.js     │  ←──→   │   FastAPI       │
│  Port: 3000  │   API    │   Port: 8000    │
└──────────────┘          └───────┬────────┘
                                  │
                           ┌──────▼────────┐
                           │   Database     │
                           │ SQLite / PG    │
                           └───────────────┘
```

## 后端架构 (FastAPI)

```
backend/
├── main.py                        # FastAPI 应用入口 + CORS 配置
├── requirements.txt               # Python 依赖
├── init_db.sql                    # 数据库初始化 SQL
├── migrations/                    # 数据库迁移脚本
│   ├── add_ppt_versions.sql
│   ├── add_template_options_to_ppt.py
│   ├── add_version_fields.py
│   ├── create_demo_templates.py
│   ├── remove_parent_add_user_prompt.py
│   ├── remove_version_label.py
│   └── seed_templates.py
└── src/
    ├── api/                       # API 路由层 (FastAPI Router)
    │   ├── auth.py                # 认证 (框架存在，实现未完成)
    │   ├── content.py             # 内容管理 + 个性化
    │   ├── assessments.py         # 测验生成 + 评分
    │   ├── pdf_processing.py      # PDF 上传 → 解析
    │   ├── pdf_editing.py         # PDF 编辑
    │   ├── ppt_processing.py      # PPT 生成/处理
    │   ├── ppt_editing.py         # PPT 编辑
    │   └── demo_templates.py      # 模板管理
    ├── services/                  # 业务逻辑层
    │   ├── ai_processor.py        # AI 调用统一接口
    │   ├── editor_processor.py    # 编辑器后端
    │   ├── ppt_processor.py       # PPT 处理
    │   ├── read.py                # 阅读服务
    │   ├── modify.py              # 修改服务
    │   ├── template_registry.py   # 模板注册
    │   ├── template_customizer.py # 模板定制
    │   ├── prompts/               # Prompt 模板
    │   │   └── ai_prompts.py      # 集中管理的 Prompt 字符串
    │   ├── html_generation/       # HTML 生成子系统
    │   │   ├── base_generator.py  # 生成器基类
    │   │   ├── fast_generator.py  # 快速模式 (~30s)
    │   │   ├── heavy_generator.py # 重模式 (~2-3min, 2阶段)
    │   │   ├── cache.py           # 生成结果缓存
    │   │   └── components/        # HTML 组件
    │   │       ├── interactive_components.py
    │   │       ├── layout_components.py
    │   │       ├── visual_components.py
    │   │       └── themes.py
    │   ├── templates/             # 模板
    │   │   └── heavy_mode_prompts.py  # 重模式 Prompt 模板
    │   └── validators/            # 验证器
    │       ├── content_validator.py
    │       ├── html_validator.py
    │       └── sim_validator.py
    ├── models/                    # 数据模型层 (SQLAlchemy ORM)
    │   ├── user.py
    │   ├── document.py
    │   ├── content_section.py
    │   ├── personalized_content.py
    │   ├── learning_progress.py
    │   ├── ppt_document.py
    │   └── demo_template.py
    └── core/                      # 核心配置
        ├── database.py            # DB 连接 + Session 管理
        └── security.py            # JWT 安全
```

## API 端点总览

### PDF 处理
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/pdf/upload` | 上传 PDF → 处理 |
| GET | `/api/pdf/documents` | 获取文档列表 |
| GET | `/api/pdf/documents/{id}` | 获取文档详情 |
| GET | `/api/pdf/documents/{id}/processing-status` | 查询处理状态 |
| DELETE | `/api/pdf/documents/{id}` | 删除文档 |

### 内容管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/content/sections` | 获取内容段 |
| GET | `/api/content/sections/{id}` | 获取特定段 |
| POST | `/api/content/personalize` | 个性化内容生成 |
| GET | `/api/content/personalized/{id}/{mode}` | 获取个性化内容 |
| GET | `/api/content/search` | 搜索内容 |

### 测验评估
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/assessments/generate` | 生成测验 |
| POST | `/api/assessments/submit` | 提交作答 |
| GET | `/api/assessments/progress` | 学习进度 |
| GET | `/api/assessments/feedback/{id}` | 测验反馈 |

## 生成器模式: Fast vs Heavy

```
                    ┌─────────────────┐
                    │  用户请求生成    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  选择生成模式    │
                    └───┬─────────┬───┘
                        │         │
              ┌─────────▼─┐  ┌───▼──────────┐
              │ Fast Mode  │  │ Heavy Mode    │
              │ (~30s)     │  │ (~2-3 min)    │
              ├───────────┤  ├──────────────┤
              │ one-shot   │  │ 2-stage       │
              │ 单次 LLM   │  │ pipeline      │
              │ 调用       │  │ + 验证 + 精修 │
              └─────┬─────┘  └───┬──────────┘
                    │             │
              ┌─────▼─────┐  ┌───▼──────────┐
              │ HTML 输出  │  │ Stage 1:      │
              │ + 元数据   │  │ 内容对齐模拟  │
              │ + 交互元素 │  │ Stage 2:      │
              └───────────┘  │ 布局精修      │
                             │ 每阶段 3 次   │
                             │ 重试机会      │
                             └──────────────┘
```

### Fast Generator 特点
- 一次 LLM 调用直接生成完整 HTML
- 适合简单内容、快速预览
- 失败时降级到 fallback 模板

### Heavy Generator 特点
- **阶段 1**: 程序性概念提取 → 左侧过程展示 + 右侧交互模拟
- **阶段 2**: 布局优化、视觉美化、功能验证
- 每阶段有 3 次精修机会
- 阶段失败自动降级/回退
- 生成结果缓存

## 数据流

```
1. 用户上传 PDF
   POST /api/pdf/upload
   → PyPDF2/pdfplumber 提取文本
   → 识别章节/概念/学习目标
   → 存储到 Documents + ContentSections 表

2. 内容分析
   AI Processor → LLM 分析
   → 提取 key_concepts, learning_objectives, procedural_concepts

3. 个性化
   POST /api/content/personalize
   → 根据年级/兴趣/学习风格调整内容
   → 存储到 PersonalizedContent 表

4. HTML 生成 (Fast or Heavy)
   → 生成交互式学习网站
   → 嵌入测验、交互模拟、进度跟踪

5. 学习追踪
   LearningProgress 记录
   → 学习时间、测验分数、完成状态
```

## 数据库关系

```
Users (1) ──→ (N) Documents
Users (1) ──→ (N) PersonalizedContent
Users (1) ──→ (N) LearningProgress
Documents (1) ──→ (N) ContentSections
ContentSections (1) ──→ (N) PersonalizedContent
```
