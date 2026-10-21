# 验收材料深度整理（2026-10-21）

用户明确选择深度归档：旧验收包迁入local-materials，保留恢复清单并修复现行引用和检查。当前分支codex/phase-1.5-requirements，基线a59038c。此为维护治理，不领取Phase 1.5任务、不改开发范围，不发Provider请求。

## 实际整理

- 32个无当前backend/tests、scripts/tests及其导入依赖的旧包，共346文件／7,491,365字节，从docs/acceptance迁至local-materials/acceptance-archive-20261021/snapshot/；来源提交逐文件比对，SHA256保持。验收目录约42MiB→35MiB。未删除历史Git提交、失败、停止、未运行或已签核原件。
- 根与backend的mypy／pytest／ruff缓存及.DS_Store，共116,324,509字节（约111MiB）归置至同一目录rebuildable-cache/。虚拟环境、node_modules、数据库、凭据、媒体、.pnpm-store、在用预览产物和未跟踪参考目录不动。工具后续会重建缓存；这次是移出工作目录，不是释放全部磁盘占用。
- 78个目录保留：75个仍为现有回归／脚本的静态依赖，加最终交接、H、用户报告保护目录。追踪574个Python模块；保留不意味着它们是Phase 1.5正式验收材料。不能为了减少目录数把测试夹具、Schema及导入依赖删掉。

## 后续开发真正需要的内容

| 优先级 | 资料 | 用途 |
| --- | --- | --- |
| 每日使用 | 根task.json、PRD、PRD-phase-1.5-draft、phase-1.5-task-plan、ADR-0023及docs/design | 当前42项规划、已确认方向和页面原型；尚未授权领取 |
| 持续保留 | 目录原签核／release allowlist、固定课程包、各阶段账本、process.txt | 正式产品来源、任务状态和历史追溯 |
| 边界依据 | P1最终交接、ADR-0022、PROVIDERS／队列／DSL／人工历史等实现契约 | 已交付／未验证、失败退出及权限安全边界 |
| 回归必需 | acceptance中kept_directories所列75个包及固定C工具链／夹具 | 现有代码测试和历史缺陷回放；不当泛化集 |
| 继续封存 | H01–H08 | 新课程契约另评适用性，不调优、不自动继承资格 |
| 偶尔查阅 | 已归档32包 | 旧实验／退役运行／重复准备或旧实现记录；需要时查Git原提交或恢复 |
| 可重建 | 已迁出的工具缓存／Finder元数据 | 不作为源码或验收证据；无需版本管理 |

[完整清单](acceptance-archive-20261021.json)给出每个保留目录的消费模块、每个迁出文件的SHA、来源位置和已有本地材料迁移别名。历史日志路径不回填；805条已有迁移位置只登记为别名，实际材料不再次移动、不改变摘要。

## 恢复与引用

```sh
python3 scripts/manage_acceptance_archive.py check
python3 scripts/manage_acceptance_archive.py restore
# 或仅恢复指定历史文件到local-materials：
python3 scripts/manage_acceptance_archive.py restore --path docs/acceptance/phase-1-plan-boundary-results-r01/README.md
python3 scripts/check_phase_handoff.py
```

恢复依赖本地仍有来源提交对象；工具只做git show、SHA检查和缺文件时的新建，不联网、不覆盖已变文件、不运行旧执行器。浅克隆缺该对象须另取准确历史或维护者档案，不冒称本地材料随clone分发。

现行ADR索引、ADR-0022及P1交接共7处入口链接转向[归档索引](../acceptance/ARCHIVE.md)，修改前文档原件也备份在本地。其余冻结历史文件不改字节，旧相对路径按来源提交／清单解释。check_phase_handoff改按T042对应提交核验初始切换，不再把后续合法42项规划误当“根账本被破坏”；证据定位只接受明确归档或迁移位置，所有原摘要检查保留。H及阶段归档不改。

## 实际检查

- 归档346/346字节摘要一致；一次真实离线单文件缺失恢复后内容一致，未改原用户文件。
- 新定位边界4项测试通过；受影响回归78项通过（计划审核台账、固定C登记、审核输入／整单元、目录包），合计82项；均离线／合成，不是模型质量成绩。
- 88项历史完成提交／验证／证据及H、旧台账／回执摘要重新核验通过。初检查发现此前本地材料被嵌套迁到phase-1/phase-1-t034/等位置，按相同SHA精确登记805个别名后通过，没有放宽比较或改原封印。
- 课程签核清单核验HUMAN_APPROVED；42项活动任务仍todo且字节保持；目录默认和无Provider授权不变。
- Ruff、工作流、现行入口本地链接／归档锚点、Git差异及暂存检查；未重跑全部质量、性能、渲染或真实Provider验收。

用户已有phase-1-plan-p01-retest-r01/results/README.md编辑及docs/reference/openmaic/head-insertion-20261019/未跟踪目录保持原样、不混入提交。纯历史冻结执行器不作为当前入口，也不能以“恢复材料”恢复旧预算／继续模型试错。
