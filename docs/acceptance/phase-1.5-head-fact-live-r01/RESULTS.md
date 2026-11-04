# T108：单次四字段事实修订与完整私有课程交付

**本批一次HTTP200；F01/F02解决，完整课程独立教学重评及实际应用验收通过。** 两项非阻断质量问题保留。本批STOP，后续请求0，不自动扩展主题或T038。模型正文来自r03原稿加本次模型四文本修订，助手补写0；原首稿结构失败不追认为通过。

## 实际课程入口

[EduMind开发应用](http://127.0.0.1:5198/)；当前 `t108-fact-r01-live` 预览学习身份已打开新课程，或从首页“继续学习”进入。course `0dbf8532-b1a8-4135-bdd3-5696a2cd6b85`，scene `a0a552dd-db86-48a0-9175-162b3028f830`，课程v2。身份及完整绑定见 [app-binding.json](app-binding.json)。它是实际私有子课程快照，不是独立HTML播放器；其他浏览器身份不会自动取得私有访问权限。

新来源 `targeted_fact_revision`，显示“模型四字段事实修订”、准确父摘要及新协议。原r03失败课程、恢复父课程和旧作答均未覆盖或重新评分；子课程记录父候选关系，使用自己的场景/题组版本，不能把父作答套在新版本上。[实际页面投影检查](page-projection-check.json)核全文和来源等于准确装配、正文与演示替代文本同步，作答前无答案泄露。

原始目标确由原r03实际应用目标表单输入、真实规划选head-new-A；本次精确复用该规划/材料，不新增规划或全文生成，也没有手写规划。代码、事实、轨迹和答案由程序管理；全部教学文字来自真实模型输出及本次四字段真实修订，无助手兜底。

## 准确来源与新旧差异

- 批准提交 `7429407`；准确manifest `a96bab6b252feea6e4541d1c869a9643dabbc12164dc35bfb5dee17f51c5e4b3`。批准登记 [ADR0052](../../ADR/0052-fact-revision-approval-20261104.json)，原冻结提案字节不改。
- 父候选 `7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`；新候选 `4db6214e41291b7aa07f852914eccb56455a6c722a5d976e38764a283b936c8a`。
- [模型四字段原输出](revision.output.json)、[四处新旧逐字差异](revision.diff.json)、[完整合并候选](revision.candidate.json)、[完整私有装配/答案](revision.assembled.private.json)。仅paragraphs[1].text、[5].text、[6].text与learning_summary变化，其余文本/引用/step_notes/题干/解析/代码/事实/轨迹/参考答案/payload全部相同。
- 新summary明确本例data再next不是必要顺序，使用字段前需初始化；新paragraphs[6]和summary明确NULL条件执行、假时只跳过提前返回分支。程序重新装配text-12和head-state.text_alternative，两处逐字同新summary。
- 真实规划摘要b6cc3d...e4991、basis dbfa7a...a28899、材料a3fc33...f7ce1e保持；完整准确值见 [独立重评](INDEPENDENT-ASSESSMENT.md)。

## 单次调用与原件

新窗口北京时间2026-11-04 23:14:53—23:24:53，最多1HTTP，实际1；计划0、全文生成0、自动重试0、额外探测0。实际原件文件mtime显示attempt23:15:17、body23:15:21、STOP23:15:21（本机观察，非独立计时或延迟证明）。收到HTTP200后先保存完整加密body，严格phase/JSON/Schema通过再合并；成功即STOP，无ACTIVE，不再有下一请求。

完整原HTTP为4022字节，SHA `fbaeb8c2b1a0acffeddaee8e5fccbd2d00e42c77450d348d3df8a6e0b946f6f7`；phase final_answer，输入19197/输出598 token为服务自报，实际账单未验证。请求SHA `0320d95d3c502c02cff48b41e4a0e2995c6d77fbfaba3b6d8a027f04d9c96486`。收据、实际请求/attempt、观察记录均在本目录。私有完整原件目录 `/Users/apir/.local/share/edumind/head-goal-fact-r01/`；[原件索引](originals-manifest.json)不含raw.key值或摘要，Provider Key未保存或进入聊天/Git。旧r01/r02/r03原件/失败/STOP保持。

`backend/.venv/bin/python docs/acceptance/phase-1.5-head-fact-live-r01/check_results.py` 实际通过：核准7429407执行树459项摘要；解密回读长度/SHA/收据/请求、准确父/四路径差异及完整装配、单attempt/STOP。独立助手只核安全导出，不声称独立解密HTTP。后续授权的应用来源接线改变当前源码，旧执行manifest不改，历史准确代码通过Git复核；不重新启动旧入口。

## 独立教学和实际学习验收

[逐段/13帧/四题完整独立教学重评](INDEPENDENT-ASSESSMENT.md)、[准确机读pass](final-review.json)：F01/F02解决；作用域、返回值、可达性、四题答案/解析与代码状态一致，无直接泄题。非阻断Q01：两处替换复制相邻原段，阅读冗余；Q02：引用保持原值后粒度不足，不能声称ID存在即证明语义。必要讲解仍由完整代码、帧和新summary覆盖，理由及精确位置在报告中。没有改引用、删冗余或追加调用。

[独立实际浏览器报告](BROWSER-ASSESSMENT.md)、[原始浏览器记录](independent-browser-learning.json)：新guest实际导入同一准确候选、来源/父摘要检查，13帧状态/高亮/作用域及播放/暂停/前后步/重置通过；四题全错0%/正确100%，四解析逐字等模型原文，scene读取不含私有答案；刷新前后scene和最新attempt完整对象相等，刷新新增POST0。独立副本是同一候选的本地实例，不计额外模型成功。

刷新后“继续完善或新作答”按钮消失、表单直接可编辑这一既有差异如实保留，答案/解析/版本不变，未扩建表单持久化或声称整个DOM逐字相等。截图本机 `data/screenshots/t108-fact-r01-independent.png`，不提交生成媒体。独立重评和浏览器验收均无新Provider。

## 必要工程检查与边界

- 已执行11项定向请求/合并/装配/单入口Mock回归；新来源真实PG事务回滚检查，覆盖准入、来源篡改拒绝、私有答案投影/幂等、原r03仍failed/v1/0候选。
- 新发布服务mypy、变更Python Ruff、前端类型/构建/ESLint、工作流与diff检查通过。未重跑无关全量套件。
- 新发布只补固定真实候选/准确review pass/原件收据/来源约束，沿用store_plan、commit_outline、机械准入、commit_scene、私有反馈和既有Vue组件；无新播放器/调度器、无迁移。数据库sent_attempts=1/usage归因于本次唯一历史HTTP，本地多身份副本不能相加当调用。
- 真实候选到手后按已批准ADR补来源enum/协议/准确父指针及pass约束，未改教学Schema。没有把HTTP接受、结构通过或旧父版浏览器成绩当成新课完成。

本次完成限定头插新目标课程的有限交付；不是学生学习效果实验、稳定率证明、T038多主题准入或生产动态开放。T102保持blocked，catalog_only/H/旧评分权限不变。完成提交后停止，由用户决定后续。
