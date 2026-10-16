# r04 真实小诊断准入包

本包把原r04方案落实为可执行入口，保持四份请求字节不变。
冻结根：`91c9d5f818d1f675f22691f9e318aec89fc6f0828bb070f245c86cc1b07ea1db`。
当前工程准备完成，**独立人工标签/预算门禁尚未解除，真实请求0**。

## 需要核对的具体材料

请阅读 [human-review.md](human-review.md)，其中展开实际讲解、代码/关键步骤、题目/解析及内部计划。
预期标签为：

| 案例 | 预期 | 核对重点 |
| --- | --- | --- |
| trace-complete | pass | 明确状态2/7/16、i=3退出，题目要求中间状态及退出知识。 |
| trace-distributed | pass | 简短讲解没有轨迹，但代码关键步骤与题目/解析保留完整支持，不应因没有重复讲解而误拒。 |
| plan-only-gap | needs_human | 内部计划完整，学生正文仅有代码和泛化步骤；缺明确状态与退出支持。不得虚构事实错误。 |
| assessment-gap | needs_human | 已教过程，且目标承诺测量过程；题目只问下标、算术、返回/打印，未测循环过程。不得虚构事实错误。 |

上述是预制校准的待核对预期，未冒充人工已读或正式50个真值标签。
纯覆盖不足须具体指出缺口及位置；泛泛的“需要人工”不算语义识别通过。

## 模型、价格及准确上限

仅 `https://api.deepseek.com` / `deepseek-flash` / Responses JSON Schema，
`reasoning=none`、temperature=0。官方当前记录版本为DeepSeek-V4.1-Flash，不能冻结不可获知的权重版本。
2026-10-16已直接核对[中文人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
及[Responses总输出契约](https://api-docs.deepseek.com/api/create-response/)：
高峰缓存未命中输入2元/百万、输出8元/百万；max_output_tokens同时约束可见输出与推理。
证据见 [official-terms.json](official-terms.json) 及相同内容的 token-cost-proof.json。

最多 **4次、8.768806元、8192输出tokens**，每次输出2048、60秒，无重试/回退。
预算以整窗输入1048576加精确wire字节余量作保守上界：每次微元上限
`2 * (1048576 + wire_bytes) + 8 * 2048`，不是把字节当Token，也不是预计消费。
应用预留不是厂商账户硬限额；若厂商不遵守规格须停止，不保证厂商超规格时仍受本地上限约束。
模型价格或窗口发生变化、证据过期须重新冻结；不能只修改批准日期。

## 执行及停止规则

校验：`backend/.venv/bin/python scripts/prepare_coverage_admission.py`。
执行：`backend/.venv/bin/python scripts/run_coverage_review.py --run-one`。
每次最多发一条，返回完整结果后需绑定准确收据的人工继续；不自动遍历四条。
错误路由、协议/目标/费用/用量异常均持久停止，不能重试或退回已用预留。
路由匹配也只算结构门禁，须人工核对实际解释，不能自动宣称“v4.3有效”。

两份记录尚不存在，不提供自动批准CLI：

- `labels-human.json`：人实际核对后，绑定方案、四个材料摘要和标签摘要；不能由模型自审替代。
- `run-approval.json`：绑定新执行根、标签摘要、四次和准确费用、当日核验及真实用户来源。

未准入时在密钥/DNS/真实账本之前拒绝；凭据仅在后续真实发送前从服务器.env安全读取，
准备阶段只冻结文件元数据。新的本地私有账本目录为 `local-materials/phase-1-coverage-r04-real`，
默认不存在。原r01/r02/r03/r04方案不回写、余额不复用。

T040及正式100/20/20/10验收仍blocked；目录模式保留。四个预制数组例只能支持局部校准结论，
不能证明跨课程普适质量、严重错误召回或动态发布准入。
