# T109：head-new-B真实批次停止交接

**本批实际2次HTTP200：真实规划独立通过，正文首稿严格结构通过；独立教学评估stop，未交付可学习的新应用课程，T109保持blocked。** 08:38:48主动STOP，剩余1次请求作废，未格式恢复、未模型修订、助手补写0。没有为本候选修改运行源码，亦不以这一点冒称“流程复用验证通过”。

## 课程原稿及准确评估

- [完整新课程候选](candidate.json)包含真实模型全部讲解、13步说明、四题题干/解析、生命周期/失败边界/总结及同版程序材料；[原正文HTTP响应](generate.raw.json)、[原候选记录](generate.record.json)均保留，没有助手补写。候选摘要`63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`。
- [独立逐段/逐帧/逐题教学评估](TEACHING-ASSESSMENT.md)、[准确审核JSON](final-review.json)：算法主要步骤、13帧（含数据0、两次判空、作用域）、四题参考答案和解析正确，无直接答案提示；仍有下列阻断，不能以局部正确抵消。
- [真实规划独立评估](PLAN-ASSESSMENT.md)、[规划审核](plan-review.json)、[原规划](plan.output.json)。本次模型真实组织目标、引用和教学顺序，明确指定B参数，不是程序手写大纲或C01/C02改名，也不声称自由选例能力。

| 编号 | 准确位置与问题 | 影响及本批处置 |
|---|---|---|
| S01 | `failure_scope`：“只通过 allocation_success 条件掩码演示‘不分配’的分支” | 本课两次mask均true，13帧全成功；仅代码静态有不分配能力。原文将支持能力写成已交付演示，又只否认真实malloc失败动画，范围声明不清。该字段不在批准的paragraphs/summary修订集合，立即停止，不能挪允许段落覆盖它。 |
| C01 | `paragraphs[5].fact_ids`列正常caller已更新的`trace_step_05/10`和主流程分配失败0，却解释忽略返回值后的不可达 | 结论可由同版`planning_basis.ignore_return`及代码独立手算核对，但本段所列ID没有逐项支持反事实分支。不能签本批引用检查；该段单独可修，仍不能越过S01发第三次请求。 |
| E01 | 实际operation/API/页面预算与恢复入口投影 | `free_course_recovery.py`两处仅识别旧`head-goal-course-v1`，漏新`head-reuse-course-v1`。错误显示“已用0/剩余13”和通用恢复入口，未标finite_head_foreground。精确CLI3HTTP/600秒及STOP、API禁止POST新operations的既有middleware仍有效；实际本批2HTTP、余0。属于接线失败，本批不补源码续跑。 |

工程E01的[独立核对](APP-STOP-ASSESSMENT.md)与教学S01/C01分开；原教学审核JSON不改。既定恢复只针对四题同值重复，本次正常JSON不触发；不能把格式恢复用于改这句教学内容。

## 从实际输入到原件的绑定

实际首页输入完整原始目标和先备自述，并明确追加“本次明确使用 head-new-B：初始链表 [-8]，依次插入 6、0。”[实际context](context.json)保留request_1原文、request/course/operation ID及仅B支持域，未知学情未补。程序提供同版[材料](materials.json)：接收后`[0,6,-8]`；忽略两次返回后`[-8]`、t0/t1从caller不可达；迁移题仍是程序提供的独立情境。

规划原wire→本地完整校验/来源/引用/场景覆盖通过，独立语义通过后才调用正文；[规划mapping](plan.mapping.json)、[绑定](plan.binding.json)完整保存。规划摘要`f99469ee1ec137e51423337160a7e6066287cadbebb6753547202a5d68763330`；材料摘要`9aeb6bcf2208528af1d5ed7c8b9906b47fdb8a5fa8247e7798eceed62a0e9012`，B basis摘要`0360ade8fa9999d6bd2d2b5d8994c135c622ffbc0b4d4d0311ee281bdf9b6882`。原请求与冻结构造重建一致，正文实际请求与事先从真实规划派生的30760字节请求完全相等。

本批批准提交`674fc06`，manifest `f4c98c1a24d2943dd7f38350095932f1e933a46757eee3896156439d05bd239b`；[ADR0053准确批准登记](../../ADR/0053-approval-20261105.json)。本次完整原件、失败和课程候选不覆盖T108；所有410项冻结文件及旧包仍原字节。真实运行未新增或修改业务源码、提示词、Schema、执行器或播放器。

## 两次请求、停止与费用

