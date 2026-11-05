# T109 r01 真实首稿全文独立教学评估

2026-11-05。**结论stop，不发布，不调用修订。** 首稿严格结构通过，无格式恢复，但不可修订的failure_scope有范围声明阻断，另有段落5引用支持不足。不能因尚有请求余额而改范围、补写原稿或用summary覆盖不可修改段落。准确机器意见见final-review.json；没有创建repair-review.json。

准确候选 `63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`，parent=null，basis绑定见JSON。安全导出原HTTP17052字节／SHA `b5acad36fceae43082f8facc2c0c14990f98d15715b9610f7da8cca554d9fa95` 独立重算通过；请求等于m.body准确payload；原完整适配、record和candidate独立重放相等，strict_failure／recovery均null。同版B材料与冻结材料完全相同。评估者只读安全导出，没有读取vault、key或终端，没有Provider调用，没有补教学文字。

## 阻断位置

**S01：failure_scope范围声明，不能在本批修。** 原句：“本课假设主流程中的分配都成功，只通过 allocation_success 条件掩码演示‘不分配’的分支；真实的 malloc 失败并未被动画演示。”当前两次allocation_success均true，13帧没有mask=false／p=NULL／return old-head的分支。确有显示包含条件表达式的代码，且本段文字解释了p为NULL的后果；不能据此声称交付了“不分配”分支的实际演示。

若把“演示”仅理解为静态代码讲述，该句仍未明确说明掩码不分配分支也未在轨迹中演示，而只否认真实malloc失败动画，容易把代码支持能力和已展示过程混同。不论采用哪种读法，都不足以签署“未演示分支范围清楚、讲解与状态一致”。该字段在ADR0053明确不可修改，不能用允许段落／summary新增澄清来留下互相冲突的原句。因此本批必须停止，剩余请求失效，不尝试局部修订。

**C01：paragraphs[5]引用支持不足。** 该段解释忽略返回值后caller保持原入口、新动态节点不可达，结论本身正确；列出的trace_step_05和trace_step_10却是正常接收返回值后的caller=t0／t1，obs_allocation_failures仅表示正常主流程失败次数0。它们没有逐项提供该反事实分支的状态证据。planning_basis.ignore_return确有正确结果且可独立手算，因此不把结论判成算法事实错误；但不能把这些normal路径fact_ids签成已充分支持忽略分支。它是可定位段落引用问题，单独看属于允许修订范围，却不能覆盖同时存在的S01。未为赶窗口降成非阻断或预填fact_citations=true。

## 全文逐段核对

| 部分 | 独立结论 |
| --- | --- |
| prerequisites | 准确保留C指针／struct／NULL／返回值的自述起点，未知细节没有臆测。 |
| paragraphs[0] | 接口、按值复制与共享节点区别正确；trace00/01显示caller与局部head同指i0，语言语义由同版代码和basis补充核对。 |
| paragraphs[1] | 分配、未知字段、成功条件求值为假、失败时不解引用NULL均正确；没有复发必须先data再next或成功时跳过检查的旧错误。引用01/02准确定位字段初始化。 |
| paragraphs[2] | 引用02/03/04定位data、link、return前后；next保存旧头、旧节点不变的讲解正确。 |
| paragraphs[3] | 引用04/05显示返回和caller接收前后，局部生存期与节点存储分开，正确。 |
| paragraphs[4] | 引用两次caller/第二次分配/返回及最终观察，明确接收后0、6、-8到NULL；具体t1.next=t0可由同版link帧／basis核对。未捏造head=p。 |
| paragraphs[5] | 丢弃返回与分配失败区别正确，但引用不能签逐项支持，见C01。 |
| lifecycle | 自动i0不可free；动态t0/t1不因函数返回消失；先保存next再free且不读已释放节点，正确。不演示清理明确。 |
| failure_scope | 对NULL时行为及失败／丢弃差异的算法解释正确，已演示范围声明S01阻断。 |
| learning_summary | 两个核心目标、指针副本与节点、接收／忽略返回、最终B值序列正确；未复发初始化顺序或判空旧错误，未提供迁移答案。 |

六段没有相邻逐字或近似复制；各段职责分别为接口、副本／分配、链接、返回、接收和丢弃，必要代码步骤和生命周期覆盖。范围声明问题不能被其他正确段落抵消。

## 13帧核对

初始i0{-8,NULL}，插6再0、两次成功。逐个对照模型title/note、程序材料state、行号与作用域：

| 帧／行 | 独立状态与结论 |
| --- | --- |
| f00／无 | caller=i0，i0{-8,NULL}，head/p不存在，正确。 |
| f01／4 | head=i0、p=t0，t0{?,?}，正确。 |
| f02／5 | p非NULL，条件为假，不执行return head，状态不变，正确。 |
| f03／6 | t0.data=6、next仍未知，caller/head均i0，正确。 |
| f04／7 | t0.next=i0，旧链不变，正确。 |
| f05／8 | 返回t0，caller仍i0，局部即将结束，节点仍在，正确。 |
| f06／15 | caller=t0，可达6→-8，局部不活动，正确。 |
| f07／4 | head=t0、p=t1，t1{?,?}，正确。 |
| f08／5 | 第二次条件为假、caller仍t0，正确。 |
| f09／6 | t1.data=0、next未知；0是有效整数不是空指针，正确。 |
| f10／7 | t1.next=t0，结构t1→t0→i0存在，caller尚t0；文字只称结构没有称当前caller已更新，正确。 |
| f11／8 | 返回t1，局部即将结束，正确。 |
| f12／16 | caller=t1，局部不活动，0→6→-8→NULL，正确。 |

没有判空失败／不分配分支帧，正是S01的证据。未实际运行浏览器，不把这些静态正确状态说成播放器已验收。

## 四题重新手算

题干使用独立迁移初始i0{30,i1}、i1{40,NULL}，插入11一次。normal代码接收返回，discard代码丢弃。代码与程序情境一致，无结果数组、正确节点名或计数的直接提示；前文B参数为-8、6、0，没有代答迁移题。

- link_target：head=&i0，因此p->next直接指i0，答案i0，解析正确。
- normal_values：t0{11,i0}且caller=t0，沿next为[11,30,40]，解析正确。
- discarded_values：caller仍i0，原链未变，沿next为[30,40]，解析正确。
- unreachable_count：仅t0是动态且不可达，i0/i1自动节点不计，答案1，解析正确。

四题采用本课成功分配前提；allocation_success=1只是允许malloc而非现实成功保证，课程整体已作成功假设，没有把数据0与NULL混同。反馈和私有答案接口未运行；首稿没有进入应用完整课程，不预填浏览器或正式掌握度通过。

本次结果分开记：规划语义pass；真实首稿首次结构pass、恢复0；静态教学stop；修订未运行；完整新课程／浏览器未交付。原件和失败保持，T102仍blocked，按准确批停止，不再使用剩余请求或扩大可修字段。
