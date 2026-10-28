# T069 执行入口第二轮修正后的最终预审

评估者：`pilot_independent_evaluator`（**assistant**）。源码快照时间：2026-10-28T14:37:31+08:00。

结论：**暂不通过预执行门禁。** 新增逐槽离线重演已闭合上一轮报告的完整请求比对和模型审核状态重演缺口，但批次层面的独立检查点、停止顺序和真实时间窗口仍没有被证据检查器重演。它们属于同一P1-04“完整因果与停止证据”问题，而非新增质量阈值。

主助手已说明这是两轮有实质区别的修正，若仍未闭合即按AGENTS标记blocked并向用户求助。因此本次建议保留当前候选与证据，不自动进行第三轮修补、最终冻结、e03选样或真实调用；是否继续修正应由用户决定。本助手不修改task.json/process.txt或代替主执行者登记任务状态。

本轮仅只读源码/测试源码并新增本文档，没有执行Replay、被测引擎、C、测试、DNS或HTTP，没有读取Key、私有独立答案或封存材料，没有选e03。64项测试通过为开发方报告，本助手未重跑，不记为独立运行验证。

## 本轮确认已改正的部分

- `p15_pilot_replay.py`使用无HTTP能力的ReplyAdapter，将原始角色请求经`wire.request_body`完整重建后，与记录body作canonical全量比较。生成的完整request body包含固定参数、消息、Schema和全部payload，因而覆盖上一轮列出的额外上下文、temperature、tools、previous_response_id、额外消息、question_keys及修复goals漂移；无响应/unknown调用也先比较请求。
- Replay走相同ExecutionB/C及ProviderGateway/FSM，要求恰好消耗全部记录调用，并将完整重构result与原件等值比较。单槽模型unknown、事实/安全意见及第二次revise不能仅靠伪改state变为成功；停止后在同槽补调用会留下未消耗记录。
- 缺少原始响应的传输停止只能是最后一个未知调用，不能推出模型回复、成功或退款；无法重构的传输停止明确列入`unverified_transport_stop_reasons`。该标记是证据局限，不是已验证的真实网络原因。
- 四类本地拒绝使用准确spec/question重算原因，要求完整0调用空版本结果一致，已修正“任意refused都计正确”的问题。
- 严格全版本独立报告验证、外部输入/grant pin、degraded排除首次结构分子，以及原审核标准/同等review_context继续保留。

上述是静态结构判断，不代表Replay自身已被本助手运行验证，也不证明自然语言教学正确。运行时Journal原有状态围栏仍可阻止非active批次继续出站；以下发现针对只读检查器尚不能独立认证的全批协议。

## 仍阻断：逐槽重演不等于全批协议重演

### P1-04-G1：未重演独立助手检查点与全批停止顺序

位置：`scripts/check_p15_pilot_execution.py:541`至`:579`；`scripts/isolated_diagnostics/p15_pilot_replay.py:113`至`:120`。

checker按slot逐个验证报告，在decision=accept时累计分子，却没有将所有Journal事件按顺序重演为全批状态。Replay的journal是`guard=lambda: {}`的本地占位对象，只覆盖该臂槽内的模型FSM，不能检查真实Journal在active/awaiting_assistant/stopped/collected之间的转移。

因而存在下列内部矛盾尚未被拒绝的静态路径：

1. 一个槽有合法、准确结果摘要绑定的独立`decision=stop`报告，但后续仍存在下一臂/槽的预约、发送及result。逐槽Replay都可独立成立，checker只是不累计被stop槽，仍可累计后续成功；最后collected分支仅要求position/order/results数量一致。
2. 下一臂的reserved/sent发生在上一臂独立accept事件之前。最终所有报告都存在且内容合法时，当前逐槽循环不会核验出站当时是否仍在awaiting_assistant。
3. 某支持槽的workflow本身已stopped，却仍拼接后续合法臂槽证据。单槽result等值可以成立，但全批“任何确认失败即停”没有在跨槽时间线中重算。

影响：检查器可将“每槽局部自洽、整体违反暂停或全批停止”的证据标为`evidence_verified=true`并计算后续成功。无密钥摘要链本来不能防同用户重写全部记录，但即使在这一限制下，明确的协议内部矛盾仍应被检查器发现。这里不声称运行时Journal会主动允许上述出站。

所需修正方向（未执行）：按Journal事件顺序重建全批状态与当前位置，验证reserved/sent仅在对应active槽、支持槽结果后必须等待该准确result的独立accept、stop后不能再有后续新调用/结果，最后batch/pending/position须与重演状态一致。独立报告校验应与其发生时的pending状态绑定，而非仅事后按slot查找报告。

