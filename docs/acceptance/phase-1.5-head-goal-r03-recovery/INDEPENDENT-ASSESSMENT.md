# T108 r03 派生课程独立评估

2026-11-04。结论：**限定格式恢复可接受；准确课程候选教学评估 `needs_revision`，不签教学 pass。** 本轮没有新 Provider 调用，没有助手补写或改动教学文字。原 r03 严格解析失败、STOP、2 HTTP／余1失效及旧停止报告保留；这份报告是新增派生候选评估，不改写原批次结果。

- 候选摘要：`7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`。
- 首次教学核对的 artifacts.json SHA256：`d080ea6af693e2438ebecbb25ee402a02cc3e6b8783ad7681861aa01d4944dc8`。加入独立 review 来源及定位元数据修正后的当前摘要为 `1b85bdde797beb08f663404ade5eda041b9efc07845600e26b0836d811535592`；教学原文及候选摘要未变，后续复核见 BROWSER-ASSESSMENT.md。
- 真实模型规划摘要：`b6cc3d5304b87673c343a9cf31f11ae2cf8b44d4f12a07e852795ac71d4e4991`，已有规划 pass 保留。
- 所选示例 `head-new-A`；依据摘要 `dbfa7a38e73cf8cb36df518485019556bce56a23fc7d25dd1f18fbe0f3a28899`；示例依据 `2f64acc2c78f3793b085c2756b1de75124bfc38d0fb5c2c3d907cef4ad15638a`；materials `a3fc33abf64a99528d9d2a94a66f9b0721e226e48084d18b384a788a8cf7ce1e`。机器结论见同目录 final-review.json。

## 证据和恢复边界

独立读取 original-output.txt、recovered.record.json、assembled.private.json、artifacts.json，以及恢复器、派生准入和准备脚本。独立重算三份文件摘要、原文本摘要、同版请求／payload／候选摘要和装配映射，直接对安全导出原文本重新恢复，得到四个同值第二成员，结果等于准确候选。没有读取凭据、终端、私有 vault、raw.key，也没有运行会读取这些文件的 prepare 脚本；原 HTTP 加密原件与安全文本导出之间的解密证明依赖执行方所留核验记录，不能声称本评估者独立解密验证了 HTTP 原件。

恢复器以 Pairs 区分对象与数组，先递归拒绝嵌套重复；仅 `/questions` 的既定四键允许第二成员，第三次／其他层／未知键重复拒绝。字段集合、逐项 Python/JSON 类型和内容均比较，不把 true 与1、1与1.0、对象与数组视为相同。字符串未改，原稿文件未覆盖；随后重走原教学 Schema／事实／场景／帧校验。实际调用点固定原件 SHA、请求、计划、basis、派生摘要和四条变更，不是允许任意课程宽松解析。

实际执行：`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest backend/tests/test_head_course_duplicate_recovery.py -q`，14 passed。另以只读内联 Python 调用 `head_course_derivation.mapping()`，重验安全导出摘要及四条恢复；补验布尔/整数、整数/浮点、对象/数组、嵌套布尔/整数冲突均拒绝。未运行私有原件脚本或网络请求。限定恢复规则未发现本轮阻断缺陷。

## 阻断问题

**F01，事实错误。** `candidate.raw_output.paragraphs[6].text`：“必须先写 data 再写 next，才能安全遍历。”`paragraphs[1]`：“只有先写 data，再写 next，节点才处于可遍历的完整状态。”`learning_summary` 同样给出必要顺序。映射至页面 text-2、text-7、text-12 和 head-state.text_alternative。

本例确实先写 data 再写 next，但这不是 C 语言的必要顺序。对有效分配节点，先 `p->next = head`，再 `p->data = value`，在两字段就绪后读取同样成立；仅沿 next 行走且不读 data，更不依赖 data 先初始化。必须保证的是读取时相应字段已正确初始化，而非强制这两个写入的相对顺序。多处排他性用语会形成错误因果，不能用“只是描述本例”解释掉，属于事实问题，不能归入原有限普通措辞修复。

**F02，讲解与步骤不一致。** `candidate.raw_output.learning_summary`：“NULL 检查在成功路径上被跳过”，也用于 head-state 替代文本和 text-12。成功路径仍执行第5行的条件判断，结果为假，跳过的是提前返回分支；f02/f08正是这次检查的展示。paragraphs[5]又明确说不要把检查通过理解成检查不存在，未消除总结中的相反表述。不能在保留原文情况下签“正文与判空展示一致”。

## 逐段核对

