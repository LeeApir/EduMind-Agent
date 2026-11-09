# T118 统一结果记录

当前：**准备完成，待真实调用授权。Provider 请求 0；真实课程入口、独立全文审核及浏览器学习验收尚无结果。** [开发目标表单](http://127.0.0.1:5208/) 只用于后续实际输入。批准前没有启动真实操作窗口。

| 定向检查 | 实际结果 |
|---|---|
| 四份程序 C 源码编译语法检查（`clang -std=c11 -Wall -Wextra -Werror -fsyntax-only -x c -`） | 主示例、忽略返回对照和两种练习情境通过；未执行模型内容。 |
| [独立参考](independent-reference.json) 对比实际产物 | 13 帧状态、作用域与高亮行逐一相符；接收两次：`t0.next=NULL`、`t1.next=t0`、入口 `t1`、`[7,4]`；忽略两次：入口仍为空、两节点各自指向 NULL，均从该入口不可达。判空在 f02/f08，均为假并继续。四题独立预期与私有答案相同。 |
| 同一前台入口 + PostgreSQL + HTTPX MockTransport | 绑定真实应用请求快照和冻结模板；错例、篡改请求、越额批准、重复或未知引用、回抄代码及不完整审核拒绝。离线成功路径创建私有 v2，投影有原样题干和对应代码，无答案键或解析字段；四题错误/正确分别得 0%/100%，重新 GET 得同版。 |
| 停止路径 | 同值重复正文也拒绝；加密原件回读与响应字节相同，封存具体错误及 STOP，拒绝再次发送。应用取消请求阻止后续写入，仍只保留 v1 大纲。 |
| 既有行为和冻结核对 | 旧固定输入、材料及请求对照和 DeepSeek 回执定向回归通过；历史文件未改。 |

运行命令（从仓库根开始）：

- `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile empty --prepare --start`：专用开发库迁移到 0050，本地 5208 表单 HTTP 200。
- 使用上述入口生成的隔离环境运行 `backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_empty.py backend/tests/test_head_course_fixed.py::test_exact_first_request_carries_new_materials_and_historical_requests_match backend/tests/test_head_course_deepseek_wire.py`：**22 passed**，仅现有 Starlette 弃用警告。
- `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.prepare_head_course_empty --check`、`PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.head_course_goal --profile empty --inspect`：冻结清单 409 项一致，状态 `prepared_not_authorized`。
- 修改文件的 Ruff、`pnpm typecheck`（`web/`）、`python3 scripts/check_catalog_workflow.py`、`git diff --check` 通过。

真实批次用本记录续写：独立规划审核、请求次数与用量、原件/失败索引、首稿结构及教学、课程版本/场景/练习绑定、实际浏览器结果。离线通过只证明接线，不代替这些验收。
