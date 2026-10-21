# 验收资料：当前入口与回归依赖

当前阶段为Phase 1.5，42项任务均todo，尚未领取。正式运行仍catalog_only，T040／T041历史blocked不变，整理不授权模型调用、动态开放或开发。

## 后续开发先看这些

- [Phase 1.5需求](../PRD-phase-1.5-draft.md)、[任务规划](../phase-1.5-task-plan.md)、[活动账本](../../task.json)：当前开发依据。页面原型和设计说明位于docs/design/，不是旧验收包。
- [P1最终交接](phase-1-closeout-20261021/README.md)：已交付能力、限制、89 done／2 blocked、真实运行已知用量及退出决定。完成任务不等于原质量／性能通过。
- [目录课程原始签核](mvp-0.3-catalog-human-signoff-20261003.json)、[目录退出](mvp-0.3-catalog-exit-20261003.md)：当前正式课程的来源，必须保留；不能替换成模型生成成绩。
- [H01–H08封存状态](phase-1-holdout-reserve-r01/CURRENT-STATUS.md)：按新课程契约另评适用性，禁止当作开发材料或自动继承资格。
- [旧验收包归档索引](ARCHIVE.md)：查旧失败、未运行、性能及修复历史，从此进入；不是新执行授权。

## 为什么还有78个目录保留

对backend/tests、scripts/tests及其本地导入依赖作静态追踪，共检查574个Python模块。75个包名仍被回归／工具读取，加上最终交接、H和用户未提交报告的保护目录，保留78个目录；它们不是当前阶段的新验收计划。

主要用途：共享计划／资源和单元审核、节点绑定、预算和Schema兼容、固定C样本与容器、队列／DSL故障、安全及历史缺陷回放。完整的“目录→实际消费模块”清单在[保留与迁出清单](../maintenance/acceptance-archive-20261021.json)的kept_directories字段。不将这些回归材料充当泛化证明，也不为了目录更少删掉测试依赖。

当前日常入口是本页及活动账本，不必逐个阅读旧包。旧包的pending／Proposed／旧任务数按当时快照解释，不作为当前状态。

## 已迁出与恢复

32个无上述依赖的旧验收包、346个文件移至local-materials/acceptance-archive-20261021/snapshot/，按原仓库相对路径保存，逐文件SHA256一致。另将根目录和backend的检查缓存、Finder元数据移到同一整理区的rebuildable-cache/；它们可由工具重建，不含虚拟环境、凭据、数据库或生成媒体。

```bash
python3 scripts/manage_acceptance_archive.py check
# 本地Git包含来源提交、但缺历史材料时，离线恢复到local-materials：
python3 scripts/manage_acceptance_archive.py restore
python3 scripts/check_phase_handoff.py
```

原Git历史与阶段账本/process.txt不改路径、不回填成绩。现行入口链接转向ARCHIVE.md；冻结历史文件保持原字节，其旧链接经归档清单定位。阶段交接检查器同时接受明确登记的归档位置和此前已迁移的本地证据位置，摘要验证不放宽；P1切换回执与初始根账本按对应历史提交核验，不要求Phase 1.5永远停留在初始化的一条任务。

本地档案被Git忽略，不随clone分发；来源Git提交和逐文件清单随仓库保存。恢复仅取回资料，不加载.env、不调用Provider或启动旧执行器。详细操作与检查见[本次整理记录](../maintenance/acceptance-cleanup-20261021.md)。

浅克隆若没有来源Git对象，需另行取得准确历史或由维护者提供本地档案；恢复工具不会自动联网取历史。
