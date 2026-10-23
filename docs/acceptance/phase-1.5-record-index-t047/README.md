# T047 owner课程记录索引

依据ADR0028准确批准，实现GET /api/free-courses/{course_id}/records，kind必填attempt/operation/feedback/tutor，limit20默认/1–50上限，before_id同表同owner同course查锚点，按(created_at DESC,id DESC)稳定键集分页。先验证课程owner，外域/不存在统一404；所有查询独立带owner/course条件。索引只投影ID和时间，不装载正文/答案/Prompt/凭据，不筛掉失败或取消记录；无模型、迁移或写入。catalog_only可读，响应no-store。

正文仍通过原API读取最新关闭投影，不能以operation.head_version声称操作发布的准确结果；该字段保持原语义。runtime累计契约只合并ADR0028本项实现的RecordRef/RecordPage/索引GET，掌握度来源路由留T048，不提前宣称实现；原批准文件不变。

实际 r02：4新索引HTTP/PG +7原课程API +5导师API +12兼容 = **28通过，0失败/错误/跳过**，4组全新隔离数据库。覆盖会话/参数/no-store/空表、四类索引与原记录GET、取消、用量未知失败、同时间戳分页/末页、跨owner/course/kind游标、稳定返回及读取不新增记录。课程/模型数据明确合成，mock transport不是真实Provider，构造真实Gateway即失败。r01在测试前发现专用PG停止（NetworkSettings无端口）；确认测试标签和127.0.0.1:15437后启动同一容器，r02新建库验证，不跳过或用Mock数据库替代。

命令：`backend/.venv/bin/python docs/acceptance/phase-1.5-record-index-t047/run_checks.py --run-id r02 --output /tmp/edumind-p15-t047-r02`。原始日志/XML/命令摘要及SHA在该目录，results.json保留摘要；Ruff5文件、strict mypy2文件通过；runtime build_contract.py --check、ADR0028设计完整性、工作流/diff通过；41批准/manifest与50历史文件SHA、用户原README SHA保持。详细环境限定由run_checks.py及scripts/run_catalog_db_tests.py执行，不载入.env，不记录密码。

Provider0、生产catalog_only、H及旧blocked保持，无push/merge/部署。下一T048掌握度修订来源读取，阶段持续目标未完成。
