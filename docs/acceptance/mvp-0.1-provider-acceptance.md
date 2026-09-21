# MVP 0.1 真实 Provider 与退出验收

日期：2026-09-21（Asia/Shanghai）

状态：**通过**。MVP 0.1 的服务端默认模型为 `deepseek-flash`，通过 DeepSeek Responses API 完成匿名学习、临时首段、审核后的讲解/代码/练习发布和浏览器交互。

## 环境与安全边界

- 环境：macOS + OrbStack；Docker Compose 中运行 PostgreSQL、FastAPI API 和 Vue Web。
- Provider：DeepSeek `POST /responses`；模型标识：`deepseek-flash`。
- P0 策略：`reasoning.effort=none`；未指定的输出上限为 4096；未指定的结构化生成温度为 0.0。
- 凭据：仅从权限为 `600`、被 Git 忽略的根目录 `.env` 注入。所有证据均未输出 API Key、Base URL、Cookie 或模型正文。
- 首段计时入口：本机 API `POST /api/learning-sessions`，包含匿名 Cookie、CSRF、画像和 SSE，而非直接 Provider 延迟。

## 最终结果

| 项目 | 结果 | 脱敏证据 |
|---|---:|---|
| DeepSeek JSON Schema 探针 | 通过 | `/responses` 返回本地 Schema-valid 对象 |
| API 完整知识点学习 | 通过 | 首段 4680 ms；总流程 21122 ms；讲解、代码、练习共 3 项发布 |
| 真实浏览器主链路 | 通过 | 临时首段、审核正式资源、代码与练习标签均可见 |
| 首段性能样本 | 20/20 成功 | 失败率 0%；P50 3002 ms；P95 4199 ms；最大 4689 ms |
| PRD 首段 P95 ≤ 10 秒 | 通过 | 最近秩 P95 为 4199 ms |

20 个首段样本（毫秒）：

```text
3491, 3024, 2877, 4689, 4199, 3043, 3229, 2929, 2907, 2989,
3008, 2452, 3140, 2679, 3226, 4164, 2618, 2904, 2732, 2995
```

## 可复现命令

该命令会调用真实模型，必须显式确认可能产生费用；它输出的仅是脱敏汇总。

```bash
cd backend
uv run --python 3.11 python tests/manual_provider_acceptance.py \
  --samples 20 \
  --confirm-billable
```

真实浏览器验收使用无头 Chromium 访问 `http://127.0.0.1:5173`，从“学习目标”输入开始，确认临时首段、`published` 状态和三类已发布资源。Vite 代理保留浏览器 Host，因此后端在不放宽 Origin 校验的情况下接受同源匿名 Cookie 会话。

## 退出审计与已知限制

- 任务账本中的 MVP 0.1 可执行任务均已完成提交；T035 为最终真实验收，T035-2/T035-3/T035-4 是其 DeepSeek 协议、延迟和稳定性依赖。
- Mock 浏览器 E2E 与真实 Provider 验收明确分离：前者覆盖可重复的故障分支，后者证明当前默认模型的真实闭环和性能。
- 20 样本仅代表本机、当前 DeepSeek 配置与网络条件，不能替代生产监控或真实用户样本；Provider/模型/提示词策略变更后应重新采样。
- P1 的 BYOK、多 Provider、Ollama、异步队列和更深的模型策略仍不在 MVP 0.1 范围内。
