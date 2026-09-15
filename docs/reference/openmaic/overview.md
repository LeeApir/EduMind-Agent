# OpenMAIC — 项目概览

> Open Multi-Agent Interactive Classroom
>
> 仓库: https://github.com/THU-MAIC/OpenMAIC
> 论文: JCST'26 (10.1007/s11390-025-6000-0)
> 许可证: MIT | 最新版本: v0.2.2 (2026-06-02)

## 一句话定位

**输入一个主题或文档 → AI 自动生成一堂由多个 AI 角色（教师 + 同学）共同完成的互动课堂。**

## 核心价值

| 维度 | 说明 |
|------|------|
| 内容生成 | 主题/PDF → 幻灯片 + 测验 + 交互模拟 + PBL 活动 |
| 多智能体 | AI 教师 + AI 同学实时授课、讨论、互动 |
| 交互方式 | 语音讲解 (TTS) + 白板绘图 + 实时对话 |
| 导出 | 可编辑 .pptx 幻灯片 + 交互式 .html 页面 |
| 分发 | OpenClaw 集成，飞书/Slack/Telegram 直接生成 |

## 技术栈

| 层次 | 选型 |
|------|------|
| 框架 | Next.js 16 (App Router) |
| UI | React 19 + Tailwind CSS 4 |
| 语言 | TypeScript 5 |
| Agent 编排 | LangGraph 1.1 |
| 部署 | Vercel (一键) / Docker / 自托管 |
| 包管理 | pnpm (monorepo) |
| AI 模型 | 多 Provider 可切换（OpenAI / Anthropic / Gemini / DeepSeek / Qwen / Kimi / MiniMax / Grok / Ollama 等） |

## 项目活跃度

- 首次发布: 2026-03-26 (v0.1.0)
- 迭代速度: 约 2-3 周一个版本
- v0.2.0: 深度交互模式（3D可视化、模拟实验、游戏、思维导图、在线编程）
- v0.2.1: VoxCPM2 TTS 音色克隆、多模型支持
- v0.2.2: MAIC Editor 专业模式、离线导出、新搜索 Provider

## 与 EduMind 的关联

**高度相关。** 两者都是"多智能体 + 教育场景"的 LangGraph 编排系统。OpenMAIC 验证了这条技术路线，其 Agent 设计模式、课件生成 Pipeline、交互内容 DSL 都可以直接参考。
