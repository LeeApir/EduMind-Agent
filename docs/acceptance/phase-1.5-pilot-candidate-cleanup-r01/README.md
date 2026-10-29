# 头插法实验：候选整理与字段责任

本次以已批准 ADR0047 的隔离双臂实验为范围，复用 [受限示例引擎](../../../scripts/isolated_diagnostics/p15_head_insertion_engine.py)、[最小契约适配器](../../../scripts/isolated_diagnostics/p15_minimal_contract.py)与其[完整契约](../phase-1.5-minimal-output-contract-r01/CONTRACT.md)。[新版提示词候选](../../../scripts/isolated_diagnostics/p15_clean_pilot_prompts.py)是独立版本的静态材料，尚未接入运行器；既有正式自由课程 Prompt 和已冻结试验保留原样。新文本不能宣称与旧文本的模型行为等价，需重新审查和版本绑定。

## 候选与数据流

| 候选 | 现有入口 | 作用与限制 |
| --- | --- | --- |
| B 基线 | [隔离流程](../../../scripts/isolated_diagnostics/p15_minimal_pilot.py)的 `B_generate` / `B_repair` | 模型独立生成讲解、代码、四题答案与动作；修复按既定规则最多一次。程序不拿引擎答案补全或替换 B 的错误。 |
| C 协作 | 同一流程的 `C_plan` / `C_content` / `C_repair` | 程序生成准确规格、代码、轨迹及答案；模型选择给定规格与目标顺序，提供讲解和事实引用。C 普通修复仅针对教学内容。 |
| 审核 | 同一流程的 `review_B` / `review_C` | 同一个审核契约分别审核两臂完整原始输出及展示产物，并获得允许的程序参考。模型意见不是独立事实裁决。 |
| 协议探针 | [T088结果](../phase-1.5-separated-validation-r01/results/RESULTS.md)及 [R0结果](../phase-1.5-r0-once-r01/results/RESULTS.md) | 为诊断格式与单次修复行为，不是可评课程或正式链路；W4 失败不因 R0 单次机械合格而消失，R0 仍待独立语义复核。 |

## 清理历史覆盖

旧 `minimal-pilot-prompt-v1` 从旧阶段拼接指令，产生以下相互覆盖。新候选直接描述已批准最小字段，避免要求模型先遵从旧字段再自行覆盖：

| 阶段 | 旧提示中实际冲突或遗留 | 新候选处理 |
| --- | --- | --- |
| C 规划 | 先要求“observation coverage”，追加部分又要求只返回 `spec_id` 和 `objective_ids`、不返回 coverage | 只描述两字段与四目标；覆盖映射由程序持有，不要求模型复述。 |
| B 生成 | 旧描述使用 `show_state` 等动作名，追加部分要求分组数组；又先提及程序提供 code anchor、后文明确禁止模型返回 anchor，职责本身并不矛盾但容易混淆 | 明确用 `states`/`highlights`/`advances` 和全局顺序表达动作；anchor 由程序持有。 |
| 审核 | 旧说明要求 `source_sha256`、`source_pointer`、`scope_status`、`uncertain_reason`、`reject`/`uncertain` 和以 scene/source 为根的路径；后文又用短 ID、`unknown`、空字符串及完整 artifact 规则覆盖 | 只要求现行 `candidate_id`、`target_id`、`uncertainty` 与 `pass/revise/unknown`；对完整原始与展示内容审核，目标引用与准确 quote 由程序校验。 |
| B/C 修复 | 在旧修复说明后叠加新信封规则 | 单独说明每臂真实修复范围、固定题型及一次上限；事实/安全/unknown 的停止仍由控制器执行。 |

新提示直接保留事实、步骤、代码安全、复杂度、题意/参考答案、难度、误解、约定一致性以及原文和展示产物审查。清理后的表述是候选，词句改变可能影响模型；离线检查无法证明教学效果或 Provider 遵从率。

## 字段所有者与验证

[逐叶字段清单](field-inventory.json)覆盖四份 Schema 的全部字段，`*` 表示数组元素；六个提示词阶段分别映射规划、内容、修复、基线生成、基线修复、审核，审核按 B/C 两臂复用。清单分别列 **谁产生输出、现有程序机械校验、仍需的语义复核**。检查器将全部路径与冻结 Schema 对照，避免字段遗漏；验证分类供审查，不是形式化证明所有语义等价。

| 程序持有的内容 | 来源与验证责任 |
| --- | --- |
| 输入规格、规格 ID、事实目录、代码、轨迹和 C 答案 | 引擎限制规格和有限变体；`make_catalog` / `verify_catalog` 重建并绑定摘要。C 返回的 ID 须属于当前目录；**ID 存在不能证明解释正确**。 |
| run/slot/arm/revision、父版本、spec/产物摘要、anchor、Prompt/契约版本 | `identity` 固定 v1 并记录规格/父版本，`assemble` 校验契约版本和 C 规格，`verify_artifact` 校验产物形状及自洽摘要；事件记录指令摘要。现有代码不交叉核验实际指令摘要与产物 Prompt 版本。模型不生成身份；B 的内容、代码、答案、动作保留模型来源。 |
| 审核 candidate ID、target 目录及规范投影 | `make_binding` / `verify_binding` 根据完整产物重新构建；审核 ID 和 quote 必须定位当前候选。但精确定位不证明观点正确，非字符串字段投影不是事实证明。 |
| Schema、严格 JSON、范围、指针/步骤/高亮引用、动作排序 | `strict_json`、`validate` 与 `_baseline_actions` 做确定性拒绝；合法结构不代表教学、C 语言语义或代码安全已通过。独立复核逐项检查。 |
| 原文与清洗展示 | 保留 `raw_output`；展示投影按现有清洗规则生成。审核应覆盖二者，不自动改原文、不自动发布或评分。 |

程序对 C 解析事实，不代写自然语言；B 不接事实目录、C 产物或正确答案。修复输入和审核参考的边界、两臂不同修复范围及可比性保持 [ADR0047](../../ADR/0047-minimal-pilot-output-contract.md) 与 [对照说明](../phase-1.5-minimal-output-contract-r01/COMPARABILITY.md)。结构合格、模型 pass 和可定位 quote 都不是教学正确性签核。

## 当前限制与后续

现有 `identity()` 在 [适配器](../../../scripts/isolated_diagnostics/p15_minimal_contract.py)中固定 `minimal-pilot-prompt-v1`，既有 `Pilot.call()` 也直接使用旧常量。因此不能把新提示词塞进旧流程却仍记为 v1；本次**未接线**。如后续采用，需要独立版本化身份、实际请求指令版本与摘要、产物身份、父版本及审核绑定的交叉验证、完整回归和新准确兼容包，并审查 Prompt 调整对双臂可比性的影响。必须先恢复整套角色接口准入，才能准备课程实验；旧失败、预算与窗口不继承。

本次新增真实 Provider 调用 0；T038 blocked、catalog_only 与封存样本保持。R0 原件待独立语义复核，未将其改写或判为修复成功。测试命令及结果见 [verification.txt](verification.txt)。
