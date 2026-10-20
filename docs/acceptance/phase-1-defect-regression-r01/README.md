# 四类缺陷回归材料 r01：12个固定对照，零真实调用

本包扩充已知失败类型，保持审核 v4.10 / Luna high / 8192 / 60秒及实际Schema投影，不改生产规则。每类有正确、错误、信息不足三份完整材料，原目标快照、计划、讲解、代码、三题、动作、摘要/依赖、锚点与实际适配器请求均可查看。

| 类型 | 正确 | 错误 | 信息不足 |
| --- | --- | --- | --- |
| pointer-scope | Node ** / *head=NULL / &head完整匹配，pass | Node *按值传递，main再次free实际已释放对象，reject/code_safety/severe | 只有声明/调用，缺函数体及后续用途，needs_human；不得断言已free |
| plan-consistency | 目标/轨迹/实现19一致，pass | 计划目标17、自己轨迹及正确代码19，needs_human；应指出计划冲突 | 指定输入附件缺失，不能判断该次和是否19，needs_human；不把未知当确定错误 |
| requirement-origin | 原文/计划/正文19一致，pass | 原文19、模型计划17，讲解还称用户要求17，与实际源码19冲突，reject/fact/major；不能归咎原文 | 原文引用未提供的附加要求附件，needs_human；不虚构附件要求 |
| assessment-coverage | 分散教学证据＋完整状态表判断题，pass | 过程已教但三题仅算术，needs_human；不编造fact | 只提供纸质题本编号和答案转录，未见状态表正文，needs_human；不推断题本一定测/没测过程 |

完整细则见 `labels.json`；所有结果均为空。错误不一概reject：计划冲突与纯教学不足按既有规则待人工；确定学生内容事实矛盾、可达二次释放才保留严重判断。信息不足各有明确缺失前提，并不通过破坏Schema、删掉绑定原文或故意漏传已有资源制造。

材料作者为交互GPT，不是独立真人真值，也不是新的盲测集。它们复用了已暴露的缺陷模式，作为校准/回归；后续泛化仍需独立材料。这里的12个标签不能证明审核模型准确率，Mock固定pass仅用于构造请求，不保存为真实判断，不注入expected/required/forbidden字段到模型输入。

`requests/` 来自实际生产review_once与真实适配器的MockTransport捕获。连接IP为离线哨兵8.8.8.8，Host/SNI为www.cbbb.fun、路径/v1/responses；没有DNS或真实网络。业务完整Schema本地校验，出站使用现有投影。原文与模型计划在authoritative_teaching_goal中分列，program_context保留源码定位但不假装推断安全。固定材料调用审核不需要重新生成课程。

同一类型的对照保持当前Prompt/模型/Schema；有些信息不足样本需明确改变输入前提，不宣称所有三联只改一个字符。覆盖正/错对照保持相同讲解和代码，仅替换题目。所谓正确以本单元明确范围为准，不要求图谱其他目标、动画或开放题。

```sh
backend/.venv/bin/python scripts/prepare_defect_regression.py check
backend/.venv/bin/python -m pytest scripts/tests/test_defect_regression.py -q
```

check重新捕获并逐字比较12份请求和材料，也验证当前政策与冻结文件摘要。prepare拒绝覆盖已有材料。此次Provider请求0，未读真实Key；没有批准新的真实测试或恢复旧停止。旧[四项生成首败](../phase-1-generation-mini-r01/RESULTS.md)及原指针误拒/复测均不改分。

交接：下一T076将固定材料审核重复与独立生成诊断分开；各自记录请求、结果和分母，不再以全链重跑代替故障定位。真实执行须另行冻结预算、次数及停止条件后批准。本任务只交付工程可复现的材料和预标签，不声称语义测试通过。
