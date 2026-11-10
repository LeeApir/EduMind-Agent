# T119 栈课程统一结果

2026-11-10，零调用准备阶段。任务等待准确批次授权，尚无模型首稿、修订稿、独立教学结论或真实课程链接。

## 固定主例

状态数组从栈底到栈顶。高亮行号以[准确请求](request.json)中的 C 源码为准。

| 已完成的语句 | 有效元素 | 当前栈顶 | 本步取出 | 高亮行 |
| --- | --- | --- | --- | --- |
| 初始化 | `[]` | 无 | 无 | 22 |
| `push(3)` | `[3]` | 3 | 无 | 24 |
| `push(8)` | `[3,8]` | 8 | 无 | 25 |
| `pop()` | `[3]` | 3 | 8 | 26 |
| `push(5)` | `[3,5]` | 5 | 无 | 27 |

## 已验证

| 检查 | 结果 |
| --- | --- |
| 隔离 PostgreSQL 及编译运行 | 专用库 `edumind_catalog_p15_t108_t119_test` 执行 `alembic upgrade head`，随后 `python -m pytest -q tests/test_stack_course_trial.py tests/test_head_course_status_projection.py`，12 项通过。使用仓库 `scripts/run_catalog_db_tests.py` 的 `test_environment`，容器 `edumind-phase1-t037-pg`，仅传本机数据库设置。 |
| 材料与边界 | 按[独立预期](independent-reference.json)核对主例和迁移题。将同一 C 源码加独立断言后以 `clang -std=c11 -Wall -Wextra -Werror` 编译运行，检验逐步状态、出栈值、满栈入栈、空栈出栈及有效元素与存储槽的区别。 |
| 回执和课程主链 | 使用 MockTransport 比对发送的准确字节。拒绝异常 phase、未知事实、错帧、重复事实和模型添加的程序字段。异常原件可解密逐字节复核，保留 STOP 并拒绝重复发送。正例拒绝错候选审核，准入后私有 v2 回读一致，四题错误/正确反馈为 0/1，读取投影无参考答案或解析，其他访客无法读课程和作答。 |
| 页面组件 | `pnpm exec vitest run tests/course-visualization.spec.ts tests/head-course-status.spec.ts`，12 项通过。栈五帧、栈顶、单步出栈、高亮、暂停/前后步/重置及无来源时拒绝展示通过。旧头插和通用播放器/预算对照通过。 |
| 本机开发入口 | `PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile stack --prepare --start`。API 健康，Web HTTP 200，普通生成 POST 被拒绝（HTTP 409）。未创建真实生成操作或窗口。 |
| 静态检查 | `pnpm typecheck`、相关 ESLint、Ruff、`python3 scripts/check_catalog_workflow.py`、`git diff --check` 及 `stack_course_trial inspect` 通过。ESLint 无错误，课程工作区保留既有模板换行警告。 |

本轮初测纠正了独立预期中的高亮行号、提纲后写租约释放和准入时跨租约的来源绑定。候选绑定准确请求、操作及提纲，场景写入仍由自己的租约和版本围栏检查。测试正文明确标为离线夹具。

## 执行记录

| 阶段 | 状态 |
| --- | --- |
| Provider 调用 | 0 |
| 首稿结构、事实及教学 | 待执行 |
| 修订 | 本包额度 0，符合限定范围时另提准确请求 |
| 独立教学审核 | 待实际首稿 |
| 浏览器学习与刷新恢复 | 待真实候选通过审核后验收 |
| 课程入口 | 待交付。当前仅[开发应用](http://127.0.0.1:5212/)可访问。 |

下一步依[准确执行包](README.md)确认 DeepSeek 单次首稿、30 分钟窗口与 C2 例外。通过后在原访客完成实际课程验收，将课程入口、来源、首稿、失败或另批修订和浏览器证据追加到本文件。