| 原文位置／页面 | 独立结论 |
| --- | --- |
| prerequisites／text-0 | 准确保留自述先备，没有把按值传参、生命周期等未自述内容当已测掌握。 |
| paragraphs[0]／text-1 | main 的 caller_head 与函数 head 分开，初始 i0=12、next=NULL 正确；“改 head”是假设性说明，实际代码无 head=p。 |
| paragraphs[1]／text-2 | 分配及成功判空解释正确；必要初始化顺序说法 F01。 |
| paragraphs[2]／text-3 | t0.data=4、t0.next=i0、旧节点和 caller_head未改、返回p正确。 |
| paragraphs[3]／text-4 | 接收返回值才更新入口；若丢弃，仅新节点不可达而原链仍可达，正确。 |
| paragraphs[4]／text-5 | 第二次 head=t0、t1.next=t0、返回后caller=t1，最终7→4→12→NULL正确。 |
| paragraphs[5]／text-6 | 分配失败解释及不演示范围清楚；开头“if…被跳过”与后文澄清需和 F02一并处理。 |
| paragraphs[6]／text-7 | 未初始化 next 不可读的提醒合理，但强制先data后next为F01。 |
| failure_scope／text-10 | 明确成功分配假设、真实malloc失败及清理不演示；不冒充实际C执行或任意内存安全证明。 |
| lifecycle／text-11 | 自动节点i0不可free，动态节点函数返回后仍在；先保存next再free、不得读已释放存储的提醒正确。 |
| learning_summary／text-12及替代文本 | 两个核心目标解释到位；仍含F01和F02，故整体不能通过。 |

## 13 帧独立手算

下表逐帧比对模型 note、程序 state、locals_scope 和高亮行；`?` 表示未初始化。caller 帧中的旧局部值是保留的历史轨迹，locals_scope 为 inactive，不应渲染成当前仍存活局部指针。return 帧是返回过渡，局部到下一caller帧结束；f11“insert结束”的叙述应结合此边界理解。

| 帧 | 高亮 | caller／local head／p | 应有变化与结论 |
| --- | --- | --- | --- |
| f00 | 无 | i0／无／无 | i0={12,NULL}，局部不活动，正确。 |
| f01 | 4 | i0／i0／t0 | 新t0={?,?}，正确。 |
| f02 | 5 | i0／i0／t0 | 成功判空、不写字段、不提前返回，正确。 |
| f03 | 6 | i0／i0／t0 | t0={4,?}，正确。 |
| f04 | 7 | i0／i0／t0 | t0={4,i0}，旧链不变，正确。 |
| f05 | 8 | i0／i0／t0 | 返回t0，caller尚未变，正确。 |
| f06 | 15 | t0／历史i0／历史t0 | caller接收t0，局部不活动，正确。 |
| f07 | 4 | t0／t0／t1 | 新t1={?,?}，正确。 |
| f08 | 5 | t0／t0／t1 | 再次成功判空、不写字段，正确。 |
| f09 | 6 | t0／t0／t1 | t1={7,?}，正确。 |
| f10 | 7 | t0／t0／t1 | t1={7,t0}，caller尚未变，正确。 |
| f11 | 8 | t0／t0／t1 | 返回t1，正确。 |
| f12 | 16 | t1／历史t0／历史t1 | caller接收t1，局部不活动，t1→t0→i0→NULL，正确。 |

未发现这13帧的值、行号或作用域数据错误；这是数据及文本核对，尚不能替代浏览器检查当前高亮和局部状态渲染。正确帧也不能抵消总结F02。

## 四题独立手算与泄题

迁移情境是自动节点 i0{30,&i1}、i1{40,NULL}，成功插入11一次。保留返回值时新t0={11,i0}，caller=t0；丢弃时caller仍i0，动态t0不可达。

| 题 | 独立答案 | 核对 |
| --- | --- | --- |
| link_target | `i0` | 传入head=&i0，p->next直接保存该值；解析正确。 |
| normal_values | `[11,30,40]` | 从接收后的caller沿next至NULL，顺序正确。 |
| discarded_values | `[30,40]` | 仅入口未更新，原链保持；解析正确。 |
| unreachable_count | `1` | 仅新动态t0不可达，自动i0/i1不计；解析正确。 |

四题代码与各自receive／discard场景一致，题干要求节点名／JSON整数数组／整数明确。题干包含求解必需输入而不直接列答案，前文演示用12、4、7，未代答迁移数值。已核私有装配答案与模型解析一致。首次离线核对未进行浏览器复核；其后已完成服务端隐藏答案、错误／正确反馈及刷新版本的独立实际预览检查，证据见 BROWSER-ASSESSMENT.md，不改变本报告的教学非pass。

## 交付边界

这份原文完整派生候选可以作为**已知教学错误的审查对象**保留，不是教学评估合格课程。若按用户新增授权提供私有审查预览，必须真实携带 needs_revision、两项问题及 program_format_recovery 来源，不能伪造pass或计模型首次结构合格。原有准入pass门禁若为预览另作明确例外，应如实记录，不能把本JSON转成pass。

本评估不修改原稿、不提供兜底正文、不建议自动新调用。后续独立浏览器已完成审查预览控制／反馈／刷新检查，见 BROWSER-ASSESSMENT.md；没有学生学习效果实验，不得由交互可用推导教学通过。T108最终教学验收尚未完成，T102仍blocked，旧批停止不恢复。final-review.json 保持首次准确教学结论，不因浏览器复核改写。
