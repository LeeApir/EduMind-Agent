# T109 限定头插流程复用：独立准备审查

2026-11-05，评估者 `/root/head_goal_independent`。**当前准备审查通过，可交准确真实授权决策；不是新课程或教学效果通过，不完成T109。** 新真实调用0，未创建批准／窗口，未读取Key、终端、私有vault或raw.key，未修改业务代码、历史冻结包或教学内容。

当前准确manifest SHA256：`f4c98c1a24d2943dd7f38350095932f1e933a46757eee3896156439d05bd239b`，410项。对应ADR0053及当前执行包全部文件；本报告按生成规则排除在manifest之外。业务边界复验所对应的前版为 `6ad4203f612f417ae10efc4f6bf44bc603130b24a91199abf200beedd10f4c71`，其后仅做下述输出末尾空行修正。最初审查的 `aab5668b7f9ca96a8dd48bd522eb0e6030772fb0d20b0caf3ed47e5a3f79911c` 曾有下述R1，不能拿旧摘要替代当前准确授权。

## 已发现并闭合的阻断

**R1：修订输出用量超过实际请求上限仍被接受。** 原head_course_reuse.record仅检查输入139264；共享历史wire固定允许输出至8000，而本批repair请求上限4000。独立用revision_body生成实际形状请求，构造完整离线响应、令usage.output_tokens=5000及total一致，成功复现原适配接受，违反本包超限即停。

开发在新record检查 `result.usage.output_tokens > request["max_output_tokens"]`，未改历史wire。独立重验4000接受、4001和5000均抛REUSE_USAGE；所有纯离线检查再通过。另阅读新增实际入口回归：修订报告4001时必须保留加密原件、准确failure code、STOP／ACTIVE，并拒绝第二次发送；执行方记录该项及原四条定向PG/API/MockTransport通过。独立者未重跑这些PG测试，不把阅读记录冒充自己的实测。当前R1闭合，没有保留的准备阻断。

## 边界与实现核对

| 范围 | 独立结论 |
| --- | --- |
| 输入／B示例 | goal完整保存原自述及指定head-new-B，support仅列B且参数为[-8]依次插6、0。正常结果0→6→-8→NULL，含0并非缺值；忽略两次返回值时caller仍i0(-8)，t0/t1各连i0且从caller不可达。 |
| 真实规划职责 | 仍经现有规划构造、wire-v2到严格local Schema、持久化、来源和引文核对；程序不造目标／场景／教学顺序。明确是指定示例内组织教学，不冒称自由选例能力。选择A、错参数或脱离原文／目标引用被拒绝；独立真实plan/basis pass后才正文。 |
| 同版程序材料 | 引擎、basis、代码／作用域、13帧、成功判空和四题答案复用。局部head是caller的值副本，p->next=head、return p、caller接收和丢弃对照明确。不执行任意C，不把malloc成功掩码当真实分配保证。 |
| 新记录路径 | 新服务不依赖T108固定父7fde…、四字段或最终4db…摘要；由原响应／准确请求重放、候选和父摘要、审核／basis、输出重新计算。旧特殊模块仍限定历史Schema分支，新Schema先分流，不能用旧通过身份代替新候选。 |
| 首稿格式恢复 | 先走严格完整适配；仅DUPLICATE_JSON_KEY才尝试既有恢复。外层重复仍被strict_json拒绝；只允许questions既定四键第二成员完全同类型同值，nested／第三次／冲突／未知／截断拒绝；修订不恢复。原raw／严格失败／恢复记录／候选分开留存，完整信封和Schema重新校验，不计首次结构成功。 |
| 审核驱动修订 | exact parent／parent_digest／basis、needs_revision和逐字quote绑定。动态位置只限paragraphs[i]完整text+fact_ids或summary，finding需可修复类别／issue／原段职责；输出封闭Schema，不再硬编码F01/F02或索引。不可修改区域阻断则停止，不能借本路径修改题目／帧／代码／规划。 |
| 引用、职责、防遗漏 | 机械核事实ID属于同版、完整Schema、精确邻段复制及不可变区域；不能判断句子被事实支持或近似复制。最终独立review必须空blocking_findings，并对全文、逐项引用、段落职责、无邻段复制、无必要解释遗漏、代码轨迹答案、无答案提示七项明确true。这是语义职责分工，不宣称机器已理解中文或以ID存在证明语义正确。 |
| 请求至准入 | CLI reuse profile使用原前台发送／逐块加密原件，prepare/发送前重建准确请求。verify_saved从原件、receipt、attempt摘要、计划和候选重放；准入重放整个plan／首稿／可选修订链，精确review和实际应用inputs相等，统一装配后进原私有快照和commit_scene。 |
| 用量归因 | 最终DB生成行sent_attempts=1及usage仅对应最后一次HTTP，父请求／输出／用量保存在records链。ADR明确不能用此列声称整批只1次，不改旧DB约束或把父请求丢弃。 |
| 来源／页面 | 新来源分支与Legacy不相交，Legacy Schema逐字保持；candidate／parent／plan／materials来源由记录计算。原首稿、格式恢复、局部模型修订和offline_fixture分开。已修正离线文案先称“本批模型”后再否认的冲突，当前夹具单独说明未调用模型。正文summary与替代文本同候选装配；旧播放器、私有答案和版本反馈不另建。 |
| 预算／停止 | 新批拟3HTTP，规划1、正文1、必要修订≤1；每次手动启动，无自动用满额度。600秒、新准确manifest及C2另批，旧余额不继承；8000/8000/4000输出请求及本地输入预约明确。过期／未知／部分／协议／程序材料／安全等按包停，修订失败不再调。publish目前也检查窗口，文档如实说明不可临时放宽。 |
| T102与C2 | 明确仍有最后检查后暂停导致迟发／继续计费风险，尽力停止不撤回在途请求；金额没有可验证硬上限，本机原件无独立抗回滚保障。T102继续blocked，不能以复用入口将旧反例默认为解除。 |

