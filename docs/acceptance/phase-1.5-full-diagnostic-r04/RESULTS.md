# 完整开发诊断r04：首槽协议停止，T038未完成

准确批准：提交c2ccb04，manifest `beeca0bb41eaa659cc1bcda76b7236dd9b398e3dd7b16a44fbf5ff9e91cb50b2`，ADR0037 A—C及具体合成外发、新250HTTP/3小时/token金额例外。窗口2026-10-27 17:38:26—20:38:26（Asia/Shanghai）。批准登记与独立账本绑定；旧批次没有恢复。

## 已执行与未执行

首槽D01-known实际4 HTTP，均200：DeepSeek规划1、场景primary1、原预算内format_repair1；AIAPI sol场景审核1。不是重试整个课程，没有第二槽、自动补样或未知重发。其余33槽（11课程、2负例、20probe）全部未运行。

规划首次Schema正确；场景primary的code块多出 `markdown: ""`，违反原oneOf/additionalProperties，计入首次结构失败。一次原有结构修复去掉非法字段后通过，**不篡改原始输出抹去失败**。primary_schema保留[true,false]，已观察2项首次结构仅1正确；不能以修复后成功称首次98%通过。

实际隔离PG生成操作succeeded，1个可学但未签核场景ready，准入规则v2实际生效：`int a[5]`等围栏/行内代码未出现r03的反斜线破坏。首完整场景16.098563秒，生成操作done16.310953秒，来自实际PG事件相对操作创建时间；不是HTTP/首token，也未证明冷暖，T038性能仅报告不替代T041。

## 准确停止原因

sol报告completed/model正确/low，最终JSON是来源摘要准确的pass、issues=[]，但本包完整协议不通过：

1. 响应完全缺少instructions字段，而本包要求等于发送系统文本或准确37字符后缀。精确本地拒绝 `UNRECOGNIZED_INSTRUCTION_ECHO`。
2. reasoning元数据含1项summary_text（422字符），本包只允许空summary。内容未展示、未解释、未转发；同项content为空，encrypted_content是不透明2020字符字符串。只在响应副本中补echo后，仍被 `NONEMPTY_OR_UNKNOWN_REASONING_ITEM` 拒绝。

在独立副本中同时人为补echo/清空摘要才通过余下校验，这仅是**定位第二阻塞的反事实**，不是服务商真实通过；原始响应、账本unknown和旧失败均未改写。CLI把非Refused异常隐藏为TRANSPORT_DATABASE_OR_EXECUTION_FAILURE，这是安全通用码，不代表实际网络或数据库失败。只读观察者重新运行原纯验证器得出上述准确原因。

账本stopped/UNKNOWN_SEND，3个生成attempt complete、1个审核attempt unknown；这里unknown是协议可信结算未成立，四次实际HTTP200响应都已保存，不能说没发出或服务无响应。scene_review_started=1、finished=0、slot_output=0、标准assistant_review=0；未伪造完成报告。

## 用量

全部原始响应报告52884输入/3107总输出（均非已核实发票）。生成共7756/3005；sol45128/102，其中33推理已包含102，不重复相加。可信结算仅生成部分，审核保留unknown，不能隐藏其报告用量。

此前这些实验10请求保留后，累计14请求、reported81890输入/14958输出。真实收费及币种未知，不写0；剩余额度没有自动转给新批次。45128输入没有独立计数证据，不能仅据数量断言追加了什么编码助手指令或具体隐藏上下文。

## 主助手实际盲核

先阅读发送给sol的完整课程源并保存D01-known-blind-review.json，再读取sol最终意见；标记Codex assistant / delegated_assistant / independent_human_truth=false。

固定初始数组的数值映射、0..4边界、循环访问和修改代码经静态手工推演一致，无生成C代码执行。题组重新列出初始数组，因此q1答40有题面依据；不直接因代码中曾赋99就宣布答案错。但开放解释题q4接受自然语言多种表述，固定长句作精确匹配键的可靠性未证；不得凭模型pass宣布答案/评分100%。已知code_first没有落实为代码第一块，配对未运行，画像对也没有通过证据。

本次兼容和质量均未完成，未做正式答案/节点核定、产品签核、发布或评分准入。

## 字段语义及下一步

[官方迁移指南](https://developers.openai.com/api/docs/guides/migrate-to-responses?api-mode=responses)允许系统/开发者指导放在顶层instructions或兼容input消息中。本次实际发送使用input[system]，没有顶层instructions；已读取的官方指南没有保证把input里的系统消息原样复制到响应instructions。**推断**：本地把两者强绑定是额外观察门禁，不能将缺echo直接解释为系统指令未送达，或据此断言中转站不可用。官方文档也不证明AIAPI实际上如何处理或留存请求。

后续应先零调用区分“发送体准确”“回显可观测”“上游上下文完整性”三种证据，具体兼容策略取舍需新批准；不自动放宽本批规则。并先解决开放题的精确评分适用性，而不是立即启动下一轮付费同题重试。T038继续blocked，T039不领取。

## 验证

只读checker `backend/.venv/bin/python scripts/check_p15_full_r04_results.py --check`预期退出2，表示准确确认已停止而非通过；核对450源码/材料、准确批准SHA、所有私有文件SHA、只读PG来源、四次请求/状态/响应和原始/反事实区别。新增12项结果回归passed/0skip；此前85项为准备阶段离线/隔离PG-Mock结果，不冒充本次真实质量通过。容器恢复exited，无后续模型调用。

完整原件仅私有目录`/tmp/edumind-p15-full-diagnostic-r04`，不公开推理摘要或不透明密文。结果摘要results.json，盲核blind-review.json，验证results-validation.json，证据索引evidence-index.json。
