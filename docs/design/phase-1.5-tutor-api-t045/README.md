# T045 导师REST/SSE与准确恢复

接入原ADR0026已批准POST tutor-turns（202 operation_id/turn_id）及GET turn；原operation查询/取消/SSE按owner所属操作类型分派TutorRecovery或旧Recovery。SSE只带queued/started/tutor_ready/cancel/error/done状态与turn_id，正文经GET turn重新检查来源；不把TutorEvent当旧scene_ready。准确游标/Last-Event-ID、终态204、32连接上限、会话失效关闭沿原协议。

写入继续使用会话/CSRF/owner路由幂等，部分身份/未知字段/辅助确认/历史版本/活动生成被明确拒绝；提问不自动取消生成。catalog_only禁止新导师发送，允许本人旧记录/操作读取和显式取消。取消重放原回执，刷新不重发POST；ready失效后即使重放创建回执也不能取回旧正文。

累计运行契约生成器并入原先排除的已批准导师路径，并为共用操作响应列明Operation/TutorOperation联合及Event/TutorEvent。三个原始批准OpenAPI和manifest保持原字节；源文件中的planned/早期任务编号是历史提案字段，不据此推断实现，当前状态看根账本。原OpenAPI回归改为断言导师路径已实际存在，其余响应/身份/安全断言保留。

实际执行：`backend/.venv/bin/python docs/design/phase-1.5-tutor-api-t045/run_checks.py --run-id r01 --output /tmp/edumind-p15-t045-r01`，**113通过、0失败/错误/跳过**，7组隔离PG/HTTP/SSE/FakeAdapter（导师API5、原API7、导师调度11、上下文10、旧调度39、恢复29、新旧兼容12）。每组单独新库、专用容器标签/15437回环校验，不读真实.env/不构造真实Provider。结果及原日志/XML摘要在results.json。

`ruff check`覆盖新API测试/路由/运行契约生成器/旧API回归/检查脚本，strict mypy路由模块、累计契约`--check`、工作流及diff通过。35批准原件manifest、50历史原件及0047/0048迁移、用户既有README保持。新增测试逐项覆盖创建/GET/终态SSE/准确游标/幂等、CSRF/owner/未知字段/辅助确认、catalog_only/取消、正文失效/回执重放、活动生成不被导师取消。

Provider0、生产catalog_only、H/旧blocked不变，无push/merge/部署。下一T028真实导师页面接线；阶段持续目标仍未完成。
