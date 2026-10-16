# v4.4 / r05：同样本覆盖诊断运行包

本轮独立于已停止的r04。2026-10-16用户已批准四次/8.791654元及原四判据绑定；
首条完整正例已获用户实际确认；第2条分散覆盖真实一次，模型/local均pass。
本轮累计2次、两个正例自动通过，停在第2条实际结果人工核对门禁，余2反例未发。
见[第2条完整材料与意见](results/trace-distributed-02-review.md)。
当前源码基线4d66a7d（v4.4）；新执行器、准备器、测试和依赖一起冻结，共581来源文件。
运行根：`fdbb5c6563289f5f61ded5cf473fd8d3ba5dba204fd3045e2fc18eb9d8e145e2`。
完整可读内容及原始目标见 [human-review.md](human-review.md)，精确输入/请求在 [cases.json](cases.json)。

## 只换输入契约，不换学生内容

四例各三份resource envelope与r04逐字相同，content_digest逐项相等；完整计划也相同。
每例student_content_comparison记录12份资源的envelope摘要与内容摘要，准备器发现变化就拒绝。
为绑定新请求/政策，服务端身份、依赖、动作引用及unit_digest重新生成，不冒用旧审核结果。

每例保留旧冻结original_input_snapshot及其原摘要，先验证其与原binding一致。
旧goal/node_id/code_language只做结构包装成为metadata，reference_context完整保留；
新goal从原始快照取得，绝不从plan.goal反推。包装版本和两份快照、摘要均可核对。
准备器经当前生产review_once、输入投影和DeepSeek请求编码器捕获实际发送字节，
不另写简化Prompt；实际HTTP发送仍必须与冻结wire完全一致。

## 四组原判据

| 顺序 | 案例 | 预期及人工核对重点 |
| --- | --- | --- |
| 1 | trace-complete | pass；显式total=2/7/16、i=3退出及过程题。先复验r04被误转人工的完整正例。 |
| 2 | trace-distributed | pass；简短讲解，但代码关键步骤和题目/解析提供过程支持，不要求重复。 |
| 3 | plan-only-gap | needs_human；具体指出学生内容缺循环状态和退出教学支持，内部计划不能补交付。 |
| 4 | assessment-gap | needs_human；具体指出已教过程但题目未使用过程知识，不能把最终算术当过程测量。 |

后两例不虚构事实/安全finding。路由匹配只是初步门禁，泛泛“需人工”不是缺口检出；
须核对具体内容位置、缺口和影响。用户本次明确保留原判据，新的身份/摘要需在新轮批准中绑定，
不把原r04的预算或实际结果签核直接搬来。原50正式真值并未重新签核。

## 准确上限

仅DeepSeek `deepseek-flash` / `https://api.deepseek.com/responses`，JSON Schema，
reasoning=none、temperature=0、每次max_output_tokens=2048、60秒，无重试或自动回退。
最多 **4次、8.791654元、8192输出tokens（含推理）**。

2026-10-16核对[官方中文人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：
按高峰缓存未命中输入2元/百万、输出8元/百万，不假定折扣。输出总上限契约见
[官方Responses文档](https://api-docs.deepseek.com/api/create-response/)，证据存official-terms.json。
每次微元预留为 `2 * (1048576 + exact_wire_bytes) + 8 * 2048`，用整窗加字节余量保守计，
并不把字节当Token；上限不是预计消费或实际账单。本地预留不是厂商账户硬限额；
执行日条款须复核，价格/窗口/输出契约变化或无法验证则停止并重新冻结。

| 案例 | 精确wire字节 | 保守预留（元） |
| --- | ---: | ---: |
| trace-complete | 42432 | 2.198400 |
| trace-distributed | 42248 | 2.198032 |
| plan-only-gap | 41440 | 2.196416 |
| assessment-gap | 42635 | 2.198806 |

## 执行门禁与后续顺序

校验：`backend/.venv/bin/python scripts/prepare_coverage_v44.py`。
执行：`backend/.venv/bin/python scripts/run_coverage_v44.py --run-one`。
新run-approval及精确案例绑定已按用户明确批准登记；首条后仍须绑定准确收据的人工继续。
准备阶段仅读取.env文件元数据，不读取密钥；发送前由安全执行器校验冻结元数据并读取服务端配置。
新私有账本位于local-materials/phase-1-coverage-r05-real，目前两条complete、无halt。

批准后先发完整正例一次，保存完整实际结果；准确收据的人工确认后才发下一条。
任一协议/目标/用量/路由错误持久停止，不重试、不清halt、不退款复用预留。
四条全部匹配且实际语义经人工核对后，才准备事实、安全等其他诊断的新范围和预算；
诊断通过后再作正式质量准入。本四请求预算不授权这些后续阶段。

r04保持1次失败/INVALID_OUTPUT halt，余3不发；原r01–r04材料/批准/结果不改。
本次无生产业务变化，离线验证不是模型语义通过、严重召回或跨课程质量证明。
T040仍blocked、catalog_only，T041/T042不启动。
