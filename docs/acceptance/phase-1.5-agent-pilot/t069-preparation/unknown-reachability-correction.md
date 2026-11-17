# e01独立发现与v2修正

独立评估助手在选样前发现v1错误：当 next=indeterminate 时，未visited的已分配节点不能被证明不可达。其原始问题和候选摘要保存在 independent-e01-summary.json；没有独立输入/真值被签核，真实调用0。

按ADR0041已批准“未知不得当正确”的原有原则修正内部事实解释，不改冻结提案字节或新增数据权限：

- traversal_status=indeterminate 且有未访问节点：unreachable_allocated_ids=null，表示集合未知。
- traversal_status=indeterminate 且所有已分配节点已被访问：unreachable_allocated_ids=[]，仅表示已分配节点中没有剩余候选，不表示遍历终止。
- terminated/cycle保留确定集合。

字段未更名、不新增字段。原型事实引用的JSON value本来允许null；这个字段不在固定四个评分观察键中。模板/原生产代码/规则/评分权限不变，ENGINE_VERSION升级head-insertion-engine-v2，旧v1证据保留；旧候选不追认为正确。

独立助手已确认上述空集/未知区分的语义方向成立，但这不是新候选或真值签核。旧开发断言“未初始化后未visited节点等于不可达”本身错误，已据独立发现更正为null，并补六项更强回归：非空初始链、多次成功、中途失败、失败后保留unknown、无其他节点时的确定空集。

后续材料和模型必须把null解释为未知，不能转空数组。旧r01 Mock证据属于v1，当前v2核验器若不匹配应报告候选版本不支持，不能重写旧原件；新r02使用新独立输出目录。独立助手须在v2源码摘要冻结后重新开始选样，未签核前真实执行继续禁止。
