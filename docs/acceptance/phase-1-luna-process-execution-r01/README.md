# Luna四例过程校准：新执行包 r01

**材料与标签已获用户“全部确认”；真实调用尚未授权、尚未发生。** 本包只冻结这四例的准确执行路径、预算与停止规则。原制作草案保持原样，其pending描述是当时快照；本包[人工确认记录](labels-human.json)绑定`2373e15`的完整材料摘要，补充当前确认，不预签任何模型回答。

## 固定输入与配置

| 顺序 | 材料 | 已确认预期 |
| --- | --- | --- |
| cal-01 | 完整过程教学，题目明确要求推演中间状态及退出边界 | pass，无附带误报 |
| cal-02 | 过程教学证据分散在讲解/代码步骤/解析，过程题完整 | pass，无附带误报 |
| cal-03 | 正确代码与过程题存在，全部学生载体缺承诺的展开教学 | needs_human，具体指出教学缺口，不编造事实错误或“未出过程题” |
| cal-04 | 已教过程，题目只测最终算术 | needs_human，具体指出测量缺口，不误称未教 |

完整输入仍取自[确认材料](../phase-1-luna-process-calibration-r01/materials-review.md)，没有改动学生内容、权威目标、计划、动作或预期标签。判据见原criteria.md，仅供人工校准，**未注入Prompt**。这些是判据校准材料，受历史失败启发制作，不冒充正式独立集或泛化材料。

审核配置：`gpt-6-luna / low / max_output_tokens=8192 / temperature=0 / 60秒`，第三方`https://www.cbbb.fun/v1/responses`。生成仍为原DeepSeek配置，本包禁止调用生成模型。v4.9系统指令、业务Schema、Schema投影源码均未修改；原完整Schema校验、六项必检、引用定位/本地路由继续生效。

requests.json通过**实际perform → review_once → ExplicitRouter → ProjectedReviewAdapter → ExactTransport → MockTransport**捕获，四条与原确认预览逐字节相同；同时核对与上次实接成功请求的模型/推理/输出上限/temperature/系统指令/投影后Schema一致。Mock只脚本化返回pass以检查传输，不记作真实或语义成绩；8.8.8.8是离线固定IP，真实调用重新做公共IP目标审批并钉住IP、Host、SNI和路径。

| 请求 | 准确请求体字节数（不是tokens） |
| --- | ---: |
| cal-01 | 43228 |
| cal-02 | 43320 |
| cal-03 | 43152 |
| cal-04 | 42628 |

## 准确上限与授权边界

- **最多4次审核请求**，固定顺序，每个槽位至多一次；重试0、回退0、修正0。未知是否发出/崩溃/本地发送前失败也消耗预约，不重放、不退款给新槽。
- 每次最多8192输出tokens/60秒，合计最多32768输出tokens/240秒模型等待。传输关闭每次最多5秒，另受整轮墙钟限制。输入是冻结的有限完整请求体，实际输入tokens及费用以Provider返回为准，不把字节数当tokens。
- 从首个持久预约起**1800秒总墙钟**，包含人工等待；到期即停止，不因等待人工而延长。绝对授权期限为**2026-10-22 23:59:59（Asia/Shanghai）**，两者先到即停。
- 金额沿用用户“不用考虑费用，无上限”，不新增金额询问或虚构第三方单价。费用政策不扩展4次上限。Key只在新准确授权和持久预约后读取，真实.env不提交、不修改。
- 本次“全部确认”仅登记完整材料及标签确认。新manifest根、最多4次、墙钟与首败规则需另批，未批准`--run-one`在读取Key、DNS、HTTP及新私有台账前拒绝。

## 逐条核对与不可逆停止

每次命令最多发送一条，然后进入WAITING_HUMAN_REVIEW。执行器先核验HTTP/model/完整返回/原Schema/六项必检/usage/准确wire和本地结论；正例必须干净pass，教学负例必须needs_human且有具体未决、不带findings。自动结构检查不判断所有语义，不能代替人工。

下一条之前，必须对**上一条实际receipt摘要**记录人工结果核对：完整性、全部断言、全部引用与已确认判据，四项为真且issues为空。无finding时仍检查unresolved等全部文本；不能将“引用为空”解释成引用能力已经通过。结果签核不能沿用本次材料确认，不得预写后续结果、把Codex观察冒称Lee签核。

任何技术/结论/断言/引用失败即持久halt；超时、并发未知发送、崩溃、期限/墙钟耗尽也停止。第四条仍需实际人工核对，之后只能关闭为CALIBRATION_COMPLETE，不存在第五次调用。四例全过也**不能自动进入事实/安全/混合/新材料或正式T040**；下一包另准备/授权。

旧r02的1次400及11个未发槽、schema-validation-r01的1次200但CORRECT_CONTROL_NOT_PASS均只读核验、保持停止。旧状态判断题的原标签和失败不回写。新包不重用余额、不修改生产配置、catalog_only或T040 blocked。

## 验证、冻结及未来运行

零调用复现：

```sh
backend/.venv/bin/python scripts/prepare_luna_process_execution.py
backend/.venv/bin/python scripts/freeze_luna_process_execution.py
backend/.venv/bin/python scripts/run_luna_process_calibration.py
```

只有新准确授权记录存在且匹配manifest，才能使用：

```sh
backend/.venv/bin/python scripts/run_luna_process_calibration.py --run-one
```

该命令仍逐条暂停。真实结果在`local-materials/phase-1-luna-process-execution-r01/`，仅本地私有保存；对外报告仅复制审核结构、用量、安全错误及摘要，不保存Key、原始响应或思考正文。实际结果确认文件位于本包`assessments/<slot>.json`，绑定manifest/slot/receipt/reviewer/source_user_message与四项核对；未签不得继续。此文档不提供任何已填true的真实结果模板。

manifest.json绑定执行源码、旧失败证据、已确认材料/标签、准确请求和预算；禁止重封变化的旧包。validation.json为冻结前实际离线证据，results/preflight.json为冻结后只读检查记录；两者均不是模型结果。只读命令显示冻结信息，不把它的运行次数当实际调用计数。

后续事实/安全/混合及未参与修复新材料全部通过准入，才另冻结正式全集，验证Schema≥98%、自动正式成功≥95%、严重错误召回≥90%。人工通过不补自动分子，本包不产生正式T040分数。
