# T108 四字段事实修订：完整课程独立重评

2026-11-04。**准确合并候选的静态教学评估通过，附两项非阻断质量意见。** 这不是仅确认F01/F02旧句消失：已重新读取全部讲解、代码、13帧注释与状态、四题题干／答案／解析及范围声明。本报告初次签署时尚未运行新实际应用与浏览器；后续已完成独立实际验收，见 BROWSER-ASSESSMENT.md。未进行学生学习效果实验。

候选 `4db6214e41291b7aa07f852914eccb56455a6c722a5d976e38764a283b936c8a`，父候选 `7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`。准确批准manifest `a96bab6b252feea6e4541d1c869a9643dabbc12164dc35bfb5dee17f51c5e4b3`；真实规划摘要 `b6cc3d5304b87673c343a9cf31f11ae2cf8b44d4f12a07e852795ac71d4e4991`。机器结论见 final-review.json。

规划依据为head-new-A，binding版本head-planning-example-basis-v1，basis `dbfa7a38e73cf8cb36df518485019556bce56a23fc7d25dd1f18fbe0f3a28899`／example basis `2f64acc2c78f3793b085c2756b1de75124bfc38d0fb5c2c3d907cef4ad15638a`／materials `a3fc33abf64a99528d9d2a94a66f9b0721e226e48084d18b384a788a8cf7ce1e`。

## 独立证据边界

只读安全导出revision.output／diff／candidate／assembled.private、mechanical-check、request／attempt／body／window、父稿及旧独立意见，并审阅四字段合并和原完整校验源码。不读取Key、终端、raw.key或私有vault，不调用Provider，不补写模型文字。完整HTTP4022字节、SHA `fbaeb8c2b1a0acffeddaee8e5fccbd2d00e42c77450d348d3df8a6e0b946f6f7` 来自执行方安全收据；本评估者没有独立解密原HTTP，不能把安全导出一致性说成亲自核验了加密原件。

独立运行只读Python：重建f.body等于实际revision.request，request SHA `0320d95d3c502c02cff48b41e4a0e2995c6d77fbfaba3b6d8a027f04d9c96486` 与attempt一致；f.merge准确父稿／四字符串等于新候选；f.assemble等于新装配；递归差异恰为获准四路径，payload、代码、事实、答案、题目、step_notes及引用均未变。实际调用为既有执行方的一次新HTTP；评估者调用0，已停止，无自动追加。

候选文件SHA `16db731f7b5df5d84adb86e725af661192a5b17bc6b538ca421b4b86571cbd69`，装配文件SHA `d54a172ee40cd9e38475958e51bd4c7742fdf42dc683683d4657428ee6d7c9dc`。新总结同时进入text-12和head-state.text_alternative，两处逐字相同。来源准确区分targeted_fact_revision、新prompt、真实父摘要；这仍是r03原文加模型四字段修订，不是全文重新生成，也不追认原首稿结构合格。

## F01/F02与修订质量

F01已解决。新summary明确“本例代码按 data 再 next 的顺序书写，但这不是 C 的语义要求”，说明先next后data也成立、只沿next且不读data不依赖data先写。限定为已成功分配的同例有效节点，未扩张成任意C内存安全证明。原paragraphs[1]、[6]及summary中的排他性初始化顺序断言已消失；其他保留帧注释仅叙述本例字段就绪情况，不再规定两个写入必须如此排序。

F02已解决。新paragraphs[6]与summary明确第5行条件实际执行、p==NULL为假、只跳过return head分支，与f02/f08一致。真实malloc失败、清理和实际C执行仍明示未演示／未执行。

**Q01，非阻断的表达与修复指令遵循问题。** 模型paragraph_1_text逐字复制原paragraphs[0]，paragraph_5_text逐字复制原paragraphs[4]；新paragraphs[0]/[1]与[4]/[5]各重复一遍，替换段没有分别保留原分配／字段初始化及判空段的组织。连续阅读冗余，不能宣称模型完整遵循“在这些字段保留有用讲解”的提示词要求。

之所以不据此阻断完整课程：第一处分配和未初始化字段仍在完整代码、f01/f03，以及第二次f07/f09清楚说明；f02/f08和新paragraphs[6]承担判空；新summary解释初始化规则。连接旧头与接收返回值分别由paragraphs[2]/[3]/[4]及对应帧完整讲解。这些是候选本身已有内容，不是评估者补文或由旧版本借入。删除冗余段落可能改善课程，但本轮不改稿、不追加请求。

**Q02，非阻断的引用粒度退化。** 固定fact_ids依法未改，而paragraphs[5]现谈完整第二次插入，仅引用两个分配状态；paragraphs[6]现谈判空，引用仍为第一次分配／data／link状态。引用属于同版准确事实，未换例，但不是新段落每一句的充分证明。全课代码、独立帧和basis可核其正确陈述，产品正文也未展示这些ID为逐句证明。本评估没有把“ID存在”当作语义通过依据；后续如改引用需另按授权范围处理，不能静默补引用。

## 全部正文重评

