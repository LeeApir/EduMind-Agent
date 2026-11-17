# 验收材料保留清单与开发入口 · T003 / T004

T003盘点基线：`a4629602933d3966d479008a6208a6bc07640248`，2026-11-16；当时为214个目录、22个非缓存顶层文件。

**T004已执行本轮清理：移除60目录、15顶层文档和61个专属脚本/测试；当前为154目录、7个非缓存顶层文件，共161项。** 434个退役文件（3,676,975字节）来自准确提交 `787436a2c3a1b7806dada148c702374f771f536e`，见[逐文件恢复清单](acceptance-retirement-trials-20261116.json)。现存材料仍有共享依赖，不等于161项都需要日常阅读或永久维护。Finder缓存不计入。

## 清理前分类与本轮处置

不需要把这236项作为后续开发的阅读或维护任务。真正需要继承的是产品边界、可复用能力、少量代表性课程和失败教训；其余旧批次停止维护。物理文件是否能删，还要与当前消费者一起处理。

此前“149个退役候选、65个保留/保护”的划分偏粗：其中另有23个目录被后端测试或基础证据回归引用，本次单列，不能连有效回归一起删掉。126个候选经消费者核对后，60个已退役，66个因共享代码、回归或保留材料引用暂留。复杂依赖本轮不重构，不再另开逐包清理任务。

| 处置 | 目录数 | 后续责任 |
| --- | ---: | --- |
| A 当前导入或准入直接依赖 | 17 | 保持准确路径和字节；涉及开发专用导入，不表示所有页面每次都读取。 |
| B 共享代码或冻结依赖，暂留 | 29 | 保持兼容；冻结清单引用不等于实际运行必读，不为清理单独重构。 |
| C 关键交接、契约与基础夹具 | 18 | 关键结论按需阅读，基础夹具随相关缺陷使用；不恢复旧试验。 |
| D 用户未提交改动，保护 | 1 | 本次不处置。 |
| E 回归引用，先保留必要夹具 | 23 | 保留缺陷断言和必要输入；将来整理消费者时才提取最小夹具，其他历史文件可退役。 |
| F 旧试验退役候选 | 126 | 停止日常维护；后续与专属运行、校验脚本及仅验证旧批次的测试一起退役。 |

以上88个保留/暂留/保护目录也不是永久保留整包的要求。目标是减少依赖和阅读负担，不以目录数量作为开发验收指标。

## 后续开发只从这些入口开始

1. [根账本](../../task.json) 和当前任务：确定允许做什么；不扫描历史账本领取任务。
2. [PRD](../PRD.md) §0.5/§9.1、[ADR0056](../ADR/0056-phase-2-learning-ui-and-phase-3-consolidation.md)、[ADR0066](../ADR/0066-phase-1.5-contracted-closeout.md)：确认当前范围、设计方向和未通过的门槛。
3. [课程方向](../phase-1.5-course-generation-direction.md) §3/§5.4：复用共享材料、收敛准备与验证。旧任务步骤按当时背景解释。
4. [验收入口](../acceptance/README.md)：只在核对已有能力、阶段限制或某项来源时进入对应结果，不要求通读236项。

重设计按需看四份代表材料即可：[四主题共用流程](../acceptance/phase-1.5-shared-live-reuse-t127/RESULTS.md)、[程序派生二分帧](../acceptance/phase-1.5-binary-search-program-frames-t130/RESULTS.md)、[栈多场景](../acceptance/phase-1.5-stack-boundaries-t138/RESULTS.md)、[画像最终对照](../acceptance/phase-1.5-stack-profile-pair-t132/RESULTS.md)。它们说明能力和局限，不要求沿用当前课程的界面、动画或习题设计。

## 必须保住的能力及已确认的耦合

- 课程私有版本、来源绑定、服务端判卷、答案隔离、刷新恢复和播放器：保留实现及相关回归，不能以旧文档多为由一起删掉。
- `head_course_replay.mapping()`读取T107清单、逐文件核对并动态加载`prepare_mapping.py`；后者读取T106材料、动态加载T104的`prepare.py`。T104又导入`p15_minimal_contract`、`p15_teaching_revision`、`p15_pilot_wire`和`p15_head_insertion_engine`。因此不能直接删除整个`isolated_diagnostics`或所有T104以前材料。
- `head_course_archived_import.py`使用动态BATCH路径读取r05封存材料；`course_trial_publication.py`按主题配置定位固定材料。应保留当前课程可恢复性，不把旧模型失败当作删除已交付课程依据。
- `test_review_input.py`读取`phase-1-coverage-r04/cases.json`；共享规划测试读取`phase-1-om-redesign/contract-examples.json`；计划持久化测试读取`phase-1-plan-correction-proposal-r01/synthetic-record.json`；调度测试核对生成契约`policy.json`。这些是明确的夹具依赖，不是单纯历史报告引用。
- `run_p15_candidate_compatibility.py`的`bounded_resolver`仍被多个旧入口以顶层模块名导入。该目录列为退役候选不意味着脚本可单独删除；共享函数保留或随整条已停路线一起处置。

