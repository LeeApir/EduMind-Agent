# Provider Gateway（MVP 0.1）

PRD §3.8 是产品范围来源。P0 只连接一个由服务端配置的 OpenAI-compatible Provider；本文件定义业务代码和网络适配器之间的内部契约，不开放 BYOK、模型选择页或自动跨厂商回退。

## 内部调用边界

业务服务只依赖 `backend/app/services/provider_gateway.py` 中的 `ProviderGateway`、请求/结果类型与 `ProviderError`，不得直接导入厂商 SDK 或处理厂商响应格式。`ProviderAdapter` 是可替换的单次调用边界；T012 只提供该接口和测试替身，后续任务实现具体适配器。

| 方法 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `generate_text` | `TextRequest` | `TextResult` | 非流式文本生成 |
| `generate_structured` | `StructuredRequest`（含 JSON Schema） | `StructuredResult` | 结构化 JSON 输出；适配器须校验形状，不满足则报 `INVALID_OUTPUT` |
| `stream_text` | `TextRequest` | `AsyncIterator[TextDelta]` | 增量文本；应用层负责 SSE 事件、审核状态与取消 |

`TaskProfile` 保留 fast/default/quality/review 四个内部档位。P0 可以全部映射到同一个系统模型；业务请求不传 Provider URL、模型 ID 或 API Key。请求只包含必要的消息、输出上限和采样参数；模型 ID 与 token 用量只在结果元数据中返回，以供服务端诊断。正式资源仍须按 PRD 经过业务 schema 校验和 ReviewAgent，结构化适配器校验不能替代审核。

## 错误与重试责任

适配器将厂商错误转换为稳定的 `ProviderErrorCode`，只抛出安全的固定文案；原始响应、凭据、完整学生画像和消息正文不得进入异常或日志。`RATE_LIMITED`、`TEMPORARILY_UNAVAILABLE`、`TIMEOUT` 标记为可重试；配置/鉴权/能力缺失和无效结构化输出不可作为通用网络重试。限流可附带 `retry_after_seconds`。

Gateway 与 Adapter **每次调用只尝试一次**，均不自行重试或切换 Provider。上层编排依据幂等性、阶段状态和预算决定是否在同一 Provider 上限次重试；流已经输出文本后不得在同一流里静默重新生成。P0 不做跨 Provider 回退。Provider 故障不能删除已发布资源或覆盖学习进度。

后续实现仍需完成 Base URL/目标地址 SSRF 校验、超时与限流映射、网络连接关闭、真实 Provider 验证。测试替身只证明接口可替换，不代表真实供应商连通性。

## 服务端配置组装

生产生成路径通过 `backend/app/core/provider_factory.py` 的 `build_server_provider_gateway` 组装适配器。它在调用适配器工厂前读取 `EDUMIND_PROVIDER_BASE_URL`、`EDUMIND_PROVIDER_MODEL`、`EDUMIND_PROVIDER_API_KEY`；任一缺失或仅为空白时返回固定 `CONFIGURATION_MISSING` 错误，不能开始生成。此组装入口只在服务端使用，不提供读取凭据的客户端端点。

`ProviderSettings` 的普通 `repr`/`str` 隐藏 API Key，配置失败消息只列变量名，不包含值；适配器收到 Key 后仍须遵守不记录原始请求、响应或异常的约束。`.env.example` 只能放占位符，真实 `.env` 不进入 Git。T014 再验证 URL 与目标地址，T015 才接真实网络适配器。
