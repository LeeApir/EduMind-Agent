# T083：最小契约隔离适配与离线回归交接

**状态：已按ADR0047 A—D完成隔离实现与离线自查，交回审查；真实调用0。** 用户的七次合成兼容调用和新900秒窗口范围已登记在[批准记录](../../ADR/0047-approval-20261029.json)，没有再次请求这一范围的授权。按照“适配与离线回归后交回审查”，本任务不激活真实窗口。旧费用例外不继承，USD1实际账户支出可控性尚未核实。

已批准原设计入口：[T082准确13附件](../phase-1.5-minimal-output-contract-r01/README.md)。其Proposed/零额度描述保留冻结字节，当前接受状态以批准登记为准；不是改写历史。旧所有停止批次保持终止，正式教学标准与生产catalog_only不变。

## 实际实现

| 模块 | 实现行为 |
| --- | --- |
| [p15_minimal_contract.py](../../../scripts/isolated_diagnostics/p15_minimal_contract.py) | 校验准确4Schema；严格JSON/本地长度数量范围/四题覆盖；可重建的完整事实目录；明确状态tag和动作顺序解码；C事实ID解析；B答案原样保存；完整artifact与审核定位/版本绑定 |
| [p15_minimal_pilot.py](../../../scripts/isolated_diagnostics/p15_minimal_pilot.py) | 六种角色阶段的双臂Mock流程、完整原始内容＋渲染产物审核、最多一次普通教学修复、unknown/事实安全/预算/超时/取消停止、不可重启、逐事件摘要链；只接受MockTransport |
| [契约回归](../../../scripts/tests/test_p15_minimal_contract.py) / [协作回归](../../../scripts/tests/test_p15_minimal_pilot.py) | 51设计例不改预期；手写负例/无代填/未知tag/篡改/全投影；跨变体/分配失败/最大规格/修复/停止/取消/网络拒绝 |
| [prompt-snapshot.json](prompt-snapshot.json) | 新Prompt信封准确快照。原教学审核标准完整作为前缀，明确旧字段与新字段映射；不改原文件或教学维度 |

程序事实仅在C装配时解析，保存resolved_facts的program provenance。调用旧纯装配函数前，把已核验ID显式投影成内部path/value，不把这些值登记为模型复述。B装配接口拒绝参考目录；缺答案直接失败、错答案保留，只有none↔null等已批准表示解码。B生成请求先发出，之后才构造审核参考；B修复输入是原始允许输入＋其自身旧产物＋普通教学意见，不提供参考事实。

所有原始自然语言保留在raw_output，派生展示文本继续使用既有安全清洗；审核输入同时包含两者及完整参考。target目录每个叶字段有精确目标或精确祖先投影，答案/代码/动作不省略；每个动作作为完整规范JSON目标，避免逐字段重复元数据让最大规格超限。引用/quote存在不证明讲解正确；模型pass仍只是建议。

## 离线结果与证据

最终 **290 passed / 0 failed / 0 skipped**：新适配182项＋原引擎50＋原协作42＋原基线16。严格mypy两源、Ruff、原设计/302旧摘要、本地工作流与diff检查通过；实际结果及首次修正见[verification.txt](verification.txt)。没有运行全项目PG/E2E或任何真实Provider测试，不宣称生产或模型质量通过。

[Mock证据索引](mock-evidence.json)登记16组完整开发演示及各文件摘要，原件在`/private/tmp/edumind-p15-minimal-mock-r01`（目录0700、文件0600）。包括两臂的正常、最大自环、丢返回值/混合失败、未初始化next、全失败、普通修复、事实停止、本地拒绝；保留完整请求/响应、所有候选版本/审核与事件。B的Mock应答工厂在测试端使用引擎合成回复，**不是B模型计算或独立真值**；程序不代填由额外禁止引擎访问/保留错误答案测试证明，不能用Mock应答正确性宣称实验公平已独立核定。

## 七次兼容候选请求

[compatibility-candidate.json](compatibility-candidate.json)与S1–S7.request.json保存准确UTF-8请求字节及模型/路由/参数/字节摘要，不含Key。5次DeepSeek＋2次AIAPI、900秒、60秒/HTTP、9秒/DNS、输入57344/输出16896、请求65536/响应262144字节与已批准设计范围相同；任何异常停止，不重试/回退/修包补发。费用提议仍为USD1，实际费率/币种/支出控制未核实。

请求只要求固定synthetic expected_output，**不是课程生成或B独立解题**。C_plan的短spec_id与review的candidate_id/target_id按新程序绑定规范生成；除此之外沿用原手写wire fixture，完整输出Schema不改。修复请求显式带合成旧产物/普通意见，review分别含B/C合成包装及完整定位表；其source明确标protocol_fixture_only且不具课程质量，预期unknown仅为协议形态，不是实际教学审核。它们不进入课程质量/基线效果指标。

[check_preparation.py](check_preparation.py)可核对准确字节、阶段/预算、源闭包/批准附件及Mock原件事件；没有--run/凭据/网络入口。当前没有真实执行器被激活，原旧执行器不接受minimal_阶段，也不改旧scope来复用。后续应在本次审查后落实准确真实适配/执行材料和费用可控性；不隐式把七次批准解释为金额不限或允许跳过审查。若预算可核实且范围不变，不重复索要七次调用许可；若必须变更费用/协议边界，再据具体新材料决定。

## 复现

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_minimal_contract.py scripts/tests/test_p15_minimal_pilot.py scripts/tests/test_p15_head_insertion_engine.py scripts/tests/test_p15_agent_pilot.py scripts/tests/test_p15_pilot_baseline.py -q --tb=short
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_minimal_contract.py scripts/isolated_diagnostics/p15_minimal_pilot.py
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-minimal-output-adapter-r01/check_preparation.py
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-minimal-output-contract-r01/check_design.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

## 本次审查重点和边界

请评估助手检查新模块/Prompt差异、51原例及新增回归、16组全部版本和7个准确请求。重点看B值是否被替换或泄漏参考、C事实目录是否绑定原版本、raw讲解是否完整审、动作投影是否覆盖所有字段、修复是否只有一次、停止后是否不可再发。开发自查未冒充独立评估。

已知限制：这是隔离Mock流程，没有接线生产/真实Transport、独立样本、教学质量或收费验证；事件链是本地开发记录，不是外部时间/身份认证。较大文字组合仍受128000字节总输入/原件硬门约束，失败显式保留，不补内容/放宽上限。七次固定echo通过也只能证明该批观察兼容；必须全部角色通过后才另行准备一份完整可评课程，当前无课程外发、T038解除、旧批恢复、push/merge或部署授权。