| 字段／页面 | 核对结果 |
| --- | --- |
| prerequisites／text-0 | 自述C指针、struct、NULL和返回值如实保留；未知学情未虚构。 |
| paragraphs[0]／text-1 | 区分main caller_head与函数形参head、按值复制、初始i0=12及NULL，正确。 |
| paragraphs[1]／text-2 | 重复paragraph0，内容正确但冗余；分配讲解依靠下方代码与帧，见Q01。 |
| paragraphs[2]／text-3 | 写4、t0.next=i0、旧节点及caller不变、return p而非head，正确。 |
| paragraphs[3]／text-4 | main接收t0更新入口；若丢弃，原链仍在但新t0不可达，正确。 |
| paragraphs[4]／text-5 | 第二次传入t0，t1.next=t0，返回t1后caller=t1，7→4→12→NULL，正确。 |
| paragraphs[5]／text-6 | 重复paragraph4，结论正确但冗余和引用不足，见Q01/Q02。 |
| paragraphs[6]／text-7 | 条件执行与提前返回分支明确区分，失败不动画、清理不动画，正确。 |
| failure_scope／text-10 | 成功掩码是假设，真实malloc可能失败；失败和清理不演示；不冒充C执行或内存安全证明。 |
| lifecycle／text-11 | 自动节点i0不可free；动态节点返回后存在；局部变量结束与所指动态存储区分；保存next再free和不读已释放节点，正确。 |
| learning_summary／text-12和替代文本 | 包含初始化正确规则、旧头链接、局部与caller区别、接收／丢弃返回值以及判空，完整且正确。开头“三步”描述头插局部操作，随后明确补足返回和接收步骤，没有把它当全程序仅三行。 |

## 13帧独立重算

共享示例初始为i0{12,NULL}，依次成功插4、7。`?`为未初始化。逐帧核对模型title/note、程序状态、作用域和代码高亮；还以独立预期列表自动断言全部13帧的line／caller／head／p／scope，未用引擎结果当自己的预期。

| 帧 | 行 | caller／head／p | 独立状态和评价 |
| --- | --- | --- | --- |
| f00 | 无 | i0／无／无 | i0{12,NULL}；局部不活动，正确。 |
| f01 | 4 | i0／i0／t0 | 动态t0{?,?}；只能读已知指针，不读字段，正确。 |
| f02 | 5 | i0／i0／t0 | 条件为假、状态不写入、仍显示未知字段，正确。 |
| f03 | 6 | i0／i0／t0 | t0{4,?}；本时刻next尚未初始化不可沿之走，正确。 |
| f04 | 7 | i0／i0／t0 | t0{4,i0}；旧链未改，正确。 |
| f05 | 8 | i0／i0／t0 | 返回t0、caller未变；返回过渡局部活动，正确。 |
| f06 | 15 | t0／历史i0／历史t0 | caller赋值；局部已不活动，正确。 |
| f07 | 4 | t0／t0／t1 | 动态t1{?,?}，正确。 |
| f08 | 5 | t0／t0／t1 | 第二次条件为假，不提前return，正确。 |
| f09 | 6 | t0／t0／t1 | t1{7,?}，正确。 |
| f10 | 7 | t0／t0／t1 | t1{7,t0}，caller仍t0，正确。 |
| f11 | 8 | t0／t0／t1 | 返回t1；注释“insert结束”叙述返回过渡的结果，下一帧局部才不活动，不误作动态存储失效。 |
| f12 | 16 | t1／历史t0／历史t1 | caller=t1，局部不活动，t1→t0→i0→NULL，正确。 |

没有新指针别名、head=p、跳过判空的错误。字段未知只在初始化前出现，未把历史局部值当函数返回后仍存活变量；最终遍历范围从caller到NULL明确。

## 四题、答案及泄题

四题全文和解析未变，但本次仍逐题重读并手算：初始i0{30,i1}、i1{40,NULL}，成功分配t0并插11一次。normal代码接收返回值，discard代码丢弃。

| 题 | 独立推导与答案 |
| --- | --- |
| link_target | 调用时head=&i0，p->next取该值，因此节点变量名 `i0`；i1仅是旧后继。 |
| normal_values | caller接收t0，链为t0{11}→i0{30}→i1{40}→NULL，答案 `[11,30,40]`。 |
| discarded_values | caller仍i0，原链未被修改，从该入口为30→40→NULL，答案 `[30,40]`。 |
| unreachable_count | 只有一次动态分配t0，返回后无调用者指针保存它，动态不可达数 `1`；i0/i1不计动态节点。 |

独立预期与程序参考答案、模型解析相同。四个stem包含相应准确场景代码，节点名／JSON整数数组／整数格式清楚；没有直接列出答案或结果提示。演示仍只讲12、4、7，新summary未加入30、40、11的迁移答案。关于malloc真实失败的范围在课程中已明确；本题在该成功路径假设下作答。当前文件是私有装配，含答案合理；进入API时仍须用已有服务端私有投影，不能因静态通过把answer_key／solution直接发前端。

## 结论与下一门禁

此候选兑现“新节点如何连接旧链表”和“为什么调用者接收函数返回值”，全文事实、返回值、作用域、生命周期、帧和答案未见阻断错误；F01/F02已正确闭合。重复与引用粒度质量问题已明确保留，静态pass不是完善度保证，也不意味着可以扩大主题或自动再修。

可按获准范围进入同一应用的新不可变来源版本，保留父版／旧作答／原失败；实际新版本应显示模型四字段事实修订，不能沿用父版新调用0。后续独立浏览器已完成新来源、正文与替代文本同步、13步／高亮／控制、四题反馈、刷新版本及私有答案处理，见 BROWSER-ASSESSMENT.md；未复用父预览的浏览器pass。未进行学生学习效果实验。final-review.json保持静态签署原字节。完成本批后停止，T102和旧批次停止不改变。
