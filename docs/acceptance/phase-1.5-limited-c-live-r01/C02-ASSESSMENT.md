# C02 首版独立教学评估

**结论：ordinary_wording_repair。未发现事实、答案、安全或协议停止问题；发现一项 minor difficulty 题干与回答格式的措辞不一致，建议仅使用本例允许的一次普通教学措辞修复，修复后重新独立评估。** 当前首版不预填最终pass，问题、首版和修复版本须全部保留。

评估者：独立助手 `/root/limited_c_independent`，与生成执行者分工、共享工作区，非human或物理隔离。2026-11-03。准确候选 [C02-generate.candidate.json](C02-generate.candidate.json)，digest `11733f29cba774f7273429bc20326f40eae9b38e02f727f9ebf6435df9573a51`；[页面](C02-generate.course.html) SHA256 `28d3397e54b682793c57fce7cd1499781571ab4d0057c4a51aa8ec1f72a60e51`。没有修改模型文字、原件或引擎，没有调用Provider或读取API Key。

## 定位问题

- 路径：`["questions","reachable_prefix","stem"]`。
- 原文引用：`若在 NULL 处终止，请说明这是否为该指定示例的完整遍历。`
- 级别：minor；area：difficulty。
- 原因：题干在要求整数前缀之外又要求提交文字说明，但固定回答类型与输入提示仅接受JSON整数数组，参考答案为 `[5]`。本人在实际浏览器中输入 `[5]，这是本例完整遍历` 后看到“格式不正确”，仅输入 `[5]` 则回答正确。学生按题干完成额外说明反而无法被控件接受。
- 分类：这是普通教学措辞与既定回答格式不匹配，并非错误参考答案、事实/安全问题或Schema形状失败。可通过模型完整修复稿调整教学措辞，不改变事实、题型、答案、Schema或程序控件；本助手不代写替换文字。修复意见完整保存在 [C02-evaluation.json](C02-evaluation.json)。

主执行者随后也指出同一观察；本助手先独立阅读全文定位，再独立浏览器复现，没有将执行者建议直接当作结论。

## 独立手算和逐段检查

固定代码初始 `caller_head=NULL`。第12行调用参数(-3,0)，第4行条件为false，**不调用malloc**，p=NULL；第5行返回原head=NULL，没有t0，不写data/next，第12行接回后仍空。第13行调用参数(5,1)，在实际成功假设下得到t1，先写data=5，再令next=NULL，返回t1，调用者第13行接回。最终t1(5)→NULL、完整值[5]、terminated、失败计数1。

| 模型字段 | 独立结论 |
| --- | --- |
| prerequisites | 只要求给定C基础，不臆测其他历史。 |
| initial_list | normal/空链/插入值-3和5/false,true及抽象假设说明准确。 |
| attempt_0 | false不调用malloc、p=NULL、提前返回NULL、无节点/调用者头不变准确，未把强制不分配误说成真实malloc失败。 |
| attempt_1 | 假定成功分配t1、初始字段未知、判空为假、写5/链接NULL/返回t1准确。 |
| caller_result | 第13行才接回，p仅局部且返回后不在main作用域，准确。 |
| final_observation | [5]到NULL是完整遍历；合成失败1；只有t1需要最终安全释放，未声称已清理，准确。 |
| failure_scope | 明确首尝试未调用malloc，只展示固定合成失败和一次成功，不证明其他真实行为。 |
| lifecycle | 空初始链无栈结点，成功t1为动态结点，未演示释放；禁止释放未分配/未知指针，准确。 |
| learning_summary | 目标与已展示内容一致，未扩承诺。 |

## 逐帧与四题

独立硬编码手算的10帧行号是：无、4、5、12、4、5、6、7、8、13。前9帧调用者可达链仍为空，第10帧才为t1(5)→NULL。实际状态、高亮和每份模型step_notes符合；f00/f03/f09的局部head/p为不在作用域，成功分配后未初始化字段显示未知；始终没有t0。

四题独立参考答案：allocation_failures=1、caller_head=t1、reachable_prefix=[5]、traversal_status=terminated。程序答案与四份模型解析均一致，唯一发现是上述reachable_prefix题干额外提交说明的格式要求，不影响其数值/终止事实。

## 实际浏览器证据

使用 `webapp-testing` 技能，独立临时脚本 `/private/tmp/edumind-c02-independent.py` 执行：

```sh
backend/.venv/bin/python /private/tmp/edumind-c02-independent.py
```

实际Chromium经工具审批在沙箱外启动，仅加载本地课程；逐值比较展示的模型段落/边界/总结/逐步说明与真实raw_output，按本人独立手算检查10帧caller链与高亮；完成播放/暂停保持静止、前后步、重置和播放中重置；四题先错后对并展开解析，得到4/4；额外复现题干说明不能输入的问题。390px移动视口无页面级溢出，键盘Enter可步进；页面异常0、HTTP请求0。截图 `/private/tmp/edumind-c02-independent-desktop.png`、`/private/tmp/edumind-c02-independent-mobile.png`，本人另实际查看移动截图。

原始HTTP body完整性由执行者 [evidence-summary.json](evidence-summary.json)记录；本助手没有独立解密私有HTTP原件，不能冒充原件采集。候选教学字段在DOM中逐值一致，未发现助手补写。

## 边界与下一步

本次没有真实学生学习实验，四题不能证明迁移能力，失败轨迹只是合成掩码控制，不是实际C运行或malloc故障注入。只建议本例的一次普通措辞修复，修复后按准确父摘要重新检查全部受影响内容与页面；不得偷偷改首版、扩大测试/Schema试错、再建监督器或恢复T102。若修复出现事实/安全/协议/未知问题，按批次契约停止。本报告不预判修复结果或批次最终通过。
