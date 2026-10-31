# 旧审核目标逐类迁移提案

范围为 `p15_reference_review_v1.make_binding()` 创建的原目标：`c._targets()` 递归到第 4 层或动作行并将整个非字符串节点转成 canonical 文本，之后额外加入逐引用 `label`／`kind` 目标。旧目标及字面字符串不改写；新视图是新版本、独立结果，不把旧 target ID／quote 认作新证据。

| 原目标路径模式 | 新视图处理 | 程序完整性检查及变化 |
|---|---|---|
| `/raw_output/paragraphs/<i>/text` | 第 i 段原文一个可引用文本单元 | 与该槽原始响应及显示文档逐字相等；短 ID 不跨版本继承 |
| `/raw_output/paragraphs/<i>/key` | 展示顺序与段落锚点；锚点本身可作为单元引用 | 校验唯一性、顺序、块与文档映射 |
| `/raw_output/questions/<题型>/stem`、`/explanation` | 每题完整题干、解析分别可引用 | 与模型原文及播放器字段逐字绑定 |
| `/raw_output/questions/<题型>/fact_ids`、`/raw_output/paragraphs/<i>/fact_ids`（C） | 必要事实以可见参考单元及显式来源标识呈现；不以 ID 存在代替讲解审核 | 重建 catalog、逐 ID 检查成员、准确值、题型观察要求及摘要；旧 ID 数组整体 canonical 字面引用转为程序检查，具体事实值可引用 |
| `/raw_output/code`（B）与 `/source/blocks/<i>/text`（代码块） | B 原代码／C 程序代码完整可见，并以可引用的准确行及可确定顺序展示；重复副本合并 | 重建代码归属和完整行拼接，检查原代码、锚点与动作行号；旧重复副本和整块 canonical 引用改为对应可见行引用，不能跨行拼接引文 |
| `/raw_output/answers/<题型>` 或其子项（B） | B 模型独立答案按准确类型及完整值可见；具体答案可引用 | 校验 schema 与模型原响应；禁止用参考值填充或改写 |
| `/raw_output/actions/{states,highlights,advances}/<i>`（B） | B 模型的每个状态、动作及高亮关联以实际可见 canonical 字符串单独引用 | 按 order 解码和验证完整性；不可从 C 引擎替换；旧数组/对象祖先可按可见状态或动作单元引用，不能引用未发送的旧对象包装 |
| `/source/actions/<i>` | 每个实际播放动作、顺序、代码锚点及状态关联可见且有目标 | C 与确定性引擎逐项核验；B 与其模型动作逐项对应；动作来源如实显示 |
| `/source/blocks/<i>/kind`、`/anchor`、`/document`、`/stem_document`、`/explanation_document`、`/observation_key` | 显示块类型、顺序、锚点和题型，与对应正文／代码／题目单元关联；必要的可见标签可引用 | 程序检查无遗漏、重复、错误锚点、跨文档或题型错位；不再引用内部文档 ID 的旧包装 |
| `/source/blocks/<i>/answer_key` | 对应四题完整准确答案可引用 | C 与当前 catalog 观察绑定；B 与模型自身答案绑定，不以参考覆盖 |
| `/source/documents/documents/<文档>` | 旧整个文档祖先拆分为完整原文、引用标签／位置、定义与有关教学字段等可见单元 | 原 AST、occurrence、声明、完整原对象与摘要在本地重建；**旧整个文档 canonical 字面字符串不再是可引用目标**，不能以可逆解压宣称模型见过它 |
| `/source/documents/documents/<文档>/occurrences/<i>/label`、`/kind` | 每处引用的可见标签、惰性类型及其在文档的明确位置可定位；空标签使用非空的结构类型目标 | 位置、定义和标签从同一文档重建，保证不漏、不串；类型是程序结构，不冒充原文摘录。位置若是 AST 路径，明确非原文字节偏移 |
| `/source/documents/references/<ref>` | 完整目标 URL／标题等定义以惰性文本可见，按可见定义字段引用；不得激活链接／图片 | 重建所有声明与使用，包括未使用定义、同名异域和目标摘要；旧定义对象整体 canonical 字面引用拆为字段 |
| `/source/resolved_facts/<fact>/value`（C） | 与该槽教学有关的完整事实／状态以来源标识直接可见 | catalog/spec/example 摘要与值重建比对；不替换 B 模型答案 |
| `/source/resolved_facts/<fact>/{path,origin,example_digest}`（C） | 事实来源或路径中的理解所必需部分以可见标签呈现 | 完整路径、origin 和摘要进行程序绑定；旧散列文本不作为模型教学证据 |
| `/identity/*`、`/artifact_digest` | 与理解所需的槽、臂、候选短 ID 和修订版本可见 | 全部身份字段、prompt、请求/响应/收据摘要及父链本地精确校验；旧散列和内部 ID 本身转为程序证据，不允许引用本地隐藏内容 |
| `/source/{version,engine_version,template_version,example_digest,revision,parent_digest}` | 必要来源/版本标签可见 | 校验具体版本、示例、修订、父链和受控收据；不再把内部散列作为教学引用 |
| `/source/{degraded,production_scoring}` 与 `/source/provenance/*` | 明确显示模型／程序归属及降级状态 | 程序逐项验证归属、评分边界；原布尔/归属的旧包装不再是原字面目标 |
| `/source/documents/{version,digest}` | 文档表示版本标识可见 | 原文、解析树、引用和定义可重建，完整摘要本地核验；digest 字面转为内部检查 |

实现必须针对每个旧 binding 目标输出 `old_path → 迁移规则 → 新目标 ID 集合或具体程序检查 ID` 的机器报告。上表的 `<i>`、`<题型>`、`<fact>`、`<文档>`、`<ref>` 为覆盖整个合法动态集合的占位符，不是固定样本列表。目标路径若不匹配规则、映射为空而无明确程序检查、生成的对应项遗漏／重复／错位，构建即失败。空容器可能作为旧祖先目标出现：按其父级语义生成明确的“空”可见单元或带空值的对应程序检查，不得丢弃。

旧复合目标可能同时含教学材料与内部元数据：必须逐字段拆分，教学材料进入模型可见目标，内部部分登记具体程序检查，不能把整个混合对象一律归为程序检查。空容器可呈现实际的 `[]`／`{}` 或记录为程序检查；不能虚构显示文字并允许模型引用。报告须为每个旧目标提供可重放的判定规则：给定旧 path 和 quote，判断能否映射至新可见单元，或属于拆分后不可引用／转为内部检查，并给出代表性反例；不要求穷举长字符串的全部子串。

本表是提议分类，不是已完成的逐路径自动核对。上述“程序检查”必须在实际控制器中以原始响应及来源收据重放实现；单独做一个映射清单、散列或离线示例不能代替。
