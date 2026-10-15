# r03：固定检查项ID契约校准（未授权真实执行）

本轮只准备检查项ID修复后的校准，不是正式T040通过，不解除旧r01/r02停止，不复用余量。
用户本次“批准”承接零调用修复建议，不被解释为尚未呈交的新预算批准。当前真实调用/新费用授权0。

## 修复与保留的门禁

- Prompt v4.2与发送Schema明确 `coverage.checked` 只选本scope的原始五ID，不可写自然语言、
  翻译、重复或其他scope的ID；finding.anchors只选实际server anchor_catalog ID。
- 部分checked与真实unchecked/unresolved仍能表达；不强制填满或谎报已查，缺覆盖仍转人工。
  模型填出所有ID也不证明真正检查过，事实判断仍需独立核对。
- 原整单元无revise、资源两轮修正、硬安全/人工/发布/自动质量阈值不变。新规则进入政策摘要，
  已有待审依既有版本失效机制处理，不嫁接新结论到旧案件。
- r02真实prose返回由新Schema拒绝，旧本地结果仍保持needs_human/COVERAGE_INCOMPLETE。
  不将旧描述事后转成ID改分；旧r02账本1次/INVALID_OUTPUT、r01账本2次/SAFETY_FAILURE保留。

具体实现与风险见 [review-check-ids-v4.2](../../agents/review-check-ids-v4.2.md)。
统一持久Schema和ADR-0015准确批准文件不改；这里将既有ID/范围规则投影到请求Schema。

## 四槽与预期（仍需独立复核）

| 槽 | 预制材料及预期 | 最大预留（元） |
| --- | --- | ---: |
| correct-unit | 完整求和轨迹0→2→7→16、i=3停止与对应题；预期自动pass | 2.184292 |
| missing-unit-objective | 相同计划/图谱，讲解与练习未直接完成所承诺轨迹/边界目标；须具体指出并reject或needs_human，不强求fact/difficulty类 | 2.182308 |
| reachable-safety | 调用sum时必达长度3数组a[4]越界；具体检出code_safety | 2.155748 |
| fact-contradiction | 讲解称返回18，代码/轨迹16；具体检出fact，不虚构安全指控 | 2.184292 |

沿用r02配对样本家族与预期，仅重绑政策/依赖摘要并捕获实际新请求。这是校准，不冒充新独立
正式holdout，不合并旧成绩。标签仅由准备脚本输出，不发给模型；C仅展示、不编译执行。
每次实际返回仍须人工看完整结果，包括所有附带指控；类别或五ID匹配都不替代事实核对。

## 新准确预算与执行

**新请求上限4次，费用上限8.706640元，总输出8192Token（含推理）。**
DeepSeek Responses / deepseek-flash，none、temperature=0、2048总输出/次，单次60秒，
无工具/图像，无重试/回退。实际HTTP JSON字节及新Schema在cases.json冻结。

沿当日已核对的官方高峰未命中价格输入2元/百万、输出8元/百万和1M窗口的保守上界1048576，
每槽微元 `2*(1048576+wire_bytes)+8*2048`。wire_bytes只作正余量，不等同或估计Token。
这是合同预留上限，不是预计消费、实际账单或平台账户硬限额；若厂商不遵约，应用不能保证
阻止超扣，应停止如实报告。执行当天需再次核对价格/窗口/输出限制，变化或无法确认停止。
证据见token-cost-proof.json与[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、
[Responses总输出定义](https://api-docs.deepseek.com/api/create-response/)。

```sh
backend/.venv/bin/python scripts/prepare_om_admission_r03.py --check
backend/.venv/bin/pytest -q scripts/tests/test_om_admission_r03.py
# 只有新准确批准登记后才允许一个请求；当前应退出2：
backend/.venv/bin/python scripts/run_om_admission_r03.py --run-one
```

新r03使用独立base/private/run_id/批准摘要/账本。当前无run-approval.json、无真实账本。
批准须由受信维护者根据用户实际答复登记准确root、4次、8706640微元、标签摘要和当日条款日期，
不能套用r02或误登记历史。到北京时间2026-10-18 23:59:59失效。
批准前拒绝读取Key/DNS/建真实账本；执行时先持久预留，后读版本绑定0600凭据和出站。
每次只发一槽，完整实际收据经真实人工continue后才发下一槽；失败或未知用量不退款/退槽。
协议/范围/预算/严重漏检/重大无据指控/正确对照非自动pass等触发持久停止，不自动重开。

校准通过也不自动启动八类诊断或100/20/20/10正式验收；正式新例/独立真值、派生调用执行器与
费用仍需冻结批准。T040保持blocked、catalog_only，T041/T042未启动。
