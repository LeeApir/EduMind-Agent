# Provider Gateway：现行契约与验证边界

PRD §3.8 规定 P0 使用单一服务端 OpenAI-compatible Provider。系统默认连接由服务端配置的 DeepSeek 模型，使用 Responses 传输；Phase 1 新增内部连接网关、连接管理/显式测试 API 与连接管理、四档偏好页面。两条路径均不自动跨厂商回退。

## Phase 1已批准边界

用户已授权串行推进PHASE-1-T002至T005；[ADR-0008](ADR/0008-provider-credentials-and-egress-boundary.md)已于2026-10-04获用户A–D批准。确定匿名持久BYOK随原2h会话失效/清理、主密钥信封加密与显式轮换、进程/会话/单次操作内临时Key，以及配置版本绑定的数据去向同意和明确回退。批准登记见[具体记录](ADR/0008-provider-approval-20261004.json)。API/持久化/临时Key由T003至T005分别交付；批准不代表BYOK已可用，也不授权实际模型出口。

用户随后授权持续串行完成 Phase 1。T007 的 `build_connection_provider_gateway` 接受服务端解析的 owner/原会话、连接 ID/配置版本、精确模型和数据类别同意，以及绑定同一连接版本与模型的能力声明。未知或未声明的流式/结构化能力拒绝调用；能力声明不等于真实模型验收。调用方必须注入每次尝试的预算/操作授权函数，没有默认授权；持久预算账本由 T035 交付。当前没有新增对外生成端点，`catalog_only` 仍拒绝生成，仅允许声明为 `probe` 的连接测试/模型刷新操作；真实模型出口仍需独立预算授权。

内部操作与网关消费必须放在同一个 asyncio task 的上下文内；SSE 调用方应在消费任务内创建网关，不能跨任务借用已激活的凭据。每次重试都重新锁定连接、核验会话/版本/启用状态，重新解析并固定目标 IP，然后取得该次授权并读取凭据。持久 Key 不缓存，临时 Key 绑定原操作/用途/模型；明确无 Key 的连接不会借用系统 Key。禁用环境代理及跳转，保留原始 Host 与 TLS SNI。

