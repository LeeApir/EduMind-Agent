# ADR-0036：sol 已知差异的显式兼容提案

日期：2026-10-27。状态：**仅离线准备，待具体契约批准，不授予真实请求或恢复批次**。用户选择：“保留 sol，先准备针对上述已知差异的明确兼容方案”。此前 r02 准确执行授权不扩展为本提案的调用授权。

## 证据及其边界

r02 准确包 cf5ee9e9，实际 2 次 DeepSeek + 1 次 AIAPI sol 均 HTTP200；原上下文形式错误已消失，PG 操作 succeeded、1 个场景 ready 且未签核。sol 请求 reasoning none，回显 low，usage 报告推理89／总输出685；output 含 reasoning 元数据项及最终 message。请求系统728字符，响应instructions765字符，唯一差值为 `\n\nYou are a helpful coding assistant.`（37字符，含两个换行）。这仅证明**响应回显差异**，不能独立证明真实上游隐藏上下文只有这些字符或指令完整性已获证。

旧入口首先在非零推理用量处停止 UNEXPECTED_REASONING；若只去掉此门禁，还会遇到额外output类型及instruction回显不一致。最终意见静态Schema符合、verdict=revise、3项minor，但每个引用都从/source/开始，原本地契约按source对象取相对路径，因此 EVIDENCE_SCOPE_INVALID。旧提示没明确根，新Schema也未约束根，这是本地说明不足，不能全部归咎服务商。离线删除这个前缀后精确引用可以定位，只用于根因证据，不改写原输出、原失败或账本。

## A：明确限定供应商兼容范围

保留 AIAPI https://aiapi.world/v1/responses / gpt-6.1-sol，只用于合成开发审核建议。后续拟显式请求 reasoning low，要求回显low并提供非负整数推理用量≤总输出；输出用量直接采用供应商报告的总输出（已含推理），不把推理token再次相加。缺失、bool、负值或总量算术不一致停止；不得伪称token硬上界已证。

instructions只允许与准确发送系统文本完全相等，或完全相等后追加**恰好一次**已知37字符后缀；缺失、前插、替换、其他后缀甚至多一个空格都停止。记录已知差异和 upstream_context_verified=false，不剥离后伪称原样请求，也不把这个后缀作为本地主动添加指令。该范围是需要明确接受的开发实验例外，生产网关和未知真实学情不继承。

只接受一个最终 assistant/completed/message，其中恰好一个output_text、严格JSON，无工具或额外文本。可在前面有至多一个reasoning元数据项：明文content及summary必须为空，encrypted_content只能是null或≤262144字符的不透明字符串，不解密、不输出、不转发到后续课程/模型，也不作为审核证据；原响应仅保留在私有原始证据中。未知字段、非空明文/摘要、工具/多消息、拒绝或截断停止。已有响应体2MiB、请求字节限制、Host/SNI公共IP绑定、无重定向/重试及密钥回显阻断继续保留。

## B：路径契约v2，不自动修正意见

development-scene-review-v2明确source_pointer的根是 payload.source；如 /scene/content/blocks/1/markdown，不得用/source/scene/...。Schema增加相应pattern和说明，源SHA、严格完整Schema、scope/verdict一致性、RFC6901转义与精确原文子串仍本地校验。原意见不删除前缀，不猜路径，不篡改quote。生成Prompt v2与原教学准入保持；旧20探针Prompt/Schema暂不变，**不因这个场景离线原型就宣称探针接口已适配**。

## C：后续最小真实验证提案（未授权）

先只用一个新的纯合成场景审核请求（包含正确对照与明确错误片段、准确source绑定，无真实学生/旧课程/H封存样本），仍同一sol服务；请求low、max_output_tokens=1536、store=false、非流式、strict。最多1 HTTP、120秒、0重试、0回退；异常/未知/任一未列差异或路径错误即停，不自动补样。报告用量与实际费用unknown，沿用用户“不考虑上界与费用”方向作为提案，不将它当新包执行批准。

本轮此前真实请求共6次，未来这1次若获准确授权则累计最多7；其余整批不调用，原250总额不重置。绝对截止仍为原2026-10-27 13:21:21（Asia/Shanghai，epoch1793078481.255075）；到期就拒绝，需用户另批时间范围，不靠新批次重置时钟。授权后还须冻结准确新请求、代码和单次执行器，未授权前不读Key/DNS/创建真实输出或PG，不启动r03或恢复r02。

## D：质量及来源保持

助手已先看课程、后看模型意见并分别保存来源。课程形式修复有真实证据，但数组名措辞及答案形式一致性有待改进；意见有参考价值不等于可绕过协议或教学准入。模型仍只提供建议；主助手逐槽复核明确delegated_assistant，不记human真值，不发布或替代独立质量验收。r02停止、unknown结算和旧失败不被离线原型撤销。

准确准备包：docs/acceptance/phase-1.5-sol-compatibility-plan-r01。纯函数原型没有transport、凭据读取、调度接线或可用真实execute；它仅证明拟议判断规则能拒绝变体，不证明AIAPI后续遵循或审核质量已通过。
