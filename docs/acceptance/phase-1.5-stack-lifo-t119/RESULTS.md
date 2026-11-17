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

## 真实首稿与交付

用户批准 `d1d4c2d` 对应准确首稿及 C2 例外。北京时间窗口为 2026-11-10 16:47:30–17:17:30。DeepSeek 官方 Responses 直连执行 1 次首稿，HTTP 200，完整原件 7,241 字节，服务端回报输入 2,582 tokens、输出 1,246 tokens。规划调用 0，修订调用 0。封存目录为 `~/.local/share/edumind/stack-lifo-deepseek-r01`，保留批准绑定、请求、加密响应、候选、审核、准入记录和 STOP。具体模型快照、账单及服务端留存按 C2 记录为未独立确认。[批次批准](../../ADR/0059-t119-approval-20261110.json) · [交付证据](delivery.json)

首稿 `5ce963dc990e2d7e7dd93853fef3ff390ed26bdd145e15551d74ec426e3abd50` 通过严格重放及独立教学审核。评审核对五段正文和总结、全部事实引用、五帧与代码行、栈顶和出栈值的区别、容量与展示边界、四题的题意和输入格式，以及四个答案及解析。七项全部通过，阻断项为空。题干开头「在程序追加的同一完整转移场景中」略偏装配术语，总结用最终状态说明 LIFO 略间接。第 4 段和出栈帧已直接给出后入的 8 先取出、3 成为栈顶。两处均为非阻断措辞，交付首稿原文。

私有课程 v2 已在原访客的 Chromium 窗口打开。从同一会话的「继续学习」进入课程。实际浏览器验收核对五段正文及总结、五帧状态及逐行高亮、播放/暂停/前后步/重置。四道题分别以全错和全对提交，反馈为 0% 和 100%。提交前课程 API 及页面未泄漏参考答案或解析。刷新保留 v2、输入和 100% 反馈，新增作答 POST 为 0。另一访客读取场景和作答均为 404。课程 UUID `b00893e7-d464-47e3-b6b5-3927a939d5de`，场景版本 `f9f51b82-9125-49ec-a96b-bdc89a332540`。[本机入口](http://127.0.0.1:5212/)

执行命令为 `sh /tmp/edumind-t119/send.sh`、`backend/.venv/bin/python -I /tmp/edumind-t119/entry.py replay`、同一入口的 `publish` 及 `backend/.venv/bin/python -I /tmp/edumind-t119/check-browser.py`。浏览器脚本首次在提交前因选择器匹配到两个主区域而停下，限定课程区域后通过。浏览器截图在 `/tmp/edumind-t119/course-before-answers.png` 和 `/tmp/edumind-t119/course-verified.png`。
