# 可见证据正反例

以下只说明拟议校验，短 ID 和摘要为示意，不是已签核样本或可执行请求。

假设已发送且按该精确顺序呈现的视图包含候选 `candidate_A`、`view_digest=V1` 和三个不同字段：

```json
{"id":"t0","kind":"explanation","text":"先检查 head 是否为 NULL。"}
{"id":"t1","kind":"question_stem","text":"先检查 head 是否为 NULL。"}
{"id":"t2","kind":"state","text":"{\"caller_head\":\"i0\",\"p\":null}"}
```

模型输出 `candidate_A`、`target_id=t0`、`evidence_quote=检查 head`，且 `severity=minor`、`area=difficulty`、reason 非空：引文命中该次真实发送给模型的 `t0` 值，机械有效；模型观点与教学正确性仍需独立核对。`t1` 虽有相同文字，指向另一题干，不自动与 `t0` 互换。`t2` 引文 `"caller_head":"i0"` 比较的是模型解析 JSON 后实际看到的 `text` 字符串，不能用仅存在传输层的 `\"` 转义作为证据。

以下均拒绝：

- 引用本地压缩前文档的 `occurrences` 或散列，实际视图没有该字符串。
- 对候选 B、新修订或其他槽使用旧视图的 `t0` 和审核意见；即使两个单元内容或短 ID 恰好相同也拒绝。
- 对任意两条不同目标，引用只存在于另一目标而不存在于所选目标的文字；引用空字符串、伪造 ID、跨两个单元拼出句子或隐式改变字符。
- 模型声称 `pass` 却携带 issue、`revise` 无 issue，或 `unknown` 无 uncertainty；`fact`／`code_safety` 问题不能作为普通修复继续。
- 用程序参考事实覆盖 B 的原答案或状态后再称之为 B 的输出；将模拟 malloc 成功写成实际执行成功。
- 模型回复审核的证据仅是可见目标 ID 或路径、没有该目标的实际 quote；目标 ID 正确不能说明讲解正确。
- 非规范别名（如 `t01`）不能当作规范的 `t1`；原文 `[\*hi\*](url)` 的解析标签 `*hi*` 是派生视图字段，不能冒充原始 Markdown 的连续摘录。

如果一个空标签引用的显示结构为 `image`，可以将 `image` 作为该次可见结构单元的非空证据，但它是程序生成的类型标记，不是学生原文。引用目标 URL 和标题应分别是实际可见的惰性字符串；HTML 和 URL 均不激活。
