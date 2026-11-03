# T103：统一中文可学头插课程 v1

[打开课程](course.html)。单文件离线页面，直接在浏览器打开即可学习，无需后端、安装或密钥。学习顺序：中文讲解 → 13 步代码与链表回放 → 生命周期和失败边界 → 四题输入与解析。支持播放、暂停、前后步、重置及键盘操作；练习输入仅保存在当前页面内存，刷新即清空。

## 交付目标与范围

本次完成方向文档第一步的**样例交付**：弥合 T095 真候选、T098 英文播放器与 T100 中文修订之间的断层，让读者可完成一个统一示例的学习流程。最小检查是同版来源与手算结果核对、13 个展示步骤及四题的实际浏览器流程；复用原播放器构建校验，不重跑无关后端测试，不扩建引擎。

版本 `unified-head-zh-v1`：初始栈结点 i0=9，两次实际分配成功，依次头插 1、2。原 C 代码、程序答案、11 个状态、31 个动作不改。新展示把同状态的显示与代码高亮合成教学步，在两次分配后各补一次第 5 行成功判空检查，共 13 步；不是新的 C 执行轨迹或正式产品动作协议。

## T099 问题逐项结果

| 问题 | 本版处理 | 可检查位置与边界 |
| --- | --- | --- |
| 英文难以阅读 | 采用 T100 四段中文讲解、四道中文题目和解析 | 页面“先看这一个例子”“独立作答”；助手修订，不记新模型成功 |
| 完整遍历被过度保守描述 | 明确本例到达 NULL，完整结果为 [2,1,9]；区分环/未知情况下的可知前缀 | 最后一段、最终链图、第 2/3 题解析 |
| 局部变量作用域 | 初始和 caller 阶段显示“不在作用域”；原记录里的局部值明确为返回前快照；函数内才显示活跃 head/p | 各步“指针与作用域”及原始状态；t0/t1 明确为轨迹标签 |
| 跳过成功判空 | 增加两步 line=5 的成功检查，p 非空、条件为假；复用分配后状态，不新增引擎状态 | 第 3/9 个教学步骤；lesson.json 的 assistant_success_check 来源 |
| 分配失败未演示 | 明示没有失败动画；NULL 时直接返回旧头、跳过数据/链接写入；成功标记不保证真实 malloc 成功 | “没有回放的分配失败路径”；不能据成功示例宣称覆盖失败分支 |
| 资源生命周期缺口 | 说明局部指针和动态结点寿命区别，提供本例专用“先保存 next 再 free”的收尾代码，明确不释放栈上 i0 | “收尾”；附录不在插入回放中，未执行 C，不适用于环/未知链接 |

## 来源和版本对应

- 模型原稿：[T095 candidate.json](../phase-1.5-combined-candidate-r01/results/candidate.json)。真实候选 artifact_digest 为 `c96ed09ae5884a61a8acd5bf1934dea59f13d5dcb9d7f4ae6a6af101b633765d`。原批次及审核协议未通过的结论保持。
- 程序派生：[T098 播放器](../phase-1.5-real-candidate-player-t098/course.html)中的同版代码、11 状态、31 动作，构建时调用原 `build()` 重验引擎绑定及摘要，不写旧文件。四个答案另用固定独立手算期望核对。
- 助手中文修订：[T100 assistant-revision.json](../phase-1.5-teaching-revision-t100/assistant-revision.json)，校验父摘要与 artifact；按原 block 顺序和 ID 保留题目/答案对应。
- T103 助手装配：教学步标题/说明、两步成功判空、收尾附录、练习输入反馈。T100 最后一段中关于“没有单独高亮判空”的句子按本页展示更新，其他中文沿用。`lesson.json` 的 paragraphs.key、questions.anchor/observation_key、frames.state_index/source_actions 及 provenance 记录映射；`manifest.json` 记录来源文件和本版页面摘要。

所有旧文件保持原字节，新产物均在本目录。新增模型请求 **0**。助手手改、程序派生和浏览器通过都不计入新模型生成成功率，不新增正式评分、签核或质量分子。

## 实际检查

从项目根执行：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-unified-head-course-t103/build_course.py
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-unified-head-course-t103/check_course.py
backend/.venv/bin/ruff check docs/acceptance/phase-1.5-unified-head-course-t103/*.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

检查器记录见 [browser-check.json](browser-check.json)：实际 Chromium 逐步核对 13 步状态/高亮/作用域，播放暂停及暂停后静止、前后步、播放中重置、自动完成停止，四题空白/错误/正确/解析、改答案后失效旧反馈、重置保留输入，键盘 Enter 和 390px 移动布局。记录外部 HTTP 请求与页面异常，输出桌面/移动截图。最初受沙箱 Mach 端口限制无法启动浏览器，此次失败不记通过；随后通过工具审批在沙箱外运行同一离线检查。检查器先后修正了折叠状态文本读取和 CSP 下等待函数的写法；实际发现的移动端横向溢出以 grid 子元素 min-width:0 修复，最终整套检查通过。桌面截图已由开发助手查看。

最终检查：全部通过，页面异常 0、HTTP 请求 0。旧 102 个 Task 对象逐值未变，T102 仍 blocked；process.txt 只追加。未运行与本次无关的后端测试。

## 独立评估交接与停止点

独立评估已完成，见 [ASSESSMENT.md](ASSESSMENT.md)：另行实际浏览器检查与独立手算未发现交付阻塞，结论限于固定成功示例可连贯学习，不是学生效果实验。

评估要求：按实际页面逐段、逐题、逐步检查：能否分清 caller_head/head/p、未接回结点和未知字段，能否独立手算并完成四题，判空、范围与收尾说明是否误导。将教学可学性与自动浏览器交互检查分开，不用模型 pass、同源一致或答对计数证明学习效果。评估仅针对本版样例，无真实 Provider、C 执行或产品主链接线。

T102 保持 blocked，历史原件/失败及 B/C 契约不改；catalog_only、H 封存、原签核保持。此页不代替 T038、多主题开发准入或独立质量/性能验收。评估后将结果交用户决定下一批有限 C；不启动真实验证、框架迁移、T102 修复或下一任务。
