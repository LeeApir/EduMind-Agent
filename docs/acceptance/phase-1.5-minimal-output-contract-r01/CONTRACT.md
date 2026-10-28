# 最小输出契约 r01（待确认）

本文件为隔离头插小实验的设计输入，不是已实现接口。权威结构见[schemas.json](schemas.json)，所有本地规则是未来实现的强制要求。静态检查器只演示其中可机械核查的规则，不宣称完成生产校验。所有正式安全清洗、来源/身份/版本、预算与未知隔离继续有效。

## 1. 范围与共同信封

覆盖六种实际模型阶段：B生成/B修复、C规划/C内容/C修复、共用教学审核；审核对B和C分别做协议准入。示例、动作、调度与身份由程序承担，不新增模型调用。独立评估者不是待测Provider角色，不能拿模型审核代替独立结论。所有旧Schema完整快照和所有嵌套节点均在[全量审查](original-schema-audit.json)。

程序持有run/slot/arm/revision/parent_digest、spec/template/engine/Prompt/contract版本、输入/输出摘要和唯一attempt。它们不交模型计算；请求/响应原件、绑定清单与事件链是权威。短ID只在准确请求上下文/版本内有效，不能跨候选复用或被模型重新定义。ID表包含完整内容摘要；ID相同但摘要不同即拒绝，不通过文字回显证明上游身份/完整上下文。

角色Schema输出之外的任何字段均拒绝，缺字段不补。raw JSON重复key、NaN/Infinity、非对象根均拒绝。所有对象列全required、additionalProperties:false，所有array有明确items；wire不含联合类型或开放对象。长度/数量/唯一性等本地约束不是可选建议，不能因Provider接受而跳过。response大小及时间先于解析检查，原件保持不变。

## 2. 事实/规格/审核定位表（程序）

- spec_catalog：有限spec_id → 原始合法规格及摘要；本实验每槽只有准确允许规格，模型不能换成别的合法规格。
- fact_catalog：obs_caller_head / obs_traversal_status / obs_reachable_prefix / obs_allocation_failures，以及trace_step_00..实际存在的步骤ID。每项有kind、完整值、原始路径和example_digest。值可以是内部复杂结构，**不在模型输出Schema中**。目录只覆盖已核定引擎的事实，不把自然语言讲解登记成已证真事实。
- question定义：四个固定字段分别映射对应observation和fact_id。输入提供其题型与观察范围，不能把“已知前缀”说成循环/未初始化时的精确完整输出。
- review target_catalog：稳定target_id → 当前完整候选字段的路径、规范文本、字段类型和摘要。文字用原字符串；数组/数值等用规范JSON文本。每个可审核字段均有定位或有明确不可投影失败；不能静默忽略答案、代码、动作或自由讲解。提供完整source和允许参考，不只提供target表。

[context-example.json](context-example.json)是空链插入7的手写开发演示，只有部分示意target/trace用于例子，不是完整真实执行目录、独立参考或课程。未来实现必须构造完整目录并做缺项/摘要/版本负测；不得把该开发样例当通用装配器。

## 3. C规划输出

`{spec_id: string, objective_ids: string[]}`。

objective_ids恰好覆盖trace_head/trace_termination/trace_values/trace_failures，各一次。保留模型选择和排序；coverage由冻结目标定义映射，不要求重复返回四对固定映射。程序解析spec_id，不让模型重写initial_values、insert_values、variant、allocation_success或版本。返回错误ID/重复目标/漏目标即原件失败，不能猜测修正。规划输出没有正文，不能当可学课程。

## 4. C内容与普通教学修复输出

`{paragraphs:[{key,text,fact_ids}], questions:{caller_head:{stem,explanation,fact_ids}, traversal_status:{...}, reachable_prefix:{...}, allocation_failures:{...}}}`。

1–8段；key为`[a-z][a-z0-9_]{0,31}`且全局唯一，不与code及q_加四个题型名的固定锚点冲突。每段、题干、解释为1–4000字符自然语言，保留完整教学责任。每个fact_ids有1–12个不重复、当前目录中真实存在的ID；每题必须含对应observation ID。程序解析事实，显式记录origin=deterministic、fact_id与版本；不把解析值伪装成模型答案或自动插入/改写正文。

程序由固定题型名赋予题ID，不再让模型任意声明observation_key。四题不能漏/换/增；题干语义与类型/答案是否一致仍须审核。C输出不含代码/答案/actions；装配时只能使用准确引擎原件，不能推断、默认或补造未知值。代码、答案、动作原本已由程序拥有，此次改变的是事实引用和值复述、题目表示及规划冗余。

C修复复用同一Schema，只接收当前完整旧内容、原始允许输入和准确普通教学意见；最多一次；不改spec、fact目录、题型、答案、代码、动作、规则。任何事实/安全问题或unknown停止，不进入修复。不能用语义修复机会重发格式失败。

## 5. B生成与B普通教学修复输出

