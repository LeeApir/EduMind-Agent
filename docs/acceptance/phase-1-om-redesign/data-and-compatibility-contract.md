# ADR-0015 最小数据契约与三场景兼容（v1）

本附件是A/B/C/D的规范性补充，和[JSON Schema](minimum-contract.schema.json)一起在T044迁移前冻结。Schema使用Draft 2020-12，所有对象拒绝额外字段；T044建立同义的本地校验器和数据库约束，T045/T048复用，不能各自另解释字段。供应商wire可转换成其支持的schema子集，但本地完整校验不放宽。此处没有实施迁移或变更现行API。

## 1. 计划与标识

模型只生成`$defs.plan_generation`（目标、先修ID、术语、约定、示例、场景与参考短ID）；服务合并已冻结输入中的node_id/graph_version及摘要、有据画像版本/证据摘要、goal/code_language、参考ID对应version/digest和schema_version，校验后形成`$defs.plan`。未知reference_ids拒绝，不从模型接收元数据或哈希。owner、unit、operation、plan ID/版本、scene ID/版本与摘要全由服务端补充。`plan_record`是落库快照，`review_result`是模型审核正文，`review_record`是服务端绑定后的只追加记录。模型无需回显或计算哈希。资源沿用现有各类型schema。

三个固定逻辑key与角色同名：explanation → code → exercise，顺序不可变。code依赖explanation；exercise依赖explanation与code。`scene_id`是准确持久化行UUID，`scene_version`是同owner/unit/key下单调递增正整数；与`plan_version`不同，不能从相同数字推断配套。每份新计划/候选绑定均分配新的场景行，旧行不改写。三场景不得同用intro，也不增加第四个兼容场景。

计划JSON必填节点、图版本/摘要、有据画像版本或null、画像证据摘要、目标、先修、语言、目标ID、术语、约定、共享示例/逐步轨迹、版本化参考及固定三个场景。索引/容量不适用须填null并在not_applicable_reasons说明；未知且影响结论则拒绝，不能把未知当不适用。画像缺失用null和实际空证据快照摘要，不捏造版本1。目标ID/术语/参考ID不得重复；场景目标须引用本计划目标；先修/节点/参考需存在于固定版本中；role必须等于scene_key。这些跨字段规则在本地校验，不把Schema通过视为事实正确。计划规范字节≤8KiB；其他字节上限沿ADR A1。

## 2. 持久化、不可变性与摘要

T044即建立以下最小列/绑定，不等T048再决定要存什么：

| 载体 | 最小新增字段与约束 |
| --- | --- |
| learning_plan_versions | id、user_id、learning_unit_id、origin_operation_id、version、schema_version、plan_json、plan_digest、input_digest、references_digest、policy_version、policy_digest、created_at；唯一(owner,unit,version)；所有字段插入后不可更新 |
| learning_scenes | 可空plan_id与dependency_digest；现有scene_key/version/input_snapshot继续有效；新行必须同owner/unit计划，input_snapshot保存准确上游资源ID及摘要列表 |
| generated_resources | 可空plan_id、content_digest、dependency_digest；新链路均必填，绑定同owner/unit/scene/plan；content不原地修改 |
| 新审核记录（T048建表） | review_record结构：准确binding、target/request/response摘要、Prompt与Provider配置摘要、服务端anchor_catalog、result、local_routing及创建时间；只追加，不能把原needs_human改为pass |
| 发布快照（T052建表） | owner/unit、单调publication_version、plan绑定、按固定顺序三个scene_binding、动作版本/摘要、各审核记录ID/摘要、一致性结果、approval_source与可空人工decision_id、unit_digest、created_at；只追加；单元持有唯一current_publication_id |
| 人工案件/决定（T050建表） | ADR C1字段，额外绑定publication候选的unit_digest；案件状态可受锁更新，内容绑定不改，决定只追加 |

外键至少以(owner,unit,id)复合唯一键约束同域引用；服务验证对应scene的plan与resource的plan相同（数据库可用含plan_id复合键）；旧nullable绑定保持null，不伪造历史计划或新资格。计划表origin_operation_id记录首次创建操作，plan_record.binding.operation_id在创建快照中即该origin，永不随重解释更改。审核/依赖/发布/案件binding.operation_id则是当前执行操作：复用计划时可不同于origin，但须同owner/unit，plan_id/version及计划原input/references/policy摘要必须匹配。当前操作的调整请求另存既有operation.request_digest/input_snapshot，实际审核请求摘要绑定它，不覆写计划输入。旧数据不能借部分新列值进入新发布器。不可变字段通过服务拒绝更新并在PG建立写入保护/约束，owner删除仍按已批准级联规则执行；发布/撤回资格在独立指针/事实记录变化，不改历史正文。

