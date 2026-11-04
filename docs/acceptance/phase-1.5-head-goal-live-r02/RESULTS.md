# T108 r02：真实规划成功返回，独立语义核验未通过，已停止

2026-11-04。批准提交 `e8de5f82dcdc90a2406a42b2ae96bb8442860e76`，新批准登记见 [ADR0052 r02](../../ADR/0052-r02-approval-20261104.json)。准确包 manifest SHA256 `41d0bb3aec551b3ad08fa63e711476710c44d43483d41477fb5eb077b72cbc6a`。执行者Codex；独立评估者 `/root/head_goal_independent`。

**本批仅1次真实规划请求，HTTP200，新线格式和完整本地校验通过；规划语义核验不通过，按包停止，未用2次失效。没有新完整课程。** T108最终验收未达成，保持blocked。不能用接口接受、已有回放或夹具代替新课程学习验收。

## 实际结果与未运行

| 阶段 | 结果 |
| --- | --- |
| 实际应用目标输入 | 在5198现有目标表单提交原目标，POST201；新owner/course/operation见app-binding.json。自述先备和未知学情保持，未伪造画像。 |
| 真实规划 | 1 HTTP200，deepseek-flash，message phase=final_answer；完整6312字节HTTP body先加密/fsync再解析，回读与收据SHA/长度一致。 |
| 格式转换与入库 | wire v2→原local v1，完整原稿/mapping/请求绑定保存，本地Schema/来源/集合引用/支持域检查通过；选择新head-new-A，生成1份规划和v1大纲。 |
| 独立规划语义核验 | **不通过**，详见[PLAN-ASSESSMENT.md](PLAN-ASSESSMENT.md)和非pass的plan-review.json，准确plan_digest为 `bcd627a2010322abd0d27d1342c6546ff46f3d0b9232e2a602629784941bc61f`。 |
| 教学首稿、普通措辞修复 | 均0次，未运行；没有符合准入的规划，不允许用正文纠正/覆盖规划或把修复额度挪给规划。 |
| 新课程候选/页面v2/完整学习 | 均未产生。没有可阅读/演示/作答的新完整课程，完整学习及独立课程教学评估未运行。 |

规划原文称“new_node->next = head; head = new_node;”，未区分函数局部参数与调用者入口；本例固定函数执行 `p->next = head; return p;`，局部head保持旧头，调用者以 `caller_head = insert(...)` 更新入口。另称“不接收返回值会丢失链表入口”，没有限定新头/新增前缀；给定非空初始链表仍可从原caller_head访问旧节点。独立核验认为这两点影响本次核心目标，不能补作用域、改原规划或让正文覆盖后判pass。变量new_node/p的别名差异本身没有单独作为缺陷。

接口此次已接受明确简化的规划协议；停止原因是规划内容与同版代码/后果范围不一致。没有再次Schema拒绝，也没有启动下一轮字段补丁、重试或Provider切换。本批不自动修规划，后续策略由用户决定。

## 窗口、停止与费用

新窗口事前登记为 **09:22:56—09:32:56（Asia/Shanghai）**，600秒不可续。用户在终端运行最小环境包装，再在getpass隐藏提示下输入Key。没有读取项目.env、环境变量Provider Key、旧Key或终端记录。

本地文件观察：attempt 09:24:56.398、body 09:25:00.631、binding 09:25:00.780；独立非pass报告时间09:27:23，STOP在09:27:36.785落盘。这些是本机观察，不是独立网络时延证明。attempt原始attempted_unknown字段保持原字节，不事后改写；完整body/转换/后续评估给出分别的结果。

规划请求本身正常完成、验证后ACTIVE已按冻结入口删除；评估失败另写STOP，并将非pass审核及planning-review.failure.json保存在同一原件目录。此时不存在在途请求；没有generate/repair/publish文件。最多3次中实际1次，其余2次在停止时失效，即便尚有窗口也不再调用。

Provider自报输入2327、输出580 token，见plan-observation.json；不是独立账单或实际金额证明。C2未知费用、单前台尽力停止/迟发、本机原件无独立抗回滚保障仍保持，不宣称已修复T102。

## 实际应用与来源保留

入口仍为 [http://127.0.0.1:5198](http://127.0.0.1:5198)，私有身份为本次隔离浏览器 `t108-live-r02`。其他浏览器身份不能越权读此课，不自动分享或复制。新course为 `7b2efb59-1dbb-4129-9bd9-97262f1db75f`，不是旧r01课程或T107回放身份。

用既有 `Scheduler._terminal` 在准确owner/course/operation锁下收尾为failed/PLANNING_REVIEW_FAILED，保留已有规划、v1大纲和不可变期限；没有Worker/dispatch/Provider调用或运行代码修改。app-stop-result.json记录实际PG：planning_results=1、scene_generation_results=0、head_version=1。

实际课程页点击只读“重新读取进度”后显示1场景v1及“生成未完成”，原目标/未签核提示保留，没有正文、演示或题组。截图 `data/screenshots/t108-r02-stopped-app.png` 为本机证据，不提交媒体。此检查只证明停止状态和大纲保留，不冒充完整学习/刷新反馈验收。

## 原件和复核

全部新原件在 `/Users/apir/.local/share/edumind/head-goal-r02/`（0700），raw.key为0600且不导出值或摘要。保留实际approval/context、prepared/实际request、attempt、加密HTTP body/收据、模型wire原输出、版本化mapping、DB绑定、独立非pass、失败与STOP。对应关系和安全SHA见originals-manifest.json；完整HTTP body仍只在私有加密目录，不把Authorization或密钥写入Git。旧r01及T106原件/失败/STOP保持。

安全导出只包括本准确公开目标/自述先备/本次UUID、程序材料及原模型规划，无历史画像或真实学生答案。plan.output.json和plan.mapping.json均与私有原件逐字节相同，未修改模型文字。程序材料依旧标为模拟、非真实C执行。最小终端启动包装保存在plan-terminal-bootstrap.txt，不含Key。

实际检查：

- `backend/.venv/bin/python docs/acceptance/phase-1.5-head-goal-live-r02/check_results.py`：准确包/请求/原件解密长度SHA/转换/非pass/停止与未运行清单核对。
- `backend/.venv/bin/python scripts/prepare_head_course_goal_wire_package.py --check`、冻结CLI `--inspect`：原批准包仍相符，命令输出provider_calls=0仅指检查命令，**本批历史真实请求为1**。
- 实际PG终态及浏览器只读刷新：保留1规划/v1，0完整课程。
- 工作流、diff、旧冻结/失败目录、其他107项Task和日志前缀核对。没有运行代码变更，不重复旧24定向、全量前端/规划/回放/迁移或夹具浏览器套件。

本批交付真实规划原稿、独立未通过及停止证据，最终新课程仍未交付。没有助手补写、规划修复或新的Provider请求；本批停止，待用户决定后续，不自动扩主题、启动T038或恢复T102。
