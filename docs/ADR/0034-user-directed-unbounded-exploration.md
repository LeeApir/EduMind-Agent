# ADR-0034：用户指定的不要求 token／费用上界的隔离开发诊断

日期：2026-10-27。状态：按本轮直接指令实施，限独立开发诊断；不修改生产准入契约。

用户明确指令：**“不考虑上界与费用，先完成项目”**。该指令解除本轮开发诊断对独立 token 上界证明、当前费率与金额上限的前置依赖，授权按已有 DeepSeek Flash 生成／AIAPI sol 逐场景审核路线继续推进。本登记不称用户独立逐哈希审阅了随后生成的新包，也不沿用旧批次批准。

## 范围和保留条件

新批次 p15-split-experiment-r01 使用原 34 个开发槽（12 支持课程、2 负例、20 审核探针）和最多 48 个场景审核。原顺序、需求、Prompt、完整 Schema、教学阈值、标签来源、逐槽真人核对、非 pass 暂停和严重错误停止保持。最多 250 HTTP（生成182／审核68）、串行、整批10800秒／课程600秒／单次120秒。没有自动服务商回退、审核重抽样或中断请求重发。响应体2MiB、请求体128KiB等工程字节限制仍保留。

输入／输出 token 与金额上限均为 null，不先确认费率；保留 max_output_tokens≤8000 作为请求参数，供应商忽略该参数或报告超限时记录事实，不仅因此拒绝。无法承诺供应商实际费用、停止后的计费或总 token 上界。费用始终 unknown，不把零账本占额记成免费或实际账单。

地址和模型保持 ADR-0033 A：DeepSeek https://api.deepseek.com/responses / deepseek-flash；AIAPI https://aiapi.world/v1/responses / gpt-6.1-sol，reasoning none。DeepSeek只读独立Key；AIAPI优先独立审核Key，否则仅当现有服务端配置的 Base URL **准确等于 https://aiapi.world/v1** 时读取该服务的 EDUMIND_PROVIDER_API_KEY，且两把Key必须不同。不会向其他地址复用Key或修改.env。已有用户配置指向该审核供应商，此项是配置来源映射，不是切换服务商。

## 独立入口，诚实保留未验证状态

旧 ADR-0033／冻结包／Mock-only入口原字节不动。新 scripts/isolated_diagnostics 实验模块显式复制冻结 Scheduler 的 prepare／settle 和原诊断 run_slot，仅替换实验准入、token／费用预约及结算限制；保留原请求构造、持久出站标记、租约、epoch、机械准入、原子发布与终态处理。生产 Scheduler／SendPolicy／数据库迁移不改。

实验适配器 bounded_output_verified 永远 false，input_upper_bound 主动拒绝；原生产 Scheduler 仍拒绝该适配器。新 ExperimentalScheduler 只接受该独立适配器。受既有PG列约束影响，attempt.input_tokens=1是明确标记的**兼容占位值**，request_json记录 input_reservation_is_placeholder=true / verified_input_bound=null / verified_output_bound=null；不把它当真实输入或上界。settlement 及私有原始响应记录供应商报告用量（可超过占位值及请求输出），真实费用另为null。

新独立 SQLite 只限制请求数和时间；金额和 token 不预约，未知发送停止且不得自动重发。统计展示报告用量及未知条数，不用占位值代替实际用量。每次真实请求先持久预约、请求SHA与发送标记；只向公共地址固定IP连接并绑定Host/TLS SNI，禁重定向和自动HTTP重试。协议／Schema／来源／引用、额外指令、安全或人工严重问题仍可阻塞。

## 完成和后续任务边界

实验通过仅证明这一明确例外下的开发结果，不能声称原有生产预算／token硬界已验证。T038若其余实际工程与教学条件不满足仍blocked；必须保存准确例外、实际失败和真人复核，不能以“先完成项目”伪造人工签核或将todo直接done。质量／性能独立样本、人工标签和阶段开放另按原任务条件推进。没有自动部署／生产模式切换／push／merge／跨阶段授权。

准确新包见 docs/acceptance/phase-1.5-split-exploration-r01。原H01–H08和既有签核课程保持封存，不用于本轮调试。冻结后从第一个槽开始，每槽产生输出后等待真人核对，主助手不得代填真人签核。
