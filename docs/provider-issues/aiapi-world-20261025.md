# AIAPI.world 模型渠道不可用跟进记录

记录日期：2026-10-25（Asia/Shanghai）

状态：待供应商确认分组、模型权限及上游渠道

范围：接入诊断，不代表课程诊断或教学质量验收通过

## 当前结论

`https://aiapi.world/v1` 可以连接，当前项目 Key 能查询模型列表；但 `gpt-6-luna`、`gpt-5.4` 经 Chat Completions 和 Responses 生成均返回 HTTP 503、`model_not_found`。服务端一致提示当前 `codex (distributor)` 分组没有对应模型的可用渠道。

因此，切换这两个接口没有解决问题。现有证据指向分组与渠道选择阶段的失败，不能确定具体是权限、渠道绑定、渠道健康状态还是模型映射问题；也不能断定余额不足、供应商所有模型不可用或模型本身有问题。

本记录来自本次聊天中的实际工具输出。此前按用户要求未落盘保存完整 HTTP 请求／响应，本文不是原始回执归档，也不是已批准执行包。没有保存或披露 API Key；不修改旧冻结材料、课程 Prompt、教学验收标准或活动任务状态。

## 接入信息及文档边界

| 项目 | 内容 |
| --- | --- |
| Base URL | `https://aiapi.world/v1` |
| 凭据来源 | 项目服务端 `.env`，`EDUMIND_PROVIDER_API_KEY`，值不记录 |
| 被测模型 | `gpt-6-luna`、`gpt-5.4` |
| 服务端报告的分组 | `codex (distributor)`，来自错误消息，尚未通过控制台独立核对 |
| API 文档 | <https://aiapi.world/docs> |
| 快速入门 | <https://aiapi.world/docs/getting-started> |
| Codex 指引 | <https://aiapi.world/docs/codex> |

可检索的快速入门明确提供 `/v1/chat/completions` 示例。用户从 Codex 指引贴出的配置为：

```toml
[model_providers.aiapi]
name = "AIAPI.world"
base_url = "https://aiapi.world/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
```

该配置表示 Codex 使用 Responses 协议，不是 EduMind 的 `.env` 配置格式，也不证明每个分组、模型或参数均兼容。完整交互文档未能读取：网页抓取主要取得静态页面，浏览器访问报告 `net::ERR_CONNECTION_CLOSED`。因此，未找到的能力不能直接判定为文档未提供或服务不支持。

## 实际接口检查

| 方法及路径 | 实际返回 | 可以得出的结论 |
| --- | --- | --- |
| `GET /v1/models` | 两次均 HTTP 200，均返回 148 个模型；耗时约 0.59 秒、0.19 秒 | 列表查询和该请求的鉴权可用；列表包含两个被测模型，但不保证生成渠道可用 |
| `POST /v1/responses`，空对象 `{}` | HTTP 400：未指定模型名称，模型名称不能为空 | 请求进入参数校验，不能据此认定完整功能可用 |
| `POST /v1/chat/completions`，空对象 `{}` | 同上 HTTP 400 | 同上 |
| `POST /v1/embeddings`，空对象 `{}` | 同上 HTTP 400 | 同上；没有实际 Embeddings 模型调用 |
| `POST /v1/responses/input_tokens`，空对象 `{}` | HTTP 404：`Invalid URL (POST /v1/responses/input_tokens)` | 当时该地址未暴露可识别的计数路由；未获得计数结果 |
| 对上述四条路径分别 `OPTIONS` | 全部 HTTP 404，无 `Allow` 头 | 不能以 OPTIONS 结果判断对应 POST 是否存在 |
| `OPTIONS /v1/edumind-nonexistent-route-check` | HTTP 404 | 不存在路径的对照，与其他 OPTIONS 一样返回 404 |

第一次连通查询另有一次沙箱内 `ConnectError`（约 0.03 秒），无法确认到达服务端；随后获准在允许联网的执行环境中完成 GET。不将该连接失败算作已收到服务端响应的 HTTP 请求。

## 五次实际生成请求

以下均各请求一次，无自动重试、无重定向。每次请求设置输出上限 16 token、客户端约 30 秒超时；这些是请求参数和客户端限制，不是服务端费用硬上限证明。

| 顺序 | 接口 | 模型 | HTTP／错误码 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | `POST /v1/responses` | `gpt-6-luna` | 503／`model_not_found` | 2.37 秒 |
| 2 | `POST /v1/chat/completions` | `gpt-6-luna` | 503／`model_not_found` | 2.32 秒 |
| 3 | `POST /v1/chat/completions` | `gpt-5.4` | 503／`model_not_found` | 1.47 秒 |
| 4 | `POST /v1/responses` | `gpt-6-luna` | 503／`model_not_found` | 2.85 秒 |
| 5 | `POST /v1/responses` | `gpt-5.4` | 503／`model_not_found` | 1.47 秒 |