所需回归（未运行）：保持逐槽原件均合法，重算事件链后将独立stop置于后续预约前、将下一臂sent置于上一臂accept前、在workflow停止后拼接下一槽；检查器应准确拒绝。合法停止包仍应保留完整分母和未运行项。

### P1-04-G2：正常成功路径未核验真实事件的窗口时间

位置：`scripts/isolated_diagnostics/p15_pilot_replay.py:27`、`:39`至`:50`、`:71`至`:83`；checker的事件链及成功计数路径。

Replay使用固定合成deadline和通常返回0的合成时钟。真实`slot_result.epoch`仅用于在原结果主动声明`BUDGET_OR_DEADLINE`或`DEADLINE_AFTER_RESPONSE`时辅助复现；正常成功结果不会因为其reserved/sent/settled/assistant_review的真实epoch已超出新窗口而被拒绝。

checker对epoch目前只把它作为摘要链字段，没有核验调用及独立accept发生于grant的准确开始/截止时间内，也没有把这些时间事实重演到批次状态。因此保持合法wire/result内容、修改事件时间并重算链的“超窗成功”证据仍可能累计成功；独立等待是否包含在3小时中也未由该检查器证明。

影响：运行时有真实guard/sent/settle/accept_report时间检查，但离线复算不能据合成时钟认证三小时等待预算已被遵守。`authority_pins_verified`只说明grant/input摘要吻合，不能替代窗口事件核验。

所需修正方向（未执行）：从准确grant与批次时间基线核验事件时间及必要先后关系，对新预约/dispatch/成功settlement/独立accept实施其对应窗口规则，跨等待仍沿同一绝对截止时间；对合理的迟到响应保留原件和停止事实，不能算成功。无法独立确认的时钟来源/传输细节应明确列为局限，不通过合成时钟转为已核实。

所需回归（未运行）：仅改变正常成功调用或assistant accept的epoch为截止后并重算链；将出站时间移到开始前；保留合法迟到失败证据。前两者须拒绝，后者不能成为成功或恢复额度。

## 执行与独立评估边界

本轮没有发现新的B/C教学上下文差异或新增真实出站权限。已披露的模型别名、上游上下文/身份、summary隔离、实际费率/币种/取消后计费及无token/金额总上限仍是待准确批准事项；本文件不接受这些例外，也不联网验证标价。

如果用户批准继续解决G1/G2，应先完成相应实现/离线回归，再由独立助手核对全批协议；全链准确冻结后才能选择全新e03。e01/e02均保持历史原件，不追认为正式B评估集。若选择以额外独立人工/助手核对替代自动检查器能力，必须事先明确调整准确验收与声明范围，不能静默把当前`evidence_verified`当完整证明。

本文件不是T069/T070完成、方案采用、真实预算或生产发布批准；T038、catalog_only、签核/评分与H封存边界保持。

## 源码快照

| 文件 | SHA256 |
| --- | --- |
| `scripts/run_p15_agent_pilot.py` | `5994d51da35f4502b14c38339999b2912cbbf733f8e45ce7ac3b28f7ba64010a` |
| `scripts/isolated_diagnostics/p15_pilot_execution.py` | `26ee4f1c15351d069473b69b42b1b94541412a59e312ce0697934c1be9573042` |
| `scripts/isolated_diagnostics/p15_pilot_wire.py` | `7df1804195e7d20cb7fc2c4638257507210e8188ac4bcb28db68cc1d584d0dec` |
| `scripts/isolated_diagnostics/p15_pilot_replay.py` | `b9c71f3a28a5898fdb45b16b778235a9f6a0f5b21742e6a0678432544d353861` |
| `scripts/check_p15_pilot_execution.py` | `ec4f29f61a598603c00594b4a1d76221009c794b060a3b5283e0440edb623a55` |
| `scripts/isolated_diagnostics/p15_agent_pilot.py` | `560967912ef2a852365a4c1e4edd23a00b7856be4e4d1b001af83022fbb0619b` |
| `scripts/isolated_diagnostics/p15_pilot_baseline.py` | `eea13a850f653d217ab4b1aaf18a800749a352e39cff5a6c6cd521704e5585ef` |
| `scripts/tests/test_p15_pilot_wire_execution.py` | `dcdcf8961d84a68f44005199949e4e5a845bae8e555f5e227fd3e0d5454beaaf` |
