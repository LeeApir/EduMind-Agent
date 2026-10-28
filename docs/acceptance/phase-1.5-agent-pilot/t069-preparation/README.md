# T069 受控实验准备检查点

状态：零调用准备，尚非可批准的准确真实执行包；T069未完成，T070未领取。T066完成87ae7ca、T067完成58169ed、T068完成4a69022。

用户批准ADR0041准确设计后又要求“助手评估所有内容”，替代原提案中的人工真值核定要求，核定身份必须为assistant；随后明确授权独立子助手评估全部内容。冻结提案原字节保持，方向登记 assistant-review-direction.json。开发助手仍不能自签独立效果结论。

## 已交付

- development-freeze.json：核心实现/测试、原Gateway/Markdown清洗、锁文件、原审核标准与ADR0041批准的22份候选输入摘要（r01原样保留，r02含e01发现后的unknown边界修正）；这是开发源检查点，不是真实执行授权或完整传输闭包。
- scripts/check_p15_agent_pilot_evidence.py：只读核验完成的Mock课程证据。重算事件链/版本/调用顺序、角色请求/响应与Schema、原始Mock wire、规格/事实/答案/代码/动作、修复关系及审核引用。明确HTTP0、无独立真值、T069/T070未完成。
- scripts/prepare_p15_agent_pilot.py --check：核对开发冻结文件，始终exit2并显示尚需材料；不能通过改配置或新增“approved=true”变成真实入口。不加载Key、.env、数据库，不做DNS或HTTP。

## 待完成后才能提交真实执行包

1. 独立评估助手在候选冻结后选14槽输入、手算参考真值并按assistant身份核定；输入与真值分别摘要绑定，真值不交开发调参或发送给模型。
2. 实现同条件B基线与两臂完整采集；若只运行C须准确冻结无基线的绝对评估范围，不能引用旧D02计算改善率。
3. 准确锁定Provider/端点/模型/参数/Prompt/传输与兼容边界、费率和币种、新请求/token/金额/墙钟预算及合成材料外发；未知费率/中转硬限若要例外须本批明确批准。
4. 真实适配器与每槽/全批持久预算、unknown/停止、原始证据写入和完整只读结果检查器须先离线验证，再将准确代码/材料/配置闭包冻结为新的执行包。当前Mock检查器不能冒充真实结果检查器。
5. 取得该准确执行包的独立真实执行批准；未运行槽/异常保留，旧批和额度不继承。运行后才可完成T069证据采集任务，再由独立助手进行T070。

## 实际验证

```
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_agent_pilot_evidence.py scripts/tests/test_p15_agent_pilot.py scripts/tests/test_p15_head_insertion_engine.py -q --junitxml=/tmp/edumind-p15-t069-prep.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/check_p15_agent_pilot_evidence.py scripts/prepare_p15_agent_pilot.py
backend/.venv/bin/python scripts/check_p15_agent_pilot_evidence.py --directory /private/tmp/edumind-p15-t069-development-r02
backend/.venv/bin/python scripts/prepare_p15_agent_pilot.py --check
python3 scripts/check_catalog_workflow.py
git diff --check
```

115 passed、0skip（新证据/准备17+协作42+引擎56）；类型2源/Ruff/工作流/diff通过，Mock证据核验exit0，准备门禁预期exit2。篡改覆盖重算事件链后修改答案/动作/身份/请求/响应/审核来源/顺序/规格，以及权限虚报、开发冻结漂移。真实HTTP0，未运行真实基线/协作，不提供效果结论。

独立材料及真实配置仍缺，不能把这个检查点请求为“准确可执行包”批准。下一步继续完成上述独立材料和执行器准备；T038 blocked/catalog_only/H封存保持。

独立e01审阅在真值选样前发现unknown可达性错误，未签核，已保留独立问题记录。按既有未知原则修正为v2（见unknown-reachability-correction.md），旧一条错误断言据独立事实核对更正并补六项回归；独立助手已确认语义方向，正在按新SHA核验和重新选样，尚未提供完整真值。
