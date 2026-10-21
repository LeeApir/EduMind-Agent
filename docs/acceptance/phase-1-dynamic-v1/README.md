# Phase 1 独立动态验收 v1（提案）

本目录是 T035 可审阅提案，批准入口为 [ADR-0011 A–D](../../ADR/0011-independent-dynamic-acceptance.md)，hash 清单见 [manifest](manifest.json)。目前未获设计批准、真实模型选择、人工标签签核或调用预算；离线测试不代表模型质量。`configuration-template.json` 故意不可执行。

| 文件 | 用途 |
| --- | --- |
| history.json | 原归档 8 个审核案例、原 hash、payload 和 3 份失败报告 provenance |
| new-resource-cases.json | 未调参的正式资源审核 20 错误 / 20 正确 / 10 长样本及预期标签 |
| generation-slots.json | 100 个新生成目标与 9 个历史未发布槽 hash；原失败记录从归档读取 |
| configuration-template.json | 尚无目标和价格的轮次模板，授权 0；接入前必须补齐并重新冻结 |
| manifest.json | 提案附件与当前源码版本的 SHA-256，不代表未来实际运行冻结 |

固定文件顺序发送。长例为确定性构造的数组轨迹，每例 60 插入、40 删除，长度最高 22、最终 20；它们只覆盖这一种长审核输入形状，不能代替原链表长代码复验。C 错误例的类型/标准库视为已定义，调用前提写在片段前；不执行样本代码。预期严重程度和事实标签等待人工审批，不能因本地 schema 有效就称标签正确。

诊断复用历史 5/5/1/2 个输入，正式新例不参加调参。历史未发布槽只绑定原记录，复验必须从归档恢复原意图/上下文；不能从 ID 猜输入。新轮次更换指令时保留旧请求 hash，不称逐字重放。

离线验证命令（不联网、不读 Key）：

```sh
backend/.venv/bin/pytest -q backend/tests/test_phase1_dynamic_gate.py backend/tests/test_acceptance_budget.py
backend/.venv/bin/python scripts/verify_phase1_dynamic_freeze.py
python3 scripts/verify_legacy_archives.py
python3 scripts/check_catalog_workflow.py
```

门禁计数器和统计器仅供未来受信验收组合层使用；没有 CLI 网络开关。实际运行还必须绑定批准证据/响应与人工标注、模型路由/输入、SSRF/凭据/超时和真实费用上界，见 ADR C。现有生产默认拒绝预算及目录模式不改。
