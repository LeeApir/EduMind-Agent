# T079 联合类型等价提案 r01（离线完成，未采用/未执行）

范围见[ADR0046 A—C](../../../ADR/0046-equivalent-union-schema-proposal.md)。仅新增隔离纯函数和测试；无HTTP/Key读取/真实调用入口，原教学链和此前所有冻结文件不变。

## 具体变化

```json
{"type": ["string", "number", "boolean", "null", "array", "object"]}
```

拟等价改写为：

```json
{"anyOf": [{"type":"string"}, {"type":"number"}, {"type":"boolean"}, {"type":"null"}, {"type":"array"}, {"type":"object"}]}
```

兄弟约束原位保留，不删除类型、数组/对象或原本的嵌套开放值。所有拟议原始/新Schema与路径见schemas.json；最小对照的两个Schema见minimal-schemas.json。这些是设计附件，**不是可执行请求或批准**。

| 角色 | type联合变化处数 | 远端状态 |
| --- | --- | --- |
| C规划 | 0 | ADR0045表示已在T078合成上下文通过；本提案不增加证据 |
| C内容 | 2 | 旧表示T078被拒，anyOf表示未测试 |
| 审核 | 1 | 两种表示均未在本次角色准入中测试 |

同节点已有anyOf则拒绝转换，避免覆盖原约束。原Schema在Python中共享REFS字典，离线转换先展开JSON树，分别记录两个内容路径。反向还原变更节点后必须与ADR0045原wire Schema完整相等，覆盖所有边界/属性/必填规则，不能只测样例通过。

## 证据与推断

[T078原始结果](../results-role-r01/RESULTS.md)只说明规划普通数组可接受、内容Schema被拒。错误未给路径，所以不能断言类型联合是唯一原因。即使逻辑等价，服务可能对anyOf开放数组/对象仍拒绝；本提案不提前宣称兼容通过。

未来最小对照按ADR0046 C提出：先anyOf控制，再条件发送原type联合，固定echo为value:null；最多2请求，任何异常按预注册矩阵终止。两请求只比较语法表示，不证明所有类型都被服务强制约束；本地正反例不等于远端解码保证。当前不建立runner，不冻结价格，不批准外发，不沿用旧预算；准确包另行准备与批准。

## 实际离线验证

450 passed/0skip：本任务46项＋既有相关404。手写正反例覆盖布尔/整数/数字区分、number/integer语义、null分支、字符串长度、数组长度/items/uniqueItems、对象required/additionalProperties、嵌套开放JSON、原内容缺字段/少题/多题/额外字段/引用缺值/空正文拒绝；不是独立人工教学真值。

首轮448通过/1失败：共享Python引用导致两个内容路径只记录一处；保留该断言并修复JSON树复制，完整重跑449通过；补充number/integer重叠类型用例后450通过。未改旧测试或削弱原标准。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_union_schema_proposal.py scripts/tests/test_p15_role_schema_contract.py scripts/tests/test_p15_role_schema_probe.py scripts/tests/test_p15_schema_probe_p02.py scripts/tests/test_p15_schema_probe.py scripts/tests/test_p15_schema_audit.py scripts/tests/test_p15_pilot_wire_execution.py -q --tb=short --junitxml=/private/tmp/edumind-p15-t079.xml
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_union_schema_proposal.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_union_schema_proposal.py scripts/tests/test_p15_union_schema_proposal.py
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_role_schema_probe.py --check
python3 scripts/check_catalog_workflow.py
git diff --check
```

JUnit保存在/private/tmp/edumind-p15-t079.xml。原46/47/62文件冻结摘要保持一致；manifest.json仅冻结本离线候选的附件和父级源码，不提供执行权限。完成后停在离线提案；未准备课程，未恢复旧批或T038。