## 清理时的最小边界

- 原件、失败/未知/STOP、任务归档和批准记录不得改写结论。退役资料通过准确Git来源和现有恢复工具保留，不在工作区另复制一套全量档案。
- H01–H08继续封存，本次只看路径和引用，未读取样本正文；本机私有原件库、密钥、数据库和生成媒体不在此清单范围。
- 历史文档互相引用，本身不构成永久保留理由；真正被代码读取或校验摘要的文件需要保留或明确迁移。
- 旧试验的专属检查器可随试验退役；仍服务于共享引擎、安全、版本、判卷、持久化的回归不按文件名批量删除。
- 后续清理一次处理确认的范围，复杂共享依赖先留；不把清理拆成逐包审批、逐包复测或新的长期框架。只验证改变的引用/导入、恢复索引和确实受影响的回归。
- 当前T001仍是待讨论的设计任务。无需先清空所有历史包才能讨论或实施获准的新设计。

## 逐目录清单（保留清理前路径，标明实际处置）

依据来自当前跟踪源码的目录字面量、Python绝对导入及保留清单引用，并人工核对上述关键动态路径。不是完整运行时依赖证明；未运行历史脚本、模型、数据库或浏览器。E类列出测试引用，不声称这些测试全部需要永久保留。表中引用取代表入口，其余消费者仍须随实际删除范围核对。

### A 当前导入或准入直接依赖（17）

| 目录 | 用途或定位依据 |
| --- | --- |
| [phase-1.5-binary-search-program-frames-t130](../acceptance/phase-1.5-binary-search-program-frames-t130/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-binary-search-t122](../acceptance/phase-1.5-binary-search-t122/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-head-aiapi-content-r01](../acceptance/phase-1.5-head-aiapi-content-r01/) | backend/app/services/head_course_aiapi_content.py；backend/app/services/head_course_archived_import.py |
| [phase-1.5-head-b-local-revision-r01](../acceptance/phase-1.5-head-b-local-revision-r01/) | backend/app/services/head_course_evidence_revision.py |
| [phase-1.5-head-empty-citation-revision-r01](../acceptance/phase-1.5-head-empty-citation-revision-r01/) | backend/app/services/head_course_citation_revision.py |
| [phase-1.5-head-evidence-t110](../acceptance/phase-1.5-head-evidence-t110/) | backend/app/services/head_course_evidence_revision.py |
| [phase-1.5-head-fact-live-r01](../acceptance/phase-1.5-head-fact-live-r01/) | backend/app/services/head_course_fact_publication.py |
| [phase-1.5-head-fixed-live-r01](../acceptance/phase-1.5-head-fixed-live-r01/) | backend/app/services/head_course_archived_import.py |
| [phase-1.5-head-goal-r03-recovery](../acceptance/phase-1.5-head-goal-r03-recovery/) | backend/app/services/head_course_derivation.py |
| [phase-1.5-head-replay-t107](../acceptance/phase-1.5-head-replay-t107/) | backend/app/services/head_course_replay.py |
| [phase-1.5-head-reuse-live-r01](../acceptance/phase-1.5-head-reuse-live-r01/) | backend/app/services/head_course_evidence_revision.py |
| [phase-1.5-queue-fifo-t121](../acceptance/phase-1.5-queue-fifo-t121/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-shared-first-draft-t125](../acceptance/phase-1.5-shared-first-draft-t125/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-shared-live-reuse-t127](../acceptance/phase-1.5-shared-live-reuse-t127/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-shared-revision-t126](../acceptance/phase-1.5-shared-revision-t126/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-stack-lifo-t119](../acceptance/phase-1.5-stack-lifo-t119/) | backend/app/services/course_trial_publication.py |
| [phase-1.5-stack-profile-pair-t132](../acceptance/phase-1.5-stack-profile-pair-t132/) | backend/app/services/course_trial_publication.py |

### B 共享代码或冻结依赖，暂留（29）

