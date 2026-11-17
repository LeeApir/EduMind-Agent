# T072：准确 Schema 离线兼容审计

2026-10-28；新增模型请求0，不加载Key/.env、不读取独立truth/推导、不执行C。原p01保持stopped，旧41文件冻结、原始请求/响应/状态及独立样本均不修改。本轮只增加离线审计器、手写回归和提案副本。

## 有证据的结论

原始请求SHA256 `abd06d9b3a7043bef7825f1915120ad92f73bc154f744d34bb1388e27977c69b`；响应和状态准确摘要见audit.json。审计入口先核对旧manifest及41文件，再核对三份原件SHA，确认请求Schema与冻结B.SCHEMA完全相同。实际请求确为DeepSeek官方`https://api.deepseek.com/responses`、deepseek-flash、reasoning none、temperature 0.2、max_output_tokens 8000、strict true，无tools。

本地固定jsonschema 4.25.1 / Draft202012Validator.check_schema接受这份Schema。因此“不是标准JSON Schema”没有证据；[标准enum说明](https://json-schema.org/understanding-json-schema/reference/enum)允许不声明type。服务HTTP400的错误没有提供子路径，尚不能把拒绝原因认定为某一节点，也不能认定是模型生成质量问题。

逐schema位置遍历发现36个节点，包括合法的布尔叶子；只走schema关键字，不把enum/default/examples中的实例对象当schema。准确两个仅enum、没有type/anyOf/$ref的节点为：

1. `/text/format/schema/properties/actions/items/properties/kind`
2. `/text/format/schema/properties/questions/items/properties/observation_key`

这与服务错误所述“缺少type/anyOf/$ref”条件相符，是可检验的优先假设，**不是已证实的服务端拒绝位置或唯一根因**。

## 请求与端点约束对照

| 项目 | 准确请求/本地事实 | 公开约束与结论边界 |
| --- | --- | --- |
| 路径、模型、消息列表、effort、输出上限、format | 如上，文本消息列表 | [DeepSeek Responses说明](https://api-docs.deepseek.com/guides/responses_api/)列出这些支持项；不等于每个具体Schema均可接受。 |
| store=false | 明确发送false | Responses文档说明无状态、不支持store、响应固定false；不能把它猜为本次Schema错误。 |
| enum-only | 两个准确路径，枚举均为字符串 | 标准允许；响应错误未给路径。需要隔离变量观察来确认该端点是否拒绝这种形式。 |
| 长度/数量约束 | 字符串和数组共16个上下界关键字 | [函数strict说明](https://api-docs.deepseek.com/guides/tool_calls/)明确列为不支持；该规则属于Beta函数工具，仅作跨接口风险参照，不能直接认定Responses已违反。 |
| 类型数组 | 7处，包括可空指针及任意JSON答案 | Responses页未给出该形式的逐项边界；支持状态未证实。 |
| 动态对象/开放分支 | patternProperties、maxProperties各1；JSON_VALUE含无items数组及无properties对象 | 是实际形态；Responses具体支持情况未知，不能通过删约束来冒充等价修复。 |

sources.json记录公开页面、核对时间和适用范围，没有将工具调用文档冒充Responses专用规范。公开页面读取不属于Provider模型调用。

## 仅供审查的等价提案

enum-typing-proposal.json仅在上述两个节点增加`type: "string"`，原枚举及全部其他约束不变，没有接入请求构建器、生产或旧p01。每个节点原已接受且仅接受枚举中的字符串，增加字符串类型是与既有接受集合求交，集合保持不变；手写正反例及逐字差异检查支持此论证。

这仅消除两个已观察到的形态差异，**不保证DeepSeek接受全Schema**。没有删除min/max、patternProperties、联合类型或开放JSON值，没有改教学Prompt、评分/答案/动作契约或验收标准。

C规划还有5个无type/anyOf/$ref节点（含const版本及枚举），C内容1个，审核4个。完整路径见audit.json。审核走AIAPI/sol，库存形态可离线查看，但DeepSeek文档不证明AIAPI的规则。各角色尚未真实测试；不能因B两个enum补type便宣告C链兼容。

## 实际验证与交接

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_schema_audit.py -q --tb=short --junitxml=/private/tmp/edumind-p15-t072.xml
backend/.venv/bin/python scripts/check_p15_schema_compatibility.py --output /private/tmp/edumind-p15-schema-audit-r02
MYPYPATH=backend:. backend/.venv/bin/mypy --strict --explicit-package-bases --follow-imports=silent scripts/isolated_diagnostics/p15_schema_audit.py scripts/check_p15_schema_compatibility.py
backend/.venv/bin/ruff check scripts/isolated_diagnostics/p15_schema_audit.py scripts/check_p15_schema_compatibility.py scripts/tests/test_p15_schema_audit.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

34 passed、0skip；mypy两源/Ruff通过，准确原件与旧冻结一致，CLI输出changed_enum_types=2/live_requests=0。首次手写测试把空enum假定为当前本地元Schema错误而失败；已改用确实非法的enum字符串作反例，另保留空enum的“无接受值、不归一化”独立断言，没有改库验证器。jsonschema未提供已安装类型桩，沿项目方式仅标记该第三方导入import-untyped，不屏蔽本地代码类型检查。

下一步为[独立最小探针方案](PROBE-PLAN.md)，它确认一个窄问题，不恢复旧批。课程可行性必须再经相关角色准确wire Schema准入，随后用一个新合成支持槽验证C规划→内容/程序装配→sol审核及实际独立复核，交付一份完整可评课程；不以合成单字段成功替代课程可行性或T038全套通过。此处不启动任何课程或新真实请求。
