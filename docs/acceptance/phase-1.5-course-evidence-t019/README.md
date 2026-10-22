# T019：可靠准入与准确撤销

0046 增量增加 learning_evidence.source_protocol/free_course_attempt_id（旧行保持 null），以及准确 answer/mapping 核定、核定撤销、正式准入和证据撤销四类只追加表。新 quiz 必须以 free-course-v1 明示来源，禁止套用旧 resource/unit 身份；未知非空来源拒绝。准入与 LearningEvidence 通过同 owner/attempt/evidence 循环 DEFERRABLE 外键绑定，提交时由延迟触发器核对准确题组、两种核定、节点、摘要、核定时间和首次完整资格，不允许只写一半。correction 与撤销亦须准确闭合；新来源事实禁止改写、降格为旧 null 来源或删除（用户级联删除除外）。ORM/迁移检查一致。

维护入口 `python -m app.workers.free_course_maintenance --kind attestation --owner UUID --draft FILE` 默认仅预览服务器摘要；apply 须准确 content_digest、decision_key、可信本地权限和独立可复核依据。答案核定和单节点映射独立保存；机械/模型意见不能代替语义核定，节点须存在于准确 graph_version 和该清单的课程关联中。调度器可选 graph_version 接入已有 T009 建议关联；默认无关联不阻断学习，但不能获得正式准入。核定不会签核整课或发布目录。

作答事务在 owner/course/node 锁下检查当前可见版本、完整输入、两份既有有效核定及首次资格。核定必须早于首次完整提交；缺失、事后核定、求助/答案暴露和重复完整均只形成课程表现。任一 assessment_digest 或 stem_digest 既有暴露阻断跨课程、换 ID、改顺序/答案重置。旧目录从原 resource_id/resource_version 保留题干和原 answers 确定完整性及两种摘要，不读取最新版；原件缺失/含糊返回 PRIOR_ASSESSMENT_UNKNOWN。旧成绩不会反向清理。

符合资格的一次完整题组只产生一份正式 quiz_attempt，以服务器确定性比较分数沿 mastery-v1 重放全部有效旧/新历史。所有既有写入口仍走 apply_mastery_evidence，统一按来源分派；空旧来源保留原 catalog/legacy/planned 策略，新来源须有效 admission 且未撤销，correction 只审计不计分。路径 replan_required 同事务置真。

确认缺陷在 T017 原事务接点撤销准确题组、必要后代及复制来源的核定/贡献；普通修订在 T016 整体切 head 的同事务比较题组/评分、实际上下文/依赖绑定和关联的规范字节，撤销发生变化的旧贡献，完全未变者可保留。追加 revocation 与 evidence_correction 后从有效历史重算，不做分数相减，不用新答案重评旧题；无剩余有效事实为 unseen。新 revision 的 recomputed_from 指向原 revision，原始作答/旧分数审计不改写；GET 已撤回反馈为 withdrawn/null，不泄漏原失效解释。纠正/恢复不会复活旧贡献。新来源不送入模型画像回调；派生掌握来自有效 current，用户原自述/偏好保留，不制造新易错推断。

最终 r05：566 passed，0 failure/error/skip，34 组独立 PG；新增准入15、既有507、补充旧掌握度/评分/事件/画像/教学绑定44。新覆盖正式准入一次、缺核定/迟核定/帮助、质量撤销及旧写入不复活、替换/未变保留、准确旧原件/缺原件、跨课修正答案同题干、循环来源闭合/不可洗白、事务回滚、路径失效、准确核定权限与摘要。Ruff16 文件、strict mypy11 文件、工作流/diff/30冻结文件5manifest检查通过。日志/XML、命令和摘要见 results.json、verification.txt。

历史 0033 夹具用实际反射的旧列 INSERT 保存原事实；迁移摘要比较保留所有旧列，新两列在旧来源必须 null。既有 0037 造数范围边界保持。旧动态资源兼容夹具仅在新建隔离库使用其原 dynamic 可见模式，Provider 配置清空，其他组 catalog_only；无生产切换。r01 修复 asyncpg 多语句迁移；r02 核定测试缺准确关联；r03 旧动态夹具被 catalog 隐藏；r04 新夹具缺导入及精确锚点选择错误，r05 全通过。没有删断言或伪造核定；全部人工证据是显式 synthetic 测试数据，无真实课程签核。

真实 Provider0，H 样本封存、批准规范和0034–0045原字节保持，无生产迁移/push/merge/部署。提交后按批次授权实施 T020 API/SSE，完成 T020 后停止。