| 目录 | 用途或定位依据 |
| --- | --- |
| [phase-1.5-agent-pilot](../acceptance/phase-1.5-agent-pilot/) | 清单/导入：docs/acceptance/phase-1.5-minimal-output-contract-r01/manifest.json |
| [phase-1.5-development-diagnostic-r01](../acceptance/phase-1.5-development-diagnostic-r01/) | 清单/导入：docs/acceptance/phase-1.5-development-diagnostic-r02/manifest.json |
| [phase-1.5-development-diagnostic-r02](../acceptance/phase-1.5-development-diagnostic-r02/) | 清单/导入：docs/acceptance/phase-1.5-development-diagnostic-r03/manifest.json |
| [phase-1.5-development-diagnostic-r03](../acceptance/phase-1.5-development-diagnostic-r03/) | 清单/导入：docs/acceptance/phase-1.5-split-exploration-r01/manifest.json |
| [phase-1.5-development-diagnostic-results-r02](../acceptance/phase-1.5-development-diagnostic-results-r02/) | 清单/导入：docs/acceptance/phase-1.5-development-diagnostic-r03/manifest.json |
| [phase-1.5-fixed-provider-t113](../acceptance/phase-1.5-fixed-provider-t113/) | 清单/导入：docs/acceptance/phase-1.5-head-deepseek-t114/manifest.json |
| [phase-1.5-head-deepseek-t114](../acceptance/phase-1.5-head-deepseek-t114/) | 清单/导入：scripts/head_course_goal.py |
| [phase-1.5-head-empty-t118](../acceptance/phase-1.5-head-empty-t118/) | 清单/导入：docs/acceptance/phase-1.5-binary-search-program-frames-t130/manifest.json |
| [phase-1.5-head-empty-t118-r02](../acceptance/phase-1.5-head-empty-t118-r02/) | 清单/导入：docs/acceptance/phase-1.5-head-empty-citation-revision-r01/manifest.json |
| [phase-1.5-head-fixed-aiapi-r04](../acceptance/phase-1.5-head-fixed-aiapi-r04/) | 清单/导入：docs/acceptance/phase-1.5-head-aiapi-content-r01/manifest.json |
| [phase-1.5-head-fixed-aiapi-r05](../acceptance/phase-1.5-head-fixed-aiapi-r05/) | 清单/导入：backend/app/services/head_course_archived_import.py: BATCH dynamic path |
| [phase-1.5-head-fixed-continuation-r02](../acceptance/phase-1.5-head-fixed-continuation-r02/) | 清单/导入：scripts/head_course_fixed_continuation.py |
| [phase-1.5-head-fixed-t111](../acceptance/phase-1.5-head-fixed-t111/) | 清单/导入：docs/acceptance/phase-1.5-head-aiapi-content-r01/manifest.json |
| [phase-1.5-head-goal-live-r01](../acceptance/phase-1.5-head-goal-live-r01/) | 清单/导入：docs/acceptance/phase-1.5-head-goal-t108-r02/manifest.json |
| [phase-1.5-head-goal-live-r02](../acceptance/phase-1.5-head-goal-live-r02/) | 清单/导入：docs/acceptance/phase-1.5-head-goal-t108-r03/manifest.json |
| [phase-1.5-head-goal-t108](../acceptance/phase-1.5-head-goal-t108/) | 清单/导入：docs/acceptance/phase-1.5-head-b-local-revision-r01/manifest.json |
| [phase-1.5-head-goal-t108-r02](../acceptance/phase-1.5-head-goal-t108-r02/) | 清单/导入：docs/acceptance/phase-1.5-head-goal-t108-r03/manifest.json |
| [phase-1.5-head-goal-t108-r03](../acceptance/phase-1.5-head-goal-t108-r03/) | 清单/导入：scripts/head_course_goal.py |
| [phase-1.5-head-reuse-t109](../acceptance/phase-1.5-head-reuse-t109/) | 清单/导入：scripts/head_course_goal.py |
| [phase-1.5-limited-c-live-r01](../acceptance/phase-1.5-limited-c-live-r01/) | 清单/导入：docs/acceptance/phase-1.5-head-replay-t107/manifest.json |
| [phase-1.5-limited-c-preparation-t104](../acceptance/phase-1.5-limited-c-preparation-t104/) | 清单/导入：docs/acceptance/phase-1.5-binary-search-program-frames-t130/manifest.json |
| [phase-1.5-minimal-output-contract-r01](../acceptance/phase-1.5-minimal-output-contract-r01/) | 清单/导入：docs/acceptance/phase-1.5-binary-search-program-frames-t130/manifest.json |
| [phase-1.5-schema-compatibility](../acceptance/phase-1.5-schema-compatibility/) | 清单/导入：docs/acceptance/phase-1.5-minimal-output-contract-r01/manifest.json |
| [phase-1.5-sol-compatibility-plan-r01](../acceptance/phase-1.5-sol-compatibility-plan-r01/) | 清单/导入：docs/acceptance/phase-1.5-agent-pilot/execution-p01/candidate-manifest.json |
| [phase-1.5-split-exploration-r01](../acceptance/phase-1.5-split-exploration-r01/) | 清单/导入：docs/acceptance/phase-1.5-split-exploration-r02/manifest.json |
| [phase-1.5-split-exploration-r02](../acceptance/phase-1.5-split-exploration-r02/) | 清单/导入：docs/acceptance/phase-1.5-sol-compatibility-plan-r01/manifest.json |
| [phase-1.5-split-provider-design-r01](../acceptance/phase-1.5-split-provider-design-r01/) | 清单/导入：docs/acceptance/phase-1.5-sol-compatibility-plan-r01/manifest.json |
| [phase-1.5-split-provider-implementation-r01](../acceptance/phase-1.5-split-provider-implementation-r01/) | 清单/导入：docs/acceptance/phase-1.5-split-exploration-r01/manifest.json |
| [phase-1.5-stack-boundaries-t138](../acceptance/phase-1.5-stack-boundaries-t138/) | 清单/导入：scripts/stack_multiscene_trial.py |

### C 关键交接、契约与基础夹具（18）

