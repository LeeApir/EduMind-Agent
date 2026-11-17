# T118：空链表头插执行包

本包仅完成零调用准备。课程目标是首次插入时把 `t0.next` 写为 `NULL`，第二次接住返回值时把 `t1.next` 连到 `t0`，两次接收后可遍历 `[7,4]`；两次忽略后调用者入口仍为 `NULL`，两个动态节点从该入口均不可达，并未自动释放。精确表单输入见 [goal.txt](goal.txt)。

- [独立参考](independent-reference.json)：逐帧、接收／忽略、四题答案的人工预期（非模型正文）。
- [规划请求](planning-request.template.json)、[规划本地 Schema](planning-local.schema.json)、[正文请求](teaching-request.template.json)：实际构造器导出。发送前只绑定实际操作的三项 UUID；正文另绑定同批机械校验及独立审核通过的模型规划。正文所需代码、13 帧、两类补充事实、题目情境和答案已固定。请求以规范 JSON 字节发送，文件末尾用于保存的 LF 不发送。实际请求在发送前核对并保存。
- [配置](candidate-config.json)、[批准模板](approval.template.json)、[冻结清单](manifest.json)：模板默认不授权；入口验证清单、单独批准及实际 context 摘要。
- [准入差异](../../ADR/0058-t118-empty-head-supplement.md)：独立审查本批差异；既有批次保持。

## 待决定

1. 是否同意本批题干只产出单行文字、情境代码按固定题键原样装配，以及本批禁止格式恢复和模型修订。不得以放宽教学校验、改题义或补写取代通过。
2. 是否批准准确 manifest 和拟议的 DeepSeek 路线：`https://api.deepseek.com/responses`，请求 `deepseek-flash`、非流式、`store=false`、`temperature=0.2`、`reasoning.effort=none`、strict JSON Schema；最多 **规划 1、正文 1、修订 0**。无旧余额、重试、探测或回退。
3. 是否接受本批 C2 例外：请求和服务端回报分别留存；模型快照、实际留存及账单没有独立确认。每次本地输入预约 139,264 tokens，输出配置 8,000 tokens，合计分别 278,528、16,000；这些不构成费用硬上限。金额未知。单前台尽力停止仍可能迟发或继续计费，本地加密原件没有独立抗回滚保障。

## 执行顺序（仅获准后）

1. 仓库根用 `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile empty --prepare --start` 准备隔离库和 [开发目标表单](http://127.0.0.1:5208/)，API 8188。已有进程可复用。新访客，从表单只提交一次准确目标，保留该访客会话供验收。**提交前先安排评估与终端**；数据库操作创建时开始 1,800 秒窗口，登记创建及截止时刻；规划、正文、准入及学习验收在该窗口内完成。发送时至少余 90 秒；HTTP 客户端 I/O 超时 90 秒，各请求／响应体分别限制 128 KiB／2 MiB。
2. 使用 `/tmp/edumind-t118/env.json` 的本地 DB/应用配置启动干净进程（无 `.env` 或 Provider 环境凭据）。新 vault 为 `~/.local/share/edumind/head-empty-deepseek-r01`，0700，新的 Fernet `raw.key` 0600，保留原件及密钥独立于仓库。实际执行入口为 `backend/.venv/bin/python -m scripts.head_course_goal --profile empty`，各步同加 `--vault <准确绝对路径>`。先以 `--prepare --owner UUID --course UUID --operation UUID` 核对并绑定真实应用操作，准备批准记录，后续各步加 `--approval <本批记录>`。Key 只在终端的隐藏提示输入。
3. `--send plan` 一次。保留完整响应与计划绑定。独立评估检查原目标和先备知识来源、唯一示例、首次/第二次连接、接收/忽略及教学顺序；`plan-review.json` 写入计划摘要、依据 binding、评估人、pass、空 `blocking_findings`，并将 `checks.empty_goal_and_sequence`、`checks.same_example_and_caller_comparison` 分别记为实查结果。只有通过才运行 `--send generate` 一次。
4. 正文机械通过后，独立评估逐段、逐帧、逐题核对事实引用、目标覆盖、指针作用域、两次判空和未展示失败、回收与可达性、四题条件/唯一答案/解析且无暗示。最终 `final-review.json` 绑定候选、空父摘要、依据和证据摘要、评估人、结论、阻断意见；须通过既有固定课程项目（`full_lesson`、`fact_citations`、`paragraph_responsibilities`、`no_neighbour_copy`、`no_omitted_explanation`、`code_trace_answers`、`no_answer_hints`、`display_scope`、`return_contrast`、`whole_lesson_consistency`）及 `empty_first_and_second_links`、`question_conditions_and_unique_answers`。审核者依据实际候选和程序材料出具意见，不能预填。通过才 `--publish`（私有草稿准入）。
5. 在原访客实际课程页检查完整阅读、13 帧状态与高亮、播放/暂停/前后步/重置、四题正确/错误反馈、页面与读取 API 的答案隔离、刷新同版本及反馈恢复且不重复提交。统一结果记录链接课程 URL、版本/场景/题组、目标/规划/证据/候选摘要、独立审核、HTTP 用量和各项实测证据。离线夹具不计入课程验收。

协议失败、拒绝/截断、超限、澄清、机械或教学失败、取消、超时或未知结果时停止并封存；不放行正文、不重发、不恢复旧操作。加密响应及收据在解析前保存，记录失败及 `STOP`；独立评估拒绝时记录该审核、写入 `STOP` 并用原访客的取消操作封住应用写入（无 worker 时 API 可能保持 `cancel_requested`，如实记录；本地 `STOP` 禁止再次发送）。保存每次是否实际出站、实际 HTTP 状态、Provider 回报用量及未知项。保留未交付和已经生成但尚未验收的区别。