规范字节统一为Python等价`json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`；拒绝重复键、浮点数/NaN（本契约无需浮点）与非Unicode标量；不做空白、换行或Unicode归一化。SHA256小写hex。摘要输入带`kind`及`schema_version`域标签；digest字段自身不参与自己的摘要。

- plan_digest：`{kind:"plan",schema_version:"learning-plan-v1",plan:<完整plan>}`。input_digest绑定实际节点/图/画像证据/目标/语言输入快照；references_digest绑定有序参考ID/version/digest及实际参考字节的摘要。快照需保存到可读的版本化记录，只有哈希而无原文不足以复核。
- content_digest：`{kind:"resource",schema_version:<资源schema版本>,resource_type,content,prompt_version}`；dependency_digest绑定完整plan binding及按依赖顺序的上游资源ID/content_digest/dependency_digest。服务重算；不信模型/客户端提供的摘要。
- unit_digest：`{kind:"unit",schema_version:"learning-publication-v1",binding,scenes:<三scene_binding>,actions_version,actions_digest}`，尚未审核时即可计算。审核target_digest必须等于准确资源content_digest或unit_digest；审核记录本身不参与unit_digest以避免循环。审核结果/人工决定的摘要由发布快照另绑定，发布时全部重检。
- request/response_digest是审核实际wire和收到的完整最终响应字节摘要；不保存推理正文、密钥或含密钥的配置。provider_config_digest只覆盖非秘密厂商/模型/推理/采样配置。

T044先确立计划/场景/资源列及结构验证，T048/T050/T052分别增加审核/人工/发布表，不提前建立空的业务资格。需要变更本契约字段含义或不可变边界时先修订ADR/manifest，不能悄悄在后续迁移改变。

## 3. 审核结构与本地附加规则

`resource-review-v4`的scope=resource用于逐资源，scope=unit用于一致性。一致性不接受revise，不启动全单元修正循环。coverage.checked是明确检查项ID，unchecked与unresolved保留未知；服务端先从原候选生成anchor_catalog，保存anchor_id、资源ID/摘要、JSON Pointer及UTF-8范围，完整候选仍提供给审核器。模型finding.anchors只选择该目录的短anchor_id，不计算摘要或坐标；持久化review_record保留准确目录。start_utf8/end_utf8为该Pointer所指字符串UTF-8字节的半开区间（0≤start<end≤字节长度，且落在字符边界）。涉及非字符串值时锚定其既有字符串说明；无法定位不得伪造坐标，应needs_human并记录未知。整单元可引用多份绑定资源；跨owner/候选外引用、摘要或坐标失配为协议失败，不转人工洗白。

每条finding必须有类别、严重度、实际条件/反例与影响。`pass`要求findings、unchecked、unresolved全空且checked覆盖该scope必检项；缺必检项视为覆盖不完整，进入needs_human。`revise/reject`至少一条发现；`needs_human`必须有未决项或未覆盖项。结构合法但证据只剩空泛标签转人工；能否识别流畅伪反例仍待真实验收。当前有据严重reject优先结束；分类不等于事实，人工不能豁免硬失败。review_record.result原样保存解析后的模型正文，local_routing另保存最终路由verdict（额外允许failed）、固定reason_codes和policy_version；二者不可覆盖，证据不足/覆盖未知据本地路由处理，不把本地路由伪装成模型原结论。

资源checked最小集：facts、code_safety、learner_fit、objectives、reference_scope；不适用项在明确scope约定下记录检查结果，不省略必检。单元checked最小集：terminology、conventions、example_trace、answer_consistency、action_references。这些ID由服务校验，不靠数组非空冒充覆盖完成。anchor_catalog ID唯一，finding引用必须存在且属于目标；目录上限512，超限失败，不截断尾部来假装完整覆盖。服务生成目录不等于完整语义覆盖，完整内容仍接受独立审核。

文档结构检查命令为`backend/.venv/bin/python docs/acceptance/phase-1-om-redesign/check_contract.py`：只检查Draft 2020-12及合成正反例，不声称已实现跨字段、持久化或语义门禁。