| 目录 | 用途或定位依据 |
| --- | --- |
| [offline-c-fixtures](../acceptance/offline-c-fixtures/) | 关键交接/契约/代表材料；消费者：scripts/offline_c_fixtures.py |
| [offline-c-ownership-fixtures](../acceptance/offline-c-ownership-fixtures/) | 关键交接/契约/代表材料；消费者：scripts/offline_c_ownership.py |
| [offline-c-toolchain-t068](../acceptance/offline-c-toolchain-t068/) | 关键交接/契约/代表材料；消费者：scripts/offline_c_runner.py |
| [phase-1-closeout-20261021](../acceptance/phase-1-closeout-20261021/) | 关键交接/契约/代表材料；消费者：scripts/check_phase_handoff.py |
| [phase-1-holdout-reserve-r01](../acceptance/phase-1-holdout-reserve-r01/) | 关键交接/契约/代表材料；消费者：scripts/check_holdout_reserve.py |
| [phase-1.5-acceptance-contract-r01](../acceptance/phase-1.5-acceptance-contract-r01/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-archived-head-import-t117](../acceptance/phase-1.5-archived-head-import-t117/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-browser-t036](../acceptance/phase-1.5-browser-t036/) | 关键交接/契约/代表材料；消费者：scripts/check_p15_free_course_browser.py |
| [phase-1.5-compatibility-t021](../acceptance/phase-1.5-compatibility-t021/) | 关键交接/契约/代表材料；消费者：scripts/check_p15_free_course_integration.py |
| [phase-1.5-course-contract-r01](../acceptance/phase-1.5-course-contract-r01/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-course-trial-replay-t120](../acceptance/phase-1.5-course-trial-replay-t120/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-d02-formal-d03](../acceptance/phase-1.5-d02-formal-d03/) | 关键交接/契约/代表材料；消费者：backend/tests/test_p15_d02_formal_d03.py |
| [phase-1.5-generation-contract-r01](../acceptance/phase-1.5-generation-contract-r01/) | 关键交接/契约/代表材料；消费者：backend/tests/test_free_course_scheduler.py |
| [phase-1.5-integration-t035](../acceptance/phase-1.5-integration-t035/) | 关键交接/契约/代表材料；消费者：scripts/check_p15_free_course_integration.py |
| [phase-1.5-manual-bc-redesign-t102](../acceptance/phase-1.5-manual-bc-redesign-t102/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-quality-contract-r01](../acceptance/phase-1.5-quality-contract-r01/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-real-course-independent-t099](../acceptance/phase-1.5-real-course-independent-t099/) | 关键交接/契约/代表材料；供历史范围与结论查询 |
| [phase-1.5-t038-gap-review-t123](../acceptance/phase-1.5-t038-gap-review-t123/) | 关键交接/契约/代表材料；供历史范围与结论查询 |

### D 用户未提交改动，保护（1）

| 目录 | 用途或定位依据 |
| --- | --- |
| [phase-1-plan-p01-retest-r01](../acceptance/phase-1-plan-p01-retest-r01/) | 用户已有未提交README；排除清理 |

### E 回归引用，先保留必要夹具（23）

| 目录 | 用途或定位依据 |
| --- | --- |
| [offline-c-t068](../acceptance/offline-c-t068/) | scripts/tests/test_offline_c_evidence.py |
| [phase-1-coverage-r04](../acceptance/phase-1-coverage-r04/) | backend/tests/test_review_input.py |
| [phase-1-deepseek-connection-v1](../acceptance/phase-1-deepseek-connection-v1/) | backend/tests/test_t040_derived_run.py；backend/tests/test_t040_diagnostic_runner.py |
| [phase-1-dsl-v1](../acceptance/phase-1-dsl-v1/) | backend/tests/dsl_acceptance_matrix.py |
| [phase-1-dynamic-v1](../acceptance/phase-1-dynamic-v1/) | backend/tests/test_t040_diagnostic_preparation.py |
| [phase-1-five-hour-remaining-six-r01](../acceptance/phase-1-five-hour-remaining-six-r01/) | backend/tests/test_a01_process_generation.py；backend/tests/test_a02_program_context.py |
| [phase-1-five-hour-test-plan-r01](../acceptance/phase-1-five-hour-test-plan-r01/) | backend/tests/test_a01_process_generation.py |
| [phase-1-om-admission-r02](../acceptance/phase-1-om-admission-r02/) | backend/tests/test_hybrid_review_check_ids.py |
| [phase-1-om-redesign](../acceptance/phase-1-om-redesign/) | backend/tests/test_learning_plan_persistence.py；backend/tests/test_shared_learning_plan.py |
| [phase-1-plan-correction-proposal-r01](../acceptance/phase-1-plan-correction-proposal-r01/) | backend/tests/test_plan_check_persistence.py |
| [phase-1-queue-v1](../acceptance/phase-1-queue-v1/) | backend/tests/queue_acceptance_matrix.py；backend/tests/queue_fault_matrix.py |
| [phase-1-review-remaining-r01](../acceptance/phase-1-review-remaining-r01/) | backend/tests/test_learning_review_cases.py；backend/tests/test_review_evidence_v45.py |
| [phase-1-t040-deepseek-high-v1](../acceptance/phase-1-t040-deepseek-high-v1/) | backend/tests/test_review_indexing.py |
| [phase-1-t040-deepseek-v1](../acceptance/phase-1-t040-deepseek-v1/) | backend/tests/test_review_failure_paths.py |
| [phase-1-t040-deepseek-v2](../acceptance/phase-1-t040-deepseek-v2/) | backend/tests/test_deepseek_reasoning.py；backend/tests/test_review_failure_paths.py |
| [phase-1-t040-derived-calibration-r09](../acceptance/phase-1-t040-derived-calibration-r09/) | backend/tests/test_fixed_focus.py |
| [phase-1-t040-focus-r10](../acceptance/phase-1-t040-focus-r10/) | backend/tests/test_final_focus.py |
| [phase-1-t040-review-coverage-check](../acceptance/phase-1-t040-review-coverage-check/) | backend/tests/test_t040_derived_run.py |
| [phase-1-t040-review-scope-check](../acceptance/phase-1-t040-review-scope-check/) | backend/tests/test_review_scope.py |
| [phase-1-t040-review-scope-low](../acceptance/phase-1-t040-review-scope-low/) | backend/tests/test_review_scope.py |
| [phase-1.5-binary-search-frames-t129](../acceptance/phase-1.5-binary-search-frames-t129/) | backend/tests/test_binary_search_program_frames_trial.py |
| [phase-1.5-d02-recheck-d01](../acceptance/phase-1.5-d02-recheck-d01/) | backend/tests/test_p15_d02_recheck_d01.py |
| [phase-1.5-d02-recheck-d02](../acceptance/phase-1.5-d02-recheck-d02/) | backend/tests/test_p15_d02_recheck_d02.py |

