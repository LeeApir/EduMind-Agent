# T082：最小输出契约审查包 r01

**状态：设计提案；未实施；本轮Provider调用0；待用户交评估助手审查，完成提交后停止。** ADR0047 A—D及准确附件尚未接受，不是执行包。旧失败、源码/Prompt/Schema冻结、终止批次和unknown占额全部保留，原正式验收标准不变。

## 先读这些文件

| 文件 | 内容 |
| --- | --- |
| [ADR0047](../../ADR/0047-minimal-pilot-output-contract.md) | A职责/有限题型；B最小结构；C可比性/契约变化；D整体准入与后续课程门禁 |
| [CONTRACT.md](CONTRACT.md) | 每个模型/程序角色完整输入输出、局部硬门、baseline不得代填、审核不只看引用 |
| [schemas.json](schemas.json) | 四个完整最小wire Schema及六种模型阶段映射；审核B/C分成两个准入槽 |
| [PROVIDER-CHECKLIST.md](PROVIDER-CHECKLIST.md) | 所有旧角色/嵌套Schema风险、实际历史证据和未知，不把Tool文档当Responses保证 |
| [original-schema-audit.json](original-schema-audit.json) | 旧四个原Schema、已提literal/anyOf副本、93位置完整关键字路径和81分类提示 |
| [COMPARABILITY.md](COMPARABILITY.md) | 等价/非等价清单、B/C信息隔离、旧成绩不可合并与指标影响 |
| [examples.json](examples.json) / [context-example.json](context-example.json) | 51个手写正反/语义边界例及开发上下文，非独立样本/真值 |
| [COMPATIBILITY-PLAN.md](COMPATIBILITY-PLAN.md) / [机器预算](compatibility-plan.json) | 7HTTP整体准入、上限与停止门、全部角色通过后才另备课程包 |
| [protocol-fixtures.json](protocol-fixtures.json) | 七阶段纯合成echo提议，含非空嵌套节点/审核问题；不是请求原字节或可评课程 |
| [check_design.py](check_design.py) | 仅静态设计核查，不是Provider执行器、生产适配器或语义判真器 |
| [manifest.json](manifest.json) | 13份准确设计附件（含ADR/本入口/检查器）与输入源摘要；不含自身、可变账本/日志/验证输出 |
| [verification.txt](verification.txt) | 实际离线命令/结果、限制与交接，不在规范manifest内避免自引用 |

## 设计结论

C只返回有限规格/目标ID、讲解/题干/解释与事实ID；程序解析准确事实并显式标记出处。B仍返回自己的代码、四种有类型答案和完整动作，程序只装配/解码、不修正事实。审核收到完整候选和允许参考；正确ID不代替讲解正确性审核。新增wire只用七类结构关键字，长度/范围/唯一性等最终硬门留在本地，未来实施不得漏检。

这些设计减少开放JSON和冗余输出，但移除模型复述/格式出错机会，属于新的实验契约。不能宣称纯兼容转换或多Agent效果已证；见COMPARABILITY。旧Schema/旧原件不迁移、不重算成绩。最小契约只限固定头插实验，不改生产教学API/Prompt、评分权限或PRD正式验收标准。

## 本轮验证与复现

```sh
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-minimal-output-contract-r01/check_design.py
python3 scripts/check_catalog_workflow.py
git diff --check
```

检查完整原Schema快照/关键字位置、拟议wire闭合与显式类型、51个静态用例/七个协议fixture、本地边界、预算求和、所有旧46/47/62/69/78文件清单、输入来源及本包摘要与相对链接。没有读取.env/凭据、DNS/HTTP、C执行或生产数据库。全量开发回归/运行时适配/Provider成功/独立评估均未在本轮完成，不用静态设计检查冒充。

故意保留三例结构合法而语义待核查：错讲解/正确引用、错B答案/合法类型、题干与观察范围待核对。B fixture的代码与动作仅示意协议，不是完整C课；不能以51例通过声称教学正确。

## 交接和待决定事项

T082仅完成审查与提案交付，独立评估尚未进行；不请求现在立即调用。请将本入口连同manifest交给评估助手，审查ADR A—D、职责/类型覆盖、baseline没有被代填、可比性影响及7HTTP停止条件。用户在审查后决定接受/修改/停止。

若采用，后续工作顺序为：准确契约确认→另行领取隔离实施与离线回归→冻结准确请求/源码/账户费率/独立预算窗口→另批7HTTP合成兼容→全部准入后另备一份课程≤5HTTP包。上述均未领取/执行；根task.json只有T082本轮任务，没有重复领取旧任务。金额USD1仅待验证的设计建议，不能执行；旧余额/费用例外不继承。T038 blocked、catalog_only、H封存及原教学阈值持续。