`{paragraphs:[{key,text}], code:string, questions:{四个题型:{stem,explanation}}, answers:{caller_head, traversal_status, reachable_prefix, allocation_failures}, actions:{states, highlights, advances}}`。

段落、题干、解释使用C同一数量/长度/锚点规则；code为1–20000字符。B必须独立生成完整C函数、调用者代码与模型动作，沿用固定模板语义和安全要求，但本轮协议fixture不声称是C课程。**缺少任何答案、代码、状态或动作均拒绝；不得从引擎或C输出补齐，错误答案保留错误。**

| 四类答案 | wire类型 | 本地范围与语义 |
| --- | --- | --- |
| caller_head | string enum：none/i0/i1/i2/t0/t1/t2/t3 | none只编码空指针；最终头必须由模型给出，独立对照判断正确性 |
| traversal_status | string enum：terminated/cycle/indeterminate | 只描述终止分类，不声明有限遍历次数 |
| reachable_prefix | integer[] | 0–7项、每项-99..99；已知可达前缀，不能把它伪装成不确定情形的完整输出 |
| allocation_failures | integer | 0..4，bool不当整数 |

这些是所有槽共同的通用候选域，不按当前正确答案缩窄enum，也不把B问题改为读取fact_id。B生成/修复输入只含原始规格/目标、模板语义、通用ID/格式约定，不能含fact_catalog、engine_example/code/actions、expected_answers、独立真值或C候选。审核可以接收程序参考；仅按旧规则允许普通教学意见进入B修复，不夹带引擎计算结果纠正事实。

### B动作的有限表示

- states：1–64个`{order,step,caller_head,local_head,p,nodes}`；nodes为最多7个`{id,data_status,data,next}`的闭合数组，节点ID来自通用i0..i2/t0..t3，各状态内不能重复。
- 指针为固定string enum：none、indeterminate、七种节点ID；非哨兵须引用当前状态已声明节点。data_status=known时data为-99..99整数；indeterminate时data必须是占位0，并在展示/比较中还原为未知，绝不能解释为观测到0。该双字段设计保留分配后、data赋值前的状态。
- highlights：`{order,step,line}`数组，line为实际模型代码存在的1..600行号；advances：`{order,step}`数组。三数组按全局order合并，必须恰好0..N-1，N≤180；show_state的step唯一且0..63，其他动作引用已声明step。
- 程序只能合并表示、加命名空间anchor并做静态拒绝，不补缺状态/步骤或计算正确next。原动作列表的先后顺序按order精确保留；不因拆数组改变时序。完整指针步骤、状态事实、题意相关动作是否完整仍依原要求独立核对，不以动作数达标代替。
- 旧数据的null↔none、节点map↔唯一ID数组、已知/未知tag及列表↔带order分组存在条件可逆映射；允许域/约束已改变，仍按新契约审批，不直接用新表示改写旧原件。

B修复复用整个B Schema，可按既有规则改完整候选，最多一次。它与C仅改内容的差异继续披露，不把它抹平成相同干预。

## 6. 教学审核（B/C、首次/修复后共用）

`{candidate_id, verdict, uncertainty, issues:[{severity,area,target_id,evidence_quote,reason}]}`。

candidate_id必须等于当前请求绑定表条目，对应完整candidate_digest；保留原件及关联，拒绝旧revision/父候选/另一臂回显。不要求模型计算/回传长摘要。verdict仅pass/revise/unknown；uncertainty是≤4000字符字符串：unknown时非空，其他时必须空串。scope_status由上述状态规范化派生，只表示上下文是否足够，不是穷尽性保证。

issues最多20项，severity=minor/major/severe，area=fact/difficulty/misconception/code_safety；target_id必须能定位当前完整候选字段，evidence_quote为原目标规范文本中的1–4000字符准确子串，reason为1–4000字符。pass须无issue，revise至少1项；unknown可携issue但必须停止。精确quote只是可定位条件，不能证明审核推理正确。事实/代码安全意见或severe按旧策略先停复核；最终错误裁决仍由授权评估者完成。

输入必须包含完整当前source、其target_catalog、程序参考、original_goal、plan_constraints及必要upstream，原教学标准逐项保留：事实、步骤、答案、代码安全、复杂度、难度、误解与自由文本一致性。不得只审fact_id正确性。后续Prompt版本只改变信封说明，原标准文件字节不动，差异需逐条审查。模型pass不自动发布或评分。

## 7. 本地硬门与审核分工

wire成功→原件/Schema/上下文ID/边界/唯一性/跨字段/清洗校验→完整装配→模型教学意见→独立事实/逐题/动作/讲解核对。每层分别记结果；格式成功不计教学成功；C引用正确不计讲解正确；B答案格式合法不计答案正确。任何缺失不合成默认值，全部新旧原件和未运行分母保留。

[examples.json](examples.json)包括故意格式合法但讲解错/答案错/题干范围错的例子：检查器必须承认结构通过，明确交审核/独立评估。协议示例不是一份可评课程，独立评估尚未进行。
