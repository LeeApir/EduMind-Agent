# T109 B候选证据绑定局部修订：全文独立重评

2026-11-05，评估者 `/root/head_goal_independent`。**准确新候选静态教学pass，无阻断意见；新版本实际应用／浏览器学习验收尚未运行。** 已重评全部6段、13帧、4题及答案解析、先备、总结、生命周期和失败范围，未仅凭S01/C01旧句消失签署。九项明确检查见final-review.json。

候选 `560ae12dd987b2718f7f82c2f971177e9a79e7bb6595a9f87e3c663f17172ff0`，父 `63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`；证据版本head-teaching-evidence-v1／摘要 `3d7bbd32b2ca6895fc62ce46dc1f1396488e6edd78b4dd21fac09eb4c0a8c754`。plan摘要仍 `f99469ee1ec137e51423337160a7e6066287cadbebb6753547202a5d68763330`；basis／example basis／materials绑定与准确父稿相同，见JSON。

## 证据、合并与原件边界

独立只读本次安全导出record／candidate／output／diff／assembled／raw／request／body，原r01父稿和stop评估、T110补充证据和映射、ADR0054及本批准确包、对应合并／证据／准入源码。没有读取vault、raw.key、ProviderKey或终端，没有Provider调用，没有改动教学或业务代码。

实际已安全导出的raw为3252字节，独立SHA `55610671a36014f6e3f26ddd503bb352878d1a138aa838713037de10eba52aa3` 与收据相同；没有亲自读取或解密私有加密原件，不能据此宣称独立解密核验。实际请求等于当前冻结body及record.request，canonical请求摘要与attempt一致，manifest为 `106152b051afd8c28d11636f5f181e1a40b8784ec1306f1a5c4204809596b6b3`。独立重走完整响应适配、记录校验、严格合并、候选摘要和装配，均与安全导出一致；用量14886输入／366输出是Provider自报，不是账单证明。

逐项差异核对：raw仅failure_scope和paragraphs[5].fact_ids实际变化，paragraphs[5].text逐字等于父原文；其他raw字段相等。payload删除新增teaching_evidence后与父payload完全相等，旧代码／spec／catalog／轨迹／答案／规划／来源绑定／basis均未修改。证据可以从准确原材料重建，与冻结3d7…补充完整相同；不是把新ID偷偷加入旧catalog或复用旧digest。

候选文件SHA `a9b96ba8fbe04da9728f9653ca103af1022597c06ad693ac4231ec7a64664701`，装配文件SHA `068e621be331dcfb887ecf662118897fade6dcde90e84ebeb985ec19226862dc`。新来源准确为evidence_bound_local_revision／head-evidence-local-revision-v1，并包含准确父、模型、plan、materials和证据版本／摘要。summary与演示替代文本仍来自同一原总结，逐字相等。

## 两项原阻断闭合

**S01已解决。** 新failure_scope明确主播放器f00–f12两次分配成功，f02/f08两次NULL条件被求值为假后继续插入；掩码关闭“不分配”和真实malloc失败均没有在13帧展示。它还明确“代码静态上含有该分支，只说明代码具备这种能力，不等于本课演示了该分支”。不再把支持能力当已展示内容。p=NULL时返回旧head、不写p字段、没有新节点，与成功分配后丢弃返回导致新节点不可达的区别保留；不执行C、不证明任意内存安全边界仍清楚。

**C01已解决。** 段落5改引唯一准确ID head_evidence_v1.discard_return_comparison，不再引用normal caller已更新的state作为ignore分支的证据。该证据显式computed_counterfactual、displayed_in_main_player=false、main_frame_ids=[]，含独立代码、规格／示例摘要、两次调用head/p/next/returned与caller前后状态以及结果。独立手算：两次丢弃时caller始终i0，每次head均i0，t0{6,i0}、t1{0,i0}，最后可达[-8]，t0/t1不可达、分配失败0。逐项支持原段的旧入口／成功连接／不可达／不是分配失败职责。

算法文字逐字未改，未通过删除解释、复制邻段、换成总结或移走问题规避审核。新段落未称对照已在主动画播放，范围声明也没有把该计算对照等同主13帧。

## 全文及引用逐段核对

