# T109：B 课程局部修订交付

实际私有课程已交付并通过独立全文教学重评与浏览器学习流程检查。应用入口：http://127.0.0.1:5198/ 。当前浏览器已停在课程阅读页；同一学习身份可从“我的学习”继续进入含 `head-new-B`、初始 `[-8]`、插入 `6、0` 的目标课程。

课程 ID `eabc1bbb-1d5a-4b0c-9e8d-78ca3157b9ce`，阅读版本 **v2**，场景 `bdd02733-7376-4929-a29a-d7199752220c`。页面为现有应用课程页，非独立播放器；这是私有 AI 草稿，未签核，反馈为课程内暂定比较。其他浏览器身份不能据此获得访问权。

## 新旧课程及来源

| 对象 | 准确版本／结果 |
| --- | --- |
| 原真实规划 | `f99469ee1ec137e51423337160a7e6066287cadbebb6753547202a5d68763330`，沿用 r01 的真实规划，不重新生成或手写 |
| 原 B 父候选 | `63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd` |
| 程序补充证据 | `head-teaching-evidence-v1`／`3d7bbd32b2ca6895fc62ce46dc1f1396488e6edd78b4dd21fac09eb4c0a8c754` |
| 新候选 | `560ae12dd987b2718f7f82c2f971177e9a79e7bb6595a9f87e3c663f17172ff0` |
| 新来源 | `head-reuse-evidence-revision-r01`／`head-evidence-local-revision-v1`／`evidence_bound_local_revision` |
| 实际页面 | [app-binding.json](app-binding.json)，API／正文／演示／练习绑定上述同一新候选 |
| 原失败 | [r01 原记录](../phase-1.5-head-reuse-live-r01/RESULTS.md)，STOP、教学 stop、原 failed/v1 及原件不变 |

教学正文、13 帧说明、四题题干和解析均来自原真实模型稿；本批只有 `failure_scope` 的替换文本由一次真实模型修订产生。`paragraphs[5].text` 逐字保留，引用改为独立对照 ID；助手教学补写 **0**。代码、状态、轨迹、事实、答案、证据和页面装配由程序管理。新证据独立版本化，未把它偷偷加入旧目录或伪用旧摘要。

**原批未证明“不需补接点即可直达第二课”。** r01 曾因证据及允许修订范围缺口停止，后续 T110 与本次准确准备是另批已披露的接点补充。本次新修订候选在批准的 `640b4cc` 冻结运行树上完成调用、准入和学习，无后续运行源码修改；这项证据不追认原批成功，也不证明通用复用能力。

## 两项问题的闭合

| 问题 | 模型修订与程序证据 | 独立结论 |
| --- | --- | --- |
| S01：把静态不分配能力说成已演示 | 新 `failure_scope` 说明主 f00–f12 两次分配成功、f02/f08 两次 NULL 条件均求值为假后继续。掩码关闭及真实 malloc 失败未展示。证据 `head_evidence_v1.displayed_success_path`。 | 展示范围、判空和失败返回旧 head 的区别正确 |
| C01：忽略返回的段落引用 normal 路径 | 保留正确算法全文，只把 `paragraphs[5].fact_ids` 改为 `head_evidence_v1.discard_return_comparison`。该依据为独立计算、非主动画：caller 仍 i0、可达 [-8]、t0/t1 不可达。 | 引用可支持结论，未删除解释或复制邻段 |

实际叶子差异只有 `failure_scope` 与 `paragraphs[5].fact_ids`；其他教学字段不变。payload 仅增加准确程序证据，原代码／轨迹／答案／规划／目标／依据不变。见 [完整新旧差异](revision.diff.json)、[机械核验](mechanical-check.json)、[模型替换输出](revision.output.json)、[完整候选](revision.candidate.json) 和 [审核后完整课程装配](approved.assembled.private.json)。页面演示替代文本与正文总结从同一候选装配。

## 实际交付检查

- **独立全文评估 pass**：[教学评估](TEACHING-ASSESSMENT.md)、[准确签署](final-review.json)。评估者重新核对全部 6 段、13 帧、4 题／答案／解析、总结、生命周期和边界，九项检查通过，无阻断；不是仅检查两处旧句。此报告签署时尚未做浏览器验收，其范围原文保留。
- **实际课程阅读与演示通过**：[浏览器记录](browser-reading.json)。中文逐块等于场景 API，代码完整一致；全部 13 帧逐一核对状态、局部作用域、未知字段、数据 0、说明和行高亮。播放／暂停／前后步／重置通过，状态投影 finite_head_foreground／budget=null。
- **四题与反馈通过**：[提交、读取和刷新记录](browser-feedback.json)。四个合法错误答案均不匹配；正确答案均匹配，服务端原解析与模型稿逐题相等。数组空白／换行输入正常。公开场景不含答案键或解析；反馈仅在提交后读取，provisional／course_only。
- **整页刷新通过**：完整 scene JSON、完整 latest attempt JSON 与刷新前完全相等；四个输入恢复；POST 作答共 2 次，刷新新增 0 次，无浏览器脚本错误。
- **旧课程保留**：[只读开发库检查](application-check.json)。原 failed／TEACHING_REVIEW_FAILED、v1、1 条规划结果和 0 条正文准入不变；新子课程独立 v2／succeeded，完整请求／原件／审核存储绑定重新校验 accepted。

这是助手独立教学评估及开发浏览器验收，不是学生学习效果实验或正式签核；不扩展主题、T038 或生产动态权限。T102 继续 blocked。

## 执行与原件

新批准绑定提交 `640b4cc3f3990037ff0f3e7471de09c244b78710`，454 项准确 manifest `106152b051afd8c28d11636f5f181e1a40b8784ec1306f1a5c4204809596b6b3`，请求 50,920 字节。[批准登记](../../ADR/0054-b-local-revision-approval-20261105.json) 的 window_started=false 是批准时快照；实际窗口单独登记于 [执行记录](execution-window.json)：2026-11-05 16:12:32–16:22:32 +08。

本批实际 **1 次修订 HTTP200，0 规划，0 全文生成，0 重试，0 格式恢复**；已 STOP，无 ACTIVE、无剩余调用或自动后续。r01 原 2 次与本批 1 次分批记录，不继承预算。响应 3,252 字节、SHA `55610671a36014f6e3f26ddd503bb352878d1a138aa838713037de10eba52aa3`；Provider 自报 14,886 输入／366 输出 token，不代表可验证账单金额。

[准确请求](revision.request.json)、[完整原始响应](revision.raw.json)、[收据](revision.body.json)、[尝试记录](revision.attempt.json)、[完整来源记录](revision.record.json) 及 [STOP](STOP) 均保存。加密原件留在本机私有 vault；[非密钥原件清单](originals-manifest.json) 不包含本地加密键，Provider Key 未保存或导出。原 r01 原件及失败报告留原目录，本次不覆盖。C2 风险仍为已批准的单前台尽力停止／迟发及计费／本机无独立抗回滚／无可验证金额硬上限，未修复 T102。

可复核命令、检查器自身失败与修正见 [CHECKS.md](CHECKS.md)。交付后停止，后续由用户决定。