### F 原126个候选：60已退役，66因依赖暂留

| 目录 | 用途或定位依据 |
| --- | --- |
| [phase-1-coverage-r04-admission](../acceptance/phase-1-coverage-r04-admission/) | 暂留：scripts/acceptance_support/coverage_v44.py；scripts/prepare_coverage_admission.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-coverage-r05](../acceptance/phase-1-coverage-r05/) | 暂留：scripts/prepare_review_config_comparison.py；scripts/run_coverage_v44.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-defect-regression-r01](../acceptance/phase-1-defect-regression-r01/) | 暂留：scripts/prepare_defect_regression.py；scripts/prepare_plan_admission.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-distributed-budget-r01](../acceptance/phase-1-distributed-budget-r01/) | 暂留：scripts/prepare_review_suite.py；scripts/run_distributed_budget.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-distributed-diagnostic-r01](../acceptance/phase-1-distributed-diagnostic-r01/) | 暂留：scripts/prepare_distributed_budget.py；scripts/run_distributed_diagnostic.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-evidence-repair-proposal-r01](../acceptance/phase-1-evidence-repair-proposal-r01/) | 暂留：scripts/prepare_evidence_repair_proposal.py；scripts/tests/test_evidence_repair_proposal.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-evidence-v45-r01](../acceptance/phase-1-evidence-v45-r01/) | 暂留：scripts/prepare_review_model_candidate.py；scripts/prepare_review_replacement.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-five-hour-execution-r01](../acceptance/phase-1-five-hour-execution-r01/) | 暂留：scripts/run_five_hour_acceptance.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-fixed-c-design-r01](../acceptance/phase-1-fixed-c-design-r01/) | 暂留：scripts/offline_c_fixtures.py；scripts/tests/test_offline_c_fixture_manifest.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-generation-mini-r01](../acceptance/phase-1-generation-mini-r01/) | 暂留：scripts/run_generation_mini.py；scripts/tests/test_plan_repair_boundary.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-luna-process-calibration-r01](../acceptance/phase-1-luna-process-calibration-r01/) | 暂留：scripts/prepare_last_review_candidate.py；scripts/prepare_luna_process_calibration.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-luna-process-execution-r01](../acceptance/phase-1-luna-process-execution-r01/) | 暂留：scripts/prepare_last_review_candidate.py；scripts/run_luna_process_calibration.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-luna-schema-validation-r01](../acceptance/phase-1-luna-schema-validation-r01/) | 暂留：scripts/prepare_luna_process_calibration.py；scripts/prepare_luna_schema_validation.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-luna-v49-admission-r02](../acceptance/phase-1-luna-v49-admission-r02/) | 暂留：scripts/acceptance_support/luna_admission_gate.py；scripts/prepare_last_review_candidate.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-om-admission-r01](../acceptance/phase-1-om-admission-r01/) | 暂留：scripts/acceptance_support/om_diagnostic.py；scripts/prepare_om_admission_r02.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-om-admission-r03](../acceptance/phase-1-om-admission-r03/) | 暂留：scripts/acceptance_support/coverage_standard.py；scripts/prepare_coverage_review.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-om-implementation](../acceptance/phase-1-om-implementation/) | 暂留：scripts/acceptance_support/om_preparation.py；scripts/prepare_om_admission.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-plan-admission-authorization-r01](../acceptance/phase-1-plan-admission-authorization-r01/) | 暂留：scripts/run_plan_admission.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-plan-admission-execution-r01](../acceptance/phase-1-plan-admission-execution-r01/) | 暂留：scripts/run_plan_admission.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-plan-admission-execution-r02](../acceptance/phase-1-plan-admission-execution-r02/) | 暂留：scripts/run_plan_admission.py；scripts/run_plan_p01_retest.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-plan-admission-preparation-r01](../acceptance/phase-1-plan-admission-preparation-r01/) | 暂留：scripts/prepare_plan_admission.py；scripts/prepare_plan_boundary_batch.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-plan-admission-results-r02](../acceptance/phase-1-plan-admission-results-r02/) | 暂留：scripts/run_plan_p01_retest.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-plan-boundary-development-r01](../acceptance/phase-1-plan-boundary-development-r01/) | 暂留：scripts/prepare_plan_boundary_batch.py；scripts/run_plan_boundary_batch.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1-plan-gap-contract-audit` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1-plan-gap-location-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1-plan-semantic-boundary-r01](../acceptance/phase-1-plan-semantic-boundary-r01/) | 暂留：scripts/run_plan_boundary_batch.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-provider-connection-v1](../acceptance/phase-1-provider-connection-v1/) | 暂留：scripts/prepare_review_model_candidate.py；scripts/run_deepseek_connection.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-provider-selection](../acceptance/phase-1-provider-selection/) | 暂留：scripts/prepare_review_model_candidate.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-qwen-compatibility-r01](../acceptance/phase-1-qwen-compatibility-r01/) | 暂留：scripts/run_qwen_compatibility.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-qwen-continuation-r01](../acceptance/phase-1-qwen-continuation-r01/) | 暂留：scripts/run_qwen_continuation.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-qwen-http400-r01](../acceptance/phase-1-qwen-http400-r01/) | 暂留：scripts/diagnose_qwen_http400.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-qwen-http400-r02](../acceptance/phase-1-qwen-http400-r02/) | 暂留：scripts/diagnose_qwen_http400_r02.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-qwen-review-execution-r01](../acceptance/phase-1-qwen-review-execution-r01/) | 暂留：scripts/run_qwen_review.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-review-config-r01](../acceptance/phase-1-review-config-r01/) | 暂留：scripts/prepare_distributed_diagnostic.py；scripts/prepare_review_suite.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1-review-continuation-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1-review-evidence-v45](../acceptance/phase-1-review-evidence-v45/) | 暂留：scripts/prepare_evidence_v45.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-review-final-execution-r01](../acceptance/phase-1-review-final-execution-r01/) | 暂留：scripts/run_final_review_candidate.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-review-input-v1](../acceptance/phase-1-review-input-v1/) | 暂留：scripts/prepare_coverage_v44.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-review-last-candidate-r01](../acceptance/phase-1-review-last-candidate-r01/) | 暂留：scripts/prepare_last_review_candidate.py；scripts/run_final_review_candidate.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-review-model-candidate-r01](../acceptance/phase-1-review-model-candidate-r01/) | 暂留：scripts/prepare_review_model_candidate.py；scripts/run_qwen_review.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1-review-prerequisite-once-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1-review-replacement-r01](../acceptance/phase-1-review-replacement-r01/) | 暂留：scripts/prepare_review_model_candidate.py；scripts/run_review_replacement.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1-review-safety-retry-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1-review-stack-recurrence-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1-review-suite-r01](../acceptance/phase-1-review-suite-r01/) | 暂留：scripts/prepare_evidence_repair_proposal.py；scripts/run_review_suite.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-separated-diagnostics-r01](../acceptance/phase-1-separated-diagnostics-r01/) | 暂留：scripts/prepare_plan_admission.py；scripts/prepare_separated_diagnostics.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-t040-deepseek-high-v2](../acceptance/phase-1-t040-deepseek-high-v2/) | 暂留：scripts/t040_reasoning_check.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-t040-derived-calibration-draft](../acceptance/phase-1-t040-derived-calibration-draft/) | 暂留：scripts/prepare_t040_derived_calibration.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-t040-focus-r11](../acceptance/phase-1-t040-focus-r11/) | 暂留：scripts/acceptance_support/om_preparation.py；scripts/prepare_t040_final_focus.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-t040-reasoning-check](../acceptance/phase-1-t040-reasoning-check/) | 暂留：scripts/t040_high_diagnostics.py；scripts/t040_reasoning_check.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-t040-span-review-offline](../acceptance/phase-1-t040-span-review-offline/) | 暂留：scripts/prepare_t040_focus.py；scripts/prepare_t040_span_review.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1-v49-admission-r01](../acceptance/phase-1-v49-admission-r01/) | 暂留：scripts/prepare_v49_materials.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-aiapi-minimal-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-aiapi-review-probe-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-aiapi-s2-once` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-answer-contract-t061` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-archived-head-import-t112` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-bound-course-sample-t093](../acceptance/phase-1.5-bound-course-sample-t093/) | 暂留：scripts/isolated_diagnostics/generate_p15_bound_sample.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-bound-pilot-t092` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-candidate-compatibility-r01](../acceptance/phase-1.5-candidate-compatibility-r01/) | 暂留：scripts/run_p15_candidate_compatibility.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-combined-candidate-r01](../acceptance/phase-1.5-combined-candidate-r01/) | 暂留：scripts/isolated_diagnostics/generate_p15_reference_player.py；scripts/isolated_diagnostics/p15_single_course_review.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-compatibility-probe-p01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-compatibility-probe-p01-results` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-counter-probe-c01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-course-answers-t018` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-course-api-t020` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-course-evidence-t019` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-course-feedback-t017` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-course-recheck-r03](../acceptance/phase-1.5-course-recheck-r03/) | 暂留：scripts/run_p15_course_recheck_r03.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-course-recovery-t015` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-course-review-once-r01](../acceptance/phase-1.5-course-review-once-r01/) | 暂留：scripts/tests/test_p15_review_engineering.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-course-revision-t016` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-course-scheduler-t014` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-d02-scene2-review-once-p01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-data-model-t006` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-deepseek-flash-preparation` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-deepseek-flash-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-development-diagnostic-results-r03](../acceptance/phase-1.5-development-diagnostic-results-r03/) | 暂留：scripts/audit_p15_input_count.py；scripts/check_p15_r03_diagnostic_results.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-direct-relay-once-d01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-free-planning-t008` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-full-diagnostic-r04](../acceptance/phase-1.5-full-diagnostic-r04/) | 暂留：scripts/run_p15_full_diagnostic_r04.py；scripts/tests/test_p15_full_diagnostic_r04.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-full-diagnostic-r05](../acceptance/phase-1.5-full-diagnostic-r05/) | 暂留：scripts/run_p15_full_diagnostic_r05.py；scripts/tests/test_p15_full_diagnostic_r05.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-generation-semantics-t062` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-graph-links-t009` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-guarded-transport-t052` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-head-b-local-live-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-head-deepseek-diagnostic-t116` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-head-deepseek-live-r01](../acceptance/phase-1.5-head-deepseek-live-r01/) | 暂留：scripts/diagnose_head_course_t115.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-head-fact-revision-r01](../acceptance/phase-1.5-head-fact-revision-r01/) | 暂留：docs/acceptance/phase-1.5-head-fact-live-r01/check_results.py；scripts/head_course_fact_revision.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-head-fixed-repeat-r03](../acceptance/phase-1.5-head-fixed-repeat-r03/) | 暂留：scripts/head_course_fixed_aiapi.py；scripts/head_course_fixed_repeat.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-head-goal-live-r03](../acceptance/phase-1.5-head-goal-live-r03/) | 暂留：scripts/prepare_head_course_recovery.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-input-count-audit-t051](../acceptance/phase-1.5-input-count-audit-t051/) | 暂留：scripts/audit_p15_input_count.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-last-semantic-repair-t064` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-markdown-cleaning-t059` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-mastery-history-t048` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-minimal-live-r01](../acceptance/phase-1.5-minimal-live-r01/) | 暂留：scripts/run_p15_minimal_probe.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-minimal-output-adapter-r01](../acceptance/phase-1.5-minimal-output-adapter-r01/) | 暂留：scripts/run_p15_minimal_probe.py；scripts/tests/test_p15_clean_pilot_prompts.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-observability-answer-plan-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-pilot-candidate-cleanup-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-planning-objectives-t065` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-profile-create-t049` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-provider-handoff-t055` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-question-stem-t124` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-r0-once-r01](../acceptance/phase-1.5-r0-once-r01/) | 暂留：scripts/run_p15_combined_candidate.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-real-candidate-player-t098](../acceptance/phase-1.5-real-candidate-player-t098/) | 暂留：scripts/isolated_diagnostics/generate_p15_reference_player.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-record-index-t047` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-record-read-contract-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-relay-regression-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-relay-regression-r01-results` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-review-engineering-t097` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-review-observability-t060` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-review-view-contract-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-scene-actions-t012` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-scene-availability-t013` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-scene-consistency-t063` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-scene-form-contract-t058` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-scene-generation-t010` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-scene-validation-t011` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-separated-protocol-repair-r01](../acceptance/phase-1.5-separated-protocol-repair-r01/) | 暂留：scripts/isolated_diagnostics/p15_separated_probe_contract.py；scripts/tests/test_p15_protocol_task_separation.py。停止旧试验，相关消费者替换时再处理。 |
| [phase-1.5-separated-validation-r01](../acceptance/phase-1.5-separated-validation-r01/) | 暂留：scripts/isolated_diagnostics/p15_r0_once_contract.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-snapshot-repository-t007` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-sol-compatibility-once-p01](../acceptance/phase-1.5-sol-compatibility-once-p01/) | 暂留：scripts/run_p15_sol_compatibility_once.py。停止旧试验，相关消费者替换时再处理。 |
| `phase-1.5-teaching-frozen-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-teaching-revision-t100` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-ui-design-r01` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1.5-unified-head-course-t103` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |

