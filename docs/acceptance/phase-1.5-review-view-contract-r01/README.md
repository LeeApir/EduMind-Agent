# 新版审核视图契约提案

本目录及 [ADR-0049](../../ADR/0049-visible-review-view.md) 是响应用户要求的**设计提案**，不是已采纳契约、已实现视图或真实调用授权。T102 保持进行中；旧候选、旧冻结包、旧结果和正式验收标准保持。

- [可见视图与证据规则](VIEW-CONTRACT.md)：完整内容、短 ID、证据字符串、受控响应及父链。
- [旧目标逐类迁移](OLD-TARGET-MAPPING.md)：哪些教学内容拆分到可见目标，哪些内部字段改由程序校验，以及丧失的旧整对象字面引用能力。
- [正反例](EXAMPLES.md)：同文不同字段、非规范 ID、JSON 转义、隐藏内容与跨版本绑定。
- [B/C 开发样例盘点](sample-old-target-inventory.json)：分别有／无引用的旧目标路径及分类。`check_mapping.py` 只对这些样例分类并拒绝列出的未知路径，**不是**逐目标新 ID 映射实现，也不是全部合法输入覆盖证明。

离线检查：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-review-view-contract-r01/check_mapping.py
backend/.venv/bin/ruff check docs/acceptance/phase-1.5-review-view-contract-r01/check_mapping.py
python3 docs/acceptance/phase-1.5-review-view-contract-r01/verify_manifest.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

本提案需要作为实验契约变化审阅和决定；不能视为 ADR-0047 的等价压缩。若采纳，后续仍须实际构造可见视图、严格校验每个引用、遍历全量旧目标、完成容量边界与 B/C 控制器，交独立评估后再冻结、选样并准备准确真实执行包。真实调用需独立具体授权；无 Provider 调用、生产开放或旧批重启。
