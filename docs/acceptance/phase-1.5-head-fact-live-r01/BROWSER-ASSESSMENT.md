# T108 事实修订课程独立实际浏览器验收

2026-11-04。**准确新私有课程的实际学习流程通过。** 已在独立新guest浏览器完成读取讲解、查看代码与全部13帧、播放／暂停／前后步／重置、错答／正确作答及反馈、整页刷新。此前全文静态教学pass继续有效；段落重复和引用粒度的两项非阻断意见保留。没有学生学习效果实验，也不将本课通过扩大为通用生成成功率或T038通过。

## 入口、身份和证据

实际入口 `http://127.0.0.1:5198/`，首页“重新读取”→“继续学习 →”。独立Python Playwright headless Chromium新guest，仅通过页面同源fetch获取user.id，随后 `scripts/import_head_course_fact.py --owner <新guest>` 导入已固定／已独立pass的候选；这次本地导入没有模型调用或新规划，未复制主浏览器凭据。

独立验证实例：owner `5b88da09-df81-469b-a1b6-5bc6960b0a49`；course `50b08a29-aaf6-4ff7-b1b8-2145c8c93cef`；operation `c038dac9-5d29-40cc-b78b-e5f26c6c4dba`；scene `5ec2a74f-61ae-4fbf-8c8d-bae07e50b5d4`；课程v2，场景版本 `63c7d055-9a16-4360-82a3-0cdc1030fb89`，题组版本 `41dbe5a3-244f-56cf-83f3-12053b4b0323`。临时浏览器检查后关闭，用户当前可读实例由主执行方浏览器保留；没有将独立guest凭据导出。

实际命令 `backend/.venv/bin/python /tmp/t108_fact_independent_browser.py`，Chromium依既有环境需要工具批准的沙箱外执行。仅读取明确指定的专用开发DB环境，不输出其值、不读ProviderKey、终端、raw.key或私有原稿vault。独立评估者新增Provider调用为0；本课程四字段文字的真实模型修订仍准确计执行方本批1次，不能与本次本地导入混同。

实际浏览器数据见 independent-browser-learning.json，含13帧可见内容及高亮、实际API响应、两次作答和刷新前后文本。截图 data/screenshots/t108-fact-r01-independent.png，已实际查看。此轮一次运行退出码0，无需重跑；父版预览的工具／脚本失败及记录保持原目录，不覆盖为本版本成功。

## 同版与来源

候选 `4db6214e41291b7aa07f852914eccb56455a6c722a5d976e38764a283b936c8a`；parent `7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`。页面显示“模型四字段事实修订 · 未签核”、deepseek-flash／head-f01-f02-four-text-v1／head-goal-fact-r01、新候选与父摘要、原规划／materials；说明是一次真实请求修订四处文字及程序装配，保留原结构失败、父版和非阻断意见。

没有父版“程序格式恢复”或“新增模型调用为0”的误标，也没有遗留needs_revision警示。课程仍标AI草稿未正式签核；独立教学pass并不提升正式发布或掌握度权限。

独立调用只读publication.mapping核固定安全输入、准确pass和装配，再比对实际场景API：generation_source完全相等；全部text／code／visualization块与准确装配逐对象相等；四题question_id／question／input_type与准确装配相等。API练习项没有answer_key／solution。新summary在实际页面恰出现两份完整相同文本，分别是正文总结和演示替代文本；两处都包含新的初始化和判空正确规则，不是正文新稿／演示旧稿混用。

## 13步和控制

实际逐帧点击并读取data-frame、可见note／节点、active-code-line及scope提示，f00至f12高亮依次为：无、4、5、6、7、8、15、4、5、6、7、8、16。f00／f06／f12显示head/p不在作用域，其他帧活动；未初始化字段显示未知；两次NULL检查均显示第5行条件通过而不提前返回。完整帧对象也与静态教学核对的同版装配相等。

f12后退到f11，重置到f00；播放推进到f02后暂停，继续等待仍为f02。所有控制实际可用，未执行C或启动媒体生成。最终caller链t1→t0→i0→NULL、7→4→12与静态手算一致。

## 四题反馈和刷新

错误答案i1、[0]、[0]、0提交一次，201后GET原记录 `23aa71d7-e2a2-4b83-99d1-c68635f55a3b`，匹配比例0%。之后通过“继续完善或新作答”输入i0、含空格的[11, 30, 40]、含换行的[30,40]、1，201后GET `46ebb344-1fae-4535-bb02-4774b165adc2`，匹配100%。四条question_results.explanation分别与准确候选模型原文逐字一致，判断结果正确。

两次reliability均provisional，mastery_effect均course_only，页面明确仅保留课程内表现、未更新正式掌握度。未以已知正确答案冒充学习者的实际学习增益。

整页刷新前后两次GET场景的完整JSON相等；最新attempt的URL及完整JSON相等，课程／场景／题组／candidate绑定、原始answers、comparison_score和四条解析都未漂移。整个流程仅两个POST attempts，刷新没有第三个提交。场景响应始终不含私有答案。

已知表单差异如父版检查所示：刷新后仅“继续完善或新作答”按钮消失，因locked不持久而表单直接可编辑；移除此按钮行后整个练习section文字相等。脚本保留这一准确差异断言，并以完整场景／attempt对象相等和POST计数核验，不将整节DOM不等误说成版本漂移，也未修改现有表单行为。

## 结论边界

静态教学pass加本次实际流程证据支持这份限定头插私有草稿可完整学习和评估；F01/F02修订已进入实际应用。新快照未覆盖父版，仍准确标父candidate；本次验证仅新增自己的guest课程及两条作答。原r03失败／停止、父预览和旧作答的保留另由主执行方定向持久化检查确认，本评估没有跨身份修改或重评分它们。

final-review.json保持原字节，SHA `24255c6ac09fe2f11bad9c3c1453251f471732218198289a3633807752a89598`；浏览器结果单独记录，不修改已绑定入库的教学结论。两项非阻断质量问题仍可在后续由用户决定是否处理。本批到此停止，不新调用、不扩主题、不恢复T102或旧批次，也不启动T038全量验证。
