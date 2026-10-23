# T044 导师共享预算、单次调度与取消

TutorScheduler专门化现有Scheduler的PG预约/两槽/派发/结算/心跳/重启扫描/迟到处理，使用相同attempt、dispatch、settlement、capacity及包锁/费用池。每轮1次、90秒含排队、16k输入/2k输出，单课40次/600k输入/144k输出包含既有生成；没有重试、格式修复或独立聊天额度。默认无生产Adapter/执行包注册，真实发送授权仍为0。

复用TutorAgent纯请求构造和单tutor输出校验，增加显式未签核草稿Prompt版本；旧课堂默认请求/重试语义保持，15项原TutorAgent检查通过。现有结构不含合格引用字段，保存一般补充解释并返回空引用，不伪造证据来源。输出清洗后仅保存turn，不改变课程/评分/缺陷结论。

准备/派发/输出时复核准确来源与head。派发前可靠证明尚未调用的来源失败记录not_executed/零用量并释放容量；其他未知出站保持隔离，迟到只能结算不能发布。回复保存位于savepoint，输出围栏失败不得把半完成正文留在失败操作中。TutorRecovery复用现有cancel原回执和快照，仅导师显式子类开放该kind，不恢复resume/重试导师。

0048只增加批准tutor_ready类型及导师步骤专用ready分支；SQL要求真实同owner/operation/turn的dispatch+complete_response结算+回复、活租约/期限/当前清单。事件只含准确turn_id，并检查ready步骤/回复/版本；保留旧连续序号/体积/允许字段/旧计划和场景检查。有导师完成审计时拒绝回退，空库恢复旧守卫。

实际执行：`backend/.venv/bin/python docs/design/phase-1.5-tutor-scheduler-t044/run_checks.py --run-id r05 --output /tmp/edumind-p15-t044-r05`。**161通过、0失败/错误/跳过**，6组新隔离PG/纯Mock（新调度11、上下文10、旧调度39、旧恢复29、旧导师15、迁移57）。结果/准确日志XML SHA在results.json。测试专用容器标签/15437回环检查、无真实.env/Provider。

新增检查含单发送/输出上限/共享池与实际40次预约（FakeAdapter）、两槽、默认零授权/包累计、取消回执/迟到结算、崩溃不重发、未知隔离、排队总期限、派发前来源故障的零发送可信结算、拒绝伪造ready。初期发现旧ready-plan与事件允许字段守卫不识别导师，分别补准确导师分支且保留旧断言；过期夹具不能修改持久deadline，改为既有测试同款创建时过期注入，不放松不可变约束。

Ruff9文件/strict mypy4模块/累计契约/工作流/diff通过；35批准原件manifest/50历史迁移归档及0047、用户README SHA保持。Provider0、生产catalog_only、H/旧blocked保持，无push/merge/部署。下一T045导师REST/SSE；T028页面尚未完成，阶段目标继续。
