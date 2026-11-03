# C02 唯一修复版独立教学评估

**结论：pass。唯一模型修复消除了首版题干与输入格式的不一致；重新阅读全文、代码、全部10帧、四题及解析后，未发现事实、答案、安全、协议或新的教学措辞阻塞。固定空链/合成失败后成功插入的学习流程可以连贯完成。** 这只是一名独立助手对准确课程的评估，不是学生效果实验、正式签核或一般生成稳定率证明。

评估者：`/root/limited_c_final_eval`，接手因中断未完成的修复版评估；与主执行者分工、共享工作区，非human、非物理隔离。日期2026-11-03。评估对象：[修复候选](C02-repair.candidate.json)，digest `94b98e3411cdffdce46a77387aac92d3333731e5bae340e2e886cad82596dea0`，parent `11733f29cba774f7273429bc20326f40eae9b38e02f727f9ebf6435df9573a51`；[修复页面](C02-repair.course.html) SHA256 `92d7468a3b0a0b85eb5684bad9b56e16716701b6d0ccd790744f251baed31461`。本人未调用Provider、未读取API Key、未改任何模型正文或原件。

## 方法与实际操作证据

阅读ADR0050、准确包README、首版评估/定位意见，以及修复版全部模型字段和C源码。依照C代码独立手算，逐帧调用者链、高亮行和参考答案写成硬编码期望，没有从引擎的状态或答案读出期望。另递归对比首版/修复版raw_output，仅 `questions.reachable_prefix.stem` 一个叶子改变，其余字段逐值相同；这不代替本次完整语义重评。

使用已读取的 `webapp-testing` 技能，独立编写并实际执行可复现脚本 [check_c02_repair_browser.py](check_c02_repair_browser.py)：

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-limited-c-live-r01/check_c02_repair_browser.py
```

初次沙箱内启动Chromium因Mach端口权限失败，不计为通过；随后经工具审批在沙箱外运行同一脚本通过。仅打开本地修复课程，没有HTTP请求或Provider调用。脚本验证：全部教学字段和DOM逐值一致；10帧的手算caller链/节点字段/作用域/高亮；播放、暂停后静止、前后步、重置及播放中重置；四题先错后对、展开解析，结果4/4；修复后的列表输入要求；键盘Enter及390px移动布局。页面异常0、HTTP请求0。

实际截图：`/private/tmp/edumind-c02-repair-independent-desktop.png`、`/private/tmp/edumind-c02-repair-independent-mobile.png`；本人查看了移动全页截图，文字/控件可见，无页面级横向溢出，源码长行保留局部横向滚动。Ruff格式化及检查通过。没有为此重跑通用监督器或新增样例。

私有HTTP原件采集和解密核对依执行者的 [evidence-summary.json](evidence-summary.json)；本人未独立解密私有原件，不把执行者记录冒充本人采集。本文的教学结论来自独立源码推导、完整原文阅读及实际页面操作，不以模型pass、fact_id存在或共享引擎自证为真值。

## 独立手算与逐段核对

初始main仅声明 `caller_head=NULL`，没有栈结点。第一次调用参数(-3,0)：第4行条件为false，直接得到NULL而不调用malloc；第5行返回原head=NULL，无t0、无字段写入，第12行接回后仍空。第二次参数(5,1)：假定实际malloc成功产生t1；写data=5，next=head=NULL，返回t1，第13行调用者接回。最终t1(5)→NULL、[5]、terminated、合成失败1。

| 字段/段落 | 完整重评结果 |
| --- | --- |
| prerequisites | 限给定C指针/struct/NULL/返回值基础，未臆测学习历史。 |
| initial_list | normal、空链、-3/5及false/true准确；明确掩码不是实际malloc保证。 |
| attempt_0 | false不调用malloc、p=NULL、提前返回NULL、未创建节点准确；没有将合成不分配说成真实malloc故障。 |
| attempt_1 | 假定分配t1、data/next未知不能读取、判空为假、写5/链接NULL/返回t1准确。 |
| caller_result | 第13行才接回，区分main的caller_head与函数局部p，返回快照不是仍可用变量。 |
| final_observation | [5]到NULL是本例完整遍历；失败计数1；t1须最终安全释放但尚未清理，无误导。 |
| failure_scope | 固定的一次合成失败和一次成功，首尝试无malloc；不证明真实malloc或未演示分支，准确。 |
| lifecycle | 空链无栈节点，动态t1应在不再使用时释放；不释放未分配/未知指针，未声称执行清理。 |
| learning_summary | 回顾p/caller_head、掩码、失败与成功、遍历及生命周期，范围一致。 |

## 全部帧与四题

10帧高亮行手算为：无、4、5、12、4、5、6、7、8、13。前9帧caller链都是NULL，最后接回才指向t1(5)→NULL；前4帧没有节点，后6帧只有t1，始终无t0。f04/f05的data和next未知；f06仅data=5而next未知；f07起next=NULL。f00/f03/f09局部head/p不在作用域，其余函数内head=NULL，p按当前尝试为NULL或t1。每一帧实际展示和模型说明均符合这些推导。

| 题型 | 独立答案 | 修复后题意/解析/交互 |
| --- | --- | --- |
| allocation_failures | 1 | 合成false尝试一次，真实malloc行为未泛化；输入1答对。 |
| caller_head | t1 | 第13行接收返回值，题意与ID类型一致；t1答对。 |
| reachable_prefix | [5] | 明确只提交JSON整数数组、不要文字；解析仍准确说明本例完整遍历。[5]答对，带额外说明被拒与新题干相符。 |
| traversal_status | terminated | 给出准确英文token/中文含义，t1.next=NULL终止；terminated答对。 |

首版要求附加说明而控件不接受的minor difficulty已闭合。完整性解释保留在解析中，没有改变参考答案/事实/Schema/控件，也未通过助手手改正文补成功。所有剩余模型文本与首版一致且本次重新核对，无需也不允许再修复。

## 结论边界

该固定开发样例的内容/交互可用，支持本批修复后pass。四题主要测本例结果，未测真实学生保持或迁移；合成掩码与模拟轨迹不是实际C运行/故障注入，资源释放仍为说明而非执行证据。C01/C02也不能代表多主题能力、B/C提升或稳定率。准确决策见 [C02-final-evaluation.json](C02-final-evaluation.json)。T102仍blocked，正式评分/签核、catalog_only和H封存不变；本批后续由用户决定，不新增调用。
