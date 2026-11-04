# T108 r03 派生课程独立浏览器复核

2026-11-04。**实际私有审查预览交互可完成；教学结论仍为 needs_revision。** F01必要初始化顺序错误和F02判空总结问题仍在模型原文，来源区域有明确非pass警示；本次没有修改正文，没有新 Provider 调用，不把100%参考匹配当作教学质量通过或正式掌握度。

## 实际入口与独立身份

实际开发入口 `http://127.0.0.1:5198/`，从首页“重新读取”→固定派生课程“继续学习 →”进入。因子代理 MCP Playwright 会话与已占用的主会话冲突，按已授权范围改用独立 Python Playwright headless Chromium、新建 guest 与固定本地派生导入，不复制主浏览器会话或凭据。

最终核对实例：owner `211721f9-b7d9-4df9-bdda-20eb9d0aefcb`，course `3e30a1e0-9ffc-4f2d-9fc2-aee1f47f7a5b`，operation `dc468f57-6e7f-4c0c-9292-5176d3c21bc3`，scene `8d6eba62-0a1a-4023-8d7b-c4007f2dfe49`，课程v2／scene version `3861e9e4-ff2e-4368-aa12-e07f680d76b9`／题组 `21f2b80e-8dec-5697-b693-8c3d7239d574`。临时浏览器检查后关闭，因此这些ID是独立验证实例，用户继续阅读应使用主执行方当前浏览器已有私有课程；未将独立guest凭据导出。

准确候选 `7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779`，计划及basis同 final-review.json。记录为 independent-browser-learning.json；截图 data/screenshots/t108-r03-recovery-independent.png，已实际查看截图。实际命令：`backend/.venv/bin/python /tmp/t108_independent_browser.py`，本机 Chromium 启动需工具审批的沙箱外执行；脚本仅访问5198本机应用，并以 scripts/import_head_course_recovery.py --import-preview --owner <新guest> 导入同一固定候选。仅为本地导入读取明确指定的专用开发DB环境文件，未读Provider凭据、私有原稿vault、raw.key或终端记录。

## 实际检查结果

| 检查 | 独立观察 |
| --- | --- |
| 原目标／自述／来源 | 页面显示准确原目标、自述先备、candidate／plan／materials、程序格式恢复身份、模型文字未补写、首稿结构不合格和新调用0。 |
| 教学警示 | 正文前明确“教学评估未通过·仅供审查预览”，同时指出字段初始化错误因果和NULL检查问题，警告勿据此学习这两项结论；刷新后保留。 |
| 13帧／代码／作用域 | 逐帧点击下一步，帧f00–f12及高亮依次为无、4、5、6、7、8、15、4、5、6、7、8、16；f00/f06/f12显示局部不在作用域，其余活动。可见未知字段、节点值及note均记录。 |
| 控制 | f12后退到f11；重置到f00；播放推进到f02，暂停后等待仍为f02。 |
| 练习输入 | 四题可输入节点名、含空格／换行JSON整数数组和整数。题干与原文同版，未直接显示私有answer_key或solution。 |
| 错答反馈 | i1、[0]、[0]、0提交一次，服务端201；读取记录匹配0%，四条解析与模型原文一致。 |
| 正确反馈 | i0、[11, 30, 40]、含换行[30,40]、1提交一次，服务端201；读取匹配100%，四条解析与模型原文一致。 |
| 反馈边界 | 两次反馈reliability均provisional、mastery_effect均course_only，页面明确未更新正式掌握度。 |
| 整页刷新 | 两次GET场景API的完整对象逐项相等，包含课程/场景/题组/候选/来源；最新GET attempt URL和完整响应相等。answers、comparison_score、question_results及全部绑定不变。总POST attempts恰好2次，刷新没有新增作答。 |
| 私有答案处理 | 同版场景公开JSON没有answer_key及solution；解析在作答反馈返回，未因预览把服务端参考答案直接塞入课程读取。 |

最终正确attempt `5676bd47-5048-4170-9f55-497d2ca17089`，错误attempt `46ca2e66-1d92-47ee-bcb1-d74ef0620c3b`。以上是独立实际操作，不采用主执行方browser-learning.json作为自己的通过证据。

## 保留的失败与准确解释

独立脚本首个完整流程把“整个练习section刷新前后逐字相等”作为断言，刷新后失败。原失败输出保留在 independent-browser-learning.failed-r01.json，第二次带完整before／after的定位记录保留在 independent-browser-learning.failed-r02.json。两个实例均是真实额外本地导入／两次作答，不是额外Provider生成：第一course `effe76bd-ce95-46e2-86bc-4491094842d7`，第二course `58a08c03-64dc-4217-b52c-8bc491c26ff2`。

第二次的准确差异仅删除一行“继续完善或新作答”按钮。CourseExercise.initialize恢复answers／history／最新反馈而不持久locked，刷新后表单直接可编辑；因此无需该按钮。所有题干、绑定提示、答案文本、匹配比例和四条解析相同。这是既有表单状态差异，不是反馈漂移，未修改应用处理它。最终检查明确保留该差异断言，同时增加完整场景／attempt对象相等、私有答案隐藏、POST次数断言，没有仅删除失败断言过关。

另有预备阶段工具失败：MCP报browser already in use；首次受限Chromium启动因Mach端口Permission denied；沙箱外运行后，APIRequestContext GET session401（浏览器的Secure cookie未按该方式发送），后改页面同源fetch仅返回user.id成功。这些发生在课程测试前，不算产品流程通过。预备失败原始信息留在会话工具输出，早期同名JSON随后被写入覆盖，不能声称存在其独立原字节日志；完整课程流程的两次失败JSON已单独保留。

## 当前产物和准入复核

本次重算当前artifacts.json SHA256 `1b85bdde797beb08f663404ade5eda041b9efc07845600e26b0836d811535592`。当前record加入准确independent_review，assembled source加入needs_revision；最终review修正head-demo→head-state等定位元数据，教学raw_output、payload、candidate_digest均不变。独立重走 head_course_derivation.mapping() 通过。

已核旧入库审查元数据原件 review-metadata-r01.record.json 的整份canonical SHA `90d70178019f814c2240027821125afb8f1924d778cb06c33833a721f6ca8951` 对应代码固定白名单；它与当前record的candidate和recovery完全相同。validate_derivation接受当前完整record或这一整份历史record摘要，仍核整份snapshot／request／response／usage／绑定，不是忽略未知字段。当前独立浏览器API source与当前assembled source完全一致。该有限历史元数据兼容未发现本轮阻断。

私有预览的机械可读ready状态不等于教学pass；本次没有尝试修订、导师、重规划或任何新出站。不存在学生学习效果实验；T108合格新课程仍未达成，后续如何修改教学内容需用户决定，T102及原停止批次不恢复。
