# T108 r03：让真实规划读取同版示例依据

2026-11-04。**本轮仅零调用准备，新真实授权0，完整新课程尚未交付。** [r02停止批次](../phase-1.5-head-goal-live-r02/RESULTS.md)已用1请求/未用2失效、真实规划原稿及独立非pass均保持，r01也不重开。T108最终目标仍是从实际应用输入原目标，真实规划和正文生成后完成阅读、演示、作答及刷新。

本次补齐r02缺失的规划输入：参数以外的固定代码、作用域和返回值差异。[集中契约差异](../../ADR/0052-planning-basis-r03.md)与[定向检查](CHECKS.md)供评估；没有手写真实规划、补写模型正文、真实探测或新执行框架。

## 最小代码差异

| 文件 | 行为 |
| --- | --- |
| `head_course_planning_basis.py` | 调用现有引擎/材料函数，提取两候选短依据，核对固定函数和main、接收/忽略对照代码、逐次局部head/返回/调用者关系及独立闭式结果。仅固定模板范围，不解释任意C。 |
| `head_course_materials.py` | 原materials拆出按示例ID直接取材料的函数；不需要造假规划来取候选资料。原代码/帧/事实/答案不变；正文输入加入所选依据及binding。 |
| `head_course_planning_wire.py` | 保持wire v2 Schema及原转换，新Prompt v3明确规划职责，实际请求增加程序依据；mapping绑定Prompt及依据摘要。 |
| `free_course_planning.py` / `head_course_generation.py` | 原结果表记录新Prompt/请求摘要；拒绝旧Prompt或请求漂移的规划；最终评估须与材料binding一致。 |
| 原 `head_course_goal.py` | 继续使用原响应适配、原件保存和发送入口；规划评估须绑定同版材料；改指向新包和新授权字段，不建设执行器。 |

规划模型仍决定真实目标、选A/B、安排教学顺序。算法步骤/变量约定/结果若出现在规划里，须与依据一致；程序没有提供objectives、scenes、purpose、课文或完整大纲。未知学情仍未知，用户自述不是测得掌握度。

## 可审查的实际规划请求

- [planning-request.template.json](planning-request.template.json)：由实际 `scripts.head_course_goal.planning_body` 直接构造，完整system/user/Schema/模型配置；仅课程/操作/请求UUID为显式占位符。不是模型输出，不是后续真实身份。
- [planning-example-basis.json](planning-example-basis.json)：规划会收到的同版程序资料，含两个候选，无模型教学文本。
- [planning-system.txt](planning-system.txt)：新增职责规则；Prompt为head-goal-plan-grounded-v3，输出仍为[原wire v2 Schema](planning-schema.json)，本地仍为[原完整Schema](planning-local-schema.json)。没有复杂联合或引用重新外发。

准确目标保持：

> 我已了解 C 指针、struct、NULL 和函数返回值，希望通过头插示例，理解新节点如何连接旧链表，以及为什么调用者需要接收函数返回值。

规划请求明确区分insert的参数head、局部p和main的caller_head；函数接口/函数代码和关键行来自实际程序输出，自动存储初始节点i0的声明来自main。参数/局部指针在返回后不在函数作用域；返回地址的动态节点寿命不同于局部指针变量。新资料没有演示释放或真实malloc失败，分配成功前提、非真实C执行保持。

| 候选 | 接收所有返回值 | 忽略所有返回值 |
| --- | --- | --- |
| head-new-A：初始[12]，插4、7 | caller依次t0/t1，最终[7,4,12] | caller始终i0，仍可访问[12]；t0/t1从该入口不可达 |
| head-new-B：初始[-8]，插6、0 | caller依次t0/t1，最终[0,6,-8] | caller始终i0，仍可访问[-8]；t0/t1从该入口不可达 |

两种方式中函数的local head都保持各次调用入口值，p->next连接该旧头，return p提供新地址；只有调用者的接收语句改变caller_head。忽略对照只改变调用语句，不换另一套函数实现。资料按实际轨迹提取，并与独立闭式期望核对，不能拿引擎给自己当唯一真值。

