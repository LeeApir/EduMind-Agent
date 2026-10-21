# 本轮预算确认与预标签核对表

登记时间：2026-10-21T08:59:14+08:00。用户已确认最多59次请求、5小时硬截止和首败停止；费用不限。基础60次中的剩余1槽关闭，重试与回退均为0。

绑定[原冻结包](../phase-1-plan-admission-preparation-r01/README.md)，manifest SHA-256：`b99c08f657b084c849b36163339fe0526f484b40d7f76a991d8e99cca7653303`，完成提交`554e6a0`。本目录是追加登记，原包中的待批状态保留为历史。

5小时从真实运行显式启动时开始，包含人工核对等待；当前未启动。单操作180秒、单次60秒仍有效。Schema、传输、标签、全部断言及全部引用中任一失败即停止；核心拒绝正确但附带说法错误仍算失败。失败请求不退额度，不调换剩余槽位，不重开旧运行。

**当前：预算与停止规则已确认；下表16项独立签核尚未确认，持久执行包尚未冻结，真实调用0。T040仍blocked，H继续封存。** 已签核H不能代替本表。

请逐项阅读链接中的完整材料，核对预期结论与证据边界；发现问题请指出ID及改动。标签或材料需改动时另建新版本，不覆盖原冻结包。正确对照要求无附带误报；所有条目均须核对每个断言及引用。

| ID | 通道 | 预期 | 必须满足 | 独立核对 |
| --- | --- | --- | --- | --- |
| [pointer-scope--correct](../phase-1-plan-admission-preparation-r01/materials/review/pointer-scope--correct.json) | fixed_review | `pass` | 按形参Node **、赋值*head=NULL和调用&head判断；不可将讲解局部变量片段脱离完整源码而判调用方悬垂。 | 待Lee核对 |
| [pointer-scope--error](../phase-1-plan-admission-preparation-r01/materials/review/pointer-scope--error.json) | fixed_review | `reject` | malloc成功路径中Node *按值传递，函数已释放对象，main再次free同一地址构成可达二次释放；不推导UB确定返回值。 类别：code_safety；严重度：severe。 | 待Lee核对 |
| [pointer-scope--insufficient](../phase-1-plan-admission-preparation-r01/materials/review/pointer-scope--insufficient.json) | fixed_review | `needs_human` | 函数体/后续用途缺失，不能保证安全也不能断定已释放或二次释放；不能把Node *声明当函数已释放的证据。 | 待Lee核对 |
| [plan-consistency--correct](../phase-1-plan-admission-preparation-r01/materials/review/plan-consistency--correct.json) | fixed_review | `pass` | 目标、轨迹、学生实现均为19，无计划矛盾误报。 | 待Lee核对 |
| [plan-consistency--error](../phase-1-plan-admission-preparation-r01/materials/review/plan-consistency--error.json) | fixed_review | `needs_human` | 计划目标17与自身轨迹/数组和19矛盾；学生代码19正确。需修正/澄清计划，不怪用户。 | 待Lee核对 |
| [plan-consistency--insufficient](../phase-1-plan-admission-preparation-r01/materials/review/plan-consistency--insufficient.json) | fixed_review | `needs_human` | 缺指定元素，无法核验该次和是否19；不宣布计划确定自相矛盾或一定非19。 | 待Lee核对 |
| [requirement-origin--correct](../phase-1-plan-admission-preparation-r01/materials/review/requirement-origin--correct.json) | fixed_review | `pass` | 原文19、计划19、代码19一致；不把图谱背景扩大成必达目标或要求动画。 | 待Lee核对 |
| [requirement-origin--error](../phase-1-plan-admission-preparation-r01/materials/review/requirement-origin--error.json) | fixed_review | `reject` | 原文要求19，只有计划追加17；讲解把17归给用户无据，实际求和代码仍返回19，与讲解/预期17矛盾。 类别：fact；严重度：major。 | 待Lee核对 |
| [requirement-origin--insufficient](../phase-1-plan-admission-preparation-r01/materials/review/requirement-origin--insufficient.json) | fixed_review | `needs_human` | 已知求和19正确，附件的附加要求不可核验；不能虚构附件要求17或声称全部满足。 | 待Lee核对 |
| [assessment-coverage--correct](../phase-1-plan-admission-preparation-r01/materials/review/assessment-coverage--correct.json) | fixed_review | `pass` | 教学分散覆盖且完整状态表判断题真实要求推演，干净pass；不能因不是开放题或讲解未重写轨迹而误拒。 | 待Lee核对 |
| [assessment-coverage--error](../phase-1-plan-admission-preparation-r01/materials/review/assessment-coverage--error.json) | fixed_review | `needs_human` | 过程已在代码步骤明确教过；三题仅算术，未测完整状态和退出；needs_human，不编造fact。 | 待Lee核对 |
| [assessment-coverage--insufficient](../phase-1-plan-admission-preparation-r01/materials/review/assessment-coverage--insufficient.json) | fixed_review | `needs_human` | 缺题本正文，不能判断实际过程测量；指出缺证据，不能声称未见题本一定只考算术或一定合格。 | 待Lee核对 |
| [P01](../phase-1-plan-admission-preparation-r01/materials/plan/P01.json) | plan_review | `pass` | 原始19、轨迹19与目标一致，不增背景目标/动画。 服务端：accept_plan。 | 待Lee核对 |
| [P02](../phase-1-plan-admission-preparation-r01/materials/plan/P02.json) | plan_review | `issue / needs_human / reject` | 计划目标17与原文/轨迹19冲突，必须指出具体字段，不冒称原文17。 服务端：needs_human_or_reject。 | 待Lee核对 |
| [P03](../phase-1-plan-admission-preparation-r01/materials/plan/P03.json) | plan_review | `needs_human` | 指定元素缺失，不能核验19或宣称确定非19。 服务端：needs_human。 | 待Lee核对 |
| [P04](../phase-1-plan-admission-preparation-r01/materials/plan/P04.json) | plan_review | `issue / needs_human / reject` | 仅计划追加17；不能归给要求19的用户，区分原文与计划。 服务端：needs_human_or_reject。 | 待Lee核对 |

固定审核共同禁止：将模型计划冒称原始用户要求；从“无法保证P”推出“非P”；无据断言调用者悬垂或未定义行为的确定数值。引用只能支持所在字段实际包含的命题。

G01–G04是另外4份独立生成输入，不包含虚构的预期答案；实际计划和学生内容产生后另行核对。上述材料全属开发回归，不能计入T040正式验收分母。

下一步：完成本轮独立预标签签核，并准备、验证和冻结独立持久执行包；预算政策不重复询问。新执行包须绑定本登记、实际路由和材料摘要，门禁齐备后才可激活。

## 追加签核

用户随后确认“已逐项核对，确认全部16项”。当前状态见[追加状态](CURRENT-STATUS.md)和[绑定摘要的签核](human-check-20261021.json)；上方待核对表保留为登记时历史。
