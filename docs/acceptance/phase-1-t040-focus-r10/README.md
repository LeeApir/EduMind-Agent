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