## 4. 旧入口与三场景读取

| 对象/动作 | 兼容决定 | 实施与验收 |
| --- | --- | --- |
| 旧目录/无计划单元 | 保留intro及原三资源同场景布局；不迁移正文、不添加新资格 | T044迁移前后读回；T052旧签核/撤回回归 |
| 新计划单元入课堂 | 从current_publication_id的完整快照解析explanation场景；不再按key单独取max(version)，也不伪造intro行 | T052替换current_intro_scene调用为显式legacy/planned解析，课堂创建返回真实key/version |
| 前端仍传intro | 新计划单元仅把intro作为explanation的请求别名，在owner/unit/当前发布快照内解析；响应始终返回explanation；旧幂等收据逐字重放，旧会话不改写 | T052后端别名/CAS/重放；T053前端采用服务返回key与版本 |
| 阅读代码/练习 | 新单元GET按同一个发布快照返回三个场景和关联资源，受约束动作/前端顺序展示；课堂会话首版仍锚定讲解，不因查看代码/练习隐式切换会话，不新增场景切换命令 | T052读取不混版本；T053渲染三个场景；练习提交依真实resource_id走现有owner门禁 |
| 重解释取材 | legacy保持原同场景查找；planned按base发布快照取explanation和关联code场景，语言来自同一计划；缺关联代码/语言或摘要错立即失败，不能静默Python兜底 | T052覆盖reexplanation_materials，跨版本、缺代码、越权失败 |
| 对code/exercise请求重解释 | 首版不支持，409固定码REEXPLANATION_SCENE_UNSUPPORTED；仅讲解/其intro别名可请求 | T052服务/T053OpenAPI及UI隐藏不支持入口 |

新课堂会话持有publication_version，创建/恢复查询返回它；写操作基于既有expected_revision与base_scene_version，同时核对会话所绑发布快照。新发布切换时同锁更新会话锚点、publication_version并递增revision；并发旧请求409，不重新解释到任意最新资源。单元GET增加可选publication_version查询：省略取current完整快照，指定只读该owner/unit已发布且未撤回版本；不存在或不可读404，不回退其他版本。历史只读版本不自动升级会话。既有POST路径、owner/CSRF与幂等键机制保留，T053补可选publication_version响应字段与上述409；旧单元无该字段也可恢复。现行OpenAPI尚不声称已支持。

## 5. 重解释与换示例的失效范围

新链路不再把重解释当“复制一个intro场景并沿用其余审核”。旧legacy分支维持既有实现；planned分支使用整单元操作和发布快照：

- simpler/deeper：保持计划及共享示例，生成新的讲解候选与scene行。code/exercise正文仅在仍满足计划时可作为未获新发布资格的复用候选，不追加模型生成即可按新依赖重绑定为新resource/scene行；三资源全部重新审核、重组动作、重新一致性检查。任何复用内容不再适配则失败/显式新操作，不超上限补循环。
- another_example：新plan_version及新共享示例，重新生成三资源；旧code、题目/答案、动作、资源审核、一致性、未发布案件与人工决定全部不得用于新摘要。不得只换讲解而继续出旧例题。所有实际调用计入同一新操作20/22与180秒上限；无旧额度转入。
- 所有修改均使依赖图后代、原动作/单元结果/待审案失效；旧人工批准不继承。未发布的失效案按ADR C1结束。已发布旧版仍可读、继续学习，不因为新版本等待/失败就撤回旧版；只有显式撤回才撤回。新的测验/动画资格按准确新发布资源重新判断，旧答案记录/笔记/掌握度证据不搬到新题也不追溯改写；新重解释仅沿既有规则记困惑事件，不自动授予掌握度。
- 新版全部审核/人工资格有效后，同事务切换current_publication_id、课堂锚点与revision；模型调用/人工等待在事务外。拒绝、取消、超时、发布冲突或崩溃回滚都保留旧完整版本。重放同键不再生成；新请求须显式新键。不允许从新讲解+旧code的按key最大版本查询拼课。

T052把这些适配实现纳入同一“完整单元原子发布”任务，T053同步SSE与UI：重解释awaiting_human只结束流、不发scene_ready；新完整发布成功才发scene_ready（讲解锚点及publication_version），前端随后GET准确完整版本。无论自动或人工，均不在部分资源准备好时发送正式就绪。
