# T039 真实 Provider 接入

当前用户已批准本轮仅 `qwen3.8-max-0902` 最多4次请求、费用上限人民币1元；失败和超时计数，禁止重试、回退、模型列表刷新和执行工具，不包含T040/T041或动态开放。授权见 [独立记录](authorization-20261014.json)，历史ADR零预算保持原样。

[冻结轮次](run-r01.json) 绑定实际端点摘要、模型、公开探测正文、源码/锁文件、官方定价/能力和输出限制。顺序为普通响应、严格JSON Schema、固定工具调用格式、流式响应；每项至多1次/10秒/单并发。生产P1连接工厂/ConnectionOperation负责真实PG会话/所有权/版本/SSRF/DNS/TLS/临时凭据；透明HTTP transport仅核对正文并捕获有界响应的安全摘要/usage，不替换IP/TLS/追踪钩子。

先在本地SQLite持久预留请求及保守费用，再读取单次凭据；费用不以免费额度/缓存折扣抵扣。max_completion_tokens=64、enable_thinking=false，按官方最多10 token偏差预留74总输出，UTF8正文长度加512模板开销作为输入上界。usage缺失记unknown并停止；stream放最后。原始响应和Key仅在内存，报告不保存头/明文Key/会话token，结束撤销连接并核对数据库无持久密钥。

[离线结果](offline-checks.json)：专用PG122通过/0失败/0跳过，mypy166源、Ruff通过；首轮夹具/入口失败如实保留。仅声明真实云端兼容目标结果，其他Ollama/Anthropic/Gemini/星火适配器无本轮配置/凭据/预算，不能借Mock或本目标成绩冒充验收；T039整体完成标准不自动降低。

运行入口：`backend/.venv/bin/python scripts/run_phase1_provider_connection.py --freeze`（只运行一次，已冻结）；在专用测试PG环境迁移至head后执行同脚本无参数。固定SQLite台账拒绝重启后重用已耗尽槽位，冻结附件改变将拒绝发送。严禁拷贝新台账重跑同一授权。

用户模型候选和条件兜底偏好见 [选择记录](model-selection-20261014.json)；本轮不调用DeepSeek，不自动扫描其他候选。
