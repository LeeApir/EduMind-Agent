# 完整审核兼容性实测与语义核对

## 结论

独立单次修正请求成功取得完整审核结果，Schema传输/完整业务校验/准确wire与策略审计/用量/清理均通过。实际模型qwen3.8-max-0902，11479输入+403输出=11882 Token。按官方北京未缓存全价12/36元每百万的参考值为0.152256元，非账单，不假定免费。预算1/1已用尽，原始complete receipt不改；无第二请求/重试/其他样本。

语义核心检出正确，全部结构化引用有实质支持；第二条一句措辞有两种读法，需要人工复核，不宣称整体无瑕疵通过，也不将歧义硬判成已证实的数值事实错误。兼容性成功不等于质量验收通过。

## 完整性

normal_finish/schema_valid=true；准确请求摘要e47aa275af3828cc2bef90b5aade6e5ea81c62496e632401c153c9d1c42d9653，业务绑定与v4.5 Prompt符合冻结；输出403≤8202，单send1。连接disabled、持久Key为空、版本失效三项通过。实际review_record/响应哈希保留，无原始响应/密钥/思考正文。成功状态由完整结果和本地完整Schema检验得出，不据HTTP状态猜测。

## 全部断言与全部引用

|位置|核对内容|证据与判断|
|---|---|---|
|finding0 condition|数组长度3，合法0至2，实际读取a[4]|a6源代码直接支持；可达越界的核心判断正确|
|finding0 condition|越界属于未定义行为；不保证特定返回值或正常执行|与源码事实相符，未推出确定数字/崩溃|
|finding0 impact|学生看到的标准示例含可达越界，不能正确示范数组安全求和|原目标要求下标0至2及求和循环；a6和绑定目标支持，该影响不是新增图谱必达目标|
|finding1 condition|讲解有total=0，i=0/1/2，total=2/7/16，i<3边界，return16|a1完整片段支持所有这些命题|
|finding1 condition|实际源码没有loop/total/i，而return表达式为a[4]|a6直接支持；不是用未定义行为推算固定值|
|finding1 condition|“returns a[4] (undefined behavior) instead of 16”|表达式和UB正确，但instead of 16可被读成源码实现对比，也可被读成排除返回16；后者不成立。结合finding0的no particular return guaranteed，不能武断判为明确的必定不等于16断言，亦不能当作完全无歧义通过，保留原文待人工|
|finding1 condition|key_steps中2/7/16状态与i=3检查在源码不存在|正文引用a3/a4分别直接支持步骤文字，a6证明源码没有循环变量；额外正文引用也逐个核对，不能只检查anchors数组|
|finding1 impact|源码没有实现讲解/步骤的算法，因此无法据它追踪该循环，单元矛盾|a1+a6及实际a3/a4支持，严重程度major与整体reject有根据|
|全部结构化引用|finding0的a6；finding1的a1和a6，共3次|绑定资源digest/JSON指针/UTF8片段均核对，有实质贡献；未发现仅字段相关的无关辅助锚点|
|coverage/unresolved|5个checked，无unchecked/unresolved|结构完整且检查项无重复；未新增动画要求或误读q3。空unresolved是模型原输出，不抵消上述待人工措辞。不得用声明checked替代语义审查|

没有要求把已在正文准确引用的a3/a4强行补入anchors数组；现有契约未规定此约束，不额外发明失败判据。没有q3判断题曲解或答案字段借邻字段。

## 后续边界

本次用户批准只覆盖1次兼容性请求；结果人工签核未预填，语义状态needs_human_review_of_ambiguous_wording，非生产审核协议中由模型返回的needs_human。旧所有账本仍停止；不能据此自动恢复旧候选或跑后续材料，更不能计入T040正式验收分母/分子。历史400存在已证明Schema不兼容点，修正后成功说明当前请求可用，仍不追认此前每次400的唯一原因。
