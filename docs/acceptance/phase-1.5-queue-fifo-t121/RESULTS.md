# T121 队列课程统一结果

2026-11-10 完成零调用准备。真实首稿、独立教学审核和队列课程浏览器验收待准确授权。

| 操作完成后 | 有效元素（队头到队尾） | 队头 | 队尾 | 本步出队 |
| --- | --- | --- | --- | --- |
| 初始化 | `[]` | 无 | 无 | 无 |
| `enqueue(3)` | `[3]` | 3 | 3 | 无 |
| `enqueue(8)` | `[3,8]` | 3 | 8 | 无 |
| `dequeue()` | `[8]` | 8 | 8 | 3 |
| `enqueue(5)` | `[8,5]` | 8 | 5 | 无 |

共用 CLI 的队列主题提供检查、准备、发送、严格重放、准入及停止。固定提纲流程从原栈代码提取，沿用 T120 的传输、封存和已有私有仓储。队列适配只提供专属目标、提纲、程序材料、教学检查和播放投影。原栈首稿请求与历史文件逐字节相等。真实队列批次使用新的专用库和私有封存目录，MockTransport 夹具限于独立测试库。

| 复核 | 实际结果 |
| --- | --- |
| `pytest -q backend/tests/test_queue_course_trial.py backend/tests/test_course_trial_transport.py backend/tests/test_head_course_deepseek_wire.py` | 23 项通过。Clang C11 断言独立核对五帧、FIFO、前移、判空判满及迁移数据。隔离 PostgreSQL 验证错批次、错审核、异常响应保全、重复发送拒绝，以及私有 v2、四题反馈、答案隔离和版本回读 |
| `pnpm typecheck` 与 `pnpm exec vitest run tests/course-visualization.spec.ts tests/head-course-status.spec.ts` | 13 项通过，覆盖五帧队头、队尾、出队结果和逐行高亮。定向 ESLint 无错误，保留 4 条原模板换行警告 |
| `scripts.check_course_trial_replay` 在当前代码的临时本机应用执行 | T118、T119 原冻结读取器均通过。实际 Chromium 同一访客验收 13 帧和 5 帧、播放、四题反馈及刷新。7 个隔离库反例被拒绝，43 个原封存文件摘要一致。[回归明细](replay-regression.json) |
| 本机队列开发入口及批准门禁 | API 健康、Web 200，普通生成 POST 409。没有本批封存目录时执行共用 `send --topic queue`，在提示密钥前即拒绝。没有创建真实生成操作 |
| 静态检查与冻结 | Ruff、工作流、Git 差异检查和 `scripts.course_trial inspect --topic queue` 通过。历史冻结目录的 Git 差异为空 |

Provider 调用 **0**。下一步需批准准确执行包、30 分钟窗口、单次 DeepSeek 首稿及 C2 例外。真实首稿通过独立审核后，才进入实际私有课程和浏览器验收。[准确执行包](README.md)

## 真实首稿与停止

用户批准检查点 `78e5c5c` 与本批 C2 例外。实际窗口为北京时间 2026-11-10 17:49:00 至 18:19:00。通过共用入口发送 1 次 DeepSeek Responses 正文请求，规划、修订、重试及回退均为 0。HTTP 200，回报输入 2,817 tokens、输出 1,263 tokens。实际账单、具体模型快照及服务端留存未独立确认。[批准登记](../../ADR/0061-t121-approval-20261110.json)

首稿候选 `39742e3ccc803c1afe313c7d90dc69fb778ea349227db248a09decd295c1cb97` 通过共用入口严格重放。本地原件保全了准确请求、加密响应、HTTP 回执、候选和绑定审核。格式恢复、模型修订和助手正文改写均为 0。[真实结果与原件索引](live-result.json)

独立全文审核 6 项通过、2 项未通过，集中于一处阻断 Q01。审核者独立推演确认五帧、对应的 C 代码行、队列实现边界、四题的唯一答案和解析。初始化帧的“出队值为空”指该步没有出队，属于非阻断措辞。

| 阻断位置 | 原稿结论 | 代码反例 |
| --- | --- | --- |
| `raw_output.paragraphs[2].text` | “被移除的值和新的队头是两个不同的值” | `[3,3]` 出队后，出队值和新队头的值均为 3。二者对应不同的元素位置 |
| 同一段 | “移动后新的队头是原来的第二个元素” | `[3]` 成功出队后为空，没有新队头。仅原队列至少有两个元素时，第二个元素才会成为新队头 |

核对依据为程序代码第 15–19 行及 `dequeue`、`order`。主例取出 3 后的新队头为 8，演示与练习正确。首稿的一般性解释仍未通过，审核以准确候选摘要存入原件目录。

执行 `backend/.venv/bin/python -I /tmp/edumind-t121/entry.py replay` 和 `stop`。保留 `STOP`，追加 `HALT`，取消专用开发应用操作。以原访客的 Chromium 页面会话运行 `backend/.venv/bin/python -I /tmp/edumind-t121/check-stop.py`，确认操作为 `cancel_requested`、队列场景已取消、版本列表只有提纲 v1、就绪场景 0、v2 场景读取返回 404。此次仅通过停止状态检查。真实队列的阅读、播放、反馈与刷新验收因无就绪场景未执行，T121 保持 blocked。

## Q01 单段修订准备

以首稿 `39742e3ccc803c1afe313c7d90dc69fb778ea349227db248a09decd295c1cb97` 为准确父稿，绑定原请求、加密响应、首稿审核、固定提纲及程序材料。新 Schema 仅接受 `paragraph_2_text`，合并只替换 `raw_output.paragraphs[2].text`。原事实引用顺序、其他文字和全部程序材料逐项比对。新操作使用独立批次，原首稿拒绝、STOP、HALT 与取消记录按原摘要核对。[准确请求和执行包](q01-revision/README.md)

| 本步实测 | 结果 |
| --- | --- |
| 隔离 PostgreSQL 与 MockTransport，`pytest -q backend/tests/test_queue_course_revision.py backend/tests/test_queue_course_trial.py backend/tests/test_course_trial_transport.py` | 14 项通过。验证唯一文本叶、原样及邻段拷贝拒绝、旧批准/旧审核拒绝、新操作与私有 v2、答案隔离、协议失败保全和第二次发送拒绝 |
| `pnpm typecheck` 与 `pnpm exec vitest run tests/course-visualization.spec.ts tests/head-course-status.spec.ts` | 类型检查通过，13 项通过 |
| 共用入口 `replay --topic queue/head/stack`（分别执行） | 三份封存候选严格重放通过，队列首稿使用历史冻结提交 `898bbe4`。真实队列父稿的本地占位合并逐项比对通过，未写入原件或准入 |
| 共用入口 `inspect --topic queue-revision`、定向 Ruff、工作流及 Git 差异检查 | 通过。请求 6,453 字节，SHA-256 `173c99bfba7c4967a979455b10e06970dc37e45b92d8aff2805445f71b4da4af`。清单 SHA-256 `fe47c6b1650e4024178c991088e51a8b5e6a2975e6b916f5c141b85e75f7dd6b` |

本步 Provider 调用为 **0**，没有创建修订批次原件目录或应用操作。拟新开 30 分钟窗口，规划 0、整课生成 0、Q01 修订 1，费用及停止语义见 [ADR0061 补充提案](../../ADR/0061-t121-q01-revision.md)。等待准确授权。真实修订、独立全文重评和实际学习验收仍待执行，T121 保持 blocked。
