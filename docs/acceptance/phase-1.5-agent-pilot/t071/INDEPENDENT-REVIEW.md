# T071 独立复审

评估者：`pilot_independent_evaluator`，身份 **assistant**，非human。复审日期：2026-10-28。候选与测试后复核时间：2026-10-28T15:38:12+08:00。

**结论：通过本次T071限定离线实现的独立复审。** 已核对原手写期望未改，并实际运行113项离线测试，113 passed、0 failed、0 error、0 skipped。本轮未发现仍可绕过当前槽检查点、全批停止或有效操作窗口的实质门禁问题。此前P1-04-G1/G2在本候选的共享批次规则及投影核验中已闭合。

通过只适用于下述准确候选及离线边界，可供主助手完成T071交接并重新冻结T069准备材料；不是T069采集完成、T070效果评估、e03核定、真实调用/费用批准或生产准入。当前没有选择e03。

## 准确候选与独立期望

候选清单：`docs/acceptance/phase-1.5-agent-pilot/t071/review-candidate.json`。

SHA256：`3c5ac5827061c562fd951fc266804616030b36c6161b5d1b0ec9e727824361c3`。

清单内7个文件的实际SHA在测试前、测试后均逐一匹配：

| 文件 | SHA256 |
| --- | --- |
| `scripts/isolated_diagnostics/p15_pilot_batch.py` | `78ebf0bc5ea79805b210c5d79c37246113c1f2a7b9dacda22f8aa4959873c1ae` |
| `scripts/isolated_diagnostics/p15_pilot_execution.py` | `0c1243049fdcf4bfca94ba6852ecbb600c8ff792e40fb61fe1a04754853f61bf` |
| `scripts/check_p15_pilot_execution.py` | `fc798fc371dcef56a4d23de11c911ccb581b66aa9fe00801cfe20e48daa30804` |
| `scripts/isolated_diagnostics/p15_pilot_replay.py` | `213d7f8c840e02367725c17bea1881e6452932f6ad9dc3de196bd89ef026c1e2` |
| `scripts/tests/test_p15_pilot_batch.py` | `7b25affe2c681cc1085827538e57b9250c8fdb4d3e75485c6163952d99724b9b` |
| `scripts/tests/test_p15_pilot_wire_execution.py` | `6540d4e709e467d02fcfcb180147b63ddd63255506ccec35e51d09bbe3ae81d9` |
| `scripts/tests/fixtures/p15_pilot_batch_manual.json` | `fcec4421aaf162af0d9e6c3a8da044cd5fd7dc748f73babb52374dbecfc4452c` |

最后一项与本助手在读取Reducer实现之前写出的独立fixture摘要相同：38例，8个接受轨迹、30个拒绝轨迹。状态/拒绝位置和语义理由均为原手写值，没有用Reducer结果更新期望。测试不只要求反例抛错，还确认拒绝点之前的前缀合法，并在独立指定事件处拒绝；正例逐项核对状态、位置、pending、预约/可信结算/独立接受数量，以及指定的调用终态。

## 实际检查与命令

