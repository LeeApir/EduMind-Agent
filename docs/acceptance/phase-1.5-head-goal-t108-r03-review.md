# T108 r03 同版规划依据独立准备审查

2026-11-04。评估者：独立评估助手 `/root/head_goal_independent`，与开发分离。准确对象：[r03 manifest](phase-1.5-head-goal-t108-r03/manifest.json)，SHA256 **`43ec5edb6eb741cad8c324aae4c8037fe90bc0fb65bd70cd623d81b75b5f0850`**；契约差异见 [ADR0052 r03补充](../ADR/0052-planning-basis-r03.md)。本报告置于包外，未修改实现、冻结材料或旧失败。

**结论：本次限定准备通过独立审查，未发现阻断交付至准确授权决策的缺陷。** r02缺失的具体实现/作用域/返回值差异现在随真实规划构造入口发送，并与后续正文、修复和评估绑定。该结论不能把r02原规划改为pass，也不代表未来模型会遵守依据或新课程教学效果已通过。本轮新增真实调用0，新真实批次仍待准确批准。

## 核验结果

| 对象 | 独立观察 |
| --- | --- |
| 实际规划入口 | 从本包占位输入调用实际`head_course_goal.planning_body`，结果逐对象等于冻结request模板；user载荷的planning_example_basis逐对象等于当前`build_basis`。新Prompt明确模型负责真实目标、选例与顺序，不能另造实现/重命名指针/加入head=p，明确区分local head与main caller_head。不是仅在文档中声称提供材料。 |
| 程序依据的来源 | `_example`从原材料函数和共享引擎取代码/轨迹，核对固定insert函数及main的准确模板、声明、关键行，忽略返回值对照代码仅改变调用接收语句。`_calls`提取各次调用前入口、local head、p->next、返回地址及调用后入口，并检查这些关系。没有模型调用、C执行或任意C解释。 |
| 独立期望与范围 | 对A手算：接收两次返回值依次得到[4,12]和[7,4,12]，caller为t0/t1；全部忽略则caller始终i0，原[12]仍可访问，t0/t1不可从该入口到达。B同理得到[0,6,-8]或保留[-8]。函数局部head分别保持各次调用入口，return p本身不写调用者变量。helper对这些闭式期望进行额外核对，未只把引擎观察当作自身唯一真值。支持域仍只有这两个已知模板/全部成功前提，没有分配失败或释放动画的新证明。 |
| 不是手写规划 | basis提供函数接口、代码、变量作用域、关键行、接收/忽略状态及摘要，不提供objectives/scenes/purpose/课文。模型仍须生成新的真实规划；“有材料”不等于目标、教学顺序或自然语言事实已正确。 |
| 同版传播 | `materials_for_example`允许直接取得支持例材料，无需造一个假规划取资料。正文payload.planning_basis的evidence等于规划输入中所选候选，binding覆盖version、全部basis_digest、selected_example、example_basis_digest和materials_digest。修复在original_input完整保留该依据；candidate摘要覆盖完整payload，旧候选不能直接混用。 |
| 持久化及评估门禁 | mapping新增Prompt/basis摘要；原本地v1计划和严格转换继续保留。persist_outcome复算新完整请求摘要并保存grounded-v3 Prompt；generation_context校验该Prompt和真实请求摘要，使未携带依据的旧规划无法继续。CLI要求规划pass附准确planning_basis_binding；publish对最终候选pass做同样核对。缺失/错版意见拒绝，摘要与资料存在仍不自动授予语义pass。 |
| 契约和旧批 | wire v2 Schema、完整local Schema、教学Schema均与r02逐字节相同；两候选完整materials也逐对象相同。新授权字段包含r03 flag和新Prompt版本；本提案仍3HTTP/600秒，不继承r01/r02余量、窗口或C2。原规划不可修复，严重/事实/协议/答案/安全/unknown即停；接口再拒绝须留错并交用户决定Provider路线，不追加自动修补或探测。 |

## 实际独立检查与证据边界

已执行：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_planning_basis.py backend/tests/test_head_course_planning_wire.py
backend/.venv/bin/python scripts/prepare_head_course_goal_grounded_package.py --check
backend/.venv/bin/python -I scripts/head_course_goal.py --inspect
```

结果：**33 passed**；包重建和入口返回同一准确摘要。另用只读本地Python重算manifest及其**427份文件**摘要，无差异；核对模板来自实际构造、发送basis与程序函数相等、两完整materials及上述三Schema未改。没有网络请求或真实模型成功。

已阅读开发者[CHECKS](phase-1.5-head-goal-t108-r03/CHECKS.md)和3项定向PG/API/Mock测试实现：新Prompt/请求摘要、缺失/错评估绑定、旧规划漂移拒绝的测试与本次改动相关，开发记录为3 passed。**本独立审查未重跑PG，不把开发记录当作自己再次执行**；未重跑无改动的全量前端、旧规划、迁移或浏览器套件。

本次未读取Provider Key、终端或私有vault/raw.key，未改源文件、模型原稿、旧STOP或冻结包，未创建批准记录。r01/r02失败和未用额度失效结论继续有效，T102仍blocked。

## 尚未取得的证据

新输入可能仍被真实模型忽略、误读或产生错误规划/正文；资料和摘要不能替代逐段语义核验。未来真实规划必须由独立评估者按准确plan摘要和basis binding核对目标/作用域/实现/结果范围，再决定能否发正文；不允许把计划中的错误留给正文覆盖。最终仍须取得未经助手补写的完整新课程，并在实际应用完成讲解、逐帧代码/状态/高亮、四题不泄题与反馈、刷新版本一致及独立教学评估。

单前台尽力停止、检查后迟发/继续计费、本机原件缺少独立抗回滚保障及金额无可验证硬上限是原已披露局限，本次没有扩大监督器或修改T102来处理。新批次须用户准确批准本提交/manifest、ADR补充及本批C2/窗口后才可开始。

**本报告仅通过r03准备审查，不授权真实调用、不完成T108，也不是新课程教学效果评估。**
