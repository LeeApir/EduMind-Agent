# ADR0054：限定前台状态与可引用教学证据

2026-11-05。**本轮用户已授权的零调用修复已实施；第3节是后续模型局部修订的待决定差异，不是本轮调用或修订批准。** T109 r01保持STOP/blocked，原稿、原材料、原审核不改；T102 blocked，新Provider预算0。

## 1. E01沿用现有操作契约

`head-goal-course-v1`和`head-reuse-course-v1`属于同一限定前台模式，由状态投影中的同一个白名单判断，均返回`execution_mode=finite_head_foreground`和`budget=null`。未知版本不自动当作前台模式；普通调度的预算仍返回。沿用已有OpenAPI字段和前台页面控制，不改DB状态或统计口径，不把真实2次请求写成普通调度0次，也不伪造退款或重置历史用量。

原操作仍为failed/TEACHING_REVIEW_FAILED，仅前台失败操作的显示标签为“生成已停止”；其通用预算、恢复/澄清/调整入口继续按既有前台模式隐藏或禁用。普通调度的failed标签与自身预算/恢复约定保留。本轮不改正式课程权限，不新增调度器或停止监督器。

## 2. 新依据是显式版本补充，不重写旧材料

新增`head-teaching-evidence-v1`，从原`materials`/13帧及`planning_basis`提取和核对；材料/引擎/模板/主例/规格/basis/frames摘要都进入来源与证据摘要。两类事实分别为：

- `head_evidence_v1.displayed_success_path`：`evidence_kind=displayed_trace`。穷举主播放器f00–f12，f01/f07分配成功，f02/f08执行`p == NULL`且结果false，分别继续f03/f09；不分配分支帧为空，真实malloc失败也未展示。这是程序模型中的展示范围，不是真实C执行；两次判空是已有播放器对分配状态投影出的帧，来源明确标注。
- `head_evidence_v1.discard_return_comparison`：`evidence_kind=computed_counterfactual`、`displayed_in_main_player=false`、主帧引用为空。以相同spec只变`variant=discard_return`，用既有引擎单独计算、与已保存basis.ignore_return核对，并用闭式期望独立核验：caller仍i0，可达[-8]，t0/t1不可达、分配失败0。该对照有自己的代码/规格/示例摘要和逐调用状态；不能写成主13帧已播放。

`with_evidence(original_payload)`显式生成新输入副本的`teaching_evidence`字段，旧catalog/代码/轨迹/答案/basis/原目标均保持相等。只有带这个版本字段且完整重建校验通过的输入，正文请求构造才提供新证据，段落引用才可使用“旧catalog IDs ∪ 新supplement IDs”。未知ID、伪造证据、来源/类型/帧/结果漂移均拒绝。未带补充字段的旧输入仍只接受旧ID，旧请求按原材料逐字重建，旧候选按原响应复现。

完整教学输出Schema不变；`failure_scope`仍为字符串。补充依据不是模型新生成成功、不是助手补写教学、不是自动语义pass。本轮仅导出明确标记的离线新输入/请求预览及引用准入检查，不把该预览写进旧候选或现有课程版本。

## 3. 后续局部修订所需最小差异（待决定）

1. **准确父稿和材料绑定。** 父候选仍是r01的`63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`，原raw/payload不变。单独登记“程序证据补充”派生关系与新evidence_digest；只允许输入增加经完整验证的teaching_evidence，不得改原code/spec/trace/answers/basis来掩盖原问题。修订新候选须绑定准确父稿及新证据版本，不能把新ID塞进原材料或复用旧摘要冒充同版。
2. **只扩一个必要字段。** 既有r01规则不允许`failure_scope`，后续须显式允许审核定位的该字段，限纠正实际已展示/未展示范围；同时允许审核定位的`paragraphs[5]`完整text+fact_ids处理C01。继续由意见派生封闭输出Schema，不把S01/F01或索引写成通用源码常量；其他未被准确审核定位的字段不动。当前summary没有对应阻断，不应为方便而自动加入。
3. **引用及职责。** 新review应可携带上述支持证据IDs，校验其版本/来源；模型替换段落须保留“忽略返回导致入口不变、节点不可达、与分配失败区分”的原职责，采用正确counterfactual ID。`failure_scope`明确两次成功/判空以及掩码不分配与实际malloc失败均未演示。不能用把问题移到别处、复制邻段或删除必要解释通过。
4. **原停止不解除。** 后续准确请求、修订协议版本、候选派生准入、调用预算/窗口/C2须另行冻结批准；本轮不实现或启动这些真实执行变化，不重开r01或继承余1。若获准修订，严格合并、全文重评和实际学习/反馈/刷新仍是课程验收前置。现有r01局部修订入口不会因本轮新增证据自动接收这些新字段或新payload。

本轮交付是修复状态和必要证据前置，不能因此把T109标done。无需改教学Schema或移植运行框架；是否启动上述有限修订由用户后续决定。