先只读检查候选清单自身SHA、每个源码SHA及原fixtureSHA，核对38例/8正30反。完整阅读Reducer、Journal接线、checker接线、Replay及全部T071测试源码后，执行：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_pilot_batch.py scripts/tests/test_p15_pilot_wire_execution.py -q -p no:cacheprovider --junitxml=/private/tmp/edumind-p15-t071-independent-review-20261028.xml
```

实际结果：**113 passed in 1.33s**。JUnit再次解析确认tests=113、failures=0、errors=0、skipped=0。其中T071批次49项（手写38例＋新增集成/对抗11项），既有wire/账本/逐槽回归64项。

证据：`/private/tmp/edumind-p15-t071-independent-review-20261028.xml`。

JUnit SHA256：`d1bb00f1a44f11fa25296e1de375cfcc8a1d50dfa15932abb9848e773954c5b6`。

两测试模块均有autouse网络拒绝夹具，覆盖`socket.getaddrinfo`及`socket.socket.connect`；集成路径使用HTTPX MockTransport及合成resolver/凭据字符串，不加载真实Key。按主助手澄清的授权，Mock集成可以调用纯抽象`build_example`构造既有开发数据；没有用它生成或修订独立38例的期望，没有运行C、真实Provider、DNS/HTTP，也没有读取私有e02答案或H材料。

本助手未独立重跑mypy/Ruff/全项目检查，不将开发方这部分报告计为本轮独立运行证据。仅新增本审阅文件；未改候选源码、fixture、任务账本、执行日志或Git历史。

## 关闭G1：发送端与检查器共享完整批次投影

- `reduce_batch`从grant/inputs导出的初始顺序及实际receipt按序应用事件；开始、当前slot/arm、唯一在途ticket、B4/C5阶段及90总预约都进入同一状态。不能只靠各槽数量相同伪装整体合法。
- 支持槽的model advisory result只能把当前槽转为`awaiting_assistant`；完整调用序列须已可信结算且末次是审核。随后独立报告必须绑定该pending的准确slot/arm/result及package/assistant身份；accept才推进，stop立即终态。
- 任何已停止路径不再允许新预约、发送、可信结算或接受推进；已有未完成调用保持unknown。独立stop、workflow stopped result与传输停止都不会被后续合法槽重新激活。已发送ticket的迟到原件观察仍可保留，不产生成功或退款。
- `Journal.record`在事务内先核验历史链及批次/调用投影，再应用待写事件，原子保存新事件与batch/calls投影。`guard`同样核投影；不再通过手工advance使数据库状态领先receipt。
- checker在逐槽Replay之前调用同一Reducer，并将最终batch和完整calls投影与SQLite逐字段比较。事后将DB改为active/下一槽，或重算摘要链后将下一臂预约移到上一臂accept之前，均不能只靠局部合法结果过关。

实际集成回归覆盖了重算链后的独立stop后拼接后续槽、accept前跨臂预约、直接调用record绕过发送规则、篡改DB状态及reservation时钟竞态的回滚，均通过拒绝断言。原严格全版本独立报告与逐槽完整请求/FSM重演仍保留，Reducer未取代教学事实审核。

## 关闭G2：有效操作使用实际receipt epoch

- 正常预约、sent、可信settled、model pass检查点及独立accept必须满足准确`[start, deadline)`，且不早于之前已观察的receipt时间上界。允许合法的同epoch事件，不把非递减误写为严格递增。
- 检查器直接把SQLite中的实际receipt epoch交给批次规则；逐槽Replay的合成时钟不再作为真实窗口认证依据。独立等待仍消耗原绝对窗口，不能通过新一臂或新报告重置截止时间。
- 截止后的原件和候选只可作为不推进的证据保存；late_slot_result不打开有效检查点、不增加首轮结构或端到端成功分子。调用和未运行分母保持原值。
- 对reserved/sent/settled/assistant_review/slot_result分别把实际epoch改到截止点并重算链的集成回归，以及原手写起点前、截止等号、窗口内时间倒退、重复与漏检查点反例，均实际通过拒绝断言。

## 限制与准确声明

1. 本轮验证的是记录的时钟数值、因果关系与窗口策略一致，不是独立UTC时钟认证。`clock_source_independently_attested=False`必须保留；同一用户重写全部证据及未签名时钟来源的限制仍在。摘要链及共享规则不等于密码学身份或真实账单证明。
2. 非推进性的stop、原件观察可在窗口外保留。代码中的`not timely`也涵盖时钟回退等异常，因此late_slot_result标签本身不能证明自然墙钟已经越过deadline；该路径先停止、保留证据且不推进/计成功。后续准确执行包应按实际实现描述“迟到或时钟异常的非推进观察”，不声称所有receipt都在窗口内或标签本身构成时钟证明。
3. 纯Reducer只验证批次生命周期。角色Schema、完整请求/响应、逐槽FSM、所有版本的独立报告及候选内容仍由既有层分别核验；Reducer接受轨迹不能直接当课程正确或模型质量通过。
4. 113项离线测试和源码审阅不能证明全部故障组合、服务对新Schema的实际兼容、模型教学质量、成本或中转隐含上下文。未做真实Provider或C执行，也未准备新独立课程样本。

本轮未发现上述局限可转为新的出站、可信结算或推进权限，故不作为T071核心门禁的阻断项。后续仍须完成新的全链准确冻结、独立e03核定、准确执行包及用户真实预算批准；T069/T070和T038的原门禁保持独立，不据本次测试改分或提前完成。
