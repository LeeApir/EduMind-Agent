# 完整Schema审查与Provider兼容清单

审查基准为T081停止后的仓库源码，**本轮无网络/Key读取/真实Provider调用**。本清单区分历史实测、已有官方说明及未知；没有重新查询最新模型价格/能力，不把链接标题当完整Schema支持承诺。完整逐位置数据见[original-schema-audit.json](original-schema-audit.json)，包含原生Schema、ADR0045 literal副本、ADR0046 anyOf候选、所有关键字位置及风险项。副本仅用于完整审查，不是采用旧修补路线。

## 完整覆盖

| 独立输出Schema | 对应实际模型阶段 | 原Schema位置数 | 嵌套审查 |
| --- | --- | ---: | --- |
| B SCHEMA | B生成、B修复 | 36 | 四题answer_key、ACTION、STATE、NODE、POINTER全部展开 |
| C PLAN_SCHEMA | C规划 | 19 | SPEC_SCHEMA、目标列表、coverage全部展开 |
| C CONTENT_SCHEMA | C内容、C修复 | 24 | 段落/题目/REFS/开放JSON_VALUE全部展开 |
| REVIEW_SCHEMA | B/C首次、B/C修复后审核 | 14 | issues、nullable reason及定位规则 |

共93个Schema位置，81条分类提示；提示可以重叠，不是81个服务端已证错误。六种调用阶段中，repair与初次共享完整Schema，但输入不同。程序示例/动作/身份不调用Provider；其内部产物仍须版本/事实/范围核验。本清单不扩大到与该隔离实验无关的生产全站Schema。

## 已有准确请求证据

| 历史包 | 实际观察 | 可以/不可以推出 |
| --- | --- | --- |
| [T069 p01](../phase-1.5-agent-pilot/results-p01/RESULTS.md) | B完整原Schema首请求400，要求type/anyOf/$ref，无路径 | 该请求不兼容；不能从错误猜某一字段，更没有课程质量证据 |
| [T076 p02](../phase-1.5-schema-compatibility/results-p02/RESULTS.md) | 显式string的最小enum成功，删除kind.type的对照400 | 该最小enum-only形态被拒；不能外推全部Schema支持 |
| [T078 role-r01](../phase-1.5-schema-compatibility/results-role-r01/RESULTS.md) | C规划200；C内容400 unknown variant array；审核未发 | 规划该准确合成上下文准入；含5普通array已成功，不能说array普遍不支持；内容类型联合只是候选解释 |
| [T081 union-p01](../phase-1.5-schema-compatibility/results-union-p01/RESULTS.md) | anyOf控制400 missing items；原type联合对照未发 | 该控制没有通过；服务未给分支路径，补items足够、object分支支持均未证 |

上述批次全部终止，未用请求/窗口/费用例外不继承。不能把不同请求的400拼成单变量对照。AIAPI本轮新角色Schema未准入；早期sol样例或旧容错不能自动证明新Schema可用。

## 逐类风险与整体处理

