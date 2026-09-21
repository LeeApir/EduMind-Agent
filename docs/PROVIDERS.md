# Provider Gateway（MVP 0.1）

PRD §3.8 是产品范围来源。P0 默认且只连接一个由服务端配置的 DeepSeek 模型，并通过 DeepSeek 的 OpenAI Responses-compatible API 调用；本文件定义业务代码和网络适配器之间的内部契约，不开放 BYOK、模型选择页或自动跨厂商回退。

## 内部调用边界

业务服务只依赖 `backend/app/services/provider_gateway.py` 中的 `ProviderGateway`、请求/结果类型与 `ProviderError`，不得直接导入厂商 SDK 或处理厂商响应格式。`ProviderAdapter` 是可替换的单次调用边界；T012 只提供该接口和测试替身，后续任务实现具体适配器。

| 方法 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `generate_text` | `TextRequest` | `TextResult` | 非流式文本生成 |
| `generate_structured` | `StructuredRequest`（含 JSON Schema） | `StructuredResult` | 结构化 JSON 输出；适配器须校验形状，不满足则报 `INVALID_OUTPUT` |
| `stream_text` | `TextRequest` | `AsyncIterator[TextDelta]` | 增量文本；应用层负责 SSE 事件、审核状态与取消 |

`TaskProfile` 保留 fast/default/quality/review 四个内部档位。P0 可以全部映射到同一个系统模型；业务请求不传 Provider URL、模型 ID 或 API Key。请求只包含必要的消息、输出上限和采样参数；模型 ID 与 token 用量只在结果元数据中返回，以供服务端诊断。正式资源仍须按 PRD 经过业务 schema 校验和 ReviewAgent，结构化适配器校验不能替代审核。

## 错误与重试责任

适配器将厂商错误转换为稳定的 `ProviderErrorCode`，只抛出安全的固定文案；原始响应、凭据、完整学生画像和消息正文不得进入异常或日志。401/403 映射 `AUTHENTICATION_FAILED`；429 为 `RATE_LIMITED`（解析秒数或 HTTP 日期 `Retry-After`）；408/504 为 `TIMEOUT`；其余 4xx 与 501 为 `CAPABILITY_UNAVAILABLE`；其他非 2xx 为 `TEMPORARILY_UNAVAILABLE`。配置、鉴权、能力缺失、非法目标和无效输出均不可重试。

`ProviderGateway` 默认**只调用一次**。只有调用方确认请求尚未产生可见副作用并显式传入 `retry_safe=True`，才会在同一个适配器（同一个 Provider）上重试 `RATE_LIMITED`、`TEMPORARILY_UNAVAILABLE` 或 `TIMEOUT`；重试最多 3 次，指数退避不超过 2 秒。超过本地等待上限、无效或负数的 `Retry-After` 会停止重试，避免忽略上游限流窗口；不会静默切换厂商。流式调用永不自动重试，特别是已经输出 token 后。Provider 故障不能删除已发布资源或覆盖学习进度。

Mock HTTP 只证明协议转换，不代表真实供应商完整链路可用。真实 Provider 的普通流式连通与旧 Chat Completions 性能基准已有脱敏记录；切换 Responses 适配器后必须重新验证结构化生成、正式发布、真实浏览器流程和性能。

## 服务端配置组装

生产生成路径通过 `backend/app/core/provider_factory.py` 的 `build_server_provider_gateway` 组装适配器。它在调用适配器工厂前读取 `EDUMIND_PROVIDER_BASE_URL`、`EDUMIND_PROVIDER_MODEL`、`EDUMIND_PROVIDER_API_KEY`；任一缺失或仅为空白时返回固定 `CONFIGURATION_MISSING` 错误，不能开始生成。此组装入口只在服务端使用，不提供读取凭据的客户端端点。

`ProviderSettings` 的普通 `repr`/`str` 隐藏 API Key，配置失败消息只列变量名，不包含值；适配器收到 Key 后仍须遵守不记录原始请求、响应或异常的约束。`.env.example` 固定公开的 DeepSeek Base URL 和默认模型标识，但 API Key 只能放占位符；真实 `.env` 不进入 Git。

## Provider 目标地址边界

