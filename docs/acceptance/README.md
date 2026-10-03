# 验收报告与本地材料

当前交付是 PRD §0 / ADR-0007 的课程目录版。T033 保持 `blocked`，动态生成、重解释和实时 AI 暂缓；累计 Provider 请求仍为 **2033/2500**。整理不改变旧成绩、协议、阈值或付费授权。

## Git 中保留

- [目录版退出报告](mvp-0.3-catalog-exit-20261003.md)、[工程验收](mvp-0.3-catalog-engineering-20261003.md)、[实际签核验证](mvp-0.3-catalog-signed-handoff-20261003.md)及[Lee 原始批准](mvp-0.3-catalog-human-signoff-20261003.json)。批准 JSON 原样保留，是课程 approval/allowlist 的受信依据。
- [已提交版本安装/构建/运行验证](mvp-0.3-clean-checkout-20261003.md)、[合并前审查](mvp-0.3-pr-review-20261003.md)。本地自查不替代 GitHub 独立批准。
- [验收口径](mvp-0.3-acceptance-plan.md)、[插入模板](mvp-0.3-t006-insertion.md)、[删除模板](mvp-0.3-t007-deletion.md)、[容器恢复](mvp-0.3-t031-compose-recovery.md)、[动画性能](mvp-0.3-t032-animation-performance.md)。两个模板报告仍是注册表引用的批准证据。
- [MVP 0.2 收尾决定](mvp-0.2-closeout-decision.md)、[闭环](mvp-0.2-closed-loop.md)、[质量](mvp-0.2-resource-quality.md)、[MVP 0.1 历史报告](mvp-0.1-provider-acceptance.md)。不同模型/配置的成绩不拼接。

## 原始材料的位置

2026-10-03 整理前快照为 `2537e4ccffd1f986e0aa4408a744bf8bcde7407e`。254 个原验收文件均先逐字节备份、校验 SHA-256；其中15份报告/签核保留，239份移出验收目录。239份中14个工具及4份原样夹具因回归测试依赖保留在下述工程目录，其余221份只保存在本地材料。另保存先前已独立归档的169份 T033 失败/诊断证据。

维护者本地位置为仓库根目录 `local-materials/acceptance-20261003/`：`snapshot/`、`t033-evidence/` 均沿用原仓库相对路径，`manifest.json` 记录来源、哈希和新位置。该目录被 Git 忽略，不随 PR 或拉取分发；报告中的“本地材料”是档案标识，不是当前 checkout 的文件链接。其他贡献者可运行当前离线回归，复核课程签核与报告结论；详细历史材料需维护者另行提供，或从已有 Git 提交恢复到本地。

已跟踪历史文件可用 `git show 2537e4ccffd1f986e0aa4408a744bf8bcde7407e:docs/acceptance/<文件名>` 读取。此整理仅精简当前文件树，旧提交历史保留；未重写历史。T033 未上传的证据仍在本地归档提交 `588f5dc90680ab551b70f13c5f8a77c8cece6b60`，其代码归档为 `29d5bf5e17975d57865cea5afa9b176dafe84382`，两者都未合入 PR。

## 回归与历史执行器

离线回归依赖保留在 `scripts/acceptance_support/`、`backend/tests/fixtures/acceptance/`、`web/tests/fixtures/`；只调整路径，不删断言，不把失败夹具换成成功样本。课程审阅 HTML 今后由 `scripts/prepare_catalog_review.py` 生成到 `local-materials/`，不写入验收目录。

`task.json`、`docs/tasks/` 和 `process.txt` 的历史证据路径仍按当时快照解释，不回填历史。`verify_catalog_exit.py`、`verify_catalog_acceptance.py` 及旧冻结/运行脚本依赖历史协议、源文件哈希和原工作树，不能作为当前干净 checkout 的入口；需要复核时恢复准确历史源码与材料，不能改哈希强行通过。当前入口是 `scripts/check_catalog_workflow.py`、`scripts/verify_catalog_release.py` 和后端/前端离线回归。保留工具不意味着授权运行 Provider、重跑基准或自动推进阶段。

## 整理后的离线核验（2026-10-03）

后端完整离线回归 **548 passed、177 skipped**，前端 **136 passed**；Ruff（后端 app/tests 及迁移工具）、课程签核和任务依赖检查通过。后端执行器移除 Provider/数据库配置并阻断外部连接；未启用数据库/Docker的跳过项不计为通过。生产代码、迁移、签核内容、锁文件、`task.json` 和原批准 JSON 不变，沿用已验证的构建与实际数据库/浏览器证据，未重新运行它们。

254 个验收原件和169份 T033 原证据逐文件哈希一致；4份回归 JSON 字节不变，14个工具的 AST 除导入排序外不变，74个当前验收文档链接可解析。440份本地原件（包含被修改的外部文档/测试原件）全数校验通过。验收目录由约2.57MB减至约74KB（15份报告/签核＋本索引），不含移至测试目录的依赖。

检查命令及完整输出只存于本地材料的 `checks/`，包括首次 Ruff 导入分类失败、文件计数发现旧字节码缓存的失败及后续修正结果；没有把失败改为通过。工具导入排序由独立 Ruff 配置固定，无检查逻辑或断言变更。Provider请求 **0**，累计 **2033/2500**，T033仍 `blocked`。已有 PR #4 等待其他账号批准，未管理员绕过或合并；此推送需要审核新的 HEAD。
