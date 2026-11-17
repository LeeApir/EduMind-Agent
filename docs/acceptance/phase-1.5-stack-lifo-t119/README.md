# T119 固定栈课程执行包

本包交付第二主题的必要接线及离线证据。实际模型调用、独立教学评估及实际学习验收待新批准。教学目标见 [goal.txt](goal.txt)。

- 现有目录已有栈讲解和静态 C 代码，课程主链已有普通栈元素显示、播放器、私有版本及服务端判题。T119 增加固定材料、五帧逐行定位、出栈值及明确的栈顶标记，复用同一播放器及反馈流程。
- 主例有效元素按栈底到栈顶列出。初始空栈，依次为 `[] → [3] → [3,8] → [3] → [3,5]`，栈顶依次为无、3、8、3、5，只有第三个操作产生出栈值 8。高亮定位到每个完成的调用者语句，初始化也有一帧。
- 固定容量 3，使用 `count` 确定有效元素区间。满栈入栈和空栈出栈返回 false，失败出栈不改输出参数，成功出栈不会清除物理槽。本例只演示初始化和成功操作。迁移题共享不同数据的完整程序情境，要求指定检查点、一个整数或明确顺序的 JSON 整数数组。参考答案及解析在提交前留在服务端。程序代码只作课程中的文本。
- [独立预期](independent-reference.json) 给出主例逐帧状态和另外一组题目数据的预期。离线测试将同一 C 代码加断言后编译执行，核对有效元素、各次出栈与满空边界。模型教学必须另经全文审核。

[准确请求](request.json) 是实际发送的规范 JSON 字节。程序固定提纲、目标、全部材料、Schema 和提示词，用户、应用操作及会话标识只在本机证据中绑定。[冻结清单](manifest.json) 和 [准入差异](../../ADR/0059-fixed-stack-lifo-course.md) 一起审批。真实执行前，运行 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.stack_course_trial inspect` 核对摘要。

## 待授权的范围

| 项目 | 本批提议 |
| --- | --- |
| 服务和请求 | DeepSeek 官方直连 `https://api.deepseek.com/responses`，请求 `deepseek-flash`，非流式、`store=false`、`temperature=0.2`、`reasoning.effort=none`、strict JSON Schema。按现有封闭回执检查，保存完整原件及用量回报。 |
| 请求数 | **0 次规划、1 次首稿、0 次已纳入修订**。一次发送，无探测、重试或回退。 |
| 时间与用量 | 建立实际操作时开始新 1,800 秒窗口，登记北京时间起止。发送前至少余 90 秒，I/O 超时 90 秒，请求和响应最多 128 KiB／2 MiB。输入回报上限 139,264 tokens、输出请求及回报上限 4,000 tokens。 |
| C2 例外 | 这些限制不构成金额硬上限。实际账单、具体模型快照、服务端留存没有独立确认。前台停止存在迟发和继续计费可能，本机加密原件没有独立抗回滚保障。 |
| 有限修订 | 若首稿机械合格且仅有可定位的讲解措辞、解释缺漏或引用问题，可另提最多一次。允许经审核定位的段落文字及对应事实引用、单帧说明、总结或单题解析。限定确切路径与父稿摘要，重跑机械校验及独立全文审核。代码、状态、帧序、题干、题义和答案均保持。范围、预算及准确修订请求需要单独批准。 |

## 获准后执行

1. 用 `PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile stack --prepare --start` 启动隔离 PostgreSQL 和[本机应用](http://127.0.0.1:5212/)，API 8192。应用进程禁用后台 Provider 和新生成／编辑操作入口。由该应用创建一个私有访客会话，保留同一会话验收。先安排终端及独立审核，再开始操作窗口。
2. 用 `/tmp/edumind-t119/env.json` 的本机开发配置启动干净进程，附 `PYTHONPATH=backend:.`。批准记录须绑定准确 manifest、批次 `stack-lifo-deepseek-r01`、`explicit_user_authorization=true`、`accept_T119_scope_and_batch_C2=true`、`max_http_requests=1`、`window_seconds=1800`。运行 `backend/.venv/bin/python -m scripts.stack_course_trial prepare --owner <访客 UUID> --approval <批准记录>`。此步骤通过既有仓储建立 v1 提纲并启动实际窗口，创建 0700 新证据目录 `~/.local/share/edumind/stack-lifo-deepseek-r01`，绑定操作、材料和批准。
3. 同一环境和仓库根运行 `backend/.venv/bin/python -m scripts.stack_course_trial send` 一次。密钥只在终端隐藏提示输入。使用独立目录加密保全实际响应，保存 HTTP 状态、完整性、原件摘要、用量及 STOP。异常或未知保留已收到的字节和失败，停止该批并以同一入口的 `stop` 子命令取消应用操作。取消应用不能可靠撤回已发的请求。在途需同时停止前台。
4. 只有 `replay` 严格重放成功才交独立审核。评估须核对原目标、初学者适配、全部段落及引用、五帧与高亮、栈顶和出栈结果区别、LIFO、固定容量与展示边界、四题条件/唯一答案/无暗示及正确解析。在证据目录保存逐项意见和 `review.json`，绑定候选摘要、独立评估人、`verdict=pass`、空阻断项及代码中列出的全部实查检查项。只有机械和教学双通过，才在有效窗口内运行 `backend/.venv/bin/python -m scripts.stack_course_trial publish`，生成私有 v2。审核未通过则记录问题及未交付，并执行 `stop`。
5. 用原访客刷新「继续学习」列表，进入 v2，检查完整阅读、五帧和高亮、播放/暂停/前后步/重置、四题正确及错误反馈、答案隔离、刷新同版本与反馈且无重复提交。统一结果记录课程入口、版本、首稿与任何另批修订、独立审核、实际请求次数及用量、保管原件和停止结论。
