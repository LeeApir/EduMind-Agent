# MVP 0.1 真实 Provider 验收

日期：2026-09-21（Asia/Shanghai）

状态：**阻塞**。真实流式调用和首段性能达标，但当前模型无法完成正式资源所需的严格结构化输出，因此不能宣称 MVP 0.1 退出验收完成。

## 环境与安全边界

- 环境：macOS + OrbStack，Docker Compose 中运行 PostgreSQL、FastAPI API 和 Vue Web。
- Provider：服务端配置的 OpenAI-compatible 接口。
- 模型标识：`deepseek-flash`。
- 凭据：仅从被 Git 忽略且权限为 `600` 的根目录 `.env` 注入；报告和命令输出均未包含 API Key、Base URL 或模型响应正文。
- 测量入口：本机 API `POST /api/learning-sessions`，包含匿名 Cookie、CSRF、画像生成和 SSE 首段链路，而非直接 Provider 延迟。

## 结果

| 项目 | 结果 | 证据 |
|---|---:|---|
| 最小真实流式连通 | 通过 | 首个非空块 1637 ms；最多 8 个输出 token |
| 完整知识点学习 | 失败 | 最终未发布；讲解、代码、练习三类结构化生成均失败 |
| 严格结构化能力探针 | 失败 | `response_format.type=json_schema`、`strict=true` 返回 `CAPABILITY_UNAVAILABLE` |
| 首段性能样本 | 20/20 成功 | 失败率 0%；P50 4922 ms；P95 6968 ms；最大 7405 ms |
| PRD 首段 P95 ≤ 10 秒 | 通过 | 最近秩 P95 为 6968 ms |

20 个首段样本（毫秒）：

```text
3806, 4152, 5894, 5068, 4850, 4147, 5915, 5939, 4250, 7405,
4862, 6923, 4136, 4893, 6227, 4624, 6968, 4950, 5627, 4344
```

## 可复现命令

以下脚本必须显式确认可能产生费用，且只输出脱敏汇总：

```bash
cd backend
uv run --python 3.11 python tests/manual_provider_acceptance.py \
  --samples 20 \
  --confirm-billable
```

结构化能力探针使用与应用相同的 `ProviderGateway`，只记录成功布尔值或标准化 `ProviderErrorCode`；本次结果为 `CAPABILITY_UNAVAILABLE`。

## 阻塞与恢复条件

`docs/PROVIDERS.md` 将 OpenAI Chat Completions 的严格 JSON Schema 响应格式定义为 P0 适配器契约，正式学习资源还必须经过本地 schema 校验和 ReviewAgent。不能用提示词要求普通 JSON 来替代该能力并宣称验收通过。

恢复 T035 前，应将服务端模型配置改为支持 OpenAI `response_format: {type: "json_schema", json_schema: {strict: true, ...}}` 的模型，然后强制重建 API/Web，并重新执行：

1. 最小严格结构化能力探针；
2. 一次完整知识点学习，确认讲解、代码和约三道练习均发布；
3. 真实浏览器主链路；
4. 如模型或 Provider 发生变化，重新采集 20 个首段样本，因为当前性能结果只适用于 `deepseek-flash`。
