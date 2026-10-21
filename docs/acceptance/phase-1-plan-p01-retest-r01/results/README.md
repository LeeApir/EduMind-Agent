# P01单次重测结果：摘要误读复发

已按“重测一次”完成独立1次请求，运行随后无条件停止。原r02仍维持原halt，账本摘要逐字不变；未发P02或第三次请求，没有恢复旧58次额度。

- HTTP200、gzip完整解码、完整业务Schema、精确模型`gpt-6-luna/high/8192`、实际请求/回答摘要均通过；新旧请求实际字节SHA-256相同。
- 冻结正例要求`pass / accept_plan`，本次仍返回`needs_human / needs_human`，不符合标签。
- 模型再次将计划条目digest `f83f…b0015d`与参考快照容器`source_digest=b333…3b219`比较并误报冲突。实际p11、p34所指字段值均为前者；后者已独立重算确认为整个references容器摘要。p34不支持模型的条目digest声明。
- 本次没有再提出“三题”意见，也未引用p20；不能把上次全部错误都算作再次出现。
- 本次输入8713、输出1123，共9836 Token；与前次合计2次、20025 Token。相同开发样本的两次观察不能当作代表性总体错误率。

[实际完整回答](actual-response.json)、[核对草稿](codex-assessment-draft.json)和[运行摘要](summary.json)分别保存。Codex审阅14项断言，覆盖全部12模型文本字段及2个不同锚点；草稿仍为gpt_draft/pending/signed=false，Lee实际输出签核未代填。机械标签不符和停止已确定，草稿不是独立人工评分或正式验收分子。

当前仅此单例结束，不修改Prompt/Schema/模型/材料，不自动重复直到通过。T040仍blocked，H封存，无生产发布。原始包络和完整请求/用量/私密台账只保存在local-materials/phase-1-plan-p01-retest-r01/，不入Git。
