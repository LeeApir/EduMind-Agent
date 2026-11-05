# T109：限定头插流程复用验证——零调用执行准备

**本轮交付可审查的接线和准确包；真实调用0，新课程尚未生成，T109不完成。** 下一核心交付是EduMind实际私有课程，不以夹具或本次准备评审代替。契约差异集中见 [ADR0053](../../ADR/0053-limited-head-reuse.md)。

## 本次课程与现成组件

[准确目标](goal.txt)：已了解C指针、struct、NULL和返回值；明确指定 **head-new-B：[-8]，依次插入6、0**，学习连接旧链及调用者接收返回值。规划器只在指定示例内组织目标、目的和教学顺序，不声称自由选例验证。[同版材料](head-new-B.materials.json)、[规划简短依据](planning-basis.json)由已有引擎提取并闭式核验：接收后`0→6→-8→NULL`；忽略两次返回值时调用者仍指向`-8`，动态节点t0/t1不可达。13帧含成功判空、函数作用域及准确代码行；不真实运行C。迁移0，继续使用原播放器、四题迁移情境和服务端私有答案。

## 最小代码变化与映射

| 接点 | 旧T108 | 本批记录驱动路径 |
|---|---|---|
| 原目标输入 | 一个准确GOAL，两种候选可选 | 追加参数的准确原文，支持清单只列已有B；原文完整保存，self-report不改为掌握度 |
| 规划 | wire-v2→严格local-v1，grounded-v3 | 同协议、同basis；真实规划目标/顺序，严格拒绝A或错参数/来源/引用 |
| 首稿 | strictJSON，r03失败另获事后恢复授权 | 同完整教学Schema；事前只允许既有四题同值重复恢复，原文/严格失败/恢复分别记录 |
| 修订 | 固定父7fde…、F01/F02、四文本位置 | 从准确父记录和独立意见生成封闭Schema；只替换审核定位段落的text+fact_ids及总结，不再绑定固定finding/索引 |
| 准入 | 最终候选文件SHA写源码 | 原请求/原响应重放→候选→父稿/审核→统一重装配，重新计算摘要；不写新候选摘要常量 |
| 页面 | 恢复/四字段事实修订的历史来源 | 不相交新来源分支；新模型首稿/格式派生/一次模型段落修订分别显示，旧分支原样保留 |

实现：`head_course_reuse.py`提供确定性记录/恢复/审核派生修订/全文合并及准入；`head_course_goal.py --profile reuse`复用原发送和加密原件，不另写HTTP器。现有规划、目标创建及准入只增加显式协议分支；Vue只补来源描述。旧特殊模块保持历史用途，不作为新候选运行依赖。新候选与审核均不得再要求修改运行源码；若需要，应记本验证失败并停止。

## 准确请求与预算

- [规划实际构造模板](planning-request.template.json)、[原输入模板](planning-input.template.json)、[wire Schema](planning-wire.schema.json)、[本地完整Schema](planning-local.schema.json)。模板只有实际应用course/operation/request UUID尚未发生，明确为占位；批准后从实际应用读取，`--prepare`输出准确请求，发送前再次逐项重建核验。没有伪造模型规划。
- [正文实际构造模板](teaching-request.template.json)、[完整教学Schema](teaching.schema.json)、[教学提示词](teaching-system.txt)：计划占位必须由本批真实且独立通过的准确规划替换，其余使用同版材料。
- [条件修订协议](revision-protocol.json)、[修订提示词](revision-system.txt)：父稿/审核/位置/Schema尚不存在，调用前从实际记录派生并封存完整请求。只返回所列段落对象/总结，不返回全文。不拿测试意见充当真实修订依据。
- [准确配置](candidate-config.json)、[待批准模板](approval.template.json)。拟新批`head-reuse-r01`，**3 HTTP/600秒：规划1、正文1、必要修订≤1**；当前批准0。DeepSeek官方Responses/deepseek-flash，max_output=8000/8000/4000，temp0.2/reasoning none，无重试/回退。旧余额0继承。
- 本批C2需新接受：单前台尽力停止仍有暂停后迟发/继续计费可能、金额无可验证硬限、本机证据无独立抗回滚。T102继续blocked，旧反例仍适用。

## 获准后的实际顺序

1. 复用T108显式开发配置/API8178/Web5198及专用开发库，实际首页输入`goal.txt`；保留owner/course/operation/request映射。只提供本机测试库配置，不读取Provider环境变量/.env。
2. 用户终端隐藏输入就绪后，登记一个全新600秒窗口/准确manifest批准，建立0700新vault和0600原件加密key。运行既有入口 `--profile reuse --prepare` 后单独 `--send plan`，无下一步自动调用。
3. 全原件先保存再严格验证/持久规划；独立规划审核逐项核对目标、先备、来源、指定B、变量作用域、接收/忽略返回值、同版basis，记录`plan-review.json`。失败/澄清即STOP。通过后显式`--send generate`。
4. 首稿严格通过或仅既定格式恢复后，出逐段/13步/四题完整评估。pass直接发布。若只有允许段落/总结内可修复问题，准确意见写`repair-review.json`，给每段原职责/逐字引用/相关事实依据；显式`--send repair`最多一次。其他问题停止。修订后重新评估全文，不能仅检查问题句消失。
5. `final-review.json`绑定准确候选/父稿/basis，verdict=pass、blocking_findings=[]，明确`checks`七项均true：全文、事实引用、段落职责、无邻段复制、无必要解释遗漏、代码轨迹答案、无答案提示。它们是独立评估声明，程序不把fact ID存在等同语义正确。
6. `--publish`只做本机私有v2，正文及演示替代文本统一装配；实际阅读、13帧作用域/行/状态、播放暂停前后步重置、四题错误/正确反馈、刷新完整scene及latest attempt版本相等/POST新增0。完成或任何失败均STOP、余量失效；保存首稿/恢复/修订/失败分别结果，停止交评估，不自动追加调用。

具体入口和停止方式见ADR。600秒只约束该批新请求；评估和只读证据核验可能晚于窗口，不能借此续窗或再发请求。当前CLI发布门禁也检查窗口，若评估未及时通过则停止，本轮不能临时放宽门禁。

## 检查与评估

[定向检查记录](CHECKS.md)。本轮没有新真实模型规划/课程/教学审核pass；测试夹具标记offline_fixture且不算成功。完整范围、源码、提示词、Schema、材料及模型配置通过`manifest.json`冻结，旧包保留原字节；工作流/任务记录和评估报告作为状态证据，不作为循环自摘要输入。
