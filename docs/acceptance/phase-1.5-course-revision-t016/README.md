# T016：局部修订与完整替换集合

私有 `Revisions` 提供按结构依赖计算的影响预览、明确基线/影响摘要确认、新请求/新计划、私有暂存和整体原子切换。0043 只新增 revision、plan binding、stage provenance 三类只追加表；旧 schema/迁移保持。用户已授权 T016–T020 按依赖连续开发，每项独立提交；本项不开放真实调用/API。

局部 revise_scene 的目标及有向后代由服务计算，不接受客户端删减；adjust_outline 影响整个旧大纲（可以是显式 null 基线下尚无大纲的课程）。预览不读取/推断自然语言意图，只返回批准 Impact 结构：准确基线、影响 ID、13 次/600 秒上限、requires_outline_adjustment 和摘要。创建时重新核对 owner、head、摘要、活动操作、未知发送与课程累计额度；幂等键同体原样重放，改体冲突。原目标与要求保留在原请求/adjustment 来源链，修改文本另存，不回写原件。

revise_scene 确定性复制不可变计划的全部全局字段，候选只能输出原场景 schema 中的 blocks/actions，不能改全局计划或自动升级为整课生成；全局字段不一致则 OUTLINE_ADJUSTMENT_REQUIRED。这里保证结构/版本范围，不宣称用字面校验证明模型语义、教学事实或共享示例讲解正确。普通语义建议不触发额外模型循环。用户需要全局变化时须显式选择 adjust_outline；后者重新规划但仍受 1–8 场景/共享预约及重试池约束。大纲澄清通过新 clarify 操作继承该准确原子替换范围和基线，补充原文另存、预算不重置课程累计。

旧 head 始终可读。未受影响且已 ready 的场景复制为绑定新 plan 的新 scene_version，按拓扑重建依赖引用，保留准确源 scene_version/presentation 来源事实；复制不伪造 Provider 调用或模型准入。局部新候选经过 T010/T011/T012 后仅保存私有 scene/stage，不写 ready/切 head。下一个场景只使用该新计划中准确暂存的必要上游，不能混入旧计划。所有目标/后代完整后，在同一事务提交全清单/head、全部 ready、scene_ready、首次里程碑（全课唯一）和替换派生效果接点。任何步骤/提交/效果失败、取消或超时保持旧 head。旧版本/请求/原作答不会套用新答案。

已有 stage 的修订租约失效时终止 LEASE_LOST，不把旧 epoch 私有集合重新贴成新 epoch，也不继续花费；未知发送优先 OUTCOME_UNKNOWN/隔离，保留已发生次数。失败后需显式新修订及新确认。所有内部计划/复制/发布收据键含 operation ID，连续修订不互相覆盖。未受影响但原本缺章的绑定保持 null，局部修订不偷补生成；操作成功与整课内容齐备分别判断。

`free_course_effects.replacement_effects` 是同事务接点。T016 时尚无新题组准入/正式贡献，接点为空；T019 必须在 API 开放前实现核定/贡献撤销。T017 才实现已确认缺陷禁用，T018 才形成可提交题组；本项不宣称这些后续能力已完成。既有签核/评分不改，无旧动态验收追认。

实际最终 r05：484 passed，0 失败/错误/跳过（新修订10、前置自由课程427、旧图谱路径47）。新增覆盖拓扑影响及 Impact schema、真实私有集合不可见、两步只切一次、复制准确来源/新计划/依赖、新大纲可变场景、取消/失败保持旧 head、幂等/越权/陈旧摘要、派生效果失败全回滚、澄清衔接、null 基线与数据库拒绝 null 局部修订、过期 epoch 不重发。日志/XML 在 `/tmp/edumind-p15-t016-r05`，重跑用新 run-id/目录，摘要见 results.json。

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-course-revision-t016/run_checks.py --run-id r05 --output /tmp/edumind-p15-t016-r05
backend/.venv/bin/ruff check backend/app/models/free_course_revision.py backend/app/models/__init__.py backend/app/services/free_course_revision.py backend/app/services/free_course_effects.py backend/app/services/free_course_recovery.py backend/app/services/free_scene_generation.py backend/app/services/free_course_scheduler.py backend/alembic/versions/0043_free_course_revision.py backend/tests/test_free_course_revision.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-course-revision-t016/run_checks.py
(cd backend && .venv/bin/mypy app/models/free_course_revision.py app/models/__init__.py app/services/free_course_revision.py app/services/free_course_effects.py app/services/free_course_recovery.py app/services/free_scene_generation.py app/services/free_course_scheduler.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

r01 因跨操作固定内部收据键冲突 1 fail，改为 operation 绑定；r02 全479通过，r03 加衔接/空基线后482通过，r04 加数据库约束483通过，r05 加失效围栏484通过。未削弱旧断言。30 份批准规范/5 manifest、0034–0042 原字节保持，Provider0/catalog_only/H 封存，无生产迁移、真实质量/性能声明、push/merge/部署。完成本项后按既有批次授权领取 T017，不再逐项求批准；T020 后停止。
