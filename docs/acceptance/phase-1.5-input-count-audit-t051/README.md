# T051：r03 输入计数差异零调用排查

结论：**现有证据支持客户端之后的请求转换／计量口径不一致，不能把差异判为客户端漏传 Schema，也不能精确认定某一中转内部实现。r03 停止正确；不应放宽相等门禁。相等门禁自身又不足以证明上下文完整性或输入／输出硬上界。** 本次新增 Provider 请求 0；T038 继续 blocked。

## 请求与回执对照

原始证据的路径、长度、SHA256 与逐字段摘要见 [comparison.json](comparison.json)。只提交摘要，不复制私有正文或回执追加指令。原件与原 r02/r03 manifest、批准、停止账本及 unknown 预约均保持原字节。

| 项目 | 客户端／预计数 | 生成回执 | 判断 |
| --- | --- | --- | --- |
| 地址 | `POST /v1/responses/input_tokens` | `POST /v1/responses` | 同源同模型；不是在另一个厂商计数 |
| 请求体 | 同一 10,208 字节；SHA256 `7f8e56421d98920c9603c61d842839c1bbdcaa2b10c7239a34032233a55af34f` | 原冻结传输器将相同 `request.content` 发送到两端 | 代码路径＋实际 Mock 重放支持相同；历史只保存一份 body，无独立计数 body／抓包，不能伪称有两份历史抓包 |
| 输入 | system 1,542 字符＋system 4,088 字符＋user 960 字符；无顶层 instructions／历史会话 | `instructions` 为 26,968 字符 | 回执先精确拼接两段 system（用两个换行，合计 5,632 字符），再追加 21,336 字符／21,348 字节 |
| 追加文本 | 请求未包含 | 编码助手身份、共享工作区、协作／commentary 等指令 | 是回执中的明确额外文本；不是本轮课程规划输入。**回执声称的指令不等于独立证明实际模型上下文** |
| 输出上限 | `max_output_tokens: 8000` | `max_output_tokens: null` | 回显不一致，不能据此证明实际取消了上限，也不能证明仍受 8,000 硬限制 |
| 结构输出 | 原投影 Schema＋`strict:true` | Schema 值相同、strict 仍 true；多一个 description 字段 | 未发现 Schema 值被替换；回显相同不保证服务端逐条执行 |
| 输入计数 | 1,677 | 6,507 | 差 4,830；生成回执分项为 instructions 5,725＋text.format 456＋items 324＋2＝6,507 |
| 输出／缓存／推理 | — | 输出 480；缓存 0；推理 0 | 不能用缓存减免或输出推理 token 解释输入差额；这些仍只是服务报告 |

冻结源码位置：`scripts/acceptance_support/p15_diagnostic_transport.py::CountedTransport.handle_async_request`，用原 `request.content`、headers、extensions 构造计数请求，然后发送原生成请求；`p15_strict_transport.py` 在此之前加入完整原 Schema 指令及 strict 标志；`backend/app/services/deepseek_responses.py::_request_body` 把消息放在 input 数组。没有先计数、后加入完整 Schema 的客户端路径。历史没有持久化 HTTP 状态、headers、实际 IP/TLS 记录；这里不补造。

## 根因能确认到哪里

1. **已确认的直接停止原因**：冻结传输器比较 `usage.input_tokens != count`，触发 `USAGE_BOUND_MISMATCH`；不是业务 Schema／首槽教学质量失败。离线用实际原件、明确注入 HTTP 200 的 Mock 重现相同异常；Mock 的 200 不回填历史 HTTP 状态。
2. **已确认的协议表象**：客户端系统指令与回执 instructions 不同，输出上限回显不同，预估计数与生成报告不同。这些独立于任何 tokenizer 猜测。
3. **证据支持的首要解释（推断）**：中转／上游链路在生成路径把 system 转为 instructions 并追加编码助手模板，计数路径未使用同一最终上下文或计量实现。回执的完整前缀、额外模板和 instructions 分项支持它。还可能是回执合成／回显错误、计数端 tokenizer／型号映射不同、生成 usage 错算；现有原件无法排除。
4. **无法确认**：具体由哪台服务追加、追加是否实际送入模型、4,830 中各项的精确占比、实际模型快照、账单与输出硬上限。不能把新增字符按 chars/4 或未知模型的本地 tokenizer 换算后称作根因证明；也不能拿单次差值作未来固定补偿。

## 现有门禁是否适用

OpenAI 官方文档将输入计数定义为同一 Responses 输入的完整计数，要求使用同一 payload，并涵盖消息结构与 Schema 等开销。因此相等检查有明确的兼容契约依据；它不是无条件适用于任何中转实现的数学定律，官方说明也不保证 cbbb.fun 的行为。[OpenAI Docs：Counting tokens](https://developers.openai.com/api/docs/guides/token-counting)、[计数参数参考](https://developers.openai.com/api/reference/python/resources/responses/subresources/input_tokens/methods/count)。

对准确获批 r03：**适用且必须保留，本次应停**。它检测出两个路径未能满足本轮的计量一致性要求。6,507 小于已预约 32,000，只是事后报告在占额内，不能证明发出前的独立输入上界，更不能替代未来请求保证。常量 `input_upper_bound=32000` 不是模型／中转的独立上界证据。

对未来包：**相等是兼容性检查，单独不充分**。离线把计数改成 6,507、保持实际额外指令和 null 上限，原传输器会结算通过。这个反例不依赖真实探测，说明即使两端同样计入错误上下文，数值相等仍不能证明课程指令未被污染或输出限制可信。另见[待审提案](contract-proposal.md)；本轮没有修改任何生产或冻结运行门禁。

## 交付、验证与交接

- `python3 scripts/audit_p15_input_count.py --check`：纯只读，先核对原 r03 全部冻结源码／原始证据／停止账本，再重新计算摘要并精确比较；无 start／advance 功能。
- `backend/.venv/bin/python -m pytest scripts/tests/test_p15_input_count_audit.py -q --junitxml=/tmp/edumind-p15-t051-offline-r01.xml`：9 passed、0 skipped。实际原件重放停止、计数相等但指令变异的反例、干净对照，以及计数／指令／上限／Schema 分别异常的离线判据；禁用 socket connect、DNS 和 .env 文件访问。
- 原 r02/r03 结果 checker 仍分别预期退出 2，表示原 blocked 事实被准确验证；不是质量通过。Ruff、工作流及 diff 检查结果见 validation.json。

本次足以完成门禁适用性判断，**不需要真实探测，也未提出或使用新真实预算**。进一步精确定位内部实现，优先由用户／服务商提供两端最终上下文摘要、型号／tokenizer 映射、usage 口径及输出限制证明（本轮不代发消息）。如这些证据仍不足且确需探测，另提只含合成输入的最小准确请求包、HTTP／token／时间／费用边界，单独申请；不能借此次排查执行 r04 或完整课程。

T051 仅完成排查及待审方案，不解决 T038 真实准入。r02/r03 均保持 stopped，累计仍为 4 HTTP／2 生成，unknown 合计 64,000 输入／16,000 输出占额；不追认结算、不退款、不重启、不继续 T039，不 push／merge／部署。