## 规划、正文和评估使用什么版本

```text
SPECS + 同版模板/引擎
 → 两候选basis（函数/作用域/状态差异 + basis_digest）进入实际规划请求
 → 真实wire原输出 + 原local严格转换 + mapping的Prompt/basis摘要
 → 真实模型选例 + 该候选materials_digest/示例依据摘要
 → 正文payload.planning_basis（binding + 所选evidence）
 → 修复original_input完整保留 → 候选摘要 → 原私有课程版本/反馈
```

新 `planning_basis.binding` 含version、basis_digest、selected_example、example_basis_digest、materials_digest；字段由程序派生，不要求模型复制摘要。正文所带选例依据逐对象等于规划请求对应候选，且摘要绑定原完整materials。其他候选不作为正文内容。候选中的完整payload也提供给独立评估者。

规划评估必须核对原目标、实际原输出/完整local值、对应依据和完整同版材料；pass记录的plan_digest及planning_basis_binding要准确。正文最终pass也必须附相同binding及candidate_digest。缺失/错材料评估拒绝；即使旧计划文字相同，没有新Prompt/请求绑定也不能继续生成。资料存在与摘要一致不是语义正确保证；仍独立核对局部/调用者区别、目标兑现、无另一实现、结果范围及澄清必要性，不自动补计划或改引用。

教学正文与唯一允许的修复均继续使用head-goal-course-v1输出Schema，所有讲解/题干/解析由未来真实模型生成。输入增加程序依据使候选摘要变化；不借用旧回放、r02规划身份或旧候选。原参考答案仍服务端私有处理，现有课程组件与交互协议不变。

## 新批次提案与停止点

本轮不创建执行窗口、不读取Provider Key、不调用Provider、不启动旧操作。新准确包须先评估，真实批次另行准确授权。

拟议配置仍为DeepSeek Responses `https://api.deepseek.com/responses` / deepseek-flash / reasoning none / temperature0.2 / max_output_tokens8000 / stream=false / store=false / 无工具。最多3 HTTP：规划1、正文1、仅普通教学措辞的一次条件修复。新窗口600秒且受新应用操作期限约束，较早截止；输入预约139264/次合计417792、输出请求8000/次合计24000；请求≤131072字节、响应≤2097152字节、单项I/O90秒。预约和输出请求值不是上游金额硬上限，C2仍须新批接受。

新批准须绑定提交/manifest，并含planning_wire_version=head-goal-planning-wire-v2、planning_prompt_version=head-goal-plan-grounded-v3、version=head-goal-course-v1、accept_ADR0052_R03_and_batch_C2=true、explicit_user_authorization=true及新starts/expires=+600；当前没有这些批准记录或新窗口。未来私有原件须新目录，不能使用r01/r02。

规划语义通过才正文，首稿通过或唯一允许措辞修复后完整通过才入实际课程；协议/Schema/事实/答案/安全/原件缺失/unknown/过期/超限即停，未用额度失效。不修规划、不探测/重试/回退；若新规划协议被拒，准确留错并停，Provider路线由用户决定，不自动字段补丁。允许正文修复仍仅独立认定minor difficulty/misconception、精确父稿/path/quote，不能挪给规划。

Key未来仅终端getpass；原HTTP body先加密/fsync再解析，原输出/失败/父修复/评估均保留。STOP/Ctrl-C仍尽力，可能迟发或继续计费；本机原件没有独立抗回滚保障，金额没有可验证硬上限。T102 blocked未解除，原七角色/B-C及T038契约不改、不回填分母。

零调用复现：`backend/.venv/bin/python scripts/prepare_head_course_goal_grounded_package.py --check`、`backend/.venv/bin/python -I scripts/head_course_goal.py --inspect`。实际开发入口仍5198/API8178；本轮未向运行实例提交新目标，不产生新课程。未来批准后按原CLI prepare/send plan→独立评估→send generate/条件repair→publish，再在同一私有身份实际阅读、全部帧/高亮/控制、四题反馈和刷新恢复，交独立教学评估。完成一课后停止，不扩主题或恢复旧批。
