# r05 实际执行结果：停止，T038未通过

用户明确批准提交6b4f6ce及manifest `2896fc5f9c02bcce67a2c32a2a1773f106a3d49ebae42ca199335db8a9371723`；批准登记见execution-approval.json，来源call_4c391511662944b7a9c6aa25f9d701dd。独立窗口2026-10-27 22:03:09至2026-10-28 01:03:09（上海），最多250HTTP；实际已因停止条件结束，不使用剩余额度。冻结README/代码/manifest保留原字节，准备时措辞不代表当前执行状态。

## 实际进展与停止原因

| 槽 | 实际生成 | 审核及助手复核 |
| --- | --- | --- |
| D01-known | 规划＋1场景成功，无格式修复 | 审核协议/最终JSON通过；助手先读课后读意见，逐块事实与4题记录已标准入账 |
| D01-unknown | 规划＋1场景成功，无格式修复 | 同上；与known原输出SHA绑定，实际比较循环/边界示例与直接读写示例的差异，4题已核对 |
| D02-known | 规划＋2场景成功，无格式修复 | 第1场景审核HTTP200后被完整协议拒绝；第2场景未发审核请求。无标准slot_output，助手完整盲核另存，不能伪造标准报告入账 |
| 其余31槽 | 未运行 | 保留固定分母，包括9课程、2负例和20probe |

本批10HTTP全部200：7生成＋3审核；7项已实际主步骤首次Schema均通过，不代表34槽全部结构/质量通过。三个隔离PG生成操作均succeeded、共4ready；完整标准槽输出和实际助手复核各2。主账本仍stopped/UNKNOWN_SEND，9complete/1unknown。

直接停止原因是第10次请求：sol报告50推理token（包含于总输出426），output仅有最终message，没有reasoning项；现有已批准门禁要求非零推理用量与reasoning项一致，故报`REASONING_ITEM_MISSING`。最终JSON本身通过原完整Schema、准确来源及引用校验，给出revise/3条意见；这不构成完整协议通过。不是HTTP不通，也不能据此宣称Responses接口缺失。CLI外层把ValueError笼统报告为TRANSPORT_DATABASE_OR_EXECUTION_FAILURE，不能据此反推传输或数据库故障。

D01两次已成功观察记录保留准确请求/响应SHA和已知37字符后缀；instruction_delivery_verified和upstream_context_verified始终false。没有伪造缺失项、重算/退回unknown占额、修改原始响应、重启旧批次或发额外探测。实际费用未知。

## 独立于协议的内容失败

助手在查看D02模型意见前已逐块读完两个场景，盲核[原记录](D02-known-blind-review.json)保存时间与source SHA。以下问题足以阻止质量准入，即使元数据门禁另作取舍也不能绕过：

1. 第二场景声称遍历时`head = head->next`会永久丢失入口，“函数返回后无法再访问任何结点”。但准确代码为`printList(struct Node *head)`，C指针形参按值传递，移动局部head不会改变main持有的head。建议游标是良好实践，不能把理由讲成错误的参数传递语义。
2. 第一题只写`insertHead(head,1/2/3)`，未接收返回值，却要求以`3,2,1`精确判卷。已给函数返回新头、形参按值；严格按该C调用写法，caller head仍NULL。得到3,2,1需要补上`head = insertHead(...)`或明确题目是抽象的更新操作。题干/真实接口不一致使参考键不可靠，不能擅改题干或答案追通过；按原答案/评分键错误属于自然严重问题，保存1项并停止。

其余两题在明确规定链状态后参考3/3可核对；不能因此删除失败题。所有原答案、解析、候选、依赖及PG原件保持，无编译/执行任意生成C。

第1场景模型意见另指出尾插复杂度缺少未维护尾指针前提、malloc图示把未初始化next称为NULL，以及资源释放/分配失败传播不足。实际复核见[后续对照](D02-known-post-model-observation.json)，不把模型严重度直接当产品确认。助手盲核初次对图示next=null作“示意状态”解释过宽，后续按明确caption与准确malloc步骤追加纠正，原盲核文件不覆盖。模型未审核第二场景，不能把助手独立发现归功于模型。

这是真实受委托助手审阅，reviewer=Codex assistant、review_type=delegated_assistant、independent_human_truth=false；没有独立人类真值或生产评分资格。两份D01标准报告与D02另存盲核明确区分。standard_assessment仅覆盖已导入的两份报告，其no_severe=true不包含停止槽；全部已观察内容已有严重答案问题，整体质量明确false，不得用这个局部字段宣称自然严重错误0。

## 用量与时延

全部响应报告33184输入/10317总输出；账本可信协议结算29750输入/9891输出，unknown审核另报告3434输入/426总输出（含50推理，不重复加总）。旧14次保留，这组实验累计24HTTP、115074报告输入/25275报告总输出。不是整个项目的总调用数。真实费率/币种/账单未知，不记为0或可信发票。

PG创建操作至first_scene_ready/done的观察分别为：D01-known 16.236/16.503秒，D01-unknown 12.597/12.882秒，D02-known 13.717/21.955秒。这不是HTTP首字节或正文首token，未分开验证冷/暖，不能代替T041独立性能。D02生成完成不等于课程质量通过。

## 验证与交接

- `backend/.venv/bin/python scripts/check_p15_full_r05_results.py --check`：预期exit2，确认停止而非验收成功；461冻结SHA、准确授权、原始响应/账本/两份标准报告/另存盲核、PG只读来源、观察收据与真实用量均核对。源码/材料未修改使旧包冒充匹配。
- `backend/.venv/bin/python -m pytest scripts/tests/test_p15_full_r05_results.py -q --junitxml=/tmp/edumind-full-r05-results.xml`：20 passed / 0skip。覆盖无reasoning项的原始拒绝、静态JSON不等于协议成功、来源/引用错误仍拒绝、不得伪造完成/人类/零费用/隐藏unknown、历史、未运行或严重质量失败。
- 结果checker/Ruff、工作流和diff检查通过。原128项离线/PG-Mock是准备证据，不计为此次真实质量分数。首个只读观察误用系统Python缺jsonschema，换项目venv后完成，没有新增请求或改Schema。
- 专用PG已恢复exited；私有原始响应（含可能的推理元数据）只留独立700目录，不展示/解释/转发隐藏推理。公开提交仅脱敏报告、合成引用、SHA及批准记录。停止后真实调用0。

T038保持blocked，无Task-Completed，不领取T039，不push/merge/部署。后续建议先离线处理C接口语义与题目状态一致性，再单独评估“推理token必须伴随输出项”这一额外观测约束；本轮不改契约、不修剪失败样本、不重开真实批次。