新窗口 **2026-11-05 08:30:09—08:40:09（Asia/Shanghai）**。主流程在08:38:48依据独立评估已定位S01写STOP；独立完整报告签于08:39:58。这些时间和文件mtime仅为本机观察，不提供独立抗回滚或网络时延证明。批准窗口不续；应用自身deadline为08:40:44.492319，不替代较早的批准窗口。

| 阶段 | HTTP/完整body | 结构/语义结果 | Provider自报输入/输出 |
|---|---|---|---|
| 规划 | 200 / 7290字节，SHA `31f6111a4cc8ce891674fc2053ffd0dd39a65314e68c9105e2e9cfe376d52e50` | strict/wire-local/独立语义pass | 4867 / 839 |
| 正文首稿 | 200 / 17052字节，SHA `b5acad36fceae43082f8facc2c0c14990f98d15715b9610f7da8cca554d9fa95` | 首次结构pass；独立教学stop | 9215 / 3669 |
| 格式恢复/模型修订/发布 | 均未运行 | 格式恢复不适用；修订被S01禁止；无v2课程 | 0 / 0新增 |

合计输入14082/输出4508，自报不等于账单，实际金额未知。STOP存在、无ACTIVE、恰好两份attempt；每个原attempt的`attempted_unknown`初始字段保留，用后续完整body/结果说明，不追改原件。剩余1次许可作废，没有第三次探测、修复或重跑；没有读取终端记录、旧Key、项目.env或Provider凭据环境。用户只在getpass隐藏提示下输入Key。`raw.key`仅为本地HTTP体加密key，不是Provider Key，不导出其值或摘要。

[原件索引](originals-manifest.json)定位0700私有vault及两份完整加密响应；[批次结果](batch-result.json)、[窗口最终记录](execution-window.json)、[初始窗口快照](execution-window.initial.json)分别保留。批准的单前台尽力停止、暂停后可能迟发/继续计费、本机无独立抗回滚及金额无可验证硬限仍适用，不追认T102解除。

## 实际应用与未运行验收

入口 [EduMind开发应用](http://127.0.0.1:5198/)；当前浏览器上下文`t108-fact-r01-live`是标签沿用，本次来源/课程没有借用T108回放身份。实际owner `0b1b71df-9b00-470e-abc4-ae41aeb20cf9`，course `6be90c82-adfd-408d-82b6-32125db0dcbf`，operation `ecb65468-da85-4772-8a5d-b7f1bb5e8fa1`，request `200704c7-946b-485e-b0b1-2ff1767845ab`。这些为本次实际应用返回，不是身份替换；其他身份没有自动访问权。

为避免已停生成仍显示运行中，沿既有Scheduler `_locked(live=False)`锁内报告收尾/`_terminal`记failed/TEACHING_REVIEW_FAILED并追加终态事件，不申请执行租约、不改deadline或启动Worker。保留1规划/v1，0场景生成准入行、无场景正文版本、无题组或答题记录。首次报告辅助脚本误读ORM `head_version`字段，事务完整回滚；改用原仓储投影后收尾成功，[失败记录](cleanup-first-failure.json)、[收尾源码证据](app-stop.source.txt)、[实际PG结果](app-stop-result.json)均保留；未修改运行源码或旧数据。

实际浏览器“重新读取进度”后显示准确原目标、1场景v1、“生成未完成”。[实际API和页面读取](app-browser-stop.json)保留E01错误预算及恢复入口，未点击恢复。只读采集的两次工具适配失败也保留在[browser-diagnostics.json](browser-diagnostics.json)，不伪称第一次采集成功。未执行完整阅读/演示/四题反馈/整页刷新恢复验收，因为没有获准发布的完整课程；失败页读取不算完整学习流程通过。

## 必要检查及下一步

- `backend/.venv/bin/python docs/acceptance/phase-1.5-head-reuse-live-r01/check_results.py`：两完整原件解密回读、请求/attempt/候选/规划/basis/审核/STOP/无修订发布/余1失效及v1失败状态通过，确认nonpass不能准入；只读调用Provider0。
- `prepare_head_course_reuse.py --check`及冻结CLI reuse `--inspect`：准确manifest未改；输出Provider0仅指检查，不否定本批实际2HTTP。
- 新只读核对器Ruff，workflow/diff、旧冻结目录/历史108Task/日志只追加和运行源码不变检查。未重复无关全量单元、PG迁移或前端构建。

**本批停止，最终新课程验收未达到，不创建Task-Completed提交。** 后续由用户决定是否及如何处理S01/C01与E01；当前不申请或启动新请求、不临时扩修、不恢复T102，也不推进T038。本次真实结果既不能算课程成功，也不能据此宣称指定示例流程已经无缺口复用。
