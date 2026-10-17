# 续测第2条：教学缺口＋越界，未通过后停止

## 结论与停止依据

模型返回完整且有效的审核结果，保持major code_safety/reject并正确检出长度3却访问a[4]。但未满足混合样本冻结判据：unresolved为空，未单独说明学生可见过程支持/过程考查缺口。此外finding1明确写“whose result is undefined, not 16”，从未定义行为推出“不是16”，结论强于证据。两点独立存在，整体不通过。新候选按首败规则停止，不改变材料/Prompt/Schema/判据来补过。

这是业务诊断判据失败，不是HTTP400、JSON解析或Schema失败。CLI的requests_sent=null来自通用本地失败观测未附sent；真实完整outcome.sent=1以及Token和准确wire审计证明实际仅1次，不能把null当成没有请求。账本保留首个归一化INVALID_OUTPUT，具体gate_code=CANDIDATE_CRITERION_FAILED；不改写halt冒充其他错误。

## 完整性

normal_finish/schema_valid=true；真实模型qwen3.8-max-0902，11230输入+397输出=11627 Token，输出397≤8202，单send1。准确request_sha7f52c84047e506edd4807ff1b90e453a60f689810bcc25224b14ddac30e181b6、binding、v4.5与冻结一致。临时连接disabled/持久Key空/配置版本失效均通过。完整原review_record、正常但判据失败receipt和outcome均保留，不删finding，不伪造Schema错误。

## 全部断言与引用

|位置|核对|结论|
|---|---|---|
|finding0 condition|a5明确数组3元素、有效0至2、return a[4]，无循环/求和|源代码直接支持可达越界与UB；核心安全检出正确|
|finding0 impact|错误源码作为学习单元代码示例向学生展示|材料中的code资源及目标支持；major/reject保留正确，未因教学缺口降为待人工|
|finding1 condition前半|a1确写sum返回16，实际绑定目标及计划要求数组求和说明16；a5无求和且return表达式是a[4]|这些具体声明及实现不匹配有证据，a1/a5有实质贡献|
|finding1 condition后半|“whose result is undefined, not 16”|不成立的数值排除：UB不保证16，也不能证明必非16。a5仅证明危险操作与无保证；不是上一例可作源码表达式比较的instead of16措辞|
|finding1 impact|把具体结果称为returns undefined value，并以此与16作直接矛盾|代码不实现目标的矛盾应保留；但UB不是语言定义的一种特殊返回值，也不保证正常返回。不能把缺少保证当作确定值反证|
|finding2 condition|a3“遍历并求和后返回结果”，a5无loop、无sum，直接return a[4]|字段和源码直接支持，属于真实实现与步骤描述不符，不应因其他错误抹去|
|finding2 impact|所述算法在源码中完全未实现，误导学生理解代码|a3/a5支持；此事实错误检出不等价于完成纯教学覆盖缺口报告|
|全部5次结构化引用|a5；a1/a5；a3/a5|资源digest/指针/UTF8片段有效，相关事实各有实质支持；但引用a5不能支持finding1的not16推断，故不是“所有论据均被引用支持”|
|coverage/unresolved|5 checked、unchecked空、unresolved空|结构/去重合法。覆盖声明不能补缺失教学审查；冻结mixed要求reject+具体缺口unresolved，本例空数组不满足|

## 教学缺口独立核对

学生讲解a1只给数组容量/下标及返回16；key_steps a3仅“遍历并求和后返回结果”，源码本身无循环；练习只考合法下标、2+5+9=16算术、return与print概念，未要求追踪循环的中间状态和退出边界。a11包含2+5=7、7+9=16的算术分解，不能当作已明确展示i/total逐轮状态及i=3退出条件。内部plan虽写有轨迹，student_delivery规则不把内部计划当学生交付。缺口可分布在任一学生可见资源，不要求讲解重复所有内容，也不新增动画要求。模型finding2只指出步骤描述与代码实现不符，未给独立过程支持/考查缺口，unresolved仍空。

## 用量与状态

本条按官方北京未缓存12/36元每百万参考0.149052元（非账单），新包两条共23388 Token，参考0.294360元。新预算已用2/11，保守已占26.556612元，剩9槽预留119.588268元按冻结规则不复用。持久halt INVALID_OUTPUT，原首条complete/人工通过保留；旧17账本不变。没有发送正确对照或迁移材料，没有重试/调参/回退/更换候选。T040 blocked/catalog_only，正式质量验收未开始。
