# ADR-0046：联合类型的等价表示提案（仅离线）

2026-10-28；Proposed。T079只交付方案与离线反例；未批准采用或执行，无新真实调用授权。

## A：事实与待证假设

T078角色包已终止，见[准确结果](../acceptance/phase-1.5-schema-compatibility/results-role-r01/RESULTS.md)。DeepSeek规划Schema含5处普通type:array且被接受；内容Schema返回unknown variant array，未给JSON Pointer。内容中有两处fact_refs.value的type联合：string/number/boolean/null/array/object；审核另有string/null联合，但审核未发送。

“类型联合中的array/object触发拒绝”只是候选解释，不是单变量证明；不推断所有array都不支持，也不把服务错误当成教学错误。此前enum-only最小拒绝证据不等于该新问题已经定位。旧源码/Prompt/Schema/结果与未知占额保持。

## B：保持接受集合的纯离线候选

对某节点的`type: [t1, ..., tn]`，拟仅替换成`anyOf: [{type: t1}, ..., {type: tn}]`，兄弟关键字原位保留。JSON Schema兄弟约束为合取，两种表示都要求“至少一种列出的类型成立，且所有原兄弟约束成立”，所以接受集合相同。number和integer有重叠也不影响anyOf的析取；不能改成oneOf。

数组和对象分支不补items/properties/additionalProperties、不收窄为标量、不JSON字符串化。原开放嵌套JSON值仍被接受；长度、数量、uniqueItems、required、additionalProperties、事实引用和完整原Schema/语义校验均保留。未知服务约束不得以删字段/删类型/放宽断言绕过。

先采用ADR0045已批准的literal显式type副本，再提出联合表示变化：规划0、内容2、审核1处。schemas.json逐项冻结原生Schema、ADR0045 wire Schema、拟议Schema、摘要和准确路径；不把未发送审核角色登记为失败或通过。新增函数仅供离线提案与测试，不被任何旧执行入口/教学工作流导入。

同节点已经存在anyOf时拒绝转换，不覆盖原anyOf，也不自动引入新allOf契约；遇到这种新形态另提方案。Python共享字典先展开为JSON树，确保两个实际路径均单独登记，原输入对象保持不变。

这些逻辑等价事实不能证明服务支持anyOf中的开放array/object、其他未验证关键字或完整课程上下文。

## C：未来最小实测与课程门禁（本次不执行）

建议未来独立两请求对照，仅DeepSeek官方/responses、deepseek-flash、none，纯合成`{"value": null}`。固定外层object/required/additionalProperties:false和其他请求参数；唯一Schema差异为value节点的联合表示。S1先用anyOf候选，完整200/协议/原Schema/准确echo通过才发S2原type联合。S1异常即停；S2任何结果都终止，无重试、重定向、回退、补发、续旧批或换模型。

- S1失败：候选没有准入，S2不发送；不能推断是anyOf、开放array/object或其他具体关键字的唯一问题。
- S1通过、S2匹配Schema 400：该最小上下文下观察到等价表示影响服务接受；不证明原完整内容Schema唯一根因。
- 两者均通过：两种最小形式都可用，原复杂拒绝仍未定位。
- S2其他HTTP/协议/未知失败：对照结论不确定，仍终止。

建议最多2HTTP，新90秒、单HTTP25秒、每目标DNS9秒；输出请求上限每次32/总64，输入占额每次4096/总8192，请求/响应1024/65536字节。只发送合成数据与最小Schema，无sol、课程、学生、e03或H。上述是后续包的预算提议，**当前真实额度0**：尚无执行入口、准确请求体、当前价格冻结或执行批准，不能运行；后续需完整冻结源码/请求/单次窗口/费率与金额边界并准确获批，不继承旧费用例外。

即使最小对照通过，完整内容/审核角色仍须使用新准确包独立准入，不能沿用T078规划结果当新整批通过。全部相关角色准入后才准备一份完整可评课程；课程真实调用另需准确包。T038 blocked、catalog_only、H封存和原教学标准保持。
