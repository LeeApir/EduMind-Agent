# T069 执行门禁修正独立复审

评估者：`pilot_independent_evaluator`（**assistant**）。复审记录：2026-10-28T14:10:37+08:00。

结论：**上轮P1-01、P1-02、P1-03及P2-01的针对性修正已在源码中确认；P1-04尚未闭合，暂不建议最终冻结、选e03或真实执行。** 剩余发现属于原有请求权限／因果证据门禁，不要求改变教学阈值或增加调用。

本轮只做静态源码及测试源码审阅，没有运行引擎、C、测试、DNS或HTTP，没有读取凭据或任何独立私有答案，没有选择e03。本文件是唯一新增文件；未修改开发源码、账本、日志或Git历史。49项通过属于开发方报告，本助手没有重跑，不把它作为独立运行证明。

## 针对上轮发现的复核

| 上轮发现 | 源码所见修正 | 本轮判断 |
| --- | --- | --- |
| P1-01 独立核定元数据缺失 | `run.validate_materials`验证公开摘要版本/状态、assistant准确身份、核定时间不早于候选冻结、候选摘要、四份材料路径/SHA声明及0700/0600；逐项重核候选文件，`read_inputs`另核准确输入SHA及槽分母 | 原已报告的缺少姓名/时间/候选/摘要问题得到针对性修正。最终冻结仍须独立检查candidate-manifest确实完整覆盖源码/Prompt/执行器/政策，而不能只依赖文件列表的自称完整。 |
| P1-02 首版false可被空issues掩盖 | 提取`validate_assistant_report`；每个false需匹配领域证据，逐版指针和值精确匹配；任何版本facts/answers/code=false或严重/事实安全问题要求stop | 已补足原缺口；没有把最终pass替代首版事实。 |
| P1-03 checker未复验报告 | checker调用同一纯验证器，保留报告文件/事件/result绑定，并新增外部grant/input pin | 已补足原缺口。独立身份仍是用户委托与记录，不是OS或密码学认证；未给外部pin的直接checker调用会如实标记`authority_pins_verified=false`。 |
| P1-04 输入/工作流/审核因果绑定不足 | 已增加示例spec=准确slot.spec、candidate事件=versions、artifact identity/parent、plan与content关联、审核source与reference/context、修复原文和原意见 | 有明显补强，但仍有下面两组阻断问题。 |
| P2-01 degraded被计首次结构成功 | 仅首版存在且非degraded才增加initial_structure，新增故障回归源码 | 针对性修正成立。 |

私有truth/ratification/推导内容不由运行入口读取的约束保持；它们的SHA声明来自独立公开核定材料，实际私有字节仍应由独立评估者在核定及使用时重核。本轮未要求开发方读取答案。

## 仍阻断的P1-04

### R1：仍有部分字段比对，未完整重建允许请求

位置：`scripts/check_p15_pilot_execution.py:181`附近wire配置检查；`:361`至`:421`的content/repair/review分支；`:341`的plan分支。

- content只检查`plan`与`example`，没有核验完整键集合或`question_keys`。在匹配两项的同时加入额外上下文/参考字段，或改变问题键，仍不会被这一层拒绝。
- C repair只核原文、原意见、reference；B repair只再核semantics/spec，没有完整核对goals和全部键。review同样只核若干既有字段，没有拒绝额外上下文。
- plan输入只有在存在response时才核验。unknown/无响应请求也属于实际已外发材料，不能因没有模型回复就跳过请求权限核验。
- wire请求只比对model/max_output/reasoning/stream/store/strict及system/schema的部分字段，没有按`wire.request_body`完整重建请求。temperature漂移、额外tools/previous_response_id、附加input消息等，未被这些字段比较覆盖。

影响：只要同步改动request/dispatch并重算相关摘要，非冻结材料或参数仍可能被当成证据已验证。这里要求发现内部协议不一致，不是声称无密钥SHA链可抵御同一用户重写全部证据。源码实际构造了合法请求，并不等于只读检查器已独立重核合法性。

建议：按每个角色、每次revision重建**完整允许payload**并作canonical等值比较，不允许额外键；再以准确角色/阶段/固定system/Schema/参数重建完整wire body作等值比较。对无response/unknown请求照常核对。请求和response的角色/identity也应绑定该槽和准确版本，不能仅检查artifact的identity。

必要离线回归：重算请求摘要、工作流与账本链后，分别加入额外上下文、改content.question_keys/B repair.goals、改temperature、加入tools/previous_response_id/额外消息、unknown plan携带额外字段，检查器仍须拒绝。测试不得只凭旧SHA被改而通过。

### R2：审核Schema有效不等于遵守停止状态机

位置：`scripts/check_p15_pilot_execution.py:423`至`:430`；拒绝槽`:267`至`:273`。

