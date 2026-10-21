# Qwen审核诊断执行包：零调用实现与冻结

本轮批准仅用于落实0bfab25方案的零调用执行前置，不是新的真实请求或费用批准。本包保持原设计1个候选、原4＋新8材料、v4.5 Prompt/Schema/政策、生成deepseek-flash、审核qwen3.8-max-0902非思考/json_schema。原方案与材料不改写；所有旧停止运行/余槽/账本不恢复，catalog_only不变。

## 真实路径与审计

run_qwen_review每次只运行一个槽。批准/标签/当日官方条款复核/来源摘要门禁全部通过后，先SQLite持久预留，再读取本机inactive Aliyun配置和创建私有测试DB临时连接。只能选inactive且模型与T039端点摘要匹配的唯一Qwen组，active DeepSeek组必须仍存在且Key不同；不修改.env、不使用默认Key或静默回退。

仅允许loopback15437、数据库edumind_catalog_qwen_review_20261017，禁止生产数据库。使用真实GuestSession、ProviderConnectionStore、TemporaryCredentialRegistry、ConnectionConsent/Route/ModelCapabilities和ConnectionOperation，purpose=connection_test、data_categories=probe，内容只为原授权的公共合成诊断材料。仍执行目标检查、DNS/IP固定、版本/同意/撤销检查与单次预算authorize；不绕过catalog_only来生成真实学生资源。生产默认/factory/adapter不改。

实际调用review_once，由其产生固定quality审核请求，AuditedGateway保留原诊断8192覆盖，经生产OpenAICompatibleAdapter发出。ExactTransport核对准确请求字节、选定Host/SNI/path/HTTPS/公共IP，不缓存headers或Key；原始response只计大小和哈希，decoded录制留内存给实际解析器。审计桥用观察到的请求/响应字节及明确模型/能力/Prompt/政策摘要产生TransportAudit，不用占位值或合成pass。官方同一快照别名qwen3.8-max-2026-09-02可接受，其他模型拒绝；原回答保留实际信息。

所有成功、失败、超时、取消均关闭临时registry，撤销连接，核对连接disabled、持久Key为空和版本失效。模型调用外层60秒覆盖读取配置、目标/DB/临时凭据准备、HTTP和完整解析；到期不续发请求，随后只允许最多10秒本地撤销清理，不延长Provider等待。旧临时凭据TTL和operation期限不因此放宽。私有成功receipt保留实际review_record与结果，不存原始响应、思考正文或真实密钥；结构完整不等于语义通过。

## 8192与8202预算

请求参数严格max_completion_tokens=8192，官方允许最多10token误差，因此输出预留与返回用量检查为8202。新独立qwen_review_budget预算核相对旧phase1_budget只改变目标输出天花板8192→8202（以及说明文字），其他SQL持久预留、失败/未知不退款、顺序/并发/冻结/授权规则保持。旧核和历史来源字节不变。实际wire摘要固定，不能靠8202预留偷偷提高8192请求参数。

12槽精确费用预留仍为 **161.071260元**，全局上限164元，不假定免费或缓存折扣；每次先预留再读Key/DB/HTTP，不重试/纠错/工具探测/回退/换模型。任意请求失败、费用或用量异常、Schema/模型不符即持久停止并淘汰唯一候选，已占槽不返还。超过8202也停止。费用/窗口/输出误差假设必须执行当日复核，Provider账户账单不由本地核控制。

## 两阶段与逐条人工门禁

每次仅一个请求，保留准确proposal/receipt摘要；下一槽要求真实Lee确认记录：完整性、全部断言、全部主辅引用三项均true，issues空。不能由合成测试、模型自身输出或预算批准预签结果。模型正向类别/路由检查只作结构信号，无一般自然语言语义证明器。混合样本还需保留缺口说明与严重code_safety/reject。

第4条全部完成且签核后，另要求screen-pass.json准确绑定四份实际receipt的人工“admit_generalization”决定，才允许进入8例新材料。第12条也须签核；--check-complete只报告DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION，永不报告T040质量通过或自动发正式验收请求。任何实际语义或引用错误使用eliminate记录单独semantic-stop并持久halt，不能改写原回答。负向人工结论同样持久停止；没有下一候选。

失败观测仅允许状态码、规范错误、用量、finish枚举和原Schema安全位置；未知字段名只保留哈希，不保存Provider原文/字段值/异常消息。正常结束但criterion不符也保存实际失败review，不删finding或放宽Schema后改分。

## 批准与复现

准备：backend/.venv/bin/python scripts/prepare_qwen_review_execution.py --write。
可复现隔离PG/MockHTTP验证：backend/.venv/bin/python scripts/verify_qwen_review_execution.py（只使用既有专用测试容器，剥离Provider环境变量，数据库迁移head，不读取.env）。
执行前置：专用数据库已迁移head；独立run-approval.json绑定本包12次/161.071260元（164总上限内），labels-human.json批准本包12标签材料。当日terms-YYYY-MM-DD.json记录官方来源复核并绑定本proposal和原official-terms摘要，跨日需新不可变复核文件；不得篡改原预算批准日期来续跑。复核记录不是新模型调用。

真实单槽命令：backend/.venv/bin/python scripts/run_qwen_review.py --run-one。
最终只读检查：backend/.venv/bin/python scripts/run_qwen_review.py --check-complete。

本轮不会创建真实run-approval、labels-human、当日terms或私有运行账本；未批准CLI必须在Key/DNS/DB/私有目录前拒绝。实现批准文件scope=zero_call_implementation_only，不能替代真实费用批准。后续真实请求须在本包来源与准确预算冻结后单独授权，不自动使用用户刚才的零调用实施批准。
