# T108 r02 独立准备审查

日期：2026-11-04。评估者：独立评估助手 `/root/head_goal_independent`，与开发分离。准确对象：`phase-1.5-head-goal-t108-r02/manifest.json`，SHA256 **`41d0bb3aec551b3ad08fa63e711476710c44d43483d41477fb5eb077b72cbc6a`**；对应 [ADR0052 r02 补充](../ADR/0052-planning-wire-r02.md)。本报告置于包外，未修改冻结包或实现。

**结论：在本次限定接口边界修复与准确准备范围内通过独立审查，未发现阻断送交用户授权决策的缺陷。** 规划 wire/local 的职责与固定转换清楚，真实 CLI、保存/复核及持久化摘要对应。该结论不代表 Provider 已接受新线格式，也不代表真实新课程或教学评估通过；本轮新增真实调用0。

## 独立核验

| 审查点 | 观察与结论 |
| --- | --- |
| 准确包 | 重新计算 manifest 自身 SHA及其404份文件摘要，均一致；实际包生成器 `--check` 与 CLI `--inspect`均返回上述摘要。 |
| 远端 wire Schema | `head_course_planning_wire.schema.json`每层节点明确指定基础类型；对象关闭额外字段且所列字段必填，无anyOf/oneOf/allOf、引用或条件结构。它是明确的有限规划格式，原完整本地Schema单独保留。旧成功教学Schema的结构参考不构成本新规划已兼容的证据。 |
| 无损转换与严格拒绝 | `to_local`先校验准确协议版本及完整wire结构，深拷贝后只转换已声明标记：单元素plans解包；澄清空plans映射null；正常空reason及建议目标两个空来源串映射null。建议带非空来源、澄清带活动计划、无效正常/澄清分支均拒绝，未静默删有意义字段。文本、目标ID、引用、场景顺序及依赖不补写或改写。转换后完整调用原本地`validate_response`和限定选例检查。 |
| Prompt与实际请求 | CLI `planning_body`实际调用新wire builder；新system词明确plans/空串规则，并替换原建议来源null措辞，未向模型同时要求null与空串。实际模板由同一入口构造，真实课程身份仍须来自新应用请求，不把模板占位符或fixture当真实规划。 |
| 原件和映射审计 | `send`继续先保存加密HTTP body，再解析；`plan.output.json`保留wire原JSON，`plan.mapping.json`含wire/local版本、双方内容摘要与本地值。`verify_saved`解密并核对body/attempt/request、重新响应适配、对比wire原输出、重新转换并逐对象比对mapping，才向后续生成返回本地规划。不能靠仅保存转换结果覆盖原稿。 |
| 持久化请求摘要 | `save_plan`先严格转换，再以`request_digest(plan_wire.build_request(inputs))`创建本地PlanningOutcome；`persist_outcome`对head_support分支复算同一新请求，保存wire v2的prompt_version与原local schema_version。普通规划分支仍使用原builder；原输入和写入围栏未放宽。 |
| 正文和修复 | 实际`m.body(payload)`与`m.body(payload,parent,issues)`保留同一head-goal-course-v1教学Schema及Responses格式；本次未修改其材料构造器、Schema或前端/答案/API契约。新规划本地对象继续经同版材料与候选绑定进入原链。 |
| 授权及停止 | 新入口要求新manifest、新planning_wire_version及`accept_ADR0052_R02_and_batch_C2`，旧批准字段不能启用。新3HTTP/600秒为提案，旧2次余量无效；简化规划再拒绝即留原件并STOP，后续Provider路线交用户决定，不允许本批字段补丁、探测、重试或自动换路由。 |

独立执行：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_planning_wire.py
backend/.venv/bin/python scripts/prepare_head_course_goal_wire_package.py --check
backend/.venv/bin/python -I scripts/head_course_goal.py --inspect
```

结果：**21 passed**；逐字节重建/入口摘要通过。覆盖正常原文保留、空标记、澄清、引用/覆盖/依赖/支持域/未知字段版本拒绝、三个实际Schema构造、旧批准拒绝与实际入口模拟400后原件保留/停止。Mock结果不计模型成功。

另审阅开发者 [CHECKS](phase-1.5-head-goal-t108-r02/CHECKS.md)及对应测试实现：3项定向实际PG/API/MockTransport通过；首次沙箱权限拒绝有披露，随后同组运行通过。**本独立审查没有重跑PG**，不冒称再次独立执行这3项，也没有扩跑全量前端、旧规划、迁移或浏览器套件。

只读对照`221ae7a`还确认：原`app.agents.free_course_planning`本地Schema/验证器模块、其Schema文件、head_course_materials、产品API契约，以及旧T108准备目录和head-goal-r01停止交付目录的已跟踪文件保持原字节。新增适配没有追改原HTTP400或旧失败结论。

## 结论边界与下一门槛

这次修复解除的是“规划入口直接发送内部复杂Schema”的明确接线前置。静态基础类型与本地检查不能证明新Provider调用会被接受；若再次拒绝，按本包立即停止，交用户决定Provider路线。T102迟发反例、单前台尽力停止、在途可能继续计费、本机原件无独立抗回滚保障及金额无可验证硬上限，均是已披露、需要本批重新批准的边界，本审查不宣称解决。

本次只读审查未发网络请求、未读取Provider Key/终端/任何私有vault或raw.key、未修改Schema、冻结包或教学内容；未创建批准记录。head-goal-r01仍STOP，旧未用2请求不继承，T108仍未完成。

通过准备审查后，应先由用户准确批准新提交、此manifest、ADR补充及本批C2/新窗口，才允许真实规划。新课程必须经历真实规划语义核验、未经助手补写的完整教学正文、必要且仅一次允许措辞修复、实际应用学习与刷新核验，再交独立教学评估。**本报告不是新课程教学效果评估，也不授权开始调用。**
