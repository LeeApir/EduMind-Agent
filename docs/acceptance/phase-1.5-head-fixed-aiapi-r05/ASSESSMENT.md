# T111 AIAPI r05 提取正文独立评估

2026-11-09，评估者 `/root/head_goal_independent`。**诊断正文的教学评估通过，十项检查均为真。外层协议结论仍为 `AIAPI_ENVELOPE`，本样本准入资格为 `false`。** 精确候选 `b7759b9d5d7b7f0cf2fb96445e776d1fec3592dd97c1d741f1ee655a5fedcdc9`，parent=null。[教学机器记录](teaching-review.json)

## 评估对象和绑定

使用执行方从完整HTTP200响应中无改写提取的text-only诊断文件。文件SHA为 `7234c656b147261c606dc66552c599da2a43219c9bc7aa23add4fb2c3ef8dc2c`，其记录的原响应SHA为 `9ee52d2cac136a4a12fa2b0847dac26364a0ff2b2b8f3e8e3420afcaf27639e9`，提取正文SHA为 `3b60c059efe52991aeab4fb3e669356c8923f4b567e828af349be4abe116ec79`。独立复算候选摘要并重走内容校验及本地装配。原始加密响应的回读与提取由执行方完成，本次评估的直接输入是安全导出。[诊断输入](text-inspection.json)

payload与历史候选使用的原payload逐对象相等，保留已审计划 `0997615bbdb35b96df95904d4d4d1730d08a94a2f797091c04a48e484a6452ee`、head-new-C同版材料及原先备自述。证据版本head-teaching-evidence-v1，摘要 `8a4c8b44ac01d0f72660c222ff849c45a014ee8157b3725031ad34f18a3d5553`，完整basis和materials绑定见机器记录。

诊断记录外层缺少model和store。请求模型为gpt-6.1-sol，实际响应未确认模型身份或store状态。教学评估仅归于提取内容。严格响应接收失败仍作为本批协议结果，应用课程、浏览器学习与反馈验收均未发生。[本批准确方案](README.md)

## 原 r03 问题复查

**F01未复发。** `paragraphs[1]` 分别说明malloc后两个字段不确定、本例第6行只写data，以及第7行写入next后才可沿这条链接遍历。它准确限定在模板状态和读取相应字段前的初始化条件。C允许在有效新节点上先写next再写data，全文没有将本例的相对写入顺序升格为语言规则。

**Q01未复发。** 四个迁移题干逐题明示“假设分配成功”。`unreachable_count` 还限定“insert 调用结束后、main 返回前”，从caller_head沿next计数。因此唯一动态t0因返回值丢弃而不可达，计数1。主例的成功假设与各迁移题自身的成功前提分别清楚。

原r03另有只举第一次丢弃调用的表达问题。本文 `paragraphs[4]` 明示独立对照将两次调用都改为忽略返回值，准确使用discard_return_comparison证据。对应的t0、t1均不可达。[历史全文标准](../phase-1.5-head-fixed-t111/review-policy.md)

## 逐段及范围

| 位置 | 核对结论 |
| --- | --- |
| prerequisites | 原目标及[5]、-2、9两次成功前提准确。C指针、struct、NULL和返回值只作为自述先备。 |
| paragraphs[0] | trace00/01支持i0初值、NULL尾、caller及局部head指向。由同版C接口核对按值复制及p为局部指针的语言解释。 |
| paragraphs[1] | 展示证据及trace01/02支持成功分配、两次判空、未知字段及写data后next仍未知。next就绪才可沿新链接访问，与F01反例相容。 |
| paragraphs[2] | trace03/04/05支持t0.next=i0、return p返回地址值、caller在第15行接收前保持旧值。旧链内部未改，局部p变量本身未被返回。 |
| paragraphs[3] | trace06/08/10和两个观察支持第二次head=t0、t1.next=t0、main第16行接收及[9,-2,5]到NULL完整终止。 |
| paragraphs[4] | 引用独立discard_return_comparison，明确两次均丢弃、两次局部head=i0、两个动态节点各指i0、可达仅[5]。旧头没有反向指向新节点。 |
| failure_scope | 程序模拟，两次成功并实际呈现两次判空为假。掩码0时不调用malloc，真实分配失败也可使p为NULL，两种失败均未在主画面展示。第5行返回旧head且不写字段的静态能力与展示范围分开。 |
| lifecycle | 自动i0/i1与动态t0/t1的生存期及所有权清楚。局部指针结束不释放动态节点。清理先保存next，free后不读字段，遇到自动节点不free。清理未动画或执行。 |
| learning_summary | 链接旧头和交回新入口的职责区分清楚，接收两次后遍历[9,-2,5]并到NULL。装配中的text-10和head-state替代文本与这份总结逐字相同。 |

五段分别承担接口与作用域、分配判空、第一次链接与返回、第二次插入和独立丢弃对照。各段依据支持具体状态，代码语言语义另从同版C核对。未发现邻段复制、必要解释遗漏或相互冲突的教学说明。

## 13帧

从固定代码独立手算，逐帧断言装配行号、caller/head/p、返回值、各节点data/next及locals_scope，并逐句比对标题和说明。`?`为未初始化。

| 帧与行 | 状态核对 |
| --- | --- |
| f00／无 | caller=i0，i0{5,NULL}，局部未活动。 |
| f01／4 | head=i0，p=t0，t0{?,?}，caller=i0。 |
| f02／5 | p非NULL，条件为假，继续第6行，字段保持。 |
| f03／6 | t0{-2,?}，next不可遍历，caller/head仍i0。 |
| f04／7 | t0{-2,i0}，旧i0保持，caller尚未更新。 |
| f05／8 | 返回t0地址，caller仍i0，调用者赋值尚未完成。 |
| f06／15 | caller接收t0，-2→5→NULL，局部值是已结束调用记录。 |
| f07／4 | head=t0，p=t1，t1{?,?}，caller=t0。 |
| f08／5 | 第二次条件为假，未提前返回，继续第6行。 |
| f09／6 | t1{9,?}，caller/head仍t0。 |
| f10／7 | t1{9,t0}，t0.next=i0，caller尚在t0。 |
| f11／8 | 返回t1地址，caller仍t0，赋值尚未完成。 |
| f12／16 | caller接收t1，9→-2→5→NULL，head/p为历史记录，动态节点仍在。 |

全部帧的说明、程序状态及代码行一致。f00/f06/f12的局部状态不活动。独立丢弃对照的主帧引用为空，程序及全文均将它与可播放的正常路径分开。

## 四题

迁移题各用对应程序代码。i0{30,i1}、i1{40,NULL}，在题面明确成功的前提下插11。题干的数值与地址是推导必需输入，格式提示无答案示例。主例中的[9,-2,5]不代答迁移题。

| 题 | 独立推导及解析核对 |
| --- | --- |
| link_target | head=&i0，t0.next保存i0地址，答案i0，解析准确。 |
| normal_values | 接收t0后由t0、i0、i1到NULL，答案[11,30,40]，解析准确。 |
| discarded_values | 丢弃t0后由i0、i1到NULL，答案[30,40]，解析准确。 |
| unreachable_count | 在成功分配、丢弃返回值、main仍活动的明确条件下，唯一动态t0不可达。自动i0/i1不计，答案1，解析准确。 |

上述答案与程序参考一致，题目与解析对应。评估实际覆盖文本诊断及本地装配结构。真实应用中的答案私有投影、控件、作答和刷新仍无本样本运行记录。评估者Provider调用0。[T111验收标准](../phase-1.5-head-fixed-t111/review-policy.md)
