# ADR-0047：头插实验的最小输出契约与全角色准入

2026-10-29；**Proposed，待外部评估助手审查及用户准确确认**。PHASE-1.5-T082仅完成设计，不批准采用、实现、Provider调用或课程实验。本ADR不取代已冻结记录；只有后续准确批准才允许按指定范围改变隔离原型。

## 背景

T069基线Schema拒绝、T078规划通过而内容拒绝、T081 anyOf控制缺items后停止。证据只证明准确请求的行为，不提供服务完整Schema子集，也不能评价模型教学质量。继续保留任意嵌套JSON并逐字段试错，无法让整套协作链进入可评状态。完整审查见[Provider清单](../acceptance/phase-1.5-minimal-output-contract-r01/PROVIDER-CHECKLIST.md)与[全量Schema快照](../acceptance/phase-1.5-minimal-output-contract-r01/original-schema-audit.json)。

## A：事实所有权、有限题型和完整讲解审核

采用[最小契约](../acceptance/phase-1.5-minimal-output-contract-r01/CONTRACT.md)。协作规划返回有限spec_id与目标ID，不重复规格值/覆盖映射；内容/修复返回自然语言和fact_ids，程序按当前候选的准确版本解析事实值。代码、轨迹、答案与动作仍由已验证引擎负责，不让模型复述任意JSON事实对象。

四类题目分别是节点指针、终止分类、已知整数前缀、分配失败计数；精确完整输出在不确定/循环情况下仍不支持。引用存在只说明来源可解析，讲解、题意、解释和答案关系仍要原教学标准审核及独立复核。程序解析不得把引用自动写成正文或“修正”模型讲解。

基线独立输出代码、四类有类型答案和动作状态；程序不能读取引擎答案补字段、替换错误或转换unknown为正确值。固定题型/通用节点ID约定是公共格式信息，不提供该槽正确答案。拒绝/失败必须保留原件和分母。

## B：最小结构与本地约束分层

采用[schemas.json](../acceptance/phase-1.5-minimal-output-contract-r01/schemas.json)。wire只使用显式单type、闭合object、完整required、带items的array及同型string enum；没有任意JSON、联合类型、anyOf、patternProperties或递归引用。长度、数值、唯一性、上下文成员资格和跨字段约束仍在本地强制，**不降低原教学与安全要求**。

审核返回短candidate_id绑定程序保存的完整摘要、pass/revise/unknown、非nullable uncertainty字符串、可定位问题。输出target_id由程序映射原候选中的字段，审核输入仍含完整候选、原教学标准及允许参考，不只给引用表。针对答案/动作等非字符串字段提供带原始路径与摘要的规范文本投影以便精确引用；投影不充当事实证明。首次与修复后候选各自绑定，不能混用。

基线节点字典改有限节点数组；状态/高亮/步进分别使用有全局order的数组，合并可还原动作顺序。indeterminate数据使用显式tag和非事实占位0；指针none是空指针编码，不是C节点名称。状态和答案仍是模型产物。具体局限与可逆条件见CONTRACT。

## C：契约变化、可比性和评分边界

采用[可比性说明](../acceptance/phase-1.5-minimal-output-contract-r01/COMPARABILITY.md)。字符串literal增加type属于接受集合等价；type联合→anyOf只有逻辑等价，远端未通过。移动约束到本地仅在最终校验合取完全保留时保持端到端接受集合，不能说wire Schema本身等价。

fact值→ID、规划不再复述coverage、固定题型答案、审核摘要→ID/指针→target ID、节点/动作表示变化均按**新的实验契约**提请确认，即便部分存在无损映射，也不能冒充原始Schema逐字节兼容修补。候选/Prompt版本必须更新；旧批准、样本成绩与首次结构指标不可继承。

两臂继续同一目标/规格、同一生成与审核配置及原教学标准；C有引擎事实而B没有，这仍是明确干预。新的输出约束改变任务难度/错误机会，结果不能与旧单例算提升率，也不能归因于角色数量。保留ADR0041的10支持+4拒绝、最多一次普通教学修复、严重错误即停及原采纳阈值；单份课程可行性通过不满足这些阈值。新独立样本须在实现与Prompt冻结后另行核定，不读取e03/H真值调优。

## D：先整套接口准入，再准备课程

采用[兼容验证方案](../acceptance/phase-1.5-minimal-output-contract-r01/COMPATIBILITY-PLAN.md)与[预算机器表](../acceptance/phase-1.5-minimal-output-contract-r01/compatibility-plan.json)。建议新独立批次最多7HTTP：C规划/内容/修复、B生成/修复、审核B/C各一。全部使用准确最终Schema和纯合成固定echo；不进行课程生成/教学判定。任何接口、协议、Schema、固定echo、来源、用量、时钟、预算或未知发送异常即全批停止，无重试/回退/逐字段改包补发。

全部7槽通过只准进入“另行准备一份可评课程”的前置状态；没有自动课程外发、旧批恢复或生产开放。服务缺少Schema回显不能证明强制执行，记录unknown；与观察兼容的条件准入须在后续准确包中明确接受，不隐去此局限。

当前真实额度0。后续实施、准确请求/源码/费率、凭据隔离、独立窗口、外发与费用边界需在外部审查后具体决定。提议预算不是可运行执行包，不继承旧金额例外或未用请求。T038 blocked、catalog_only、H封存和正式验收标准保持。

## 本轮交付与待决定

[附件入口及manifest](../acceptance/phase-1.5-minimal-output-contract-r01/README.md)绑定A—D及准确文件；check_design.py只检验静态设计材料，不是运行时适配器。设计自查不能代签独立评估。请评估助手重点核对B答案没有被代填、C事实引用是否仍可审计、讲解错误能否被独立发现、有限类型是否覆盖原支持范围及指标变更是否公平。审查后再由用户选择接受/修订/停止，当前不请求立即执行。