| 类别及准确位置示意 | 完整旧角色覆盖 | 风险/证据等级 | 最小契约处理及保留硬门 |
| --- | --- | --- | --- |
| 字符串enum/const未显式type | C目标/coverage/spec；B observation_key/action.kind；审核verdict/scope/severity/area | 最小enum-only拒绝有证据；复杂字段单独因果未知 | 同型string enum都显式type；spec版本/值不再让模型复述 |
| type为数组（含null） | B answers/line/pointers/node.data；C fact_refs.value；审核uncertain_reason | 全量位置见JSON，不能逐一声称已拒 | 全部替换为明确题型/有限enum/ID或tag；这是新契约，非自动等价转换 |
| 任意嵌套JSON array/object，没有items/properties | B answer_key；C两处fact_refs.value | T081控制实际拒；开放递归JSON的Responses支持未知 | C只返回ID，B四种明确答案；不再需要递归任意JSON |
| anyOf（nullable state等） | B ACTION.state；ADR0046候选联合 | Tool文档有anyOf不等于Responses所有分支组合支持 | 新wire完全不用anyOf；不能据此判服务anyOf普遍不支持 |
| 动态对象键patternProperties/maxProperties | B STATE.nodes | Responses支持未证；任意节点字典增加兼容面 | 有限节点数组，重复/数量/引用本地核查，状态值仍由B模型计算 |
| pattern | B KEY/POINTER/NODE.data，C KEY，审核digest | 不能从历史200证明服务一定强制pattern | wire固定域用enum；通用ID/key格式本地核查；长digest归程序 |
| min/maxLength、min/maxItems、uniqueItems、minimum/maximum | 四角色相关所有位置在JSON清单中 | 既有C规划200只证接受该请求，不能证明逐关键字强制 | wire不携带这些关键字，原范围/唯一性本地必检；不得放宽最终通过条件 |
| required/additionalProperties:false/items | 每个object/array，B旧动态节点除外 | 常见严格格式能力；新组合整体仍待实测 | 新wire对象全部required且闭合，数组都有具体items；未知额外字段/缺项拒绝 |
| nullable reason + scope/verdict关联 | 审核 | Schema本身未完整表达状态一致；后续本地有规则 | uncertainty空串编码无理由，unknown非空；candidate_id/target_id本地绑定 |
| 跨字段/上下文规则 | 所有角色：规格选中、四题覆盖、事实相等、节点引用、动作、review绑定/quote | 不是单靠Schema能证明的约束 | 完整保留或明确变更职责；程序ID解析替代事实值复述，不代替语义审核 |
| 响应信封/模型/phase/reasoning/echo/usage | 两Provider，全部阶段 | 旧样例观察有边界，不能推定新请求都同样 | 冻结新的受控校验策略及原件；不自动加例外/修响应/回退 |

JSON中的all_keyword_locations还列出type/properties/required/additionalProperties/items/enum等所有出现位置，确保没有只列“可疑字段”而漏掉普通字段。新增设计只用七种wire关键字；减少兼容面不是远端支持证明。

## 官方说明的证据边界

先前审阅过的[DeepSeek Responses兼容说明](https://api-docs.deepseek.com/guides/responses_api/)列出text.format能力，但没有给出覆盖上述所有JSON Schema关键字/组合的完整保证。[Tool Calls严格模式](https://api-docs.deepseek.com/guides/tool_calls/)说明的是Beta工具Schema，包含array/items和anyOf等示例，以及部分长度/数量约束限制；**不能把Tool Beta限制当作Responses确定规则**。本轮只利用已记录说明划出未知，不新增线上检查；后续准确执行包应重新核对官方文档、端点、模型ID及可获得的账户费率。

[AIAPI文档](https://aiapi.world/docs)及此前sol样例不能独立认证上游路由/完整上下文/留存或Schema强制执行。其已知37字符后缀、有界reasoning summary/成对UUID若继续使用，必须逐项在新准确包列明，不能因旧批准自动继承。未知新字段、工具调用、来源或参数冲突仍停止，不扩大隔离规则。

## 准入检查项

1. 新源码/Prompt信封/全部4Schema/6调用阶段及审核B/C上下文冻结；离线正反例全部可解释；独立评估同意新契约后才实施。
2. 凭据按两个目标显式隔离；先获准确授权再读Key；公网DNS固定目标、TLS Host/SNI、无重定向/代理环境借用/传输重试/跨厂回退。
3. 真实HTTP200、completed、准确模型/reasoning/store/stream策略、输出phase、无拒绝/截断/工具调用、严格JSON/本地规则/固定echo均满足才推进。缺usage/unknown发送或超预算即停。
4. format/strict/Schema回显若存在必须与准确请求相容；矛盾即停，缺回显记录unknown。即使样例成功也只证明观察兼容，不宣称所有未来输出受Schema强制；这种证据局限须在准确执行包提前获接受。
5. 七个槽全部通过且处于有效窗口才完成协议准入。任何失败保持完整分母与未运行，不能跳过B/修复接口或只用C规划旧成功充数。通过后只准备课程包，另获授权才能外发课程。
