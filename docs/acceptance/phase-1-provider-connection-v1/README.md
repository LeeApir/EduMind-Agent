# T039 真实 Provider 接入

当前用户已批准本轮仅 `qwen3.8-max-0902` 最多4次请求、费用上限人民币1元；失败和超时计数，禁止重试、回退、模型列表刷新和执行工具，不包含T040/T041或动态开放。授权见 [独立记录](authorization-20261014.json)，历史ADR零预算保持原样。

[冻结轮次](run-r01.json) 绑定实际端点摘要、模型、公开探测正文、源码/锁文件、官方定价/能力和输出限制。顺序为普通响应、严格JSON Schema、固定工具调用格式、流式响应；每项至多1次/10秒/单并发。生产P1连接工厂/ConnectionOperation负责真实PG会话/所有权/版本/SSRF/DNS/TLS/临时凭据；透明HTTP transport仅核对正文并捕获有界响应的安全摘要/usage，不替换IP/TLS/追踪钩子。

先在本地SQLite持久预留请求及保守费用，再读取单次凭据；费用不以免费额度/缓存折扣抵扣。max_completion_tokens=64、enable_thinking=false，按官方最多10 token偏差预留74总输出，UTF8正文长度加512模板开销作为输入上界。usage缺失记unknown并停止；stream放最后。原始响应和Key仅在内存，报告不保存头/明文Key/会话token，结束撤销连接并核对数据库无持久密钥。

[离线结果](offline-checks.json)：专用PG122通过/0失败/0跳过，mypy166源、Ruff通过；首轮夹具/入口失败如实保留。仅声明真实云端兼容目标结果，其他Ollama/Anthropic/Gemini/星火适配器无本轮配置/凭据/预算，不能借Mock或本目标成绩冒充验收；T039整体完成标准不自动降低。

运行入口：`backend/.venv/bin/python scripts/run_phase1_provider_connection.py --freeze`（只运行一次，已冻结）；在专用测试PG环境迁移至head后执行同脚本无参数。固定SQLite台账拒绝重启后重用已耗尽槽位，冻结附件改变将拒绝发送。严禁拷贝新台账重跑同一授权。

用户模型候选和条件兜底偏好见 [选择记录](model-selection-20261014.json)；本轮不调用DeepSeek，不自动扫描其他候选。

## r01 实际结果：停止，未通过

已提交冻结源码 `5014173` 后执行真实云端1次，HTTP200、1.381369秒；探测记录为 `TEMPORARILY_UNAVAILABLE`，未取得模型ID/usage。原脚本只保留泛化错误与响应摘要，无法追溯区分内容校验、解析或传输环节，不据此指认厂商/账号故障，也不能宣称认证或模型能力通过。此前聊天“响应解析未完成”表述过窄，以此证据限制为准。

严格首败停止：剩余结构化/工具/流式3项未发送，0重试/0回退/0工具执行；台账不清零或另建来绕过失败。按冻结付费价和上界持久预留人民币 **0.01086元**，实际token及账单未知，不能按0记账或宣称免费。连接已撤销，独立PG确认无持久Key。原始脱敏结果 `local-materials/phase-1-t039/r01/result.json` 与SQLite台账核对一致，全部冻结源码附件SHA核验通过；[提交摘要](results/r01.json) 分开标记真实云端/未测原生适配器。

T039保持blocked，T040/T041未开始。后续先离线增强有界、无正文的异常阶段/类别、编码和响应结构诊断，再单独冻结诊断轮次；不能在原轮次默默重试。

## 用户要求排查后的单次诊断 r02

用户询问“排查是无法调用吗”后，在原4次/CNY1总授权内单独分配1次/CNY0.03诊断，原r01台账不改不重置。冻结源码16f46ec，实际请求正文SHA与r01完全相同；未切换Provider/模型/参数。诊断经真实ConnectionOperation权限/SSRF/TLS/临时凭据，原生产OpenAICompatibleAdapter解析；旁路只记录解码后长度/结构/usage与安全异常类别/源码行号，不记录正文/Key/headers/异常消息。

[真实诊断结果](results/diagnostic-r02.json)：HTTP200，1.108264秒，生产解析通过，模型ID `qwen3.8-max-0902`，usage输入17/输出2，共19 tokens；正常JSON、无error、1个choice。因此**当前配置可以调用**。精确OK匹配false、编码gzip，实际复现了两处测试观测缺陷：r01把本地内容检查的ValueError统一归为TEMPORARILY_UNAVAILABLE；r01按原始压缩wire字节读JSON导致usage丢失。离线使用OK.示例复现前者、gzip合成响应复现后者，36项回归/Ruff通过；诊断已通过，但不把其结果改写为r01通过，不推断第一轮未保留的具体正文/唯一根因。

累计真实2次，持久保守预留CNY0.02172，首轮usage仍unknown；本次19 tokens按冻结原价估算CNY0.000276，并非真实账单。两轮结束均已撤销连接/核对无持久Key。T039仍未完成结构化/工具/流式及其他适配器验收，未启动T040/T041。现有总4次预算只余2次而剩余主模型探测3项，不静默超额补跑。
