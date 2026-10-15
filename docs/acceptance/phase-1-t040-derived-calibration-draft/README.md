# T040 逐声明审核：真实发送组合离线验证与试跑草案

本次用户“好”承接c8b5c31后的下一步：只实现离线发送组合与准备方案，真实Provider请求0、费用0、生产catalog_only。T040仍blocked。

## 本轮实现与结果

[阶段契约](../../../scripts/acceptance_support/derived_review_contracts.py)固定提取、独立覆盖、逐声明和整体审核的Prompt/schema，所有字符串/数组/对象均有有限结构界；本草案禁用修正。规则不含原病例ID、目标问题数量或标准答案。审核只定位问题/条件/反例，不生成替换代码和修复公式。

复查补齐了预算内核的实际wire：原文叶子blocks包含block_id/path/text，审核阶段提供review_identity；模型可以复制服务器摘要，不需自行计算SHA。此前合成输出由测试计算摘要，未暴露这个真实可用性缺口。本轮保留完整候选与参考上下文、原始锚点和父DAG要求。

[发送组合](../../../scripts/acceptance_support/derived_responses_sender.py)先consume持久化尝试，再执行公共地址策略、固定IP连接、原域名Host/SNI和当前凭据/同意lease校验。直接content=冻结wire，不经SDK重序列化；禁代理环境、重定向、自动重试。一次尝试的重复调用在读取凭据/DNS/HTTP之前失败。响应原始字节≤2MiB、拒绝压缩、严格JSON（拒绝重复键/NaN）、只接一个assistant消息和一个输出文本块，非预期工具输出即停。

原始和JSON解码后的密钥回显均检测，防止Unicode转义绕过；不持久化原始响应、推理正文、Header或供应商错误正文。仅保留经校验结构化结果/摘要及安全数值。失败已观察的有效用量保留，未知或不安全数字为null；预留不退。取消、协议/用量/身份错误和超时均持久停止，无自动修复或重试。

[验证记录](validation.json)：42项新增发送/契约测试+原269项=311项离线通过；Ruff、生产app mypy166源文件及流程/历史批准/冻结校验通过。测试仅合成模型/lease/费用、MockTransport和合成DNS，真实socket/DNS在测试中禁止；未验证真实云端兼容性、延迟、成本或语义质量。scripts不在严格mypy范围。原6提案来源、r08 186来源和1次停止台账保持。c8b5c31旧内核验证摘要通过该提交归档核对，不覆盖旧验证记录。

## 两例草案与启动缺口

[proposal.json](proposal.json)由以下命令生成/核对，明确DRAFT_NOT_EXECUTABLE：

```sh
backend/.venv/bin/python scripts/prepare_t040_derived_calibration.py
backend/.venv/bin/python scripts/prepare_t040_derived_calibration.py --check
```

使用原queue:explanation:1错误例，再使用原correct-list-concept正确对照，完整原payload/标签摘要固定；模型不接收标签。K16、无修正，每例最多19次，共最多38次潜在请求；不是38条资源，不等于原完整诊断，也不是当前调用授权。每次拟low/8192总输出/120秒，具体整体期限待启动方案冻结。错误例仍须检出原两项缺陷及类别，正确对照不能误拒；汇总后展示具体证据，经独立事实核对和人工门禁才能推进，不能以泛泛revise或自动quality_failure=null晋级。

依据每个可接纳父结果≤65536 bytes、完整候选及blocks、最终清单新增16个服务器ID，以及二次JSON字符串转义≤两倍的保守界，固定两例的最大wire界分别为564005、550049 bytes，小于草案1MiB上限。此界仅针对这两例和当前派生/schema，不是Token界，也不保证提取≤16声明或质量通过；超限应失败，不静默省略/合并独立断言。

2026-10-15核对[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，deepseek-flash峰值未命中输入2元/百万Token、输出8元/百万Token；仅本日标价观察，非实际账单或未来保证。[官方Token文档](https://api-docs.deepseek.com/zh-cn/quick_start/token_usage/)提供比例估算及离线示例，并未建立当前模型/Responses服务端格式的严格上界，因此本草案cost_cap=null，不能用字节界直接冒充Token证明；旧wire+1024做法也不自动成为本轮证明。[官方Responses兼容说明](https://api-docs.deepseek.com/guides/responses_api/)用于核对协议与usage口径，不能替代实际接入验证。

仍须补齐：实际输入Token及服务端格式上界证明；据此计算最坏费用和固定期限；受信真实运行审批解析、当前服务端凭据版本/同意lease提供方；独立事实评估与人工组门禁的组合。发送模块不读env/Key、无CLI或生产注册，Approval和lease是受信调用方输入，不会从任意approved=true JSON产生人类授权。模拟lease不证明实际凭据可用、同意未撤回或权限正确。

目前不申请付费额度，不能通过填一个approved=true或绕过缺失证明启动。随后将形成准确根清单/源码/目标/费用与事实核对入口，再单独呈交真实调用方案；旧r01–r08不恢复、不拼分，不进入正式质量/DSL/T041。
