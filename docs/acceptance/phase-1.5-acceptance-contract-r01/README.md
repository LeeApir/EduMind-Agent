# T005 独立验收口径与交接

状态：ADR-0027 A—E及准确附件提案，尚未批准；仅设计，不是运行结果。

## 审批入口

请审阅[ADR-0027](../../ADR/0027-independent-free-course-acceptance.md)的A—E：[完整契约](contract.md)、[政策](policy.json)、[计算边界例](examples.json)、[离线检查器](check_design.py)。[manifest](manifest.json)绑定准确文件摘要；批准不自动提供真实Provider、费用、T006执行或运行开放授权。

拟议门槛包括98%首次结构、95%完整草稿/需求兑现/可学性、90%画像对照与审核召回/意见精确率、99%事实、100%答案、自然严重错误0；质量40课程槽与审核20错/20对照，性能另40课程槽及20取消/恢复槽。分层也须达标，不能挑成功样本。首完整可学场景P95≤10秒、后续每课最大等待≤30秒、短/长整课≤180/480秒；准确时钟、失败处理、冷暖分别达标见契约。

## 证据与恢复

设计检查命令（无网络/Provider/H内容/凭据）：

```sh
python3 docs/acceptance/phase-1.5-acceptance-contract-r01/check_design.py
backend/.venv/bin/ruff check docs/acceptance/phase-1.5-acceptance-contract-r01/check_design.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

实际结果及读者检查见[verification.txt](verification.txt)。计算例均为规范算术示例，不能冒充真实生成内容、人工标签或性能成绩。此前T001–T004已批准冻结文件另复核摘要，不改字节。

本包不替代T035/T036隔离集成和业务浏览器验收；T037开发包与T039独立包仍需候选、材料/人工标签、准确请求/token/费用/时间预算、执行器及新批准。旧P1失败不改，H继续封存。具体阈值待批准时T005保持blocked，获准后登记提案commit与manifest、复核再完成独立Task-Completed提交。下一T006数据模型仍todo，需执行授权。

分支codex/phase-1.5-t001。用户旧报告改动及OpenMAIC参考目录保留且不提交；不push/merge/部署，catalog_only保持。