准确教学模板中的未来plan和真实UUID均显式占位，未把夹具大纲当真实规划。修订父稿、意见、动态Schema尚未产生，由未来准确记录构造，当前没有虚构真实审核或可发布新候选。

## 独立实际检查

- `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_reuse.py -k 'not actual_entry_and_private_application'`：最终15 passed、5 deselected；有既有Starlette/anyio弃用提示，无失败。覆盖实际构造B请求、规划严格拒绝、恢复、动态修订／父稿／引用／作用域拒绝及历史请求／Schema保持。
- `backend/.venv/bin/python scripts/prepare_head_course_reuse.py --check`：业务复验时410项摘要和请求／Schema／提示词／材料重建通过，返回前版6ad420…准确摘要、Provider0；提交前格式复核结果另见补记。
- `backend/.venv/bin/python -I scripts/head_course_goal.py --profile reuse --inspect`：同一摘要，prepared_not_authorized，Provider0。
- 独立内联Python复现并关闭R1：实际revision_body／fixture响应，4000接受，4001／5000精确拒绝REUSE_USAGE。全部是离线数据，不是Provider探测或教学成果。

此外只读检查新服务、原CLI复用差异、API／规划／准入分流、来源Schema和Vue文案、定向PG/API/MockTransport测试实现与CHECKS记录。没有重复全量PG／前端构建／lint；执行方已有这些结果，本次未声称自行重跑。Git中三处无关历史改动及外部参考目录不属于本审查修复范围，未触碰。

## 授权后仍未验证的事项

准备不能证明本批真实模型会接受动态修订Schema，或能生成正确且引用充分、无复制遗漏的中文完整课程。真实规划、首稿、必要一次修订、首次结构／恢复／修订分项结果，以及实际课程阅读／13步／四题反馈／刷新均尚不存在。未来评估须绑定新的准确候选，逐句核事实引用和教学职责，不继承T108或本报告的教学pass。

现有测试证明相应可编程边界和夹具接线，并不提供通用C执行器、通用语义监督器、真实金额硬封顶或生产动态开放保障。当前可以提交准确预算与C2授权决策；没有代用户批准、启动窗口或发送任何真实请求。T109继续未完成；完成本批或失败后停止，由用户决定后续，不扩主题或T038。

## 提交前纯格式核对补记

提交前发现revision-system.txt末尾多一个空行。生成器仅将该输出表达式改为 `reuse.REVISION_INSTRUCTION.rstrip().encode() + b"\n"`，文本文件只删除最后一个换行；实际revision_body及业务提示词常量未变。当前暂存区已是新版，直接拿index作前版比较所得差集为空；因此未将那次无效比较声称为通过。

独立将当前上述两个文件在内存反向还原，再只替换manifest中其两个文件摘要，重新canonical计算，精确得到前版6ad420…f4c71；这验证其余408项摘要未变及确切格式变化。随后prepare --check和reuse --inspect均返回当前f4c98c…239b／410项／Provider0。没有重复运行测试；15项离线及预算边界复验保留为6ad版业务证据，对本次未变业务仍适用。当前准确授权对象应为新版f4c98c…239b。
