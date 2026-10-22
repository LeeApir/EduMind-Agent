# T018：准确题组作答与暂定反馈

0045 新增私有题组版本、不可变原始作答和 owner 范围的测量暴露事实。逻辑 exercise_id 由 owner/course/scene/本地题组键确定，准确 exercise_version_id 另绑定不可变 scene_version；复制保留逻辑身份但新版本独立。私有题干答案/解释、评分规则、教学上下文及必要上游摘要由服务器重算，不接受客户端分数、节点或核定字段。assessment_digest 使用既有目录的规范化题干答案规则，另记录仅题干集合摘要，忽略显示 ID/顺序/解释，跨课程仍可判断重复测量。

提交在 owner/course 锁及事务内检查当前 head、准确清单/场景/题组和可见性。最多4项短文本，每项≤500字符；至少一个非空、不可重复 ID 或包含组外 ID；未知字段拒绝。部分提交保存原文，comparison_score=null、无逐题结果/答案解释；后续作答创建新 attempt，不能更新旧行。完整提交采用 quiz-exact-text-v1 的 NFKC/casefold/空白折叠比较，反馈明确 provisional 和 course_only，不调用模型判卷，不写 learning_evidence/mastery。

首个完整作答消费测量名额，部分提交不消费；已有 help/solution/完整记录通过任一摘要阻断后续首次资格。暴露登记与作答共用 owner 锁；并发完整作答只有一份首次快照。原始输入、首次/暴露快照与提交时反馈只追加。T019 再补可靠核定、准确旧目录原件检查、正式准入与撤销，不将当前 course_only 追认为正式成绩。

幂等 POST 只回 attempt_id，同键同体重放先于 head/禁用检查，不回放旧答案；改变内容冲突。owner GET 即使题目禁用仍返回自己的原始作答，但最新反馈改为 withdrawn/null，隐藏已失效解释；其他 owner 统一 NOT_FOUND。历史版本只读，新提交 STALE_COURSE_VERSION，不自动套用新题答案。公开 ExerciseBlock/DisabledExerciseBlock 纯投影遵守已批准 schema，隐藏答案、solution、核定和私有摘要；T020 接入 HTTP 前使用该投影。该私有服务本身不改变生产 catalog_only 门禁。

准确隔离运行命令、测试数、日志/XML SHA256 见 results.json 和 verification.txt。真实 Provider0，无生产迁移、共享/目录发布、push/merge/部署。完成后按已授权批次继续 T019，T020 后停止。

最终r02：507通过（新增12、既有495），0失败/错误/跳过，25组隔离PG。Ruff7、strict mypy3、任务/diff/冻结SHA检查通过。
