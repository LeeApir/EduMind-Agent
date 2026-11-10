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

## r01 已停止

用户批准 `194086a` 及本批 C2 例外后，于北京时间 2026-11-10 08:23:02 创建应用操作，原截止为 08:53:02。准确授权、课程和操作 ID 见 [批准登记](../../ADR/0058-t118-approval-20261110.json)。

本机前台在密钥输入阶段收到 `KeyboardInterrupt`。原件目录 `~/.local/share/edumind/head-empty-deepseek-r01` 保留 `plan.prepared-request.json`、`plan.failure.json`、`ACTIVE` 和 `STOP`。没有 `*.attempt.json`、HTTP 收据或原始响应。实际 HTTP 尝试 0，规划、正文和修订均为 0，无可报告的 Provider 用量。使用现有取消服务对该绑定操作发出取消请求，回读为 `cancel_requested`、`finite_head_foreground`，`head_version=null`。浏览器原标签页已不可用，因此这一步通过本机后端取消服务执行。

用户要求另开独立批次。[r02 执行包](../phase-1.5-head-empty-t118-r02/README.md)复用完全相同的请求模板与独立参考，分离批标、库、原件及授权。隔离 PostgreSQL 上的 22 项离线检查通过，包括跨批操作和批准拒绝、准入来源、四题反馈及 STOP。原 `194086a` 归档清单 409 项全部复核；新清单 410 项、Ruff、前端类型检查与工作流校验通过。r02 的实际操作及窗口待另行授权。

## r02 实际生成及独立审核

r02 的 30 分钟窗口于北京时间 2026-11-10 08:33:36 登记，原截止为 09:03:36。对应检查点 `f4cd8ad`，新操作和准确清单见 [r02 批准登记](../../ADR/0058-t118-r02-approval-20261110.json)。实际发送规划 1 次、正文 1 次、修订 0 次。两次均为 DeepSeek 官方直连 HTTP 200，回报模型标签 `deepseek-flash`。实际模型快照、服务端留存和账单均无独立确认。

| 阶段 | 首次结构 | 独立审核 | 输入 / 输出 tokens |
|---|---|---|---|
| 规划 | 通过，完整回执及本地映射重放一致 | 通过，目标、空链表的两次链接、变量作用域与调用者对照符合程序依据 | 3,647 / 855 |
| 正文 | 通过，完整回执、原请求 Schema、事实 ID 合法性、帧序列、四题题干与情境装配检查通过 | STOP，12 项中 11 项通过，`fact_citations=false` | 10,498 / 2,918 |
| 合计 | 2 次 HTTP | 无格式恢复、修订或助手补写 | 14,145 / 3,773 |

独立评估者 `t118_r02_independent` 的唯一阻断 `C01` 位于第 5 段 `raw_output.paragraphs[4].fact_ids`。该段写道「若不接收，insert 内部虽然建好了结点，caller_head 仍是 NULL，新结点从 caller_head 出发不可达。」只引用的 `trace_step_05` 对应接收路径 f06，记录的是 `caller_head=t0`。此断言需要引用 `head_evidence_v1.discard_return_comparison`，第 8 段的正确引用无法替第 5 段建立证据绑定。结论本身与对照相符，机械检查验证引用存在，独立审核验证每段引用是否支持具体声明。

其余通过项包含全文完整性、段落职责、无邻段复制、无解释遗漏、代码轨迹与答案、无直接答案提示、实际展示范围、接收与忽略的对照、全文一致性、空链表两次链接、四题条件充分和答案唯一。f04 和 f10 分别完成两次链接，调用者入口分别在 f06、f12 更新。f02/f08 两次判空均为假，失败和忽略对照明确未播放，局部指针作用域与动态节点生命周期区分正确。审核按两种练习情境独立手推四题得到 `NULL`、`[8,6]`、`[]`、`2`，与参考答案和解析相符。

| 绑定 | SHA-256 / 内容摘要 |
|---|---|
| 规划实际请求 | `28ac73f38a71997b60f17e7317083d52bf29bb5375ea11d4a088c52ec984f091` |
| 规划原始响应，7,463 字节 | `55c082f5d22b9680c274a7b494d215aaaa078b84f768454e6c1b2dd0fd838eb5` |
| 规划及其独立审核 | `928cd1b3d60a7fa7a5c19b2b455a5c684c83c07d68aca1cbbfec73f3f024b291` / `e94e4ad815572b791de3852a5552d9b2122909db516e6f677ac209310d79ee8f` |
| 正文实际请求 | `04f7508ab028104cfd50ecf9c1fe1a05eec7c770202b233614383bbbd4813e74` |
| 正文原始响应，15,299 字节 | `31f985fd029768ed54ef7df6cc3802f4b9440e95441a3d2f04b20584281ebcd0` |
| 正文候选及全文审核 | `49fd497d8d45f928eaacb67bdf9bb37ef6ee77ae160e01d7ed70b3cfb339a21c` / `f648de6c8409bbd9daad95c664b19d2d80e633ca573aa90271714bee75456fe8` |
| 同版程序材料及补充教学证据 | `6521537455ce7e11d13c7e5b34f91826413057b93dafc2b63330c8c45653f0e1` / `2eb56295c35ebe2378dbe4032381a7beafcbf9880cb7247c1d47afd15e89f261` |

原件目录 `~/.local/share/edumind/head-empty-deepseek-r02` 保留两组 `*.request.json`、`*.attempt.json`、`*.raw.enc` 和 `*.body.json`，以及 `context.json`、`approval.bound.json`、`plan.mapping.json`、`plan.binding.json`、`generate.record.json`、两份独立审核和 `STOP`。本机重放 `verify_saved`、`review_binding` 通过，停止门禁返回 `HEAD_VAULT_STOPPED_OR_UNSAFE`。通过现有本机取消服务回读 `cancel_requested`，只保留大纲 v1，没有准入、可学课程入口或浏览器学习验收。
