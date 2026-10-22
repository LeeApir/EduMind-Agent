# T013：首场景与后续场景增量可学习交接

新增free_course_steps/events、0040前向迁移，以及私有大纲/场景原子提交和准确读取原语。不调用Provider、不接线HTTP/SSE或后台调度，产品模式仍catalog_only。

## 原子可学习边界

commit_outline校验实际owner/请求/准确计划/epoch，首次无head时提交包含全部scene_version_id=null的完整清单、pending步骤和outline_ready事件；不会产生first_scene_ready。可选图谱建议沿T009生成，空关联不阻断。已有head不能通过本函数被空大纲覆盖。

commit_scene从实际validation_id重新通过T011/T012实时检查，要求生成候选的expected_head、owner/course/operation、计划/场景、必要上游、epoch/token/租约/截止及取消均有效。一个保存点中保存完整清洗正文/私有练习与动作、准确依赖、全清单新版本、CAS head、ready步骤和scene_ready事件；计划第一个场景就绪时再按顺序追加唯一first_scene_ready。正文、步骤、指针或事件/收据任何失败全部回滚，调用者仍须提交外层事务。没有外层commit，其他连接不可见。

首场景无需等其他场景或普通语义签核；first_scene_ready严格指计划第1个场景，不把先生成的其他章节冒充首章。该里程碑按course唯一，重放保持相同operation/seq。每次后续提交仅替换原清单中对应的null绑定，保留已就绪准确版本与节点依据；不覆盖ready正文。不同基线拒绝，不在新的head上偷套旧候选。

commit_outline/commit_scene只接受首次/补章方向的create/clarify/resume操作类型，拒绝revise_scene/adjust_outline混合增量替换；完整恢复新操作/复制计划和普通修订全替换仍由T015/T016实现，并未因预留类型而交付。全场景就绪是内容条件，T013不写操作succeeded或done；T014负责实际调度、完整终态与共享预算。

## 失败、准确读取与事件

fail_scene只接收固定原因码，将目标标failed、其必要后代标blocked_dependency，独立后续步骤保持pending。已有ready不可被此接口当普通生成失败撤回；确认缺陷后的禁用由T017处理。失败不创建正文/新清单，也不隐藏缺章或把全课改为成功。此接口是内部步骤处置原语，没有模型判定/自动重试；未知发送的隔离和终止仍须T014/T015接线。

read_availability按准确历史清单绑定计算content_state/ready_count/all_scenes_ready；只有存在T013 ready步骤绑定的正文才被本原语视为可学习，旧仓储私有候选不能借有正文绕过准入。generation_state是该准确计划步骤的最新进度，单独返回，不把历史空绑定因后来步骤ready变成有正文。read_ready_scene从准确绑定取经摘要校验的T012表示副本，不返回answer_key/solution。内部题目仍有局部exercise_key，正式UUID/公开练习响应由T020/T022处理，当前返回体不是已开放REST场景API。

read_events只查询持久记录，无Provider或自动resume。事件携带准确版本/场景ID与固定状态/原因，不带正文、答案或异常文本。序号按operation连续递增、最多256条，完整单事件≤4KiB；after从下一条重放，非法/超前游标拒绝，末尾返回空列表。没有HTTP连接、心跳/终态204或EventSource测试声明，SSE实际接线留T020。所有正文/事件读取均owner限定且返回副本；已就绪内容不会因取消而被此生成原语删除。

## 数据库保护

0040新增持久步骤和只追加事件，为T012表示加同owner/course/id唯一约束，以复合外键绑定准确来源。步骤静态身份不可改，ready必须引用实际已准入的相同操作/计划/场景正文及当前head清单；事件有序号唯一/连续插入保护、payload字段白名单、ready版本绑定和首场景部分唯一索引。状态表不是完整Worker账本，attempt/capacity/计数/token/费用、重领和取消扫尾由T014/T015补齐。

锁序owner→course→operation→步骤/事件/收据，Provider网络不在事务内。最后以PG时钟SQL复核期限，即使事件提交途中租约失效，也不留部分head/ready/事件。已有步骤或事件时0040拒绝downgrade，不删除审计强退；用户删除沿既有级联。0034–0039历史迁移保持原字节，旧签核发布/评分路径不改。

## 实际验证

```sh
backend/.venv/bin/python docs/acceptance/phase-1.5-scene-availability-t013/run_checks.py --run-id r01 --output /tmp/edumind-p15-t013-r01
backend/.venv/bin/ruff check backend/app/models/free_course_progress.py backend/app/models/free_scene_actions.py backend/app/models/__init__.py backend/app/services/free_scene_availability.py backend/alembic/versions/0040_free_scene_availability.py backend/tests/test_free_scene_availability.py backend/tests/test_free_course_migrations.py docs/acceptance/phase-1.5-scene-availability-t013/run_checks.py
(cd backend && .venv/bin/mypy app/models/free_course_progress.py app/models/free_scene_actions.py app/models/__init__.py app/services/free_scene_availability.py)
python3 scripts/check_catalog_workflow.py
git diff --check
```

最终406项通过，0失败/错误/跳过：新可见性19项、前置自由课程340项、旧图谱/路径47项。计数及源文件/原始日志/XML摘要见results.json，过程见verification.txt。既有test-only PostgreSQL绑定127.0.0.1:15437，20个新隔离库，不读.env或打印凭据；原始日志/XML在/tmp/edumind-p15-t013-r01，重跑使用新的run-id/输出目录。

新测试覆盖空大纲不可学、首场景独立就绪、逐个追加、独立后续/依赖失败、历史准确绑定、私有答案剔除及副本隔离、全内容就绪不伪造操作完成、双连接并发幂等/基线冲突、manifest/首事件/收据失败整体回滚、写入途中租约过期、未提交跨连接不可见、错误owner/候选/epoch、事件上限整体回滚、游标/只追加/连续和首里程碑唯一、有数据拒绝回退。Event schema与批准T002副本一致。前置自由课程与旧图谱/路径/签核链在隔离PG/Mock回归。

30份批准规范/5份manifest及0034–0039原字节不变。无真实模型、教学质量/性能、浏览器或新产品E2E验收声明；Provider0/catalog_only/H封存、旧失败和用户无关改动保持，无push/merge/部署。下一T014持久渐进调度与共享预算仍todo，未领取。
