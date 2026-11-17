# 形式契约v2与受委托助手复核 r02

按用户“先完成项目”、本轮明确合成外发授权和“你帮我复核，不用给我材料”指令继续，不重新要求用户审阅候选材料。规则见 ADR-0035；T058完成31ca187，旧r01失败466a015不改写、不恢复。

保持原34个开发槽、DeepSeek Flash生成／AIAPI sol逐场景审核、完整Schema及教学阈值。只更新场景Prompt v2的精确forms传递与助手来源标记，并纠正CLI终态优先级。新增7离线+1实际隔离PG-Mock通过，底层形式修复144项回归通过。测试不作为真实模型通过证据。

原请求/墙钟共享：旧r01真实3次+本轮最多247次≤250；生成剩179，审核68；不重置r01原3小时绝对截止。费用与token不限、实际费用unknown，报告用量和累计分别保留。准确配置plan.json，代码与原34槽SHA见manifest.json。user-direction.json如实登记直接指令，不声称用户独立逐哈希审批了新包。

新输出/tmp/edumind-p15-split-exploration-r02；新专用PG数据库edumind_catalog_p15_t020_exploration_r02，回环15437。--check只离线核对；--step单槽；--review导入主助手实际逐项核对报告，事件为assistant_review，禁止冒用human身份或独立真值。非pass意见、严重/未决、协议/来源/安全/未知发送、请求数或原截止到期均停止；不重抽样、不静默回退、不自动发布或部署。

```sh
backend/.venv/bin/python scripts/run_p15_split_exploration_r02.py --check
backend/.venv/bin/python scripts/run_p15_split_exploration_r02.py --step
backend/.venv/bin/python scripts/run_p15_split_exploration_r02.py --review /absolute/path/assistant-review.json
```

该版本不恢复生产SendPolicy上界标志；独立人类质量/性能验收未完成时不凭助手委托提前完成阶段或T039–T042。
