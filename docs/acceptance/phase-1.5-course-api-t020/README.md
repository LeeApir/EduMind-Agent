# T020：自由课程 API 与持久事件恢复

14 个资源路径（15 个操作）接通创建/列表/课程/head/历史版本/准确场景、恢复/澄清/修订/取消/影响预览、反馈及原始作答。共用现有 cookie owner、CSRF 和同源检查；ID 不赋予权限，缺失/其他 owner 一律404。写操作使用批准 ASCII Idempotency-Key，按 T007–T019 的同事务收据重放/冲突；只返回准确 ID 或批准 Operation，不能回放失效正文/答案。公开响应按累计 JSON Schema 校验，错误不回显请求或私有上下文，全部 no-store。

公开课程为 ai_draft/unendorsed；manifest 保留准确历史标题/绑定/非可靠节点关联，去掉证据引用和私有摘要；场景使用 T012 纯呈现、T018 公开题块、T003 禁用占位，不返 answer_key/solution/核定原文或私有 digest。C 对外为 c，创建可显式 code_language=null。组内禁用保留可用讲解但返回 exercise_unavailable，场景禁用409；原始作答始终 owner 可读，撤销后的评分/解释隐藏。无共享、目录发布、学生核定或可信处置路由；旧资源接口不接受自由课程 UUID 当作签核资源。

创建返回201并持久排队，后续操作返回202。HTTP 路由不构造 Provider，不启动另一个执行器；测试驱动 T014 持久调度器及显式 FakeAdapter，API GET/SSE 不触发生成/恢复。真实出站仍需要独立准确执行包/预算授权和可信适配器，本次0调用；不宣称真实质量/性能或生产链路已验收。

SSE GET 只按 operation_id/seq 读取 PostgreSQL 事件，data 为已批准 Event，无正文/答案。after 与 Last-Event-ID 同时提供必须一致；负数/非整数422，超前409。重连只重放游标之后的顺序事实；终态仍先重放未读 done 后关闭，读尽204。连接最多60秒后可用游标重连、15秒心跳、1秒短事务轮询；进程级32连接容量保护不承载业务状态。断开连接不取消、不重发请求；持久取消使用明确 POST。每轮重验原会话，撤销或到期停止；新连接仍需有效 cookie。终态读尽不占连接容量。

生产默认 catalog_only 未改：阻止创建、新生成/修订/恢复/新作答，仍可 owner 读取已存在内容/操作/事件/作答、报问题和取消。隔离 E2E 中才选择 dynamic，继续显示草稿未背书，无课程发布提权。T023 导师接口未实现、未注册或提前宣传；T021 前端也未领取。

`backend/app/contracts/free_course.openapi.json` 与 `docs/api/phase-1.5-free-course.runtime.openapi.json` 是 T001+T002+T003 累计实现契约：按批准顺序替换题块 DTO，并把已批准 DisabledExerciseBlock 加入场景 oneOf；无新的契约决策。三份冻结原件字节保持。运行依赖包内 JSON，不再从容器外 docs 目录读取质量 schema；OpenAPI 组件使用 FreeCourse 前缀避免与旧接口撞名。重建/校验命令：

```sh
python3 docs/acceptance/phase-1.5-course-api-t020/build_contract.py --check
backend/.venv/bin/python docs/acceptance/phase-1.5-course-api-t020/run_checks.py --run-id r02 --output /tmp/edumind-p15-t020-r02
backend/.venv/bin/ruff check backend/app/api/free_courses.py backend/app/main.py backend/app/services/free_course_contract.py backend/app/services/free_course_quality.py backend/app/services/free_course_scheduler.py backend/tests/test_free_course_api.py docs/acceptance/phase-1.5-course-api-t020/run_checks.py docs/acceptance/phase-1.5-course-api-t020/build_contract.py
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/app/api/free_courses.py backend/app/main.py backend/app/services/free_course_contract.py backend/app/services/free_course_quality.py backend/app/services/free_course_scheduler.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

最终 r02：573 passed，0 failure/error/skip，35 组实际隔离 PG；新 API/SSE 7 项宽路径 E2E 加前序566。覆盖默认模式/鉴权/CSRF/同源、全资源 owner、幂等、草稿可读且不能发布、答案字段去除/禁用占位/反馈撤回、准确修订/旧版拒绝、取消/恢复及不自动澄清、列表/版本分页、完整 OpenAPI 响应契约、持久流顺序/重连/终态204/非法游标、容量和撤销会话。r01 仅分页夹具未按 owner 单活动约束串行创建，改为真实取消再创建后通过，未放宽活动门禁。日志/XML SHA256 见 results.json。

Ruff8 文件、strict mypy5 文件、累计契约重建、全部 OpenAPI 本地引用/安全 scheme 解析、30 冻结规范与5 manifest SHA256、工作流和 diff 检查通过；0034–0046无改动、本项无生产迁移。无真实 Provider、push/merge/部署，H 样本封存。T016–T020 批次完成后停止，下一项 T021 保持 todo、待明确新执行授权。
