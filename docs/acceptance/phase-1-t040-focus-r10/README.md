# T040 r10：四条固定焦点审核，待独立运行批准

用户确认了[四条声明对原文的忠实转述范围](../phase-1-t040-span-review-offline/scope-confirmation.json)，没有预签模型判断或整篇覆盖。原 unsigned worksheet 保留历史字节；此次只准备独立实验，真实请求0、费用授权0，没有读取真实Key。

## 准确方案

- 冻结根：`e8388f55fe970be398d44bf4543d85f3dd03004e6c4fb6e44b98e44b1ef8923a`，对应[run.json](run.json)；[plan.json](plan.json)绑定目标、四条声明、原候选/上下文、期望标签、凭据文件metadata和退出条件。
- 同一服务端 `deepseek-flash` / `https://api.deepseek.com` / `responses_json_schema`；不切模型、不回退。
- 四个[静态实际请求](requests.json)：`focus-01` 至 `focus-04`，按顺序各最多一次。前两条来自原队列错误例，后两条来自原正确链表对照。完整候选与上下文保留；期望标签只在本地，不进入wire。未新增正式测试材料。
- `reasoning.effort=none`、temperature 0、每次最多2048总输出Token、60秒、零重试/零修正；总运行窗口最多3600秒，首次登记后不可续期。批准最晚有效至2026-10-18 23:59:59（项目本地时间）。
- 四次总费用保守上限 **CNY 8.551250**（8551250微人民币）；每槽取 `(实际wire字节数+1048576)*2+2048*8` 微人民币。见[独立费用推导](token-cost-proof.json)：以供应商1M整窗界覆盖全部模型输入，wire只加正余量，未把字节当Token。峰值输入2元/输出8元每M，未假定缓存或折扣。**不是预计消费，也不是供应商账户硬限额**；实际账单未知。运行前须再核对当日模型/能力/价格，无法核对或发生变更即停。

