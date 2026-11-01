# T102 可见目标、容量与离线控制器证据

本目录是**开发中的离线证据**，不是冻结后的实验包、真实调用许可、独立教学评估或 T102 完成证明。旧 T101 冻结内容和停止的批次未修改；本轮真实 Provider 调用为 0。样例均为开发构造，B 测试输出由测试夹具借用引擎构造，不能冒充模型基线或独立真值。

## 逐目标迁移

- [B 逐目标报告](b-target-report.json)及[旧目标、新视图和绑定来源](b-target-sources.json)：206 个旧目标。
- [C 逐目标报告](c-target-report.json)及[旧目标、新视图和绑定来源](c-target-sources.json)：160 个旧目标。
- 报告由 [迁移器](../../../scripts/isolated_diagnostics/p15_visible_migration_v1.py)逐个旧目标生成；出现未分类路径即失败。`visible_ids` 在同臂来源文件的 `visible_view.cells` 中查找，准确来源在 `visible_binding.paths` 中按 ID 查找。`direct` 是相同字段的可见单元；`split` 是拆分后的可见子单元，不能将同文自动认作原字段的等价引用；`program` 是程序检查，不再声称旧值为模型可见目标。
- 程序检查名称和实际范围：`ARTIFACT_RECONSTRUCTION` 重组候选及来源；`CATALOG_BINDING` 重建规格、例子和事实目录；`DOCUMENT_RECONSTRUCTION` 重建 Markdown 原文、解析树、引用和定义；`IDENTITY_SHAPE` 校验身份字段及规格约束。样例报告中的 `RECEIPT_AND_PARENT_CHAIN` 标为 `pending_controlled_http`：这些样例只是本地组装，不凭摘要冒充真实收据。下方独立 Mock 链另从实际发送的 Mock HTTP 字节和回包重建其收据及父链。
- 引用 URL、标题各有独立短 ID，绑定准确的解析后字段；完整 Markdown 原文仍是另一独立目标。解析器将空标题 `""` 规范为 `null` 时，原文中的 `""` 仍可见，不能把解析后 `null` 冒称原文字面值。共享事实摘要只用于目录检查，不借父对象中的同文冒充各事实字段。

## 边界与预约

[预演记录](capacity-evidence.json)覆盖最长 3+4 规格、B/C 16 个长文本字段、重复和不同定义的密集引用、转义字符、首次及修复后审核；B 另覆盖结构上允许的 20,000 行代码、64 状态和 180 动作。这些是结构压力样例，不是教学合格样本。9,693 个不同定义的 B 臂样例，完整外层初次/重审分别为 **7,680,483／7,680,579 字节**；包含 Prompt、Schema、外层 JSON 和二次转义，超过旧 4 MiB。计算方法、开发门限、已知空白和下一步见[容量说明](CAPACITY.md)。

## 完整 Mock 链

[B 原件及收据](b-mock-flow.json)和[C 原件及收据](c-mock-flow.json)来自同一本隔离批次账本：B 为 4 次 Mock HTTP，C 为 5 次；各自走过生成、包含非空问题及真实可见目标/引文的审核、一次修复和重审，C 另有规划。记录包含完整请求体、原始回包、预约、使用量、候选版本及摘要。模拟审核通过不等于教学质量通过；B 反馈核定人是测试夹具，不是独立评估结论。

相同控制器另以每臂 9,693 个不同引用定义的大规模样例走完完整 9 次 Mock HTTP。完整请求、原始响应、候选、问题和共享账本快照保存在[压缩证据](stress-mock-flow.json.gz)；压缩只用于本地存档，模型在 Mock 请求中收到的是完整可见视图。其报告的 token 用量是夹具数值，不是服务商实际用量。

[控制器](../../../scripts/isolated_diagnostics/p15_controlled_mock_v1.py)仅接受 `httpx.MockTransport`，不会读取密钥或发起真实网络请求。它把包、固定账本路径、槽位顺序、B/C 同槽规格、Prompt/Schema/路由摘要和预算绑定；记录请求/原始响应并从响应解析用量。未知或超预约停止并保留预约；停止后的迟到响应只留证和结算，不推进。新增的本地拒绝回归覆盖未知变体、超长、任意代码和未知精确结果，两臂均为零 HTTP，尚未纳入独立实验分子。

当前还不是可批准的真实执行器：实际凭据、目标核验与防 SSRF 的受控传输尚未接线；全部支持域的容量上界未证明；正式样本和独立评估尚未在执行器与策略冻结后选择。SQLite 和旁路 anchor 依赖可信本地目录：单独丢失、清空或回滚其中一个会拒绝恢复，但同时回滚/删除两者、或替换父目录不受其保护；未证明系统断电后的目录项持久性。需不可回滚保证时必须另用独立持久单调状态。

## 复现

```bash
PYTHONPATH=backend:. backend/.venv/bin/python scripts/isolated_diagnostics/generate_p15_visible_migration_report.py
PYTHONPATH=backend:. backend/.venv/bin/python scripts/isolated_diagnostics/generate_p15_mock_flow_evidence.py
PYTHONPATH=backend:. backend/.venv/bin/python scripts/isolated_diagnostics/generate_p15_visible_capacity_evidence.py
PYTHONPATH=backend:. backend/.venv/bin/python scripts/isolated_diagnostics/generate_p15_stress_mock_evidence.py
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-visible-migration-t102/check_evidence.py
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-visible-migration-t102/check_stress_evidence.py
```

Mock 记录中的临时账本路径会随复现改变，相关包和收据摘要也会改变；原始阶段、字段和校验方式可以重新检查。
