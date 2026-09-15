# OpenMAIC — 架构设计

## 整体架构

OpenMAIC 是一个 **Next.js 单体应用**，没有独立的 Python 后端。所有逻辑（API 路由、Agent 编排、LLM 调用、文件存储）都在 Next.js 服务端完成。

```
┌─────────────────────────────────────────────────┐
│                   nginx (8927)                    │
│                 反向代理 / 入口                    │
└─────────────┬───────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────┐
│              Next.js Server (3000)                │
│                                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ App Router│ │ API Routes│ │ Server Components│ │
│  │ (页面)    │ │ (25+ 端点)│ │ (RSC)            │ │
│  └──────────┘ └────┬─────┘ └──────────────────┘ │
│                     │                              │
│  ┌──────────────────▼──────────────────────────┐ │
│  │          LangGraph Agent 编排层              │ │
│  │  scene-outlines → scene-content → actions   │ │
│  │  → agent-profiles → assembly               │ │
│  └──────────────────┬──────────────────────────┘ │
│                     │                              │
│  ┌──────────────────▼──────────────────────────┐ │
│  │              核心 Packages                   │ │
│  │  @maic/dsl (幻灯片DSL)                       │ │
│  │  @maic/renderer (幻灯片渲染)                  │ │
│  │  @maic/importer (PPTX 导入/导出)              │ │
│  │  pptxgenjs (PPTX 生成)                       │ │
│  │  mathml2omml (数学公式)                      │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## 目录结构

```
OpenMAIC/
├── app/                          # Next.js App Router
│   ├── api/                      # API 路由
│   │   ├── chat/route.ts         # 课堂聊天 (SSE)
│   │   ├── generate-classroom/   # 课堂生成 (异步 Job)
│   │   ├── generate/             # 各类生成子路由
│   │   │   ├── scene-outlines-stream/  # 场景大纲 (流式)
│   │   │   ├── scene-content/          # 场景内容
│   │   │   ├── scene-actions/          # 场景动作
│   │   │   ├── agent-profiles/         # Agent 画像
│   │   │   ├── tts/                    # TTS 语音
│   │   │   ├── image/                  # 图片生成
│   │   │   └── video/                  # 视频生成
│   │   ├── quiz-grade/           # 测验评分
│   │   ├── pbl/chat/             # PBL 聊天
│   │   ├── web-search/           # 网络搜索
│   │   └── parse-pdf/            # PDF 解析
│   ├── classroom/[id]/page.tsx   # 课堂页面
│   └── generation-preview/       # 生成预览页
├── packages/
│   ├── @maic/dsl/                # 幻灯片领域语言
│   │   └── src/
│   │       ├── index.ts          # DSL 入口
│   │       ├── slides.ts         # 幻灯片数据结构
│   │       ├── stage.ts          # 舞台/场景
│   │       ├── guards.ts         # 类型守卫
│   │       └── version.ts        # 版本管理
│   ├── @maic/renderer/           # 幻灯片渲染引擎
│   ├── @maic/importer/           # PPTX 导入器
│   ├── pptxgenjs/                # PPTX 生成 (fork)
│   └── mathml2omml/              # MathML 转换
├── components/                   # React 组件
│   ├── agent/                    # Agent 相关 (头像/配置/栏)
│   ├── ai-elements/              # AI UI 元素 (30+)
│   ├── canvas/                   # 白板画布
│   ├── chat/                     # 聊天区域
│   ├── edit/                     # MAIC Editor (v0)
│   └── ...                       # 更多 UI 组件
├── lib/                          # 核心库
│   └── server/                   # 服务端逻辑
│       ├── classroom-generation/ # 课堂生成核心
│       ├── classroom-job-runner/ # 异步 Job 执行
│       ├── classroom-job-store/  # Job 状态存储
│       └── classroom-storage/    # 课堂数据存储
├── configs/                      # 配置文件
│   └── server-providers.yml      # LLM Provider 配置
├── skills/openmaic/              # OpenClaw Skill 定义
│   ├── SKILL.md                  # 主 Skill 文件
│   └── references/               # 分步参考
│       ├── clone.md
│       ├── startup-modes.md
│       ├── provider-keys.md
│       ├── generate-flow.md
│       └── hosted-mode.md
├── docker-compose.yml
└── package.json                  # pnpm workspace
```

## 课堂生成 Pipeline

这是 OpenMAIC 的核心流程，从用户输入到生成完整课堂：

```
POST /api/generate-classroom
  │
  ▼
┌──────────────────┐
│ 1. Job 创建       │ ← nanoid 生成 jobId, 返回 pollUrl
│    状态: queued    │
└────────┬─────────┘
         │ after() 异步执行
         ▼
┌──────────────────┐
│ 2. 场景大纲生成    │ → POST /api/generate/scene-outlines-stream
│    (流式 SSE)     │   LLM: 根据 requirement 生成场景大纲
│    状态: running   │   输出: [{type: "slides"|"quiz"|"interactive"|"pbl"}]
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 3. 场景内容生成    │ → POST /api/generate/scene-content
│    每个场景独立生成 │   LLM: 为每个场景生成具体内容
│    可并行          │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 4. Agent 画像生成  │ → POST /api/generate/agent-profiles
│    (可选)         │   LLM: 生成 AI 教师/同学的角色设定
│    agentMode:     │   输出: [{name, role, personality, avatar}]
│    "generate"     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 5. 场景动作生成    │ → POST /api/generate/scene-actions
│    (白板/语音)    │   LLM: 为每页生成 agent 动作
│                    │   (讲解词、白板绘图、讨论触发)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 6. 课堂组装       │ → 将各场景 + Agent 画像 + 动作合并
│    status:        │   保存为课堂数据
│    succeeded      │   返回 classroomId + URL
└──────────────────┘
```

### Job 轮询机制

- `POST /api/generate-classroom` → `{ jobId, pollUrl, pollIntervalMs: 5000 }`
- `GET /api/generate-classroom/:jobId` → `{ status: "queued"|"running"|"succeeded"|"failed", step, result? }`
- 推荐轮询间隔: 60 秒（保守），避免频繁请求

## LangGraph 编排

OpenMAIC 使用 LangGraph 管理课堂生成的 Agent 流程。关键特点：

1. **状态图 (StateGraph)**: 定义生成流程的有向图，节点是生成步骤，边是依赖关系
2. **并行执行**: 多个独立场景可以并行生成内容
3. **条件分支**: 根据输入类型（纯需求 vs PDF）和 Agent 模式选择不同路径

## 数据存储

- **课堂数据**: 文件系统（`classroom-storage`）
- **Job 状态**: 内存 Map（`classroom-job-store`，重启丢失）
- **上传文件**: 本地 `uploads/`
- **无需数据库**: 整个系统无状态运行
