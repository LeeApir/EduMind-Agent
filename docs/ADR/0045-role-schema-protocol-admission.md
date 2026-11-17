# ADR-0045：课程前置的三角色合成协议准入

2026-10-28；Proposed。T077只准备；本提案仅T078 / role-probe-r01，等待准确A—C和执行包批准，不授权课程。

## A：接受集合不变的类型显式化

T076单变量观察已复现DeepSeek对最小enum-only的拒绝，见schema-compatibility/results-p02。对头插C原型的PLAN_SCHEMA、CONTENT_SCHEMA和REVIEW_SCHEMA，仅给没有type/anyOf/$ref、且由字符串enum或字符串const蕴含字符串类型的节点增加type:string；分别5、1、4处。原enum/const、长度/数量、uniqueItems、联合类型、开放JSON值及其他全部约束保持，不投影或删约束。

当enum所有成员为字符串，或const为字符串，原接受值已经都是字符串；增加该类型不改变每节点或整个Schema接受集合。固定原Schema和wire Schema逐项存schemas.json；原源码/教学Prompt保持字节不变，返回值继续通过原完整本地Schema。未证实的关键字支持仍留待实际观察，失败不自动删约束。

仅在新隔离准入中，对生成和审核message沿用缺省或准确phase=final_answer的校验视图；原始响应保留，其他值/位置和其他未知字段仍拒绝。审核保留原Review规则：缺回显未知，回显仅准确system或已知37字符后缀；最多一段4096字符summary及指定成对同UUID元数据隔离、不信任身份，其他协议/工具/用量门禁不放宽。若响应明确回显不同format/strict/Schema则停止；缺Schema回显记未知，即使样例符合也不证明服务会强制保证所有未来输出。此处是新目的的明确范围，不继承旧批准或改生产。

## B：三个固定协议fixture及最小调用

S1为C规划Schema、S2为C内容Schema，均用DeepSeek官方api.deepseek.com/responses / deepseek-flash / none；S3为审核Schema，用AIAPI aiapi.world/v1/responses / gpt-6.1-sol / low。温度0.2、strict true、非流式/store false，仅发送完整角色Schema和手写合成echo JSON，消息要求准确原样返回，不评教学。

这些fixture不是课程：内容引用故意不对应课程事实，原课程语义校验仍拒绝；审核固定unknown/insufficient_evidence和全零占位digest，不代表实际审核结论。没有学生、旧签核材料、e03真值或H；不调用教学工作流、评分、发布或C执行。

每角色最多1HTTP，依S1→S2→S3逐个完整200/协议/准确fixture/原Schema通过才推进；任一异常终止。最多3HTTP，无重试、重定向、回退、修Schema补发、额外计数/models或续批。新窗口300秒含本地处理/等待，单HTTP90秒，每个目标DNS等待最多9秒（空凭据子进程/超时终止回收），两次生成复用核定公网IP，审核单独核定公网目标并保留Host/SNI。

输入本地占额每请求8192、总24576；输出请求上限S1/S2各2048、S3为4096、总8192。请求体≤16384字节、响应≤65536字节。报告用量超单次界限即停；预约不代表可验证服务端硬限，未知占额不退款/重发。

pricing.json按2026-10-28公开标价和全部占额参考$0.0917504，非实际账单上限；实际账户币种/费率、推理/缓存和中转上游上下文/路由/留存、取消后收费及输入/输出硬界未独立认证。提议本包再次明确接受**实际金额不设硬上限**和这些边界风险，不继承旧例外。

## C：准确授权、证据与课程门禁

新scope/package/全部例外及300秒窗口在Key/.env、DNS或创建输出前校验。生成只用EDUMIND_DEEPSEEK_COMPAT_API_KEY；审核优先EDUMIND_AIAPI_REVIEW_API_KEY，缺失/空时仅当generic Base URL准确为https://aiapi.world/v1（可末尾斜杠）才借用EDUMIND_PROVIDER_API_KEY，不向其他服务回退。

固定新目录/private/tmp/edumind-p15-role-schema-probe-r01仅一次创建，0700/0600原件与逐事件摘要链；预约后唯一发送、每角色可信校验后推进、任一终态不可逆。只读核验从原件重算全部控制/Schema/时钟/来源，不采纳篡改summary，区分real/mock、协议用量未知和未运行。完整三角色通过且窗口内成功终态才protocol_admission_complete；只读核验本机时间数值不是外部时间/身份/账单证明。

这是合成上下文下三个实际角色Schema和响应协议的必要准入，不是原教学Prompt、完整课程上下文或教学正确性的充分证明。全部准入后才准备一份新的完整可评头插课程样本（正文/确定性代码与答案/4题/动作/审核及实际复核），课程真实调用仍需独立准确包。未通过即停止，不跳过角色或把echo样例登记为课程；T038 blocked、catalog_only、H封存和原教学标准保持，不恢复全批或生产。