统一错误类型为 `new_api_error`；消息格式：

```text
No available channel for model <model> under group codex (distributor)
```

请求 ID 按上表顺序保存如下，仅用于供应商日志定位。ID 内数字不作为已校准的本地执行时间：

```text
1. 202610241717007033819878268d9d6t4hrpgOw
2. 202610250437281451253378268d9d6Lm6oGshd
3. 202610250437296192968658268d9d6DDyNhixU
4. 202610250450151191316758268d9d6O2rC2UOW
5. 202610250450165906026398268d9d6SOwjdEx2
```

第 1 次使用此前固定 OK 合成 JSON Schema 请求，包含 `reasoning.effort=none`、`strict=true`、`store=false`、`stream=false`、`service_tier=default`。请求文件沿用原字节，SHA256 为 `cc45e19ba242760b756bca579ee80e45c6dd93e35c351ed6128a8bef7e459422`，本次仅替换发送目标与凭据，不重启原批次。

第 2、3 次的请求形状如下，`model` 分别取两个准确 ID：

```json
{
  "model": "<model>",
  "messages": [{"role": "user", "content": "Reply with exactly OK."}],
  "max_completion_tokens": 16,
  "stream": false,
  "store": false
}
```

第 4、5 次使用简化 Responses 请求，无 JSON Schema：

```json
{
  "model": "<model>",
  "input": [{"role": "user", "content": "Reply with exactly OK."}],
  "max_output_tokens": 16,
  "reasoning": {"effort": "none"},
  "stream": false,
  "store": false
}
```

本次 AIAPI 检查共收到 16 个 HTTP 响应：2 次模型列表 GET、9 次路由诊断、5 次生成请求。五次生成均失败，没有取得模型正文、token 用量或扣费回执；实际费用未知，不能登记为零费用。此计数独立于旧 cbbb 批次，不合并或改写旧预算／unknown 占额。

## 尚未验证的能力

- 当前分组下两个模型是否有可用上游，以及模型 ID 与真实上游版本的映射。
- Chat Completions 和 Responses 的成功生成、流式输出及严格 JSON Schema。
- 是否追加系统指令、是否正确执行输出上限，以及 usage 的准确口径。
- 输入计数接口是否另有路径，或当前完全不提供。
- 实际费率、失败请求计费、余额及退款规则。

之前 cbbb 的额外编码指令和输出上限回显问题，不能自动归因到 AIAPI；本次尚未取得成功生成回执，无法比较这些现象。

## 售后联系状态

用户已向 `support@aiapi.world` 发邮件，邮箱显示：**“对方服务器未响应，重新投递中”**。这是用户报告的暂时投递状态，尚未取得最终退信或 SMTP 错误码，不能据此认定邮箱永久失效或供应商失联。

目前未收到供应商解释，也没有由助手代发邮件或工单。

## 可直接发送的反馈

> 我的 API Base URL 为 `https://aiapi.world/v1`。使用同一个 Key，`GET /v1/models` 返回 HTTP 200，列表包含 `gpt-6-luna` 和 `gpt-5.4`；但这两个模型通过 `/v1/chat/completions` 和 `/v1/responses` 都返回 HTTP 503、`model_not_found`，消息为 `No available channel for model … under group codex (distributor)`。
>
> 请确认：
> 1. `codex (distributor)` 是哪个分组？是否绑定了这两个模型的有效渠道？
> 2. 当前 Key 应选择哪个分组？该分组支持哪些准确模型 ID、接口与费率？
> 3. `/v1/models` 是否为全站目录，未按 Key 权限和渠道可用性过滤？
> 4. 是否支持 Responses 的 strict JSON Schema、`max_output_tokens` 和输入 token 计数？如支持计数，请提供准确路径。
> 5. 上述失败请求是否计费？如需更换套餐或分组，请先说明费用。
>
> 请按本文所列请求 ID 核查日志。我不会提供完整 API Key；如需识别账户，请告知控制台中可安全提供的标识。

## 后续跟进

- [ ] 等待邮件最终投递状态；若最终退信，保留去敏 SMTP 错误码。
- [ ] 查找控制台的官方工单／在线客服入口。
- [ ] 获取供应商对分组、准确模型 ID、支持接口和费用的明确回复。
- [ ] 如供应商要求调整分组，由用户确认价格与权限后操作；不因本记录自动修改配置。
- [ ] 获得明确可用配置后，再单独确定最小复测请求和预算，不自动续跑旧测试或课程诊断。

| 跟进日期 | 供应商回复／用户操作 | 新证据 | 下一步 |
| --- | --- | --- | --- |
| 待填写 | 尚无 | 本文记录的请求结果 | 等待渠道与分组确认 |