| 部分 | 职责、证据与结论 |
| --- | --- |
| prerequisites | 用户自述C指针、struct、NULL、返回值准确；未知的指针副本与共享节点区别没有冒称已掌握。 |
| paragraph0 | 接口、head与caller_head为不同变量、按值复制、节点共享正确；trace00/01显示caller与局部head指同一i0，语言语义另从同版C接口／basis核实，不把ID存在当C语义证明。 |
| paragraph1 | trace01/02对应新t0字段未知到data已写／next未知。成功路径第5行条件false、失败时return旧head且不写NULL字段，符合代码和新增展示证据；未复发成功时跳过检查或必须先data后next。 |
| paragraph2 | trace02/03/04定位数据赋值、next连接与返回前状态；head旧地址存入新next，旧链内部不变，正确。 |
| paragraph3 | trace04/05支持return t0与main接收前后；局部变量生存期和动态／自动节点存储分开，函数不会隐式改caller，正确。 |
| paragraph4 | trace05/06/09/10及最终caller／reachable／termination观察支持两次接收，t1.next=t0可直接见返回状态，最终0→6→-8→NULL正确。 |
| paragraph5 | 新独立discard证据逐项支持旧入口、不更新、新动态节点不可达及与失败区别；原算法完整保留。 |
| lifecycle | 自动i0不能free，动态t0/t1不因insert返回消失，释放前保存next、不能free自动节点或读已释放节点；不展示清理明确。 |
| failure_scope | 真实展示、静态能力、未展示两类失败边界已明确，见S01闭合。 |
| summary | 三点完整覆盖链接旧头、局部与节点、生存期、函数返回和caller接收；B参数及结果正确，没有迁移题结果或新错误。 |

六段组织为接口／分配／链接／返回／接收／丢弃，职责完整，未发现相邻逐字或近似复制、必要解释遗漏。引用核对以具体状态陈述和同版代码／basis／补充来源一起判断，未把静态C语义强说成轨迹自动证明，也没有用normal路径替代ignore证据。

## 13帧重新核对

独立手算并用独立期望列表逐帧断言line／caller／local head／p／locals_scope和各节点data/next；不是直接用引擎输出当预期。初始i0{-8,NULL}，插6再0，两次成功。

| 帧／高亮 | caller／head／p及节点状态 |
| --- | --- |
| f00／无 | caller=i0，局部不活动；i0{-8,NULL}。 |
| f01／4 | i0／i0／t0；t0{?,?}。 |
| f02／5 | 同前，NULL条件false、不提前返回，字段仍未知。 |
| f03／6 | i0／i0／t0；t0{6,?}。 |
| f04／7 | i0／i0／t0；t0{6,i0}，旧i0不变。 |
| f05／8 | 返回t0，caller仍i0；局部到函数返回结束。 |
| f06／15 | caller=t0，局部不活动；6→-8→NULL。 |
| f07／4 | t0／t0／t1；t1{?,?}。 |
| f08／5 | 同前，第二次条件false、caller仍t0。 |
| f09／6 | t0／t0／t1；t1{0,?}，数据0并非NULL。 |
| f10／7 | t0／t0／t1；t1{0,t0}，结构0→6→-8已连好，caller尚未接收。 |
| f11／8 | 返回t1，局部即将结束、动态节点继续存在。 |
| f12／16 | caller=t1，局部不活动；0→6→-8→NULL。 |

逐帧title/note与上述状态／高亮／作用域一致；两次成功判空是程序对分配状态的展示投影，证据明确非真实C执行。没有mask=false／分配失败帧。第一次检查脚本误沿用7段T108的块索引，读到text块后KeyError；改为准确anchor_id=head-state查找后重验全部边界通过，未修改课程或削弱断言。当前新课6段，summary位于text-11、failure_scope位于text-9，避免用旧版本块号定位。

## 四题、答案和泄题

四题全文和解析重新逐题读取；与父稿相等不代替本次手算。独立迁移初始i0{30,i1}、i1{40,NULL}，成功插11一次：

- link_target：head=&i0，p->next直接指i0，答案 `i0`；解析正确。
- normal_values：接收后caller=t0{11,i0}，遍历至NULL为 `[11,30,40]`；解析正确。
- discarded_values：丢弃时caller仍i0，旧链不变，遍历为 `[30,40]`；解析正确。
- unreachable_count：仅动态t0失去入口，自动i0/i1不计，答案 `1`；解析正确。

题干与各自normal／discard完整代码一致，输入格式明确，题干没有直接给结果或答案示例。前文主例只讲-8、6、0，没有代答30／40／11迁移结果。练习在本课程序材料的正常成功路径前提下解释，不把参数allocation_success=1当现实malloc成功保证。私有装配含程序答案正常；实际页面/API必须继续沿用服务端私有投影，尚未进行本候选的反馈或刷新检查。

## 签署及后续边界

原T109 r01首次结构pass、教学stop、2HTTP／余1失效、原failed/v1／STOP和原评估不追改。新证据是程序补充，新failure_scope来自这次唯一真实模型响应，原段算法文字来自父模型原稿；助手补写0，不称全文重新生成或重新规划。新批一次HTTP已用尽并STOP，本评估者调用0，不能追加请求。

准确候选全文、引用、职责、无邻段复制、无遗漏、代码轨迹答案、不泄题、展示范围、原段算法保留九项通过，可进入已授权的新不可变私有子课程导入。没有预填浏览器、E01状态投影或实际学习效果通过；仍需实际页面读取、来源／证据版本、13帧控制、四题反馈／隐藏答案、刷新scene／attempt绑定一致验收。本报告不恢复旧批、T102，不扩主题或T038。
