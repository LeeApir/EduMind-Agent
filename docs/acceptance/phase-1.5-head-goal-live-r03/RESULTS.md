# T108 r03：规划通过，正文重复JSON键，已停止

2026-11-04。批准提交 `4986af771edf94d9875840534ab4bd3f9de9cbb3`，准确manifest SHA256 `43ec5edb6eb741cad8c324aae4c8037fe90bc0fb65bd70cd623d81b75b5f0850`，见 [r03批准登记](../../ADR/0052-r03-approval-20261104.json)。执行者Codex，独立评估者 `/root/head_goal_independent`。

**本批实际2次HTTP200：带同版依据的规划通过独立语义核验；正文输出重复JSON键，被冻结严格入口拒绝。按包停止，剩余1次失效，没有合格正文候选或完整新课程。** T108最终交付未达成，保持blocked。没有助手补写、选择重复值、修JSON或追加请求。

## 实际阶段与未运行

| 阶段 | 结果 |
| --- | --- |
| 实际应用目标输入 | 5198现有表单提交准确原目标，POST201，新身份/课程/操作见app-binding.json；自述先备保留，其他学情未知。 |
| 规划 | 1 HTTP200，完整6762字节body加密保存并回读核验；wire v2→原local严格校验，选新head-new-A，保存规划与v1大纲。 |
| 独立规划核验 | **pass**，见[PLAN-ASSESSMENT.md](PLAN-ASSESSMENT.md)与plan-review.json。目标/引文/先备、head/caller_head作用域、p->next/return p及接收忽略后果一致；plan和正文输入绑定同一basis/materials。此成绩保留，不因正文失败抹去。 |
| 正文 | 1 HTTP200，完整19720字节body先加密/fsync再解析；model_output_text的questions内四题键各重复2次，抛 `PilotError("DUPLICATE_JSON_KEY")`。没有generate.record、合格candidate或页面v2。 |
| 条件措辞修复 | 0，未运行。重复键是输出协议问题，没有合格父候选，不属于获准的普通教学措辞修复，不能挪用第3次请求。 |
| 新完整课程及学习验收 | 0。正文逐段/逐题/逐帧语义评估、入库发布、完整阅读/演示/作答反馈/刷新和独立课程教学效果评估均未运行。不能用规划、HTTP200或旧夹具代替。 |

[独立停止核对](INDEPENDENT-STOP-ASSESSMENT.md)确认应停；评估者没有解密私有raw，其对重复位置的核对依据是执行方安全诊断，未冒称独立读取了正文原件或给出教学pass。

## 准确失败与原件

正文返回phase=final_answer，外层HTTP JSON envelope可严格解析。失败发生在模型output_text：questions下 `link_target`、`normal_values`、`discarded_values`、`unreachable_count` 各出现两次。重复字段不能通过选择后一值、选一份题目或合并字段得到一个新候选。保留重复项的诊断解析只统计结构，不用于装配或归一化正文；没有修改模型输出。

原generate.failure.json保持 `error_type=PilotError`、`code=null`、`state=failed_or_unknown`；没有追改入口原失败。补充generate-diagnostic.json记录准确代码、层级和重复计数，并标明不是候选。原始输出完整保留在私有generate.raw.enc中；本公开交付不把宽松解析出的对象或其中任一重复版本冒作完整课程。

正文原body SHA256为 `4f05e35015c83b5660c3508e3b7e63671036ece326637ffeb56d5cf9d9f169ee`；规划原body SHA256为 `c2143d9544007870800204831578aff2615f5f0eb12851e351a2d077f12281ca`。准确请求、attempt、收据、规划原wire/mapping/binding、规划pass、补充诊断和STOP/ACTIVE均保留。正文实际请求逐对象等于冻结 `m.body(plan.binding.payload)`，独立报告核对其请求SHA与同版basis。

新原件目录 `/Users/apir/.local/share/edumind/head-goal-r03/` 为0700，raw.key为0600，不导出密钥值或摘要。originals-manifest.json列明公开可核对的原件SHA及私有位置。两份完整HTTP body仍加密保存；Key仅在终端getpass输入，没有读取项目.env/Provider环境变量、旧Key或终端记录。两份最小环境包装已保存，不含Key。原件只有本机保管，无独立抗回滚保障；r01/r02/T106原件、失败和STOP不变。

## 窗口、停止和用量

窗口事前登记为 **10:24:46—10:34:46（Asia/Shanghai）**，600秒不续。实际新操作期限为10:35:11.371879，较晚，批准窗口较早。原初始登记的actual_http_requests=0已在最终执行摘要更新为2；原attempt的attempted_unknown字段保持原字节，由收据及后续结果分别说明。

本机mtime观察：规划attempt 10:27:17.425、body10:27:21.806；正文attempt10:32:00.416、body10:32:21.361，failure和STOP为10:32:21.433。这些只是本地文件观察，不当作独立网络时延证明。正文失败时仍在窗口内，但按包立即停，不能用剩余时间修协议。ACTIVE/STOP保留，没有清锁续跑。

Provider自报规划输入4879/输出683，正文输入8948/输出4697，合计输入13827/输出5380；正文用量仅由有效外层envelope安全提取，未形成合格正文结果。实际金额和账单未验证，不能把这些数值当作硬费用上限。单前台尽力停止、可能迟发/继续计费及本机证据局限仍保持，不宣称修复T102。

## 应用状态与必要收尾

入口 [http://127.0.0.1:5198](http://127.0.0.1:5198)，本次私有浏览器身份 `t108-live-r03`，课程 `3b616a36-e0c3-4b80-8d60-ee3cff4c053b`；其他身份不能越权读取。没有分享或换owner，不覆盖旧课。

为避免页面继续等待已停批的生成，调用既有Scheduler终态服务：首次申请活动写围栏时操作已到期，正确返回OPERATION_FENCED，事务回滚无修改；随后沿既有reconcile使用的 `_locked(live=False)` 锁内报告收尾模式，仅将准确操作记为failed/SCHEMA_INVALID并追加终态事件。没有申请新执行租约、改deadline、Worker/dispatch/Provider或新监督器。实际PG保留1份规划/v1、0场景生成候选。详见app-stop-result.json。

实际页面只读“重新读取进度”后显示原目标、1场景v1及“生成未完成”，没有正文/演示/题组。截图 `data/screenshots/t108-r03-stopped-app.png` 为本机证据，不提交媒体。这只核对失败状态与历史保留，不是完整课程学习和刷新验收。

## 检查与交接

- `backend/.venv/bin/python docs/acceptance/phase-1.5-head-goal-live-r03/check_results.py`：解密回读两完整body、准确请求/原稿mapping/basis/规划pass、真实重复键、STOP/余1失效与未运行项核对；不调用Provider、不读Key/终端、不导出正文值。
- 原准确包 `--check`及冻结CLI `--inspect`通过，摘要未改；命令输出provider_calls=0只指检查命令，**本批历史实际为2次**。
- 实际PG终态及浏览器只读刷新、独立规划pass/停止核对、工作流/diff/链接与旧包/其他Task/日志前缀核对；无运行代码变更，不重复原36项准备或其他全量回归。

本批停止，剩余1许可失效。真实规划语义通过是新增证据，最终新完整课程仍未交付；T108/T102保持blocked，不自动修正文协议、追加实验、换Provider、扩主题或启动T038。后续由用户决定。