## 原顶层22个文件：15已退役，7保留

| 文件 | 处置建议 |
| --- | --- |
| [ARCHIVE.md](../acceptance/ARCHIVE.md) | 恢复入口，保留；不通读历史清单 |
| [README.md](../acceptance/README.md) | 日常导航，保留并只链接关键入口 |
| `mvp-0.1-provider-acceptance.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.2-closed-loop.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [mvp-0.2-closeout-decision.md](../acceptance/mvp-0.2-closeout-decision.md) | 阶段退出依据，按需保留 |
| `mvp-0.2-resource-quality.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-acceptance-plan.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-catalog-engineering-20261003.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [mvp-0.3-catalog-exit-20261003.md](../acceptance/mvp-0.3-catalog-exit-20261003.md) | 目录退出边界，保留；当前源码引用：scripts/verify_catalog_exit.py，移除前需处理 |
| [mvp-0.3-catalog-human-signoff-20261003.json](../acceptance/mvp-0.3-catalog-human-signoff-20261003.json) | 正式目录课程签核来源，保留；当前源码引用：backend/tests/test_catalog_release_preflight.py；scripts/verify_catalog_exit.py，移除前需处理 |
| [mvp-0.3-catalog-signed-handoff-20261003.md](../acceptance/mvp-0.3-catalog-signed-handoff-20261003.md) | 签核课程交接，保留 |
| `mvp-0.3-clean-checkout-20261003.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-pr-review-20261003.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-t006-insertion.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-t007-deletion.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-t031-compose-recovery.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `mvp-0.3-t032-animation-performance.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1-acceptance-plan.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1-graph-plan-v1.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| `phase-1-review-binding-offline-plan.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |
| [phase-1.5-head-goal-t108-r02-review.md](../acceptance/phase-1.5-head-goal-t108-r02-review.md) | 历史验收/计划，停止日常维护，可随对应旧消费者退役；当前源码引用：scripts/prepare_head_course_goal_grounded_package.py，移除前需处理 |
| `phase-1.5-head-goal-t108-r03-review.md` | 已退役；[来源与恢复](../acceptance/ARCHIVE.md#t004-集中退役2026-11-16) |

## 验证与最终交接

T003只做用途盘点，未执行删除；当时覆盖236项、链接、原任务不变、账本和diff检查通过。

T004实际执行：

- 来源检查：`python3 scripts/manage_acceptance_archive.py check-source --index docs/maintenance/acceptance-retirement-trials-20261116.json`，434文件SHA-256通过。退役前逐文件对比Git原字节，无用户未提交内容混入。
- 删除358个目录内资料文件、15个顶层历史文档、38个专属脚本和23个专属测试；共434个跟踪文件。另移除目标目录内2个可重建缓存。没有删除backend/web实现、后端测试、共享support模块或历史账本。
- `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q scripts/tests/test_archive_paths.py scripts/tests/test_p15_reference_artifact_v1.py scripts/tests/test_diagnose_head_course_t115.py scripts/tests/test_offline_c_fixture_manifest.py::test_reviewed_package_reproduces_original_bytes_and_retains_failures scripts/tests/test_p15_candidate_compatibility.py::test_readonly_check_has_no_key_dns_or_output --tb=short`：20 passed，0.76秒。验证恢复路径、共享投影、末尾LF边界、基础C夹具和保留兼容入口，不运行旧真实批次。
- 直接调用`head_course_replay.mapping("C01")`及`mapping("C02")`：T107清单、来源和T104依赖装配均通过；不读密钥或私有库，不导入应用。
- 同一恢复工具对`docs/acceptance/phase-1.5-data-model-t006/README.md`执行`restore`和`check`：通过；只恢复一份文件到忽略的local-materials目录，不全量复制历史。
- `/tmp/edumind-cleanup-t004/verify.py`：434路径已退役；剩余跟踪源码/历史材料（排除导航、任务日志及H封存正文）的事前事后摘要一致；剩余源码/CI无已发现的退役目录、模块名和顶层文件引用。静态引用核对不声称证明任意动态路径；H正文未读取，未改动。
- 本文、验收首页和恢复导航的本地链接，剩余154目录/7文件数量，根账本与`git diff --check`核对通过。旧冻结文档、历史PRD时间记录或任务快照里的退役路径按恢复索引解释，不改写历史原件。

原用户的P1报告修改、provider问题文档删除、OpenMAIC参考目录均未处理或纳入提交。Provider调用、数据库写入、浏览器验收、全套回归和部署均0；旧通过结论不冒称本次运行。

**本轮清理结束。** 余下66个候选作为依赖暂留，不再追加清理前置。下一步讨论T001课程结构、界面、动画和习题重设计；获得设计执行授权前不自动领取。后续替换相关功能时顺带收敛对应依赖，继续使用本文件和现有恢复工具，不新增一轮盘点框架。
