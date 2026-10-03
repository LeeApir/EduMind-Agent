# 原工作区清理与 T033 恢复核验

已完成用户授权的两项清理：原 `docs/acceptance` 从418个非缓存文件降为main上的16个必要报告/签核/索引；T033实验及证据确认可恢复后移出原工作区。PR #4已合并，远端main为 `a836ab41a1bf8c8bb1a47915a3c8b5a3955b43d3`。当前功能分支 `codex/mvp-0.3` 已快进到该版本，随后仅增加本轮维护记录与归档核验入口，不在main提交。

## 实际恢复与保留材料

代码归档 `29d5bf5e17975d57865cea5afa9b176dafe84382` 包含64个实验文件；证据归档 `588f5dc90680ab551b70f13c5f8a77c8cece6b60` 包含169份证据且以代码归档为父提交，两分支都仍只在本地。

本轮使用 `git archive` 导出证据归档提交的完整历史树，实际解包783个文件并逐文件对比Git blob；旧清单覆盖的236个原件全部SHA-256一致，包括已交付修复。未导入或运行实验代码，没有将实验提交合入当前分支。恢复目录为仓库根目录 `local-materials/worktree-cleanup-20261003/recovery-checkout/`，独立tar为同目录下的 `t033-recovery.tar`；校验、SHA和清理结果分别保存在 `restore-verification.json`、`cleanup-result.json`。tar不包含真实env、忽略文件或生成媒体。

删除前另将原验收目录全部418个非缓存文件按原路径保存到 `local-materials/worktree-cleanup-20261003/old-acceptance/` 并核对SHA；先前的 `local-materials/acceptance-20261003/` 与两条本地归档分支也保留。所有本地材料都被Git忽略。

## 原工作区改动

- 12个已跟踪实验覆盖文件仅在验证归档后还原到已提交交付版本，包括混合过通用修复的审核代码；通用修复没有丢失。
- 只删除清单内且hash一致的52个未跟踪实验文件、169份未跟踪证据，没有使用批量Git clean或破坏性reset。
- 随后当前功能分支快进已合并main，由已审查的提交移除旧的已跟踪验收副本并迁移测试依赖。验收目录保留必要16文件，废弃字节码缓存单独移除。
- 真实环境配置和媒体保持原样，task.json与main一致，仍45 done / 1 blocked；T033状态、旧指标和累计2033/2500均不变。

旧清单中的“原路径保留”字段和旧日志描述的是当时冻结状态，本轮不回写它们。之后历史核验应对归档或准确恢复树进行，不能要求当前交付树继续保留已退役实验。

## 只读核验入口

```bash
# 核对本地归档ref、所有实验/证据blob、已交付修复和任务状态；不依赖旧原件
python3 scripts/verify_legacy_archives.py
# 额外核对已实际解包的全部236原件；缺失/损坏立即失败，不回退到Git蒙混通过
python3 scripts/verify_legacy_archives.py --restored-root local-materials/worktree-cleanup-20261003/recovery-checkout
python3 scripts/check_catalog_workflow.py
python3 scripts/verify_catalog_release.py
cd backend
.venv/bin/python -m pytest -q tests/test_legacy_archives.py
```

原工作树严格逐字节核验仍可显式选 `--check-worktree`，清理后的交付目录不应选它。默认归档核验没有改变旧哈希或评分：来源改为保存的Git对象，并额外核对已提交修复的原始摘要。工具不调用Provider、执行历史诊断或恢复任何付费授权。

实际归档与恢复目录检查均为236原件通过；5个离线回归通过，覆盖原件删除后可查归档、blob损坏、ref错误、恢复文件损坏和恢复文件缺失。Ruff、工作流与实际课程签核检查通过。执行命令/输出及执行器只存本地 `checks/`。第一次从历史快照调用核验脚本因该提交尚未包含该脚本而退出2，单独记录；没有修改历史恢复树或把失败改成通过。

Provider请求0；未重跑模型诊断、生成、数据库、浏览器、动画/性能矩阵或正式基准。本轮仅本地维护提交，不push、不进行新的PR合并、部署或跨阶段。
