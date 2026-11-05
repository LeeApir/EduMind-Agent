# T109 r01 停止后应用状态独立核对

2026-11-05，评估者 `/root/head_goal_independent`。**确认存在独立工程缺口E01：新限定前台协议漏接操作状态投影，页面错误显示通用13次预算和恢复操作。** 它与首稿教学S01／C01分开记，不改变原final-review.json，不构成实际完整课程学习通过。

本次仅只读主执行方安全证据 docs/acceptance/phase-1.5-head-reuse-live-r01/app-browser-stop.json 及源码；没有自行浏览器操作、发请求、修改源码、调用Provider或读取Key／私有vault／终端。证据文件SHA256 `103fb8c13a08661bed853f106d226b48e5456e8dd6c1e3647baf1517610d4dc7`，独立核其字段一致性，不冒称这份GET/UI记录由本评估者亲自采集。

## E01证据与定位

准确course `6be90c82-adfd-408d-82b6-32125db0dcbf`、operation `ecb65468-da85-4772-8a5d-b7f1bb5e8fa1` 的GET为200，state=failed、reason_code=TEACHING_REVIEW_FAILED。course保留大纲v1、complete=false，场景scene_version_id=null，未发布正文。

operation缺execution_mode，却返回通用budget：attempts_used=0、attempts_remaining=13、course_attempts_remaining=40及零token使用。UI据此显示“尝试已用0·剩余13”，并在失败后显示“新操作仅补生成缺失场景…最多13次尝试/600秒”和“确认继续缺失内容”。这些不等于本批真实额度：本批已有2/3实际HTTP且停止后剩余1作废；通用调度器未登记前台attempt，不应拿其零计数向用户表示本批未用请求或仍可继续。

直接源码原因：backend/app/services/free_course_recovery.py:368–374的execution_mode及budget=null分支只识别 `prompt_version == "head-goal-course-v1"`，没有覆盖新 `head-reuse-course-v1`。新创建课程按support版本保存该新值，因此落入通用scheduler预算分支。web/src/components/CourseOutline.vue:167、199、221依execution_mode隐藏限定前台警示／显示通用澄清与恢复；缺字段使失败状态满足恢复表单条件。这个因果与实际安全证据吻合。

## 影响及仍有效的边界

这是可见预算与下一操作的错误语义，也是“复用主链无须再改运行源码”的工程验证失败，不能仅作为教学文本缺陷处理，不能以Schema、HTTP200或准备包pass遮盖。它没有证明Provider真的又收到请求：本次未点击恢复，证据明确provider_calls_in_check=0及full_learning_flow_run=false。

既有 scripts/head_course_goal.py 的send仍按准确批准检查3HTTP／600秒、唯一stage／attempt以及STOP；--serve的no_extra_operations中间件（557–564行）仍对POST /operations及/tutor-turns返回409，Provider工厂被禁且服务器有回环网络审计。因此错误UI不能据此追认为授权13次或认定已突破真实调用预算；中间件有效性的本次依据为源码与主执行方运行说明，没有自行追加POST去试探。T102已披露的暂停后迟发风险并未解除，也不被这里的拒绝路由替代。

## 收尾结论

教学结果仍是：真实规划pass，首稿严格结构pass、恢复0，首稿静态教学stop；不可修的failure_scope S01加段落引用C01保持。工程另记E01。真实模型修订0、发布0、实际完整应用课程学习验收未运行；已有正确的13帧静态值与四题答案不等于可交付新课程。

接受主执行方本批已STOP、2HTTP／余1作废及失败收尾；本报告不重开窗口、不请求修订、不改业务或教学、不恢复T102。用户要求“若新候选还需改运行源码则记本验证失败并停”，故本轮应把E01留作具体失败证据和后续用户决策对象，不能当场补源码续跑或将T109记done。只读收尾可继续保存证据，后续范围／准备／新真实授权由用户决定。
