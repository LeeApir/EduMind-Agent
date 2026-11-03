# C01 首版独立教学评估

**结论：pass。固定两次分配成功的 C01 课程可以连贯学习；逐段、逐帧、四题答案和解析未发现事实、答案、安全或协议停止问题，无需普通措辞修复。** 此结论可用于本批 C01→C02 顺序门禁，不代表学生学习效果、正式教学签核、T038 准入或多主题方案稳定率。

评估者：独立助手 `/root/limited_c_independent`。与生成执行者分工但共享工作区，非 human、非物理隔离。日期：2026-11-03。依据为本批已批准的 ADR0050/准确输入和候选原文，不将框架 pass、事实ID存在或引擎自证作为教学真值。

准确候选为 [C01-generate.candidate.json](C01-generate.candidate.json)，digest `e80a6cd201bb12add78fe74b973df432bdef544306b33c8ec63f312c3d4856f1`；[页面](C01-generate.course.html) SHA256 `60a8f89ff8698d3d620e6f8dd8a6f0a95a2bc00e38867b394a38169ae3609a53`。本助手没有改任何模型正文、题干、解析或步骤说明，没有发送 Provider，也没有读取 API Key。

## 方法与实际学习流程

本人阅读全文和 C 代码，独立手算 caller_head、局部 head/p、next 与作用域；按实际代码而非读取引擎状态数组构造浏览器期望。使用 `webapp-testing` 技能，在独立临时脚本 `/private/tmp/edumind-c01-independent.py` 中运行实际 Chromium：

```sh
backend/.venv/bin/python /private/tmp/edumind-c01-independent.py
```

浏览器通过工具审批在沙箱外启动，仅加载本地课程。本人实际连续操作全部 13 帧，核对独立硬编码的 caller 可达链和高亮行号、模型原文在页面逐值显示，检查返回后局部变量标“不在作用域”；执行前后步、重置、播放/暂停后静止、播放中重置，四题先错后对并展开解析，得到 4/4；390px 移动视口无页面级横向溢出，键盘 Enter 可步进。页面异常 0、HTTP 请求 0。截图 `/private/tmp/edumind-c01-independent-desktop.png`、`/private/tmp/edumind-c01-independent-mobile.png`；本人另实际查看移动截图。

原件完整性采用执行者的 [evidence-summary.json](evidence-summary.json)及准确候选导出绑定，本助手没有独立解密私有原始 HTTP body，不能将执行者的原件核对冒充自己的采集。教学字段在实际 DOM 中与 candidate.raw_output 逐值对照，未发现助手补写。

## 逐段与边界核对

| 模型字段 | 独立结论 |
| --- | --- |
| prerequisites | 只采用已给定的 C 指针/struct/NULL/返回值前提，不推断其他学情。动态内存细节由本课说明，范围可接受。 |
| initial_list | main 中栈结点 i0、data=9、next=NULL、caller_head=&i0 均与固定代码一致；明确不能 free i0。 |
| first_attempt | 第4行 malloc、t0未初始化、第5行非空检查为假准确；明确是抽象成功假设。 |
| first_link_and_return | data=1、next=i0、return t0 正确；局部 head/p 返回后离开作用域，快照不是活跃变量。 |
| first_caller_result | 第15行才更新 caller_head=t0，链 t0(1)→i0(9)→NULL 正确。 |
| second_attempt | 局部 head=t0，新分配 t1 初始字段未知，成功判空准确。 |
| second_link_and_return | data=2、next=t0、返回t1准确；从t1形成链，但调用者尚未接回，这一点在对应 f10 明示 caller_head 仍为t0。 |
| final_observation | 第16行接回后 caller_head=t1，值[2,1,9]到NULL；明确本例是完整遍历，无环/未知，未把一般前缀误当全部路径。 |
| failure_scope | 明确当前没有演示失败分支；掩码不是实际 malloc 保证，不宣称任意C或内存安全证明。 |
| lifecycle | i0为栈结点不可free；t0/t1是动态结点；声明未演示清理，不冒称已释放。提出先t1再t0，且不能在仍读取结点时释放，未提供先free后解引用等危险代码。 |
| learning_summary | 正确回顾头插顺序、最终值、调用者与局部指针、未初始化字段及内存所有权。 |

## 逐帧独立推导

源码行依次为：无、4、5、6、7、8、15、4、5、6、7、8、16。初始及前一次返回前，caller链均为 i0→NULL；首次调用者接回后到二次返回前为 t0→i0→NULL；最后接回才为 t1→t0→i0→NULL。实际13帧均符合。

- f00：初始栈结点与 caller_head，局部函数变量不在作用域。
- f01/f02：分配t0后字段未知；第5行检查为假，状态不变。
- f03/f04/f05：写1、链接i0、返回t0；caller_head尚未更新。
- f06：第15行接回，局部head/p已离开作用域。
- f07/f08：分配t1，局部head=t0；第5行再次为假。
- f09/f10/f11：写2、链接t0、返回t1；对应解释明确调用者仍为t0。
- f12：第16行接回，完整最终链与遍历准确；释放说明明确未执行。

## 四题独立手算

| 题型 | 独立答案 | 检查 |
| --- | --- | --- |
| allocation_failures | 0 | 两次成功假设，题干与解析没有声称真实malloc必然成功。 |
| caller_head | t1 | 第16行接收第二次返回地址，题干指向准确时点。 |
| reachable_prefix | [2,1,9] | 从t1沿next到NULL，解析明确也是完整遍历。 |
| traversal_status | terminated | 到NULL、无重复或未知；题干列出准确英文token和中文解释。 |

程序参考答案与上述独立手算一致，四份模型解析支持对应答案，实际输入与反馈可用。事实引用足以定位当前例子的观察/步骤，但引用存在不单独证明自然语言正确。

## 可学性与局限

这是一份未经助手补写的模型教学文字配合程序代码/状态/答案的完整固定课程；正文、状态、逐步解释、题目和解析形成闭环。对已有给定 C 基础的学习者，13帧足以观察“链接旧头”和“调用者接回”两个不同时间点，判空、作用域和资源边界比只展示终态更清楚。

四题主要检验当前示例结果，尚未测量真实学生的解释、保持或迁移能力；题干中的 t1 示例也可能降低第一类题目的区分度，但不是当前事实/安全或教学完整性停止项。没有失败路径动画、释放执行或真实C运行，课程已如实说明；手机需要在代码和状态之间上下移动，源码长行在局部容器滚动。以上限制不要求本批扩功能或追加调用。

仅本C01首版通过；C02尚未评估，不预填通过。旧T102 blocked、catalog_only/H封存、正式评分和原批次失败结论均不变。
