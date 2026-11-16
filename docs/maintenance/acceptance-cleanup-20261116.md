# T102 退役资料清理 · PHASE-2-T002

用户在只读盘点后明确要求「清理」。本次只处理第一批九个 T102 过程包、确认专属的消费者、可重建缓存和导航；不清理其余退役候选，不实施课程重设计。

## 实际变化

- 57 个验收文件从当前树退役；对应九个目录见[逐文件清单](acceptance-retirement-t102-20261116.json)。包含旧探索、条款采用、准备、隔离/监督 Mock、压力和参考预览，来源提交及摘要完整保留。
- 同批退役 8 个专属生成/检查脚本和 `scripts/tests/test_p15_manual_probe_draft.py`；该测试只服务于被退役的手工探测草案。共66文件、8,665,590字节。不是删除共享模块的失败测试以过关。
- 保留引用预览 `build()` 和 `test_p15_reference_artifact_v1.py` 全部断言；关闭旧命令生成 T102 页面，以免重建已退役目录。
- 删除未跟踪的5个 `.DS_Store` 和6个 `.pyc`；空缓存目录移除。保留 .gitignore 的既有规则。
- 更新 acceptance/README 的当前阶段与入口；ARCHIVE 增加本批，既有32包清单不变。恢复工具只增加选取清单和只读检查Git来源，复用原按需恢复逻辑。

## 保留边界

T102最终重设计与独立失败记录、Phase 1.5只读账本、原任务状态、共享代码/轨迹/判卷、现存课程和原件均保留。T104/T107等依赖的 `p15_minimal_contract`、`p15_teaching_revision`、`p15_pilot_wire`、`p15_head_insertion_engine` 不改。用户未提交的 P1 README、provider问题文档删除及参考目录不动。

旧冻结资料引用已退役文件时，按 ARCHIVE 的原提交和逐文件清单恢复；不改旧冻结字节或追认成绩。源码与历史正文按各自版本核对。

## 必要验证

实际命令和结果在完成时追加。只核对来源/恢复、受影响的共享测试、剩余导入与路径、保留文件摘要、导航和账本。不运行旧模拟生成器、Provider、数据库或播放器全集。

### 实际结果

- `python3 scripts/manage_acceptance_archive.py check-source --index docs/maintenance/acceptance-retirement-t102-20261116.json`：66个来源文件摘要均通过。
- 同工具 `restore` 与 `check` 加 `--path docs/acceptance/phase-1.5-manual-bc-offline-t102/BLOCKED.md`：单文件恢复及核验通过，只写入忽略的本地档案，未运行旧脚本。
- `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q scripts/tests/test_p15_reference_artifact_v1.py scripts/tests/test_archive_paths.py --tb=short`：9 passed，全部原断言保留。
- `python3 /tmp/edumind-cleanup-t002/verify.py`：66个退役路径不存在；保留共享模块、最终失败记录、Phase 1.5归档及用户报告摘要不变；跟踪源码内无退役目录/专属模块的字面量残留；导航链接有效；T001逐值未改。
- `python3 scripts/check_catalog_workflow.py`、`git diff --check`：通过。

目录磁盘占用约56 MiB降至48 MiB；Git历史仍保留，不宣称Git对象库缩小。旧冻结索引按原提交解释；本次静态检查不声称证明任意动态加载路径。新模型调用、数据库写入及部署均0。其余候选未删除。

后续：如继续退役其他包，沿用同一恢复工具与清单格式，逐组确认消费者；本次不自动扩展范围或领取重设计。仅本地提交，不推送、不合并。
