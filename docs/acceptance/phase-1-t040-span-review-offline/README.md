# T040 离线重构：由程序定位，分开检验提取与审核

用户在r09停止后同意重新拆分任务，本次只实现离线原型、原历史样本测量、待人工核对的四条焦点清单及退出约束草案。真实Provider请求0、费用0，未读Key；r09剩余37槽不恢复、不转授，T040仍blocked，生产none/catalog_only保持。

## 两条独立路径

[隔离模块](../../../scripts/acceptance_support/span_review_offline.py)没有HTTP、凭据、Provider、模型回调或生产注册。

1. **原文片段选择**：resource-line-spans-v1按既有叶字段精确分行（保留换行），每行超过256个Unicode码点再等长分段，合计≤512段。程序保留block/path/start/end/原文，模型仅收到s0001这类短ID、文本及是否需要交代；其余完整原候选和参考上下文仍发送。模型返回声明描述+主/相关片段ID，服务器恢复和校验精确锚点并生成claim_id，模型不计算偏移、重抄引用或计算SHA。绑定候选、上下文、配置、阶段、probe与片段表摘要；跨候选/配置/上下文或阶段的响应不可混用。
2. **固定焦点审核**：先对[四条助手草拟声明](worksheet-review.md)作实际人工范围核对，再准备仅验证审核器的独立实测。当前都是unsigned/PENDING_HUMAN_SCOPE_CHECK，不冒称人工清单已批准。新focus协议只需回填request_id及判定/发现，其他独立发现单列保留；局部pass不覆盖其他发现，也不代表整篇通过或自动提取有效。源文义被草稿改写、判断不确定或输出不可用时不得成为质量证据。

[选择预览](selection-previews.json)、[焦点预览](focus-previews.json)、[清单原始数据](worksheet.json)均只用于离线审阅，没有可执行真实轮次。旧r09发送器、根/批准/模板、ADR-0011/0013/0014原附件和分块版本不改；本版本不是把现有resource-field-blocks-v1默默替换成分行。未来接入须独立冻结算法/Prompt/schema/安全发送与预算，继续严格解析JSON及先记账门禁；本次不接公开API或发布路径。

## 不能从工程结果推出的结论

一个片段可能含多项声明，一项声明也可能跨片段或涉及远处代码。分行/编号只是定位，不能证明语义清单完整。每个非空片段要有主声明引用或排除理由，相关引用不算主覆盖；纯空白按程序规则交代但仍保留原文可作上下文，不允许仅用空白作为断言依据。错误排除仍可能隐藏事实，独立覆盖检查与人工核对仍然必要。

清单和覆盖合计K仍≤16，超限/不确定/无法定位即失败，不删前16条、不合并独立断言伪装适配。排序由程序按源位置确定；相同位置的不同断言分别保留。完整ID映射及coverage_checked只证明协议步骤通过，semantic_coverage始终NOT_VERIFIED，production_approved始终false。聚合、修正、动态预算、实际发送、完整资源资格均未接入本原型。

模型侧位置重复字段已去除，坐标在本地维护；这只减少格式负担，不证明真实推理消耗/延迟改善。新增片段表本身仍有输入开销，局部协议预览不是实际API wire或Token证明，不能直接用JSON字节推断成本。

[原8历史样本测量](historical-size-screen.json)均在512段内，片段数分别124/163/119/105/91/1/1/1。只测工程尺寸，语义声明数均NOT_MEASURED，不能据此认定K16适合整篇。正式新样本未读、未用来调参。

## 待核对与退出约束

[worksheet-review.md](worksheet-review.md)包含原引用和四条拟审核表述。请实际人工核对其是否忠实原文及上下文，不预签未来模型回答。期望判定仅来自原已批准历史标签，单独保存在[expectations-not-for-model.json](expectations-not-for-model.json)，不进入任何模型预览，不能当作本次模型实测结果。

[退出草案](exit-policy-proposal.json)的strategy_id固定为span-selection-redesign-v1：两条路径共用最多两轮真实实验/每轮最多4次/总计最多8次尝试，不按案例或路径重置计数。先检验审核器，再决定是否值得测试ID选择。协议/用量/预算失败立即停；具体缺陷漏检/错类、正确对照误拒或审核回答自身事实错误均不能过门禁。失败后同配置不重试；第二轮必须有实质区别、独立冻结和批准。达到两轮或8次即结束本策略实验，保留目录版和T040 blocked，再由用户决定其他模型/策略或人工审核，不能滚动开新轮。

该退出规则目前是**离线提案**，没有建立真实策略台账，也没有具体收费预算（cost_cap=null），真实授权仍0次/0费用；不是额外8次调用许可。人工范围确认、真实轮次预算、具体结果事实确认和生产开放分别处理。四条局部诊断不替代原五检出/五分类/一正确/两长或正式质量指标。

## 验证与恢复

[验证记录](validation.json)：39项新增+61项相关原型回归=100项离线通过，Ruff、草稿重生成校验和任务依赖通过。涵盖Unicode/CRLF/空白/长行/标量字段、源位置完整恢复、超限拒绝、未知/重复/跨请求ID、映射遗漏、排除冲突、覆盖补项/超K、不确定、焦点/其他发现分离与保留原文。测试判定均合成，不能证明提取或审核语义质量。

旧339项完整相关回归沿用dff3a06记录，本轮未重跑；app无变更，未重跑生产mypy，scripts依旧不在严格mypy范围。r09 202冻结来源和1次INVALID_OUTPUT、r08 186来源和1次CONCRETE_DEFECT_MISSED均只读核验未变。没有删除、重置或解除旧停止状态。

```sh
backend/.venv/bin/python scripts/prepare_t040_span_review.py
backend/.venv/bin/python scripts/prepare_t040_span_review.py --check
backend/.venv/bin/pytest -q backend/tests/test_span_review_offline.py backend/tests/test_claim_review_prototype.py --tb=short
```

下一步先取得对四条清单的真实范围确认，再形成可审查的固定焦点测试方案和有界费用。没有用此前r09的批准代签新策略，也没有把此原型提交标为T040完成。

## 后续范围确认与独立r10准备（2026-10-15）

用户已明确确认四条声明忠实于原文及上下文，另存[范围确认](scope-confirmation.json)；以上unsigned/PENDING描述保留原草稿历史，当前范围状态以新增记录为准。此确认未签核事实结论、整篇覆盖或模型费用。新的[四条固定焦点r10方案](../phase-1-t040-focus-r10/README.md)已完成隔离执行准备，独立4次/CNY8.551250及两轮8次退出约束待准确批准；原草稿、退出提案及旧实测结果不改，真实调用仍0。