发送与删除/禁用共用 PostgreSQL 行锁；HTTPX 异步 trace 在实际 headers/body 发送开始前再次检查会话和期限，在请求体发送完成后提交并释放锁。流式读取不长期持锁。没有 trace 的测试传输保守地保持锁至响应头返回。每个操作最长 180 秒，或原会话/凭据更早的期限；同进程提交撤销立即取消，跨进程每 0.9 秒作无锁 MVCC 状态检查，检查最多 1 秒，失败同样取消。无锁观察不授予发送权限，避免观察者等待自己持有的发送锁。取消、消费者关闭、失败和正常结束均关闭上游并清理授权头/临时凭据。依据：[HTTPX trace 与 SNI](https://www.python-httpx.org/advanced/extensions/)。

连接适配器固定调用所选 Base URL 的 `/chat/completions`，只发送本次消息、选定模型和受限参数（请求 1 MiB、响应累计 2 MiB、SSE 单帧 1 MiB）。文本只接受单个 assistant 结果与 `finish_reason=stop`；流式只转发可见 content，必须收到正常 finish 和 `[DONE]`。结构化传输显式声明为 `json_schema`、`json_object` 或 `text_json`，没有自动试探/降级；三种模式都做本地 JSON/schema 校验，重复键、非有限数、工具/拒绝输出与截断均拒绝。依据：[OpenAI 结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)、[流式输出](https://developers.openai.com/api/docs/guides/streaming-responses)。正式资源仍需业务审核。

T007 验证：隔离 PostgreSQL 迁移往返及连接/临时凭据/系统 Provider 回归 276 项通过，无跳过；包括真实 HTTPX 到本机合成 HTTP 服务的发送事件测试。其余出站均为 Mock/受控 DNS，真实 Provider 请求 0。这些证据证明协议和并发边界，不证明供应商或模型可用性。

## Phase 1 Ollama 原生适配

T008 为 `provider_type=ollama` 选择原生适配器，其他业务接口仍是同一个 `ProviderGateway`。Base URL 是服务根或代理前缀，例如 `http://127.0.0.1:11434`，适配器只追加 `/api/chat`；不会访问 `/api/pull`、下载模型或自动探测能力。管理员必须同时启用 `EDUMIND_PROVIDER_DEPLOYMENT=local` 与精确 `EDUMIND_PROVIDER_LOCAL_ALLOWLIST=127.0.0.1:11434`。每次出站重新核验全部 DNS 答案，全部必须在白名单；即使是合法公网 HTTPS，也不能作为 Ollama 原生目标。通用连接元数据保存仍遵循 SSRF 资格校验，保存不证明其能通过 Ollama 的发送门禁。本地只指已批准的服务端连接目标，不保证该服务不转发到云端。

原生文本请求显式发送 `stream=false`，输出上限映射到 `options.num_predict`，温度放在 `options.temperature`；token 用量来自 `prompt_eval_count`/`eval_count`，缺失保持未知。单个完成结果必须是 assistant 文本、`done=true` 和 `done_reason=stop`。流式显式开启 `stream=true`，解析有界 UTF-8 NDJSON（含 CRLF 和无末尾换行的完整记录），只暴露 `message.content`，忽略独立 `thinking`，在正常 done 结束；截断、错误记录、工具/非文本输出均以统一安全错误终止，不自动重放。模型缺失的 404 映射为 `CAPABILITY_UNAVAILABLE`，连接失败为 `TEMPORARILY_UNAVAILABLE`，超时为 `TIMEOUT`，不回显原始错误正文。依据：[Ollama Chat](https://docs.ollama.com/api/chat)、[流式协议](https://docs.ollama.com/api/streaming)、[错误协议](https://docs.ollama.com/api/errors)。

模型能力仍显式绑定连接配置版本、模型 ID 和声明版本，不根据模型名称推断。声明支持结构化输出时，`json_schema` 使用原生 `format=<schema>`，`json_object` 使用 `format="json"`，`text_json` 仅注入 JSON 指令；三种传输必须由能力声明明确选择，不自动降级。全部结果继续经过本地严格 JSON/schema 校验与业务审核。JSON/消息参数/字节限制提取为厂商无关共享校验，兼容适配器继续使用相同规则，网络 JSON 只接受 UTF-8。依据：[Ollama 结构化输出](https://docs.ollama.com/capabilities/structured-outputs)。

Ollama 复用 T007 的 owner/会话/配置版本/同意、每次预算授权、发送行锁、撤销和临时 Key 生命周期；无 Key 连接不借用系统凭据。T008 只提供内部适配，没有增加对外生成端点或解除 `catalog_only`。真实本地实例可用性属于后续独立接入验收；本任务实际模型请求为 0。

## Anthropic 原生适配（T015）

连接管理可选Anthropic，Base URL包含版本前缀（例如供应商的`/v1`），原生适配只追加`/messages`。发送层使用`x-api-key`和`anthropic-version: 2023-06-01`，固定已批准IP、原Host/TLS SNI，关闭环境代理、重定向和自动重试；成功/失败/取消均移除Key头。复用HTTPX 0.28.1及jsonschema 4.25.1锁定依赖，无新增SDK或固定模型。模型来自确切连接选择，业务仍只依赖Gateway。依据：[Messages协议](https://platform.claude.com/docs/en/api/messages/create)。

前置system消息映射为顶层文本块，不将后置system指令跨轮提升。无用户消息、assistant前缀补全及超出原生0–1范围的温度在发送前拒绝；用户明确温度仍照传，较新模型不支持时返回安全能力错误，不能删除参数重放。固定8token/10秒/一次连接探测对Anthropic不设置已弃用的采样参数，不发送学生上下文。只返回正常end_turn的可见文本；max_tokens、refusal、pause_turn、非文本/工具结果拒绝。用量仅映射实际input_tokens/output_tokens，缺失保持未知，不推算价格或缓存账单。

流式解析有界SSE，核验message_start、顺序索引的内容块及其关闭、正常message_delta和最终message_stop；只转发text_delta，隐藏thinking/signature块。截断、错误、工具块与失序关闭连接，已输出后仍不会重试或拼接其他目标。共享1MiB请求/单帧及2MiB累计响应限制；客户端取消和临时凭据一次性清理由发送层执行。依据：[流式事件与错误](https://platform.claude.com/docs/en/build-with-claude/streaming)、[HTTP错误](https://platform.claude.com/docs/en/api/errors)。

结构化能力必须明确声明并绑定版本/模型。json_schema使用原生`output_config.format`；text_json只在明确选择时发送JSON指令。新增内部tool_schema模式还必须声明tool_calling=true，只允许固定`edumind_result`、strict input_schema及禁止并行的强制选择，返回单个同名tool_use输入作为结构化值，不执行工具。所有模式都严格解析JSON并在本地按原schema校验；不削弱schema、不自动换模式，其他适配器拒绝tool_schema。上游不支持的schema返回安全错误，正式资源仍需ReviewAgent。依据：[JSON与严格工具结构化输出](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)。

显式模型刷新使用一次`GET <base>/models?limit=1000`；has_more=true或格式无效时保留旧缓存，不自动翻页。仅映射官方明确的structured_outputs.supported与image_input.supported为声明能力，streaming/tool_calling等无明确字段仍未知；项目扩展声明可补充，但与官方声明冲突则拒绝。规则版本anthropic-model-capabilities-v1，不把声明当真实验证；当前Key回显禁止进入模型缓存或生成结果。依据：[模型列表及能力字段](https://platform.claude.com/docs/en/api/models/list)。默认生产预算仍拒绝，catalog_only持续，本任务真实Provider请求0；实际模型质量和连通性待独立授权验收。

## Gemini 原生适配（T016）

连接管理可选Google Gemini。Base URL包含版本前缀（例如`https://generativelanguage.googleapis.com/v1beta`），不包含模型路径或Key；适配器追加`models/<选定模型>:generateContent`，流式改为`:streamGenerateContent?alt=sse`。允许短模型ID或规范`models/<ID>`，拒绝斜线、查询、百分号编码和方法注入；不固定型号。发送层使用`x-goog-api-key`头，Key不进入URL，继续固定批准IP与原Host/TLS SNI，关闭环境代理和重定向，终止后清除Key头。复用已锁定HTTPX 0.28.1、jsonschema 4.25.1，不新增SDK。协议于2026-10-04核对：[GenerateContent及流式API](https://ai.google.dev/api/generate-content)、[API认证](https://ai.google.dev/api)。

前置system映射为`systemInstruction.parts`，assistant映射为`model`，不跨轮提升后置system；只接受以user开始和结束的对话。`generationConfig`保留显式温度、受限`maxOutputTokens`，固定单候选和TEXT输出，不配置工具、搜索、代码执行或安全阈值覆盖。只发布正常STOP的可见text，thought/signature保持内部；MAX_TOKENS、拒绝、工具/二进制输出和畸形候选失败。SSE解析有界UTF-8帧，按增量转发，必须正常STOP且EOF；可接受无正文的用量尾帧，禁止完成后的额外正文或模型版本变化。取消/截断/错误关闭连接，不重放流。请求及单帧1MiB、累计响应2MiB；错误只返回安全枚举，JSON转义后的当前Key回显也在发送上下文内拒绝。

结构化需明确能力与传输声明：`json_schema`使用当前官方`generationConfig.responseFormat.text={mimeType:"application/json",schema:<原schema>}`，`text_json`仅在明确选择时追加JSON指令；不使用自动模式探测或降级，不削弱schema。全部结果在本地严格解析并校验原schema，正式资源仍需ReviewAgent。用量仅映射实际`promptTokenCount`和`candidatesTokenCount`，如同时报告`thoughtsTokenCount`则计入输出；缺失保持未知，不用total反推或推算费用。依据：[结构化REST示例](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)、[响应及用量字段](https://ai.google.dev/api/generate-content)。

按[T001冻结计划](acceptance/phase-1-acceptance-plan.md)的多模态边界，内部厂商无关`TextRequest`可携带`InlineImage`及`InlineImageConsent`，仅支持PNG/JPEG/WEBP内存字节，最多4张、合计512KiB，校验MIME与文件头且整个请求仍受1MiB限制。图片仅加入最后一条user消息，不读取文件/URL、不调用Files API；HEIC/HEIF、音频、视频、PDF及工具消费入口未实现，明确拒绝而非降级。依据：[官方内联图片与格式](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding)。

图片必须有vision=true声明、generation用途与`content_for_review`类别，同时满足原连接同意和独立图片同意。后者绑定connection/config/model/operation及SHA256清单（有序图片的MIME和字节摘要、完整消息、档位、参数、结构化schema）；改变任一项须重新授权，计算摘要本身不授予同意。每个网关图片操作只发送一次，包括失败/取消，不因retry_safe自动重传；其他适配器与Gateway拒绝携图请求，避免静默丢弃。没有新增HTTP/前端上传入口，当前没有产品调用方替用户构造图片同意。未来调用方必须先取得明确目标与具体数据授权，不能把文本类别勾选视为上传授权；真实上传及云端探测仍须T035/T039单独预算和授权。

显式模型刷新为单次`GET <base>/models?pageSize=1000`；非空nextPageToken、畸形数据或Key回显失败并保留旧缓存，不自动分页。缓存保留规范`models/<ID>`，能力规则`gemini-model-capabilities-v1`；只映射明确声明的streamGenerateContent或项目布尔声明，generateContent本身不证明vision/structured_output/streaming，未声明保持未知。依据：[Models列表和字段](https://ai.google.dev/api/models)。固定8token/10秒/一次的文本探测不含图片/学生上下文，也不能将成功当成多模态或结构化证明。生产预算默认拒绝、catalog_only持续；本任务真实Provider请求0。

## 讯飞星火可选 HTTP 适配（T017）

`provider_type=spark`选择独立SparkAdapter，业务仍只依赖Gateway。按2026-10-05核对的[官方HTTP文档](https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html)、[X2 HTTP文档](https://www.xfyun.cn/doc/spark/X1http.html)和[星辰MaaS接入说明](https://www.xfyun.cn/doc/spark/%E4%BA%A7%E5%93%81%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.html)，使用所选模型对应的HTTP服务前缀（例如`/v1`、`/v2`或`/x2`），只追加`/chat/completions`，不固定域名或型号、不跨端点自动切换。只写secret.api_key承载HTTP APIPassword/API Key，通过Bearer头发送；不消费APISecret/AppID三件套或生成WebSocket/HMAC签名URL，传入额外凭据在发送前拒绝。复用锁定HTTPX0.28.1，不新增SDK/迁移。

请求保持原消息、模型、受限max_tokens及显式温度，不发送owner/session/user标识。明确设置web_search.enable=false和tool_choice=none，因为官方部分型号默认允许搜索；不注册或执行工具。若目标不支持这些禁止参数，返回能力错误，不删除参数重放。探测只发固定8token/一次/10秒的合成文本，不设置跨版本范围不同的温度，不含学生上下文。设置页可选星火并提示HTTP凭据方式；保存、打开页面和读取缓存都不触发模型请求。

原生文档的完整非流式响应没有model/finish_reason，因此以完整合法HTTP JSON响应、成功code（出现时必须整数0）、单个assistant文本作为完成依据；显式finish_reason出现时仍须stop，length/拒绝/工具/二进制/异常状态拒绝。TextResult.model_id记录所选路由，不将缺失的上游型号伪造为独立模型验证。流式按有界SSE增量处理，必须收到[DONE]且自然读到EOF，只有可见content转发；reasoning_content和HIDE_CONTINUE思考块隐藏，带隐藏建议的正文拒绝。完成后额外正文、版本变化、截断、工具/搜索、非法JSON及取消都终止并关闭，不自动重试或拼接另一Provider。

实际prompt_tokens/completion_tokens映射到中立用量，缺失保持未知；非零search_prompt_tokens或搜索输出违反禁搜索范围而失败，不推算费用。原生code10007/11201/11202/11203映射限流，11200为鉴权失败，10907为能力不支持，10013/10014/10019为无效输出；未知错误码保守拒绝，HTTP状态使用统一映射，错误正文/sid不公开。当前Key的转义回显在凭据上下文内拒绝。共用1MiB请求/帧、2MiB响应上限、目标固定IP/Host/SNI、禁代理/重定向、owner/会话/配置版本/同意、发送行锁/撤销和临时凭据单次清理。

本任务只开放已核对的文本/流式契约，结构化、图片、函数/搜索执行及模型列表刷新显式CAPABILITY_UNAVAILABLE；不因官方提到JSON/工具能力自动推断具体模型已可用于正式生成。Spark的GET模型缓存仍只读，POST刷新在出站前拒绝，不假设存在未记录的/models接口。生产预算默认拒绝、catalog_only持续；真实账号、所选型号/协议及禁搜索参数是否实际生效留T039独立授权验收，本任务真实Provider请求0。

## 显式连接测试

T010 的 POST `/api/providers/connections/{id}/test` 只接受操作ID、精确版本/模型/probe-only同意和可选临时handle；固定短提示、最多8输出token、10秒总期限、一次尝试、不回退。target是发送当时批准的Base URL，is_local来自该次DNS全部地址，不证明服务离线；文本成功仍将所有高级能力标为未知，不返回上游生成正文。响应private/no-store并提示可能调用服务。默认预算拒绝出站；Mock测试注入的授权不是生产预算或真实Provider验收，实际预算与计数由T035交付。

## 模型缓存与声明

T011提供认证静态类型目录GET `/api/providers/catalog`、owner/原会话过滤的缓存GET `/api/providers/connections/{id}/models`，以及显式POST `.../models/refresh`。类型目录包含后续原生类型，不承诺尚未实现的适配器可调用；不加载主密钥或调用模型。缓存绑定连接配置版本，存PostgreSQL `provider_model_snapshots`（Alembic0019）；空缓存/配置变更返回models=[]、refreshed_at=null，不证明供应商没有模型。读取不刷新、不做DNS/模型出口，重启可恢复同一有效会话的快照。

刷新只在精确版本/模型/probe-only同意和预算授权后，复用发送行锁、凭据/临时handle和固定IP边界。固定GET `<base>/models` 或原生 `<base>/api/tags`，不发送学生上下文；10秒总期限、2MiB累计响应、最多1000唯一模型ID，无重试/分页/回退/下载。全部响应校验后，在同一连接行锁及会话/版本复核下原子更新；错误保留旧快照，配置变更或撤销禁止发布。模型ID只允许有界无控制字符文本；原始owned_by/digest/details/secret等元数据丢弃，当前Key回显被拒绝而不是缓存/返回。用量未提供，不伪造token计数。默认预算仍拒绝，实际Provider调用0。

官方列表协议只提供模型ID等元数据，不能据名称或family推断能力：[OpenAI列表](https://developers.openai.com/api/reference/resources/models/methods/list)、[Ollama列表](https://docs.ollama.com/api/tags)。若兼容服务显式提供项目可选字段 `edumind_capabilities`，只读取已定义的streaming/structured_output/tool_calling/vision/embedding/tts/asr布尔或null；这不是官方字段。输出source=declared与本地解析规则版本model-list-declarations-v1；绝不接受上游自称verified，缺字段仍null/source=unknown，不把声明当真实质量验收。`resolve_capabilities`只解析owner/当前配置/确切模型的缓存声明，流式/结构化能力未知或不匹配由网关在预算/发送前拒绝。后续原生声明和真实验证仍各自验收。

## 四档偏好与选择

T012提供GET `/api/model-preferences` 与CSRF PUT `/api/model-preferences/{task_profile}`，保存fast/default/quality/review四档。Alembic0020的偏好按owner/原会话隔离，expected_version=0仅首次创建，随后精确比较当前单调版本；同owner行锁保护首次创建竞争。route和最多3个有序fallback包含连接/配置版本/模型/数据类别，必须明确同意，不能重复同一连接版本与模型或把鉴权/无效输出列入回退条件。不存Key/handle/响应正文，不读取主密钥或接触模型。GET只列已有档位；state=available是配置资格，能力/真实连通性仍须另验。禁用/删除/过期/缺凭据返回unavailable；有效连接版本变化为consent_required，原偏好保留便于解释和重选。

`select_route`返回内部临时覆盖→用户该档位→default用户默认→系统默认来源；未配置才继续查下一层，已保存的失效选择不自动降级。review可独立选择连接/模型。`generate_selected`只处理非流式文本/结构化请求；当前catalog_only先拒绝，所有被选目标先核验owner/会话、当前版本/资格、精确模型缓存能力、本次独立同意和实际数据类别，再由发送锁进行逐次预算授权。只有RATE_LIMITED/TIMEOUT/TEMPORARILY_UNAVAILABLE匹配用户有序fallback的on_errors时尝试对应目标，每目标一次；最多主路由+3个fallback，无同意/能力/预算即停止，无默认系统Key回退。审核结构化能力未知或不可用不返回审核结果，不能发布正式资源。临时Key分别绑定每一目标的本次操作，流式仍只用原目标、不拼接回退正文。

安全记录回调只包含所用route、收到上游响应的实际Base URL、选择来源、固定回退原因与结果码；无请求/响应正文或秘密。连接失败未收到响应则target=null，不把批准但未发送的目标记为完成。系统默认分支需调用方显式提供独立authorize_system与网关，缺少即拒绝，旧学习路由不因此切换。T013/T014负责前端设置；业务调用接入及真实预算/动态开放仍单独验收。

## 连接管理页面（T013）

课程入口中的“模型设置”可新增、修改、禁用及确认删除兼容服务/Ollama连接。打开页面只读取当前匿名会话、连接元数据和模型缓存；保存连接不测试、不刷新、不下载模型。课程组件保留在原页面，返回后继续当前练习；设置错误不会解除目录门禁或阻塞已发布课程。课程与设置同时初次读取身份时，共享正在进行的会话请求，结束后不缓存身份或CSRF。

持久化Key只在密码输入框和该次保存请求中暂存，提交前清空输入；服务端在原匿名会话期限内加密保存。替换Key留空保留，明确清除或更换地址/类型遵循后端撤销规则。临时模式只保存连接信息，测试/刷新需重新输入Key，并先上传绑定确切操作、用途、配置版本、模型及probe-only同意的一次handle；操作完成、失败或离开时清空组件秘密，handle不写任何浏览器存储。页面关闭期间仍在上传时，不继续发起测试；已上传但未消费的服务端临时凭据按ADR-0008的期限清理。

每次测试或刷新前，需选择精确模型ID并明确同意只发送探测数据。改动配置或模型、操作结束后重置同意；未保存配置不能测试。页面显示保存的Base URL与服务端白名单/公网属性，成功测试再展示该次实际目标；能力分别显示支持/不支持/未知和声明来源，不从模型名称或文本成功推断高级能力。默认预算拒绝时给出管理员授权提示，不自动重试。响应只保留安全字段，供应商原始错误不展示，所有服务文本默认转义。

验证入口：`cd web && pnpm test --run tests/provider-settings.spec.ts`；浏览器Mock流程为`web/tests/e2e/provider_settings.py`，可通过webapp-testing的`with_server.py`启动本机Vite并传入`--evidence`目录。该核验只证明界面协议、Key清空、手机布局和目录返回，不证明真实Provider可用。

## 档位与数据去向页面（T014）

“档位与数据去向”设置fast/default/quality/review四档，default同时作为用户默认连接，review可选择独立审核模型。打开仅读取会话、连接、偏好和所选连接的模型缓存，不测试/刷新/生成。未配置档位才继承default或服务端系统默认；已有的unavailable/consent_required选择显示阻塞原因，不自动换模型。页面按服务端保存回执和T012相同优先级展示配置解析，尚未发生请求的目标不称为实际调用记录。旧配置版本匹配失败时，不用新Base URL冒充旧目标。

每个主/回退目标分别显示服务类型、确切模型、Base URL、白名单/公网属性、配置版本、凭据方式和允许的数据类型。回退初始为空，可明确添加最多3个有序目标并分别选择限流/超时/暂时不可用条件；其他错误和流式输出不跨目标。改动连接、模型、数据类别、条件或顺序后取消同意，保存需重新确认全部目标。偏好只存路由元数据；临时Key仍需在调用时逐目标单次输入，保存同意不替代本次数据去向确认、能力校验、预算或动态开放批准。

验证入口：`cd web && pnpm test --run tests/model-preferences.spec.ts`；`web/tests/e2e/model_preferences.py`覆盖用户默认继承、显式回退、独立审核、目标/数据回执、手机布局及返回目录，全部API为Mock，真实Provider请求为0。

## 内部调用边界

业务服务只依赖 `backend/app/services/provider_gateway.py` 中的 `ProviderGateway`、请求/结果类型与 `ProviderError`，不得直接导入厂商 SDK 或处理厂商响应格式。`ProviderAdapter` 是可替换的单次调用边界；现有具体适配器由服务端工厂按结构化传输配置组装。

| 方法 | 输入 | 输出 | 用途 |
|---|---|---|---|
| `generate_text` | `TextRequest` | `TextResult` | 非流式文本生成 |
| `generate_structured` | `StructuredRequest`（含 JSON Schema） | `StructuredResult` | 结构化 JSON 输出；适配器须校验形状，不满足则报 `INVALID_OUTPUT` |
| `stream_text` | `TextRequest` | `AsyncIterator[TextDelta]` | 增量文本；应用层负责 SSE 事件、审核状态与取消 |

`TaskProfile` 保留 fast/default/quality/review 四个内部档位。P0 可以全部映射到同一个系统模型；业务请求不传 Provider URL、模型 ID 或 API Key。请求只包含必要的消息、输出上限和采样参数；模型 ID 与 token 用量只在结果元数据中返回，以供服务端诊断。正式资源仍须按 PRD 经过业务 schema 校验和 ReviewAgent，结构化适配器校验不能替代审核。

## 错误与重试责任

适配器将厂商错误转换为稳定的 `ProviderErrorCode`，只抛出安全的固定文案；原始响应、凭据、完整学生画像和消息正文不得进入异常或日志。401/403 映射 `AUTHENTICATION_FAILED`；429 为 `RATE_LIMITED`（解析秒数或 HTTP 日期 `Retry-After`）；408/504 为 `TIMEOUT`；其余 4xx 与 501 为 `CAPABILITY_UNAVAILABLE`；其他非 2xx 为 `TEMPORARILY_UNAVAILABLE`。配置、鉴权、能力缺失、非法目标和无效输出均不可重试。

`ProviderGateway` 默认**只调用一次**。只有调用方确认请求尚未产生可见副作用并显式传入 `retry_safe=True`，才会在同一个适配器（同一个 Provider）上重试 `RATE_LIMITED`、`TEMPORARILY_UNAVAILABLE` 或 `TIMEOUT`；总尝试最多 3 次（首次调用加最多 2 次重试），默认指数退避上限为 2 秒。超过本地等待上限、无效或负数的 `Retry-After` 会停止重试，避免忽略上游限流窗口；不会静默切换厂商。流式调用永不自动重试，特别是已经输出 token 后。Provider 故障不能删除已发布资源或覆盖学习进度。

Mock HTTP 只证明协议转换，不代表真实供应商完整链路可用。最近阶段结论见 [MVP 0.2 收尾决定](acceptance/mvp-0.2-closeout-decision.md)：Pro 质量/闭环与 Flash 性能分别成立，不能互相替代。改变模型、传输或指令后，按影响重新制定验证范围，不自动沿用其他配置的通过结论。

## 服务端配置组装

生产生成路径通过 `backend/app/core/provider_factory.py` 的 `build_server_provider_gateway` 组装适配器。它在调用适配器工厂前读取 `EDUMIND_PROVIDER_BASE_URL`、`EDUMIND_PROVIDER_MODEL`、`EDUMIND_PROVIDER_API_KEY`；任一缺失或仅为空白时返回固定 `CONFIGURATION_MISSING` 错误，不能开始生成。此组装入口只在服务端使用，不提供读取凭据的客户端端点。

`ProviderSettings` 的普通 `repr`/`str` 隐藏 API Key，配置失败消息只列变量名，不包含值；适配器收到 Key 后仍须遵守不记录原始请求、响应或异常的约束。`.env.example` 固定公开的 DeepSeek Base URL 和默认模型标识，但 API Key 只能放占位符；真实 `.env` 不进入 Git。

## Provider 目标地址边界

`build_server_provider_gateway` 在把 Key 交给适配器工厂前，先验证 Base URL；不合法时返回固定的 `INVALID_TARGET`，不回显 URL、DNS 答案或 Key。Base URL 只接受无用户信息、查询和片段的 HTTP(S) 地址。默认 `EDUMIND_PROVIDER_DEPLOYMENT=cloud`：只接受 HTTPS，解析全部 A/AAAA，任一地址不属于公网（含回环、私网、链路本地、云元数据及其他非全局地址）即拒绝。额外明确阻断 `168.63.129.16` 等元数据服务地址。

本地模型必须**同时**设 `EDUMIND_PROVIDER_DEPLOYMENT=local` 与 `EDUMIND_PROVIDER_LOCAL_ALLOWLIST`；后者是逗号分隔的精确 `IP:port` 条目（IPv6 用 `[::1]:port`），例如 `127.0.0.1:11434`。仅被列出的非公网、非链路本地、非元数据 IP 与端口可使用 HTTP；云端模式提供白名单会直接配置失败。DNS 名称解析出多个地址时，必须全部满足同一条目标策略，不能只挑安全的一条。

适配器工厂收到 `ProviderTargetGuard`，而不是可以永久信任的启动时 DNS 结果。**每次出站尝试**必须调用 `approve_base()`，只连接返回的 `ApprovedTarget.connect_ip`（或其 `addresses` 中另一已批准 IP），同时保留原始主机名用于 HTTP Host 与 HTTPS TLS SNI/证书验证；禁止让 HTTP 客户端再次解析原始主机名、使用环境代理绕过目标 IP，或自动跟随重定向。默认拒绝 3xx；若确需处理跳转，只可通过 `approve_redirect(previous, location)` 在下一次请求前重新解析并校验同源目标，不得把 Key 发送到其他源。连接失败后的每次重试也必须重新调用 Guard。MVP 0.1-T014/T015 使用受控 DNS 与 Mock HTTP 覆盖这些边界；这些测试不构成真实网络验收。

## P0 DeepSeek Responses 非流式适配器

`build_default_provider_gateway()` 在默认 `responses_json_schema` 配置下组装 `DeepSeekResponsesAdapter`；显式 `beta_tools` 配置选择 Beta 适配器，禁止自动回退。默认 Responses 适配器向服务端配置的 Base URL 追加 `POST /responses`，模型 ID 和 API Key 只从服务端环境注入。内部消息映射为 `input`，输出上限映射为 `max_output_tokens`；结构化请求使用 `text.format={"type":"json_schema","name":"edumind_result","schema":...}`。适配器只接受 `status=completed` 的 assistant `output_text`，忽略 reasoning 内容，把 `input_tokens`/`output_tokens` 转换为内部用量；不完整、失败、空文本或畸形结果返回安全错误，不会发布资源。

DeepSeek Responses 默认开启 thinking，而 P0 的第一段讲解和正式资源需要可预期的低时延。因此默认 Responses 适配器对文本与结构化请求显式发送 `reasoning={"effort":"none"}`；调用方未提供上限时使用 4096 `max_output_tokens`，已指定上限保持原值。这个 P0 策略不改变内部 `TaskProfile`、业务 schema 或审核流程；需要深度推理的独立模型策略属于后续阶段，不能通过浏览器参数覆盖。

正式 JSON Schema 生成在调用方未指定温度时还固定使用 `temperature=0.0`，以减少可复现资源的随机性；显式温度照常透传。普通文本流不注入这个默认值，保持首段讲解现有采样行为。

## 实验性 Beta 结构化传输

现有 Beta 完整质量验收未通过；协议探针通过不代表正式资源质量达标。该选项不得自动启用，历史失败见文末记录。

显式服务端选项：`EDUMIND_PROVIDER_STRUCTURED_TRANSPORT=beta_tools`。默认仍为
`responses_json_schema`，未知选项拒绝启动Provider；禁止自动回退。Beta选项只支持当前
配置已为HTTPS `api.deepseek.com:443`，不从自定义代理迁移凭据到官方站点。
仅 `generate_structured` 使用同源 `/beta/chat/completions`，强制唯一
`edumind_result` function 且 `strict:true`、关闭thinking；函数参数作为数据返回，绝不执行。
普通文本及SSE仍用原配置的Responses路径。每次尝试重新Guard校验并固定IP/Host/TLS SNI，
禁代理/跳转、超时和2MiB限制与原适配器一致。常量仅在出站schema做等价投影，原schema
仍本地校验，再进入Review；拒绝冲突的type/enum，模型/Key不变，真实`.env`未被修改。

结构化文本解析后仍以本地 Draft 2020-12 JSON Schema 校验；Provider 侧约束不能替代本地校验或 ReviewAgent。外部 `$ref`、`$id` 等可能触发远程读取的 schema 在网络调用前被拒绝。HTTPX 0.28.1 连接到 Guard 批准的 IP，同时设置原始 Host 和 `sni_hostname` 保持 TLS 证书验证；禁用环境代理与自动重定向，单次非流式响应限制为 2 MiB 并始终关闭连接。依据：[DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)、[DeepSeek Responses 使用指南](https://api-docs.deepseek.com/guides/responses_api/)、[HTTPX SNI extension](https://www.python-httpx.org/advanced/extensions/)。

## P0 DeepSeek Responses 流式适配

`stream_text` 对 `/responses` 发送 `stream=true`，只把 `response.output_text.delta` 转为业务层 `TextDelta`；reasoning 与生命周期事件不向学生暴露。正常结束必须看到携带 `status=completed` 的 `response.completed`，DeepSeek Responses 不使用 `[DONE]`。`response.incomplete` 映射为 `INVALID_OUTPUT`，`response.failed` 和终止事件前 EOF 映射为安全的临时不可用错误。

解析器按任意网络字节分片重组 UTF-8 SSE，兼容 CRLF、注释心跳和 `event:` 字段，每帧限制 1 MiB。未知或畸形事件、非法 UTF-8/JSON、完成但没有可见文本均拒绝；3xx 不自动跟随。正常完成、异常与消费者取消都会关闭上游响应，且已输出部分 token 后不静默重试。

## 历史诊断记录（2026-09-26）

以下保留当时的探针、失败和修复过程；其中“随后”“当前”“需批准”均指对应诊断时点，不替代上文现行配置或最新阶段收尾结论。历史报告不回写。

2026-09-26 严格模式兼容性排查：DeepSeek Responses 官方 `text.format` 文档未列出 `strict`。
隔离探针给现有请求添加 `strict: true`，两次中有一次返回值违反 `enum` 并被本地校验拒绝。
这证明当前配置下该字段不足以保证强约束，不证明字段被忽略的内部机制，也不代表所有 schema
均不兼容。生产适配器不据此添加字段，不静默切换端点或降级校验。原始脱敏报告见
`mvp-0.2-strict-probe-v1.json`（本地材料 `docs/acceptance/mvp-0.2-strict-probe-v1.json`）。
官方另有 [Beta 严格工具调用](https://api-docs.deepseek.com/guides/tool_calls/)，涉及 Beta Base URL
及 function 参数约束；它不是当前 Responses 文本输出开关。采用该路线前须批准接口策略，
验证当前模型/凭据/安全目标兼容性，保持业务 schema、ReviewAgent 和质量门槛不变。

随后用户批准 Beta 验证：直接传原 schema 的 enum 探针通过，但讲解 schema 被400拒绝；
常量转换为等价 `type + enum:[value]` 后 enum/讲解/代码/练习4项均通过。
这只是协议兼容性证据，完整质量和闭环须独立验收。对应探针报告为
`acceptance/mvp-0.2-beta-tool-probe-v1.json` / `mvp-0.2-beta-tool-probe-v2.json`。

完整Beta质量v1未通过：schema55/60，题型17/20，26项模型审核均不可用。
审核schema含无type的字符串enum，随后补等价类型映射并用1请求验证协议兼容；
这不代表语义审核或完整质量复验通过。仍有生成超时/缺字段/截断JSON证据，
不得宣称此选项已满足MVP0.2退出标准或自动启用。

2026-09-26 本地诊断修复：生产默认输出上限仍为4096，由中立共享常量统一；
质量基准从旧2048对齐为4096，不修改旧报告、原schema、98%门槛或严重错误召回门槛。
Provider失败只携带固定输出类别与验证过的非负整数token用量；未知/缺失用量为未知，
不能记成零。Responses incomplete/max_output_tokens 与Beta finish_reason=length
均安全映射为OUTPUT_TOKEN_LIMIT，其他非工具结束映射RESPONSE_INCOMPLETE；未知原始
供应商字符串不记录。完成响应中JSON语法/schema失败保留合法用量，不推测是否预算耗尽。
质量基准按尝试保存请求上限、固定错误类别和用量；ReviewAgent拒绝时仍保留失败尝试，
不把审核不可用当作事实错误检出。生成正文、密钥、完整供应商错误不进入这些诊断。

审核指令 `resource-review-instructions-v2` 明确问题分类：NULL解引用、释放后访问、
悬空指针和越界访问等执行/内存安全风险归 `code_safety`，即使描述出现在讲解或练习中。
非安全概念/复杂度错误仍归 `fact`；不得对正确内容虚构风险。业务审核schema-v3、
原错误集、检测口径及阈值不变，不把正确拒绝但分类不符的历史样本改计为通过。
`safety-diagnostic` 仅固定三请求（两个内存安全错误和一个正确对照），不是完整质量门禁。

画像提取指令 `profile-instructions-v2` 在消息中重申原schema的精确根字段及证据记录字段；
行为更新指令 `profile-behavior-instructions-v2` 要求唯一根字段 `updates`，证据不足时
仅返回 `{"updates": {}}`。原schema、允许字段、服务端证据归属和失败降级策略不变。
`diagnose_profile_contract.py` 以三次无重试请求验证一次提取和两次行为更新；
合法的无变化不是失败，也不能以此宣称已证明完整学习闭环。

## Phase 1 API契约

[T003契约落实](ADR/0008-provider-api-contract.md)与[OpenAPI](api/openapi.yaml)定义12个Provider操作，包括临时凭据提交及GET模型缓存/POST显式刷新。If-Match/配置版本、owner与CSRF、只写secret、同意与统一错误均固定；x-runtime-status=planned端点尚未实现。可运行 `backend/.venv/bin/python scripts/check_provider_contract.py` 离线核验引用/示例/安全字段，不能替代实际HTTP验收。

## Phase 1持久化与管理员轮换（T004）

迁移`0018_provider_connections`保存owner/原会话/到期时间、配置与凭据版本、非敏感KEK ID和AES-GCM信封；元数据只读响应不含secret/密文。`ProviderConnectionStore`在创建/更新/读取/解密/删除时验证会话与owner，行锁和版本检查防止并发覆盖；目标变更清除旧凭据，删除留禁用墓碑。内部`decrypt`不提供出站许可，T007仍须实现发送边界锁/同意与预算门禁。

依赖固定为[cryptography 50.0.2](https://pypi.org/project/cryptography/50.0.2/)，由pyproject/uv.lock锁定。服务端配置：`EDUMIND_CREDENTIAL_ACTIVE_KEY_ID`指向`EDUMIND_CREDENTIAL_KEYRING_JSON`中的KEK ID；JSON值为32字节KEK的标准base64。不要把真实值写入文档/仓库/输出。无配置不生成替代密钥，目录与health继续可用，凭据写入/解密失败关闭。

管理员从安全配置注入新旧KEK，设新active后在backend运行 `.venv/bin/python -m app.core.rotate_provider_credentials`。CLI按100行批次锁定并重包裹DEK，保留payload密文；中断可重入，失败只输出安全代码或计数，非零退出。仅所有有效凭据不再引用旧KEK、并明确处理历史备份后才退役旧KEK；提前移除会使旧信封不可解密。此CLI不创建/调用Provider，学生没有轮换HTTP入口。

凭据服务每次访问前幂等清理到期/丢失父会话的密文，API数据库runtime从首次使用开始每60s后台清理，退出时取消清理task；不加载KEK，失败只记录固定错误。过期使用独立逻辑检查，不依赖物理清理及时性。数据库/服务停机不能保证物理清空时限，恢复后先清理再操作。清理不删User或学习历史，不处理备份擦除。

隔离验证入口：`backend/.venv/bin/python scripts/run_provider_storage_tests.py edumind_catalog_phase1_<新轮次> tests/test_provider_connections_persistence.py tests/test_auth.py`，只接受专用测试库名，复用既有测试PG容器，运行迁移升/降/升与实际测试，移除Provider/主密钥环境配置；不要指向用户开发或生产库。HTTP连接管理仍由T009实现，T004只交付内部存储/维护服务。

## Phase 1临时凭据生命周期（T005）

每个ASGI lifespan拥有独立`DatabaseRuntime.temporary_credentials`注册表，关闭lifespan清除所有条目并取消活动operation；无需数据库/主密钥即可维持health。`TemporaryCredentialService`以服务端认证身份读取连接，要求当前版本、enabled与temporary模式，使用原始会话期限注册；不允许用临时清理路径改动持久信封或系统Key。后续HTTP依赖必须复用该lifespan注册表，嵌入式无lifespan调用不能临时创建另一个注册表冒充可恢复状态。

handle为32随机字节的URL-safe编码，只在所属进程/loop有效。绑定owner/session/connection/version/operation/purpose/model，不能独立鉴权。每会话最多4个待领取条目，等待最多300s或会话到期；原子单次领取后最长180s或会话到期，使用独立绝对计时器，持续token不能延长期限。所有终止路径清零并清空受控bytearray、释放条目；Python和HTTP库产生的明文副本仍遵循ADR-B7的有限保证。

后续T009连接修改/删除依赖必须使用`ProviderConnectionStore(..., on_change=registry.revoke)`，事务成功提交后同步通知所属注册表；`TemporaryCredentialService`也会为自己的store配置该回调，拒绝混用另一注册表回调。失败事务不通知。每秒另行检查DB owner/session/连接版本，检查1s未完成或失败即触发取消；取消慢的数据库检查不会延迟取消operation或等待无限清理，检查task被取消且异常不输出。session/operation绝对计时器独立于DB检查。业务代码必须在`async with registry.lease(handle, binding)`内管理并关闭上游流；租约只允许所属operation task读取secret。

注册表/条目/租约拒绝pickle与默认JSON序列化，不提供转发、恢复或持久Key替代路径。API/队列实现仍须遵守ADR-C6：不得把原始secret、handle或租约放进后台模型任务，只能移交已审核且不含凭据的DSL/Job ID。注册表与内部解密均不授予出站许可，T007须在实际发送边界实施锁、同意、目标校验和预算；T009接入HTTP时还须落实Cookie/CSRF、no-store、输入错误脱敏与前端表单清空。

测试入口：`cd backend && .venv/bin/python -m pytest -q tests/test_temporary_provider_credentials.py`运行离线生命周期测试，PG项在未配置隔离库时明确跳过；完整验收使用`backend/.venv/bin/python scripts/run_provider_storage_tests.py edumind_catalog_phase1_<新轮次> tests/test_temporary_provider_credentials.py tests/test_provider_connections_persistence.py tests/test_auth.py tests/test_catalog_mode.py tests/test_database_lifespan.py tests/test_health.py`。仅测试标记secret、受控DNS和FakeAdapter，无真实模型调用。

## Phase 1目标策略回归（T006）

云端目标须为公网单播HTTPS。除原有私网/回环/链路本地/元数据阻断外，拒绝组播、IPv6 site-local、带scope的DNS答案、保留地址、NAT64/6to4/Teredo转换地址；IPv4-mapped IPv6按内嵌IPv4分类。不能只用`is_global`判定；[Python官方ipaddress说明](https://docs.python.org/3/library/ipaddress.html)区分全球可达、组播、保留和site-local属性，分类也曾跨版本修正。本项目对转换地址采用保守拒绝，不宣称能够验证转换后的实际路由。云端HTTP在DNS前拒绝。

本地访问必须管理员设置`EDUMIND_PROVIDER_DEPLOYMENT=local`及精确IP:port白名单；回环IPv4/IPv6可以显式允许，危险特殊地址仍不能放行。域名全部A/AAAA须在白名单，混合公网/本地答案拒绝HTTP。本地判定不能由客户端标记扩大。每次实际尝试重新校验DNS，传给HTTP库的是固定IP URL，Host及TLS SNI保留原域名与端口，`trust_env=False`、`follow_redirects=False`；所有3xx（含同源）停止，无自动第二请求。

运行`cd backend && .venv/bin/python -m pytest -q tests/test_provider_target_policy.py tests/test_provider_target.py tests/test_provider_retry.py tests/test_provider_stream.py tests/test_deepseek_responses.py tests/test_deepseek_beta_tools.py`验证受控DNS、HTTPX Mock及实际构造的请求，不创建真实网络连接。后续T007/T008/原生适配器必须继续遵守同一目标策略与固定IP传输，不把保存连接时的DNS检查当成永久发送许可。

### T039 有界兼容探测

服务端内部 `ModelCapabilities.output_token_parameter` 只能显式选择 `max_tokens`（默认）或 `max_completion_tokens`；`thinking_enabled` 仅接受 bool/None，None不发送该字段。兼容适配器普通、结构化、流式共享此配置，不按模型名称猜测能力，不提供任意extra_body透传，不新增公共API/数据库字段。对默认开启思考的服务，冻结声明应选择覆盖思考与回答的总输出上限；不能把仅限制回答的max_tokens当作总费用上限。默认既有请求保持原样。

本轮主模型以64总输出加官方最多10 token偏差保留74输出预算，并显式关闭思考；定价/授权/冻结与实际结果见 `docs/acceptance/phase-1-provider-connection-v1/`。工具探测只验证远端函数调用格式，经同一ConnectionOperation权限/SSRF/预算/临时凭据通路，不执行工具，不宣称新增业务Tools接口。

T039修复版探测入口为 `scripts/run_phase1_provider_checks_v2.py`，r01/r02脚本和结果保留为历史证据。接入验收依据正常协议终止、非空有效响应、实际模型身份及严格schema；词面OK匹配单列诊断，不把不匹配冒称服务故障，不改写旧失败。新增服务端内部 `include_stream_usage: bool = False`，显式启用才发送 `stream_options.include_usage=true`；非流式/默认请求不变，无公共API/数据库字段。兼容能力声明及使用量须绑定具体配置，遵从目标声明，未知usage仍unknown。解码后的有界响应被观测后再解析，gzip/SSE用量不会直接从压缩wire读取；本地校验失败归probe_validation/INVALID_OUTPUT，本地意外错误归local_unexpected/SAFETY_FAILURE，Provider错误保留类型，敏感异常消息不记录。