`build_server_provider_gateway` 在把 Key 交给适配器工厂前，先验证 Base URL；不合法时返回固定的 `INVALID_TARGET`，不回显 URL、DNS 答案或 Key。Base URL 只接受无用户信息、查询和片段的 HTTP(S) 地址。默认 `EDUMIND_PROVIDER_DEPLOYMENT=cloud`：只接受 HTTPS，解析全部 A/AAAA，任一地址不属于公网（含回环、私网、链路本地、云元数据及其他非全局地址）即拒绝。额外明确阻断 `168.63.129.16` 等元数据服务地址。

本地模型必须**同时**设 `EDUMIND_PROVIDER_DEPLOYMENT=local` 与 `EDUMIND_PROVIDER_LOCAL_ALLOWLIST`；后者是逗号分隔的精确 `IP:port` 条目（IPv6 用 `[::1]:port`），例如 `127.0.0.1:11434`。仅被列出的非公网、非链路本地、非元数据 IP 与端口可使用 HTTP；云端模式提供白名单会直接配置失败。DNS 名称解析出多个地址时，必须全部满足同一条目标策略，不能只挑安全的一条。

适配器工厂收到 `ProviderTargetGuard`，而不是可以永久信任的启动时 DNS 结果。**每次出站尝试**必须调用 `approve_base()`，只连接返回的 `ApprovedTarget.connect_ip`（或其 `addresses` 中另一已批准 IP），同时保留原始主机名用于 HTTP Host 与 HTTPS TLS SNI/证书验证；禁止让 HTTP 客户端再次解析原始主机名、使用环境代理绕过目标 IP，或自动跟随重定向。默认拒绝 3xx；若确需处理跳转，只可通过 `approve_redirect(previous, location)` 在下一次请求前重新解析并校验同源目标，不得把 Key 发送到其他源。连接失败后的每次重试也必须重新调用 Guard。T014/T015 使用受控 DNS 与 Mock HTTP 覆盖这些边界，不进行真实网络请求。

## P0 DeepSeek Responses 非流式适配器

`build_default_provider_gateway()` 只组装 `DeepSeekResponsesAdapter`。它向服务端配置的 Base URL 追加 `POST /responses`，模型 ID 和 API Key 只从服务端环境注入。内部消息映射为 `input`，输出上限映射为 `max_output_tokens`；结构化请求使用 `text.format={"type":"json_schema","name":"edumind_result","schema":...}`。适配器只接受 `status=completed` 的 assistant `output_text`，忽略 reasoning 内容，把 `input_tokens`/`output_tokens` 转换为内部用量；不完整、失败、空文本或畸形结果返回安全错误，不会发布资源。

结构化文本解析后仍以本地 Draft 2020-12 JSON Schema 校验；Provider 侧约束不能替代本地校验或 ReviewAgent。外部 `$ref`、`$id` 等可能触发远程读取的 schema 在网络调用前被拒绝。HTTPX 0.28.1 连接到 Guard 批准的 IP，同时设置原始 Host 和 `sni_hostname` 保持 TLS 证书验证；禁用环境代理与自动重定向，单次非流式响应限制为 2 MiB 并始终关闭连接。依据：[DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)、[DeepSeek Responses 使用指南](https://api-docs.deepseek.com/guides/responses_api/)、[HTTPX SNI extension](https://www.python-httpx.org/advanced/extensions/)。

## P0 DeepSeek Responses 流式适配

`stream_text` 对 `/responses` 发送 `stream=true`，只把 `response.output_text.delta` 转为业务层 `TextDelta`；reasoning 与生命周期事件不向学生暴露。正常结束必须看到携带 `status=completed` 的 `response.completed`，DeepSeek Responses 不使用 `[DONE]`。`response.incomplete` 映射为 `INVALID_OUTPUT`，`response.failed` 和终止事件前 EOF 映射为安全的临时不可用错误。

解析器按任意网络字节分片重组 UTF-8 SSE，兼容 CRLF、注释心跳和 `event:` 字段，每帧限制 1 MiB。未知或畸形事件、非法 UTF-8/JSON、完成但没有可见文本均拒绝；3xx 不自动跟随。正常完成、异常与消费者取消都会关闭上游响应，且已输出部分 token 后不静默重试。
