# T086：协议／修复／包装诊断离线审查包

**本轮Provider调用0；只设计和回归；T085不重启。** 新方案等待评估助手审查，再决定是否准备和申请新验证包。没有新的真实许可、运行入口、窗口或费用例外。旧Schema、严格校验、冻结包、原始结果及正式教学验收标准保持。

## 审查入口

| 材料 | 用途 |
| --- | --- |
| [ADR0048](../../ADR/0048-separated-protocol-repair-diagnostics.md) | A三任务判据；B有限对照/归因边界；C严格回归；D审查后再申请 |
| [TASKS.md](TASKS.md) | 精确输入/三种成功条件、真实修复语义复核要求与公平性限制 |
| [MATRIX-AND-STOP.md](MATRIX-AND-STOP.md) | 有限顺序、单因素定义、早停/未运行解释、新预算提议 |
| [matrix.json](matrix.json) | 七例准确字节哈希、配对父例与单个JSON Patch |
| [P0](P0.request.json) | 纯回显，用户数据只有expected_output |
| [W0](W0.request.json) / [W1](W1.request.json) / [W2](W2.request.json) / [W3](W3.request.json) / [W4](W4.request.json) | 空包装、修复标签、旧候选、意见、原输入块；独立分支、不累计因素 |
| [R0](R0.request.json) / [修复上下文](repair-context.json) | 完整手写合成候选与一条普通教学措辞任务，无expected_output |
| [修复输出正反例](repair-output-examples.json) | 两种不同改写、错误但结构合格的改写、越界/未改反例；不发送给模型 |
| [原始失败来源](fixtures/provenance.json) / [精确输出文本](fixtures/t085-s5-output-text.txt) | 原3306字符和SHA；不含传输元数据或凭据 |
| [合法Schema反例](fixtures/schema-as-answer.json) / [解析前缀反例](fixtures/parsed-prefix-as-answer.json) | 派生控制，明确不是成功答案或已修复响应 |
| [新增回归测试](../../../scripts/tests/test_p15_protocol_task_separation.py) / [静态检查器](check_design.py) | 调用未改动的严格observer拒绝原错误，并核对新输入/矩阵/判据 |
| [准确清单](manifest.json) / [实际验证记录](verification.txt) | 本提案/来源闭包与离线结果，非执行授权 |

## 设计选择

本轮聚焦S5所用B完整输出Schema，其他三种Schema逐字节核对、未重验；不是重新做全角色准入。P/W复制同一目标，R0真的改写旧候选中的一段文字。修复用完整实例与独立语义标准判定，不能复用回显的固定字符串相等判据。

W0对P0只加空role_input；W1–W4从W0分别加一个字段/固定块，每对的系统指令、目标与Schema等配置相同。块增删也改变长度/重复内容；每例一次且共享W0，因此只能筛查现象，不能证明某句话/模型/服务是唯一根因。旧S4成功不作为新P0成功，R0不同任务不作为包装因果对照。

所有新示例保留当前B Schema、strict:true、模型/采样/输出参数；只改变提案中的任务说明与输入数据，不修改现有运行Prompt。R0手写旧候选不是B模型生成，不作B首次生成或B/C效果证据；程序不代填其答案。缩小为一段普通措辞修复是新的诊断任务范围，须评估确认，不替换原B一般修复权限。

拟议未来最多7次DeepSeek合成调用，先六个协议/包装例再一个修复例，任一协议异常全批终止；没有重试或自适应增样。这个新用途与旧七槽不同，输出总请求上限28672；金额/费率/币种和真实控制器未冻结，旧未用2次/旧窗口/费用例外均不继承。准确预算与停止条件在MATRIX-AND-STOP.md中；本轮不申请执行。

## 离线验证

```sh
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-separated-protocol-repair-r01/check_design.py
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_protocol_task_separation.py scripts/tests/test_p15_minimal_probe.py scripts/tests/test_p15_minimal_contract.py scripts/tests/test_p15_minimal_pilot.py scripts/tests/test_p15_head_insertion_engine.py scripts/tests/test_p15_agent_pilot.py scripts/tests/test_p15_pilot_baseline.py -q --tb=short
python3 scripts/check_catalog_workflow.py
git diff --check
```

原始文本回归不依赖/private/tmp原件仍存在，能从Git中的精确message.text和公开来源摘要复现。原完整HTTP响应仍私有原样保留，未复制其传输ID到Git。检查器没有--run/凭据/网络路径；它验证静态设计，不是未来实际任务的真实控制器或教学判真器。

## 给评估助手的问题

1. P/W是否只有一个回显目标，R0是否没有预先给定修复结果；两类后置判据是否分清？
2. 五对包装差异是否都只有登记的JSON Pointer，块级因素及长度/采样局限是否表述准确；有限矩阵是否足以决定下一步而不自动追加？
3. 原始非法文本、合法Schema、截取前缀和宽松解析诱因是否全部保持拒绝，当前Schema和严格实现是否真的没改？
4. R0完整手写候选、准确意见与唯一允许改动是否自洽；两种不同好改写和错误改写为何都不能由机械检查代签语义通过？
5. 当前仅为S5聚焦诊断，是否接受其不能代表全角色、课程质量或独立B/C效果的限制？

开发者只完成自查，未代签本次独立评估。请审查后给出接受/修改/停止建议；再由用户决定是否允许准备新准确验证包。本轮交接后停止，不自动进入真实验证或课程实验。