官方依据：[定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[Responses指南](https://api-docs.deepseek.com/guides/responses_api/)、[接口契约](https://api-docs.deepseek.com/api/create-response/)。沿用当日已核对的文档事实；实际权重版本未知。这里同时改变固定焦点输入、输出策略与预算，不能据此对旧r09作单变量因果归因。

## 执行与事实门禁

`run_t040_focus.py check` 无Key、无出站、无运行状态写入。`step` 必须先通过独立的 `run-approval.json`，精确绑定根/4次/8551250微人民币/范围确认/退出策略/期限/当日规格检查及真实用户原话。**该文件目前不存在**，范围“确认”不被当作付费授权。授权解析及Key读取仅属于受信本地执行者，登记JSON不是密码学身份证明。

单步通过现有冻结原始字节发送器发送，先记账再一次性取wire；共享根锁、固定运行登记、私有SQLite、一条未决请求限制、禁重试/重定向/代理及公共IP/Host/SNI校验保持。相同请求不重复发送；悬挂或结果持久化不完整即停止，未知用量保留未知，预留不退款。不修改r09的202来源或r08的186来源。

每个响应必须通过严格JSON/schema、request_id绑定、model/status、用量和none推理报告检查。具体缺陷漏检/错类、正确对照误拒、输出不确定/无效、用量/期限/凭据错误立即停止。错误例即使返回fact/revise也不代表事实判断正确。

每条成功返回后停在 `HUMAN_REVIEW_REQUIRED`：先通过只读 `report` 展示实际模型结论及发现，再由用户核对其是否命中该条具体问题、有无自身事实错误，核对证据绑定本次value_hash。不得凭此前范围确认预写通过；未确认不进入下一槽。`assess` 写入独立私有证据，失配或过期证据不能推进。正确对照的其他发现也不得默默忽略。

两个轨道共用 `span-selection-redesign-v1` 最多两轮、每轮4次、总共8次的退出规则。第一轮登记固定在 `local-materials/span-selection-redesign-v1/round-1.json`，不能更名重置或换账本。第二轮只允许在第一轮终止后独立冻结/批准；当前CLI只运行第一轮，不授权第二轮。以后若实现片段选择轨道，必须复用同一策略登记，不得另开计数。达到两轮或8次即结束本策略，保留目录版和T040 blocked，由用户决定其他方案。

## 验证与恢复

[验证记录](validation.json)：35项新增加238项相关回归，共273项离线通过，全部HTTP为MockTransport，真实socket/DNS在新测试中禁止。Ruff、两个旧准备器重生成检查、活动任务/历史批准/冻结来源核对通过；未批准的实际CLI `step` 以 `NOT_AUTHORIZED` 退出1，未建立r10账本/策略登记。

首次新增费用证明后，测试fixture漏复制该文件导致34项setup错误，补齐复制后相关套件273项全部通过，未弱化断言。旧339项完整应用证据沿用dff3a06，本次只运行组合涉及的238项既有回归；app未修改，未重跑生产mypy，scripts未严格类型检查。

成功receipt保留结构化模型回答、请求/响应摘要与usage；失败沿用冻结发送器限制，可能没有HTTP/上游status/model或原始响应，不能据此宣称唯一根因。mock不证明真实TLS、审核质量或供应商遵守费用契约。完整源文保留不等于整篇已审核，四条局部通过不替代T040原诊断/正式质量、自动提取或DSL/T041验收。

```sh
backend/.venv/bin/python scripts/prepare_t040_focus.py --check
backend/.venv/bin/python scripts/run_t040_focus.py check
# 以下仅在准确独立批准保存后运行；每次只发一条
backend/.venv/bin/python scripts/run_t040_focus.py step
backend/.venv/bin/python scripts/run_t040_focus.py report
# 实际用户核对后，受信执行者保存对应事实确认再调用assess
```

r09仍1次INVALID_OUTPUT停止、剩余37槽未运行；r08仍1次CONCRETE_DEFECT_MISSED停止。没有恢复或挪用旧余额。生产none/catalog_only保持，本次非T040完成提交，不push/merge。

## 2026-10-15 获批后的首条实际结果

用户yes批准9217215准确根/4次/CNY8.551250及退出规则，另存[运行批准](run-approval.json)和[当日规格核对](terms-verification.json)；以上“待批准/文件不存在”保留准备时历史，实际以新增登记为准。只发送focus-01一次，返回完成，当前停HUMAN_REVIEW_REQUIRED，后3条未发、没有人工assessment。

[完整结果与待核对观察](results/r10-focus-01.json)：5405输入+599输出=6004Token，推理0；预留CNY2.152262，峰值用量参考CNY0.015602，均不当作实际账单。主结论fact/major/revise指出循环队列回绕使rear-front失效，CAPACITY8满队列的差值0、出队后的差值-1均与原代码一致。附带发现空满判定/增量与取模的冲突，并把未使用stdio/stdlib头文件列成code_safety；未用头文件本身不能证明代码安全缺陷，该分类欠依据。建议不计干净审核通过，等待实际用户核对后才能保存本条事实结论或终止本轮；没有用原范围确认或费用批准代签。

215冻结来源、请求/响应摘要、私有账本1条及assessment为空核验通过；r09/r08原来源和停止状态不变。源码未改，273离线证据沿用9217215，不重跑业务测试；只读报告/准备器/活动任务/diff核对通过。T040仍blocked，none/catalog_only保持，本次非完成提交。

## 后续显式续测与第二条停止（2026-10-15）

用户在看见首条具体结果后要求“继续进行第二条，直到再次出现问题”，据此新增[显式续测例外](continuation-exception-focus-01.json)，保留首条误报与质量未接受，不伪写 `assess(passed=true)`。受信本地事务只把真实例外摘要写入首条receipt的assessment_hash，表示本条已获例外处置；这个字段在该条不代表事实通过。原冻结方案/退出附件/模型源码不改，次数、费用、期限、一次性wire与粗判门禁保持；用户这次指示覆盖原首条即停建议，并委托后续逐条观察至新问题。

[第二条实际结果](results/r10-focus-02.json)命中front==rear不足以判空，返回fact/major/revise，但附带重现冗余头文件code_safety分类，同时批评“未提入队满检查”造成失败路径说明不完整。原代码已做queue_is_full检查，说明也明确enqueue满时返回false；假设删除现有检查后的问题不是当前代码安全缺陷，说明详略也不足以支持该code_safety类别。按用户“再次出现问题即停”的委托，保存[Codex停止判定](delegated-stop-focus-02.json)，私有receipt绑定该摘要并将run持久置为ADMISSION_FAILED。该判定不是冒用Lee的人工事实签核。

第二条5384输入/667输出/推理0；本轮累计2请求、10789输入+1266输出=12055Token，预留CNY4.304320、峰值用量参考CNY0.031706，实际账单未知。正确对照focus-03/04未运行，不得将两条主缺陷命中当作审核器整体通过。

原215来源和准确根未变；只读核对旧r09 202/r08 186来源及原停止状态、两receipt、例外/停止登记摘要和私有权限，重新打开门禁确认为RUN_HALTED且无第二轮登记。代码未修改，273离线证据沿用9217215，未重跑业务测试；准备器/活动任务/diff核对通过。T040继续blocked，不同配置第二轮仍须独立冻结批准；当前轮不重试、不换账本、不自动恢复余槽或进入正式质量/DSL/T041。
