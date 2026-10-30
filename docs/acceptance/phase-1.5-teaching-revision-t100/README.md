# T100：一次有限教学修订

在隔离头插实验中新增 `minimal-pilot-teaching-v3`：B/C 规划、生成、修复和审核共同携带[通用教学规则](../../../scripts/isolated_diagnostics/p15_teaching_revision.py)。规则要求简体中文教学文本、按实际观察区分到 NULL 的完整遍历与环/未知情况下的可知前缀、说明实际示例/动作范围及变量作用域，并说明动态分配与安全释放边界。代码、ID、Schema key 和枚举仍保持准确原值；B 不接 C 的事实或答案。

[隔离 v3 Mock 流程](../../../scripts/isolated_diagnostics/p15_teaching_pilot.py)实际使用新版指令、请求/响应/候选/父版绑定和 T097 紧凑审核材料；B 修复前仍须可信反馈核对。审核 preflight 重建真实 wire 请求并校验字节上限、目标、候选与参考规格绑定；Mock 响应不等同真实 Responses 协议，T097 的有界加密字段适配器已提供 B/C 单独响应检查，但真实链路仍须后续准确包接线。双臂规则相同，但 B 独立计算代码/答案/动作，C 使用程序事实，不能因此认为两臂信息相同。所有语义、中文和审核效果仍须实际模型及独立评估，格式检查不能代替。

[中文修订草稿](assistant-revision.md)是助手依据 T099 独立评估对 T095 原文进行的一次离线文字修订，不是模型重生成、不是质量签核。`assistant-revision.json` 绑定原候选摘要并如实标记助手来源。原模型输出和旧冻结包保持不变。

本次**没有修改共享引擎、代码、状态或动作**。派生修订重新验证代码、4 个答案、事实目录和 31 个动作与原候选逐值一致；原播放器仍播放旧原文，不能冒充展示新文字。四变体×四种分配掩码、正常/失败/未知与规格拒绝均做离线回归；新双臂 Mock 路径包括审核、一次修复和绑定反例。真实候选审核预演保留全部181目标；对精简材料和加密字段规则不宣称真实供应商已通过。

验证命令：`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_teaching_revision.py scripts/tests/test_p15_teaching_pilot.py scripts/tests/test_p15_review_engineering.py scripts/tests/test_p15_bound_pilot.py scripts/tests/test_p15_head_insertion_engine.py scripts/tests/test_p15_minimal_contract.py -q --tb=short`：**264 passed，0 skipped**；Ruff 和三源严格 mypy、旧 T095 原件及 R0 包校验、工作流、diff 检查通过。测试中的合成 B 回复来自工厂，不是模型能力或独立真值。

未运行真实 Provider，未恢复停止批次；后续冻结代码、Prompt及审核能力后，独立评估者再选新样本。下一批必须验证新审核链路，旧模型审核 pass 和旧额度不得继承。

独立审查发现旧版新审核 helper 可将同臂不同候选的请求与响应错配；已要求从当前绑定和规格重建完整审核请求并逐字节比较，新增同臂异版本、篡改目录及 B/C 跨规格参考反例。独立教学复核指出中文题目需给出精确枚举输入格式，草稿已增加 terminated/cycle/indeterminate 与中文映射，答案未变。
