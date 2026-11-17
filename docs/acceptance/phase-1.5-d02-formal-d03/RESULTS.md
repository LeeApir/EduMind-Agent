# 正式 D02 d03：规划通过，第二场景缺字段，已停止

用户准确批准提交1810815及manifest `c7b0d71dc98f4b1be53ea4578825f5f8dab9c1fa34cb359abada2791d594e6cc`，包括ADR0040 A—B本批范围、合成外发、新窗口及费用例外；登记见execution-approval.json及ADR0040本批批准记录。新窗口2026-10-28 10:39:51（Asia/Shanghai）起1800秒，最多5HTTP。本次只执行一次正式入口，实际3HTTP200后停止，未重试、修复、回退或重启旧批次；剩余2次不用。

| 请求 | 实际结果 | 本地校验 |
|---|---|---|
| DeepSeek规划v2 | completed，2355输入/733总输出 | 通过；4个学习目标均被场景覆盖，两个场景，编排约束保留在conventions |
| DeepSeek场景v5，第一场景 | completed，4387输入/2161总输出 | 通过；有blocks及actions，持久化1个场景版本 |
| DeepSeek场景v5，第二场景 | completed，7024输入/2242总输出 | 失败；顶层仅blocks，缺必填actions |
| sol审核两场景 | 未运行 | 不作兼容或教学审核通过结论 |

第三请求原始JSON可解析，但不符合Schema。只读原始请求确认 `text.format.schema.required` 已含 `actions`；原响应缺此字段，原Schema准确产生根路径 `required: 'actions' is a required property`，原validate_response返回SCHEMA_INVALID。没有修改原始响应或补入空数组。证据支持“本次返回未遵守已发送结构契约”；仅凭响应不能确定供应商内部是否强制Schema，也不能把它解释为中转故障。此次生成服务是DeepSeek官方，审核中转并未调用。

规划补丁修复的问题在本样本中没有重现：未产生“组织两个场景”学习目标，也没有漏引用。这不证明任意后续规划可靠。场景v5本次确实执行了两次，失败属于结构缺项；不能将其说成已确认新的链表事实错误。

## 助手直接阅读观察

助手实际阅读了两个原始场景的所有正文、两份代码、全部8题的题干/答案/解析及第一场景3条动作。这是停止后的诊断阅读，未建立标准slot_output，也没有导入标准助手审核记录，更不冒充sol审核或独立人工真值。

第一场景四题答案依次为3、1、A、B；第二场景四题为B、B、A、B。逐项按明确初态追踪：正常头插得到3→2→1；第二次连接时next仍指结点1；丢弃返回值使调用者head保持NULL；先改head再连next形成自环；未初始化next不能作为确定NULL读取。这些答案与本次对应代码/变体一致，未再发现先前返回值传播和把自环当有限链表的问题。代码检查了分配失败并返回原头，调用者接收新头，正常链表释放逻辑与示例一致；示例输出以分配成功为条件。第一场景动作均指向实际存在的锚点。上述有限阅读不覆盖任意C程序正确性，不授予可靠评分或发布资格；第二场景仍因缺actions不准入。

## 用量和持久证据

3请求complete、0unknown，报告并结算13766输入/5136总输出；实际收费/币种未知。旧相关30请求保留，累计33请求、报告152156输入/36211总输出，非全项目累计。旧unknown及旧失败不重结算。

外层账本为stopped/threshold_unreachable，安全失败码FIRST_SCHEMA_THRESHOLD_UNREACHABLE。只读PG快照包含3attempt/3settlement、1plan、1scene_version及1accepted validation；第二场景没有持久候选版本。内部操作仍running、第二场景pending/format_repair，容量记录held：忠实保留原调度历史，**没有对应修复出站**。外层永久停止，进程无残留，专用PG已exited，不能用内部标记授权恢复。

私有原件位于 `/tmp/edumind-p15-d02-formal-d03`；包含原请求/响应/HTTP状态、SQLite账本、只读PG快照。results-manifest.json绑定原件SHA，results.json提供去敏机器结果。只读检查器check_p15_formal_d03_results.py重放原校验、核对请求/响应摘要与结算/PG，预期退出2表示未通过；5项证据回归通过，含请求/响应/PG/账本篡改拒绝，详见results-validation.json。停止后新增真实0，没有修改教学链路、Schema或Prompt。

一次正式测试已按约执行并保留失败；T038仍blocked。按用户指定顺序，现在进入[方案重评](REASSESSMENT.md)，不再追加本样本补丁或新调用。
