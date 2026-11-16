# 验收资料入口

Phase 1.5 已按 ADR0066 收敛退出，**原开发质量、独立质量与性能没有通过**。当前 Phase 2 先讨论课程、界面、动画与习题重设计；历史试验不再执行。当前任务以[根账本](../../task.json)为准，正式产品保持 `catalog_only`。

## 当前交接与可复用成果

| 要了解什么 | 入口 |
| --- | --- |
| 阶段结束原因、缺口和保留范围 | [Phase 1.5 收敛交接](phase-1.5-t038-gap-review-t123/GAPS.md)、[ADR0066](../ADR/0066-phase-1.5-contracted-closeout.md)、[只读任务归档](../tasks/phase-1.5.json) |
| 四主题课程的已有能力 | [四主题共用流程](phase-1.5-shared-live-reuse-t127/RESULTS.md)、[二分查找程序帧](phase-1.5-binary-search-program-frames-t130/RESULTS.md) |
| 栈的目标选择、多场景与判卷 | [栈统一结果](phase-1.5-stack-boundaries-t138/RESULTS.md)；不同批次和版本的成绩不能合并 |
| 画像适配的实际局限 | [A/B 课程及对照](phase-1.5-stack-profile-pair-t132/RESULTS.md)：两课合格，最后跨批对照仅 1/3，不通过 |
| 私有课程与兼容能力 | [四主题封存回放](phase-1.5-course-trial-replay-t120/RESULTS.md)、[已有头插导入](phase-1.5-archived-head-import-t117/README.md)、[兼容检查](phase-1.5-compatibility-t021/README.md) |
| 核心工程的原验证范围 | [集成记录](phase-1.5-integration-t035/README.md)、[浏览器记录](phase-1.5-browser-t036/README.md)；历史检查不自动证明新设计通过 |

## 保留的契约与历史

- [课程契约](phase-1.5-course-contract-r01/README.md)、[生成契约](phase-1.5-generation-contract-r01/README.md)、[质量契约](phase-1.5-quality-contract-r01/README.md)、[验收契约](phase-1.5-acceptance-contract-r01/README.md)：原指标和失败不回填，新设计如需调整另作决定。
- [T102 最终重设计与独立复核](phase-1.5-manual-bc-redesign-t102/DESIGN.md)：保留代表性失败，不恢复执行器路线。其历史相对链接可通过下述归档索引定位原提交。
- [Phase 1 交接](phase-1-closeout-20261021/README.md)、[原目录课程签核](mvp-0.3-catalog-human-signoff-20261003.json)、[目录退出](mvp-0.3-catalog-exit-20261003.md)：保留正式课程来源与历史限制。
- H01–H08 继续封存，不作为新阶段开发材料，不继承样本资格。

## 退役资料与恢复

[ARCHIVE.md](ARCHIVE.md) 列出已退役的资料批次、准确 Git 来源和恢复方法。只需日常开发时阅读本页及当前任务，不必逐个打开历史包。

- 2026-10-21：32 包、346 文件，原恢复清单保留。
- 2026-11-16：退役九个 T102 过程包及专属消费者，共 66 文件；未删除 Git 历史，不在工作区复制完整档案。见[本次清理记录](../maintenance/acceptance-cleanup-20261116.md)。

保留材料仍可能被课程导入、准入或有效回归按准确路径读取，不能按目录日期批量删除。历史文件中的 pending、旧任务数和旧阶段名称保留当时含义，不构成执行授权。密钥、私有数据库与加密原件继续本机保管。