checker调用`c.validate_review`校验审核Schema、source_digest、意见证据和scope协议。但该函数会正常接受协议有效的`verdict=unknown`，也会正常接受含事实/安全/严重问题的`revise`；它不执行`Pilot.run`中的停止决策。检查器目前只处理validate_review抛异常时的停止要求，没有对这些**校验成功但政策要求停止**的意见重演状态机。

因此“审核unknown或事实/安全意见 + 继续修复/最终成功/独立accept”的证据内部矛盾，尚未被完整拒绝。独立助手认为课程事实正确，也不能追认一次已违反冻结停止规则的继续执行。类似地，拒绝槽目前只查refused和calls=0就增加正确拒绝分子，没有重判准确槽要求对应的本地拒绝原因。

建议：从完整调用顺序与所有响应重演允许的状态转移。出现事实/安全/严重意见必须对应`FACT_OR_SAFETY_STOP`，unknown必须对应`REVIEW_UNKNOWN`且无后续调用；普通教学revise才可恰好一次修复及重审，第二次revise应为`REPAIR_EXHAUSTED`。同时检查最终状态、reason、版本数、独立报告及后续调用是否与该路径一致。本地拒绝应重核准确输入/问题及拒绝reason，不能用任意refused替代正确拒绝。

必要离线回归：保留有效审核Schema并重算链，将unknown后的结果伪改为成功、事实/安全意见后继续修复、第二次revise仍计成功、在停止点后添加调用、换一个本地拒绝reason，均须被checker拒绝。合法unknown/事实失败停止的完整原件应仍可被验证为“采集合规但质量未通过”。

## 新增审核上下文与待批方案

`agent-pilot-v2`保持原审核标准全文，明确旧scene/source_sha256/uncertain到当前source/source_digest/unknown的字段映射；B/C均附`review_context(original_goal, plan_constraints, upstream)`。目前两臂提供相同合成目标、准确规格及空上游，没有见到降低事实、答案、代码安全、难度或误区标准的改动。这是隔离原型的格式适配，不是生产审核规则变更或真实质量证明。

ADR0042及execution-p01 README/policy/rates明确处于待准确批准状态，披露固定目标与模型、具体Schema尚未真实验证、90请求/B4/C5、3小时含等待、120秒单请求、兼容回显/summary/成对UUID隔离，以及token/金额总额不设上限且实际账户/推理/取消后计费未核实。本轮不联网核价、不代签这些范围；历史费用或兼容例外不能自动继承。最终执行包应保持这些准确限制与例外，另外取得用户批准。

## 本轮源码快照

候选尚未冻结；以下SHA用于定位本次复审结论，不是运行授权。

| 文件 | SHA256 |
| --- | --- |
| `scripts/run_p15_agent_pilot.py` | `5994d51da35f4502b14c38339999b2912cbbf733f8e45ce7ac3b28f7ba64010a` |
| `scripts/isolated_diagnostics/p15_pilot_execution.py` | `686198f312e24887adac6bf34f0f84a025dd706b3be0458f2d6db5a454fd7284` |
| `scripts/isolated_diagnostics/p15_pilot_wire.py` | `7df1804195e7d20cb7fc2c4638257507210e8188ac4bcb28db68cc1d584d0dec` |
| `scripts/check_p15_pilot_execution.py` | `bf6a65d79e06e2274f865a9a72d2774fd44feedd21d390e19ac0b235f52df951` |
| `scripts/isolated_diagnostics/p15_agent_pilot.py` | `560967912ef2a852365a4c1e4edd23a00b7856be4e4d1b001af83022fbb0619b` |
| `scripts/isolated_diagnostics/p15_pilot_baseline.py` | `eea13a850f653d217ab4b1aaf18a800749a352e39cff5a6c6cd521704e5585ef` |
| `scripts/tests/test_p15_pilot_wire_execution.py` | `15cb023254a347624d48843c5c3a3141559bf2639d798b268c2851aa00b30e4d` |
| `docs/ADR/0042-pilot-controlled-execution.md` | `8f73c40446244d8a2e4d431f4c01f18ef4a50d7b29a39aef5b861c299897aa9c` |
| `execution-p01/README.md` | `9944bda5d7e3377167c6a47075d4c785740d43de5b1fdd90d1bc66e9053577d7` |
| `execution-p01/policy.json` | `406a8e09d1b0ee5d710ac0ed8b8cf3e57b72d4030fd5efb555cfc904ed083e2a` |
| `execution-p01/rates.json` | `13c567dce2a31edef841c6704ec185b1966c219dbd97e562108781581ff43491` |

R1/R2修正并经相称的离线篡改/停止回归后，提交新准确候选复审；全链冻结后再独立准备e03。e01/e02原记录保持，不作为正式B评估集。本轮不宣称T069/T070完成，不改变T038、catalog_only、发布或评分权限。
