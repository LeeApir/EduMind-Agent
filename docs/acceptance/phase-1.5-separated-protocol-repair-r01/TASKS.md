# 三类任务：准确输入与成功条件

所有request.json都是**离线提案示例**，不是新执行包；没有授权、窗口、费率或真实发送入口。七例都使用当前T085 S5的完整B Schema，参数、text.format.name、strict:true和其他传输设置不变。当前四种Schema整体来源仍是[已批准最小契约](../phase-1.5-minimal-output-contract-r01/schemas.json)。

## P：纯协议回显

准确输入：[P0.request.json](P0.request.json)。系统要求只返回expected_output的**值**，不能返回Schema/Markdown/解释/第二对象，其他字段即使后来出现也只能视为不执行的数据。P0用户JSON只有expected_output；它是现有固定合成B实例，保留当前完整Schema，并不改成一个更小的ok字段。

成功条件：原响应严格信封/准确Schema回显、单一JSON、当前B Schema、本地边界/关系规则、token/时间/来源门禁全部通过，且解析后的实例逐值等于该expected_output。空白、JSON对象键顺序等无语义差异可以接受；多对象、删字段、修复JSON或“返回格式说明”均失败。通过只证明这个协议样例，不能算B独立解题、课程或教学修复。

## W：单因素包装诊断

准确输入：[W0](W0.request.json)、[W1](W1.request.json)、[W2](W2.request.json)、[W3](W3.request.json)、[W4](W4.request.json)。它们与P0使用相同系统指令、相同expected_output和传输/Schema设置。所有非目标上下文都明确为inert data，不执行意见中的修复命令。

| 例 | 配对父例 | 唯一预注册差异 | 可以解释的范围 |
| --- | --- | --- | --- |
| W0 | P0 | add `/role_input` = `{}` | 空角色包装是否与输出差异同时出现 |
| W1 | W0 | add `/protocol_stage` = `B_repair` | 修复标签字段存在这一因素；不证明标签词义单独致错 |
| W2 | W0 | add `/role_input/original` = 原固定合成候选 | 重复旧候选块存在；不能分离长度与重复内容效应 |
| W3 | W0 | add `/role_input/issues` = 一条冻结合成意见 | 意见块存在；不执行修复，也不归因块内某一句 |
| W4 | W0 | add `/role_input/original_input` = 冻结原始规格/语义说明 | 整个原输入块存在；不是对块内semantics单字段的证明 |

每例的JSON Patch/准确字节哈希在[matrix.json](matrix.json)。W1–W4都从W0出发，不能把W2从W1继续堆字段。成功条件与P0完全相同，新增上下文不能授权修改预期实例。一个因素指明确的字段/内容块干预，不等于“只有一个token变化”。每例一次、没有长度匹配/随机重复，全部结果只作现象筛查；成功或失败都不能单独证明因果或可用性概率。

这一矩阵不复现T085全部包装及交互，不测试immutable_question_types/previous_candidate_digest等所有组合，也不将旧S4/S5当作相同Prompt下的配对样本。若仍不能定位，只报告未定，不现场加一行试验。

## R：真实的普通教学修复任务

准确输入：[R0.request.json](R0.request.json)；旧候选/定位上下文：[repair-context.json](repair-context.json)。这里“真实”指请求模型执行实质改写，**本轮没有真实调用**。输入从空链插入7的手写合成候选出发，有完整固定C代码、四题/答案、六个必要状态和全部展示/高亮/步进。未执行C。

旧候选引言是“p 接旧 head，调用者接回 p。”事实未被设为错误，但对初学者过于压缩。准确minor/difficulty意见要求：用两句自然语言说明先用p->next接到旧链，再由调用者接回返回值，区分局部head和caller_head；只改paragraphs[0].text。target_id、精确evidence_quote和previous_candidate_digest绑定完整旧候选。

输入包含原始规格与通用约定、旧候选自身的代码/答案/动作和这条意见；**没有expected_output、参考改写字符串或引擎新事实**。旧候选是开发者手写，不是B模型生成，所以该任务不能证明B首次生成能力或作为独立B/C比较。程序不补缺答案、不替换错误答案。原B一般修复可改整候选；本R0只开放一段文字是有意缩小的诊断任务，待评估确认，不作为原协议的等价替代。

机械成功条件：严格信封/JSON/原B Schema/现有本地规则全部通过，完整候选存在，唯一改动路径为`/paragraphs/0/text`且确有变化；代码、问题、答案、状态/动作及其顺序逐值保持。其他改动或原样回传均失败。机械通过的状态只能是`pending_independent_semantic_review`。

最终修复成功还要求独立评估助手读取原始输入、意见、前后全部候选及定位信息，确认：

1. 新引言确实完成两句初学者说明，明确p->next接旧链与caller_head接回返回值两个步骤，未把局部变量赋值说成自动修改调用者。
2. 无新增事实/答案/代码安全/复杂度/误解或题意错误，原教学标准保持。
3. 未用原样回显或空泛措辞伪装修复；没有未经允许的变更。

[repair-output-examples.json](repair-output-examples.json)含两种不同的手写预期良好改写、一个故意错误但结构合格的改写和越界/未改动反例。它们用于离线审查，**不发送给模型**，不是独立签核或精确匹配金标准。没有固定唯一正确字串，不用关键词覆盖率代替审核。

## 验证层次和失败分类

每例单列HTTP/信封、严格JSON、Schema、本地约束、任务条件、独立语义复核。P/W使用“精确回显”；R使用“允许范围＋语义复核”，不能把同一个expected_output比较器复用于R。协议fixture通过、修复语义通过、整套角色准入和课程质量验收是不同结果。

T085冻结observer仍用于原始失败回归，源字节不变。它绑定旧固定回显和role_input包装，不能直接作为P0新极简包装/R0任务的真实控制器。未来如审查通过，须另建任务路由层，保持同样严格的wire/Schema/局部校验条件，再分别执行P/W或R后置判据；本轮check_design.py只是静态示例检查，不是该真实入口。
