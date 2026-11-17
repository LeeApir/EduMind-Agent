# T108 r03 程序格式恢复：完整私有审查预览

本轮已交付**完整派生课程预览**，交互可用，独立教学评估 `needs_revision`，T108 继续 blocked。没有助手补写，没有新 Provider 调用，没有重启 r03 或继承剩余额度。

## 课程入口

[EduMind 本机开发应用](http://127.0.0.1:5198/)，当前审查浏览器上下文 `t108-recovery-review` 已进入课程 v2；也可从首页“继续你的学习”打开同名课程。该会话 course=`88004ec4-7a7e-42a3-aeda-b2afda4a89c5`，scene=`1fba7567-c4b2-4538-8d8d-8f9950f93839`。这是一份私有课程：另一浏览器学习身份不会自动取得访问权。

当前开发服务器仍复用原 T108 仅回环实例 API8178/Web5198，Provider factories 和外网访问被禁，无 Worker。需重建其他本机预览身份时，在该身份已建立会话后，本地运行 `scripts/import_head_course_recovery.py --import-preview --owner <该guest UUID>`，使用既有专用开发数据库环境；不复制身份凭据、不触发模型。默认不传 owner 则导入原 r03 owner，准确绑定见 [app-binding.json](app-binding.json)。原身份下另有同一候选的预览，两者不计两个模型课程成功。

[完整候选和来源](recovered.record.json)、[完整私有装配及答案](assembled.private.json)、[原始模型正文（含重复成员）](original-output.txt)。课程仍有已知教学问题，页面强制“程序格式恢复／教学评估未通过／仅供审查预览”，不冒充合格课程。截图保存在本机 `data/screenshots/t108-r03-recovery-course.png`，未提交生成媒体。

## 恢复与绑定

- 固定规则 `head-questions-identical-duplicate-v1`，只删除 `/questions` 四题各自第二次出现的**完全相同**成员。逐层字段、类型、内容相等；不使用 last-wins，不补字段、改题干或解析。规范化 JSON 序列化不改任何字符串或教学值。
- r03 完整 HTTP 原件仍在私有 vault 加密保存，原件 SHA `4f05e35015c83b5660c3508e3b7e63671036ece326637ffeb56d5cf9d9f169ee`，19720字节。旧原件索引、失败、STOP/ACTIVE全部核对未变；旧正文严格入口继续报 `DUPLICATE_JSON_KEY`。
- 恢复记录逐条列四个重复位置、对象成员序号、值摘要；原请求、原目标、自述先备、真实规划、同版程序材料、模型输出和页面候选均保留对应。候选=`7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`。
- 原规划独立 pass，plan=`b6cc3d5304b87673c343a9cf31f11ae2cf8b44d4f12a07e852795ac71d4e4991`；选例 head-new-A，材料=`a3fc33abf64a99528d9d2a94a66f9b0721e226e48084d18b384a788a8cf7ce1e`。接入复制准确模型规划，未手写新规划。
- 恢复后通过原完整响应适配、教学 Schema、事实引用、迁移题准确代码场景、13帧及轨迹绑定。使用原装配、私有答案隔离、版本和播放器；新课程是本地派生快照操作，原 r03 课程/失败操作保持原样。
- 来源 `program_format_recovery` / `head-goal-r03-derived`，模型教学原文＋程序共享代码/事实/轨迹/答案＋程序格式恢复，助手教学修改0。原首次结构合格仍为0；当前完整派生预览不计为模型首稿结构成功或 T038 样本成功。
- 唯一契约变化集中于 [ADR0052 补充](../../ADR/0052-identical-duplicate-recovery.md)。产品来源对象增加派生证据及独立审查状态，教学输出 Schema 未改。数据库 sent_attempts=1/usage归因于历史 r03 正文一次请求，本轮 HTTP0，不能把本地副本相加当新调用。

## 实际检查

| 检查 | 实际结果 |
| --- | --- |
| 14项恢复回归 | 同值恢复、正常输出不变、冲突／第三次／范围外／嵌套／缺字段／截断／语法／非有限值拒绝全部通过。 |
| `backend/.venv/bin/python scripts/prepare_head_course_recovery.py --check` | 对批准4986af7 Git树427项摘要复核，旧冻结包不修改；解密核原件与收据/请求/plan/mapping/basis/独立pass，再现原严格失败并完整重验派生候选，通过。当前实现与旧冻结运行源码的授权差异不追认回旧包。 |
| `scripts/check_head_course_recovery_db.py`（专用开发库，事务回滚） | 真实PG机械准入、独立审查门禁、伪造首次合格来源拒绝、答案私有投影和幂等读取通过；第一次测试自身修改只追加ORM对象被数据库拒绝并回滚，改用脱离ORM的副本作篡改反例后同组通过。未削弱数据库保护。 |
| 实际 Chromium 阅读/演示（MCP Playwright `browser_snapshot` / `browser_evaluate`） | 首页打开完整课程，13帧的模型note/状态/作用域/代码高亮逐项对应，前后步/重置及播放推进/暂停稳定通过。 |
| 实际服务端作答 | 全错有效输入0%、四题正确输入100%，两次POST201；JSON数组支持空格和换行。全部完成后四题解析与模型原文一致；作答前场景响应不含答案和solution。 |
| 实际整页刷新（`browser_navigate` / `browser_evaluate`） | 同一场景内容逐对象相同、v2/候选摘要/题组版本/100%反馈恢复；页面仍醒目标明未通过。原文各段与装配及所有四题解析逐项相同。详见 [browser-learning.json](browser-learning.json)。 |
| 静态检查 | 两个新服务mypy、变更Python的Ruff、变更Vue/TS的ESLint、web类型及构建通过。检查限本次恢复/来源接线，未重跑无关全量回归。 |

独立评估助手还使用独立 Python Chromium、新 guest 复验同一候选，实际13帧/高亮/作用域/控制、错0%→对100%、完整场景及最新attempt响应刷新前后相等、刷新新增POST0、答案隐藏和四解析原文一致通过。详见 [独立浏览器报告](BROWSER-ASSESSMENT.md)和[实际记录](independent-browser-learning.json)。独立核验实例是同一候选的本地副本，不增加模型成功数。

保留 [首次完整流程检查失败](independent-browser-learning.failed-r01.json)和[定位失败](independent-browser-learning.failed-r02.json)：整个练习区文本相等断言失败，准确差异仅“继续完善或新作答”按钮刷新后消失，表单已直接可编辑；题干、答案、解析、API场景及attempt相同。未修改既有表单状态处理，不宣称整个DOM逐字相等。预备工具/401失败的保存局限在独立报告中如实说明，未伪造日志。[最终实际检查脚本快照](independent-browser-check.source.txt)按原字节保存，供审查，勿覆盖历史结果重跑。

所有真实调用次数仍以原件 attempt 为准：r03计划1＋正文1，本轮新增0。独立助手对安全导出做检查，没有独立解密私有HTTP原件；原件解密证明由执行方脚本提供，二者边界不混同。

## 独立教学结论及停止点

[逐段、13帧、四题独立评估](INDEPENDENT-ASSESSMENT.md)及[准确机器结论](final-review.json)：四题答案/解析和状态轨迹正确，未发现直接泄题；整体 `needs_revision`，两项阻断：

1. **F01：** `paragraphs[1]`、`paragraphs[6]`、`learning_summary`（页面 text-2/text-7/text-12、head-state替代文本）把“先写data再写next”说成安全遍历的必要条件。实际两字段写入可交换，前提是使用相应字段前已初始化；原文会形成错误因果。
2. **F02：** `learning_summary` 说成功路径跳过 NULL 检查，与 f02/f08 确实求值条件相矛盾。跳过的是提前返回分支。相关正文前后说法不统一。

本轮仅删除相同重复成员，没有权限修改上述事实内容；因此保留原文和准确问题。私有 ready 只表示完整可读，不等于语义签核。T108 最终合格课程目标未完成，保持 blocked；无 Task-Completed 标记。已停止批次及失败保留，T102仍blocked，本轮交回后停止，不自动改正文、调用模型或扩展实验。
