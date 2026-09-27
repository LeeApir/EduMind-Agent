# T037 正式性能入口即时停机保护

用户于2026-09-27批准冻结20样本、最多240次实际模型尝试。本任务先非计费补齐保护，
不改变冻结样本、时钟起点、段落资格、并发、预热或性能标准。T032继续blocked。

原serve_first_screen.py只有计数上限；正式入口现在使用GuardedBudget，并在Responses
状态检查发现401/402/403/429时持久halt。下一adapter调用在reserve处拒绝，阻止Gateway
内部重试继续实际请求。规范化认证、限流、能力错误也保守停机；402无法另行辨别时不继续。
超时等其他错误仍依生产重试契约计数；所有started/failed/completed尝试计入240。
保护是验收进程专用单worker全局保护，不改变生产错误分类或重试策略。

run_first_screen_v2.py仍一次20槽位，单并发、0预热、学习POST180秒、匿名30秒。
读取halt后剩余槽位明确unattempted；不补跑。匿名HTTP与完整准备分开，恢复仅GET原操作，
记录实际尝试增量。恢复查询失败独立记录，不能丢弃原生成时钟/候选/发布证据。
所有候选仍独立hash评审，编号和代码成员句点不自动视作教学句。

实际验证（backend，全部mock或已有隔离回归库，无真实Provider）：

- uv run --frozen pytest -q tests/test_acceptance_budget.py tests/test_first_screen_v2.py tests/test_diagnostic_three.py：23 passed。
- EDUMIND_TEST_DATABASE_URL=<isolated regression PG> uv run --frozen pytest -q：434 passed，0skip，9既有弃用警告。
- uv run --frozen ruff check app tests ../docs/acceptance：通过。
- uv run --frozen mypy app：55文件通过。
- git diff --check：通过。

本轮仅验收工具修改，前端和生产业务源码不改，前端沿用T036的70测试/类型/构建证据，
没有将其冒充本轮重跑。只读当前配置deepseek-flash，responses_json_schema/Responses streaming。
首次只读配置打印误取不存在provider属性失败，未输出任何配置或发起模型调用，已纠正。
任务治理首次apply_patch上下文错误未落盘，随后正确追加，未覆盖历史。

下一步冻结本任务完成提交及T036生产基线，另存T032 v2 formal raw/ledger/decisions/audit/report。
固定公开目标沿用mvp-0.2-t032-retest-plan-v2.md，不混入T035三诊断样本或旧20失败样本。
新库edumind_perf_t032_v2已只读确认不存在，需新建迁移。正式结果不通过则T032保持blocked，
不盲重跑、不自动归档或跨MVP0.3；不push/merge，不修改真实.env/模型。
