# T017：准确版本反馈与可信处置

学生反馈以 owner/course/清单/scene_version/anchor 及可选准确题组绑定保存，只追加原文和 student 来源。提交收据只含 feedback_id；无论反馈次数多少均不触发模型、确认或自动修正。公开读取状态由准确相关处置事实投影，越权统一 NOT_FOUND，重复键同体重放、异体冲突。

维护入口是 `python -m app.workers.free_course_maintenance --owner UUID --draft FILE`，默认 dry-run；`--apply` 必须提交与当前影响清单匹配的 impact_digest 和 decision_key。只有仓库本地 OS 所有人可建立进程内维护能力，当前维护者 Lee；无 HTTP 确认接口或学生角色提权。严格沿批准内部 schema 接收可复核人工推演、可信引用、已批准独立离线结果或实际机械违规。机械标签须与准确生成输入和硬门复检匹配，普通模型意见不接受为来源类型。人工语义证据由受信维护者负责独立核对，程序不冒充事实验证器，不执行反例代码。

确认按题组、场景或有明确依据的课程范围追加 disable 事实；只沿准确必要依赖和记录的复制来源传播，同节点/相似文字不扩散。题组禁用保留同场景讲解，隐藏该题组内容并拒绝后续提交；依赖后代按场景暂停。旧版本读取同样检查，不以历史 GET 绕过。dry-run 不写事实；apply 在 owner→course→operation 锁和事务内重算摘要、追加决定/可见性并围栏当前受影响生成。旧租约不能继续发送/发布，不额外调用 Provider。

not_confirmed 不禁用；decision_correction 仅追加纠正，不复活内容或贡献。restore 只恢复准确选定版本/题组，要求该版本原硬门派生呈现完整、必要上游及复制来源可用，并保存新的独立人工依据。恢复不会自动恢复后代，或解除原版本以外的暂停。存储层不可变触发器禁止修改/删除审计；同事务后续效果失败则决定/可见性整体回滚。

0044 仅新增反馈、处置、可见性三表及 owner/course 复合延迟外键，不修改既有迁移。T019 必须在 API 开放前补齐 quality_effects 的核定/正式贡献撤销；此时尚无新题组正式贡献，不以空接点宣称证据回滚完成。T018 将题组禁用内部呈现转换为批准公开 DTO。本地维护不意味着共享、目录发布或恢复旧动态质量验收。

隔离运行证据及准确命令见 results.json / verification.txt。历史 0037 迁移夹具在旧 schema 造数时显式使用当时无质量事实的边界，并断言该表不存在；仅该造数范围临时替换新 guard，随后恢复真实函数。全部旧表摘要比较及升级后测试保留；生产没有缺表放行分支。真实 Provider0、catalog_only、H 样本封存，无生产迁移/push/merge/部署。T017 完成后按连续授权推进 T018，T020 后停止。

最终 r06：495 passed（新增11、既有484），0 failure/error/skip，24组真实隔离PG。Ruff13文件、项目strict mypy8文件、任务检查、diff检查与30份冻结规范/5 manifest SHA256通过。历史失败与修复详见verification.txt。
