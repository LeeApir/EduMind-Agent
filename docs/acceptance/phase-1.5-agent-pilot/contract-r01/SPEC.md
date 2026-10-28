# 有限头插规格 r01

准确输入键：version="head-insertion-spec-v1"、initial_values（空或最多3个整数）、insert_values（1–4个整数）、variant（normal/reversed_assignment/discard_return/uninitialized_next）、allocation_success（每次尝试一个bool）。整数范围[-99,99]，允许重复值，以稳定节点ID区分。所有键必需，额外字段拒绝；bool不视作整数。初始链预先构造正确，不对初始节点分配建模。

节点ID：初始 i0…，尝试插入 t0…；链表 head 为节点ID或null，next 为节点ID/null/indeterminate。未成功分配不产生节点。明确假设单线程、固定模板、无外部别名修改、不释放节点直至观察结束、整数值无运算溢出。每次函数调用结束把返回值交给调用者或显式丢弃；轨迹保留局部 p、局部 head 与 caller_head，不能混用观察范围。

| 变体 | 固定程序语义 | 允许断言 |
| --- | --- | --- |
| normal | p=allocate；失败return head；成功p.data=value,p.next=head,return p；caller_head=insert(...) | 最终可达值与头节点；遍历到null终止 |
| reversed_assignment | 成功后 head=p，再p.next=head，return head；调用者接回 | 新头自环，旧链不再从新头可达；遍历重复节点，不能给有限遍历次数答案 |
| discard_return | 函数体同normal，调用者调用但丢弃返回值 | caller_head始终为原头；新节点存在但不可从caller_head到达；不能把局部新头当调用者头 |
| uninitialized_next | 成功后p.data=value，省略p.next赋值，return p；调用者接回 | next=indeterminate；追踪到该字段即unknown，不推断null/自环或确定遍历输出 |
| allocation_failure（由掩码控制） | malloc返回null立即return原局部head，其余语句不执行 | 原调用者头/链保持；与全部变体组合时失败路径优先 |

输出 observation：caller_head、reachable_prefix、traversal_status（terminated/cycle/indeterminate）、cycle_entry/null、allocation_failures、unreachable_allocated_ids。可达序列最多节点总数+1次观察，有visited集合；indeterminate停止，不读取虚构指针。仅这些可判定观察可成为标准答案；指针未初始化的“精确遍历结果”问题返回unsupported_question，不生成可靠答案。

拒绝：任意C/自定义语句/未知variant/越界参数/无关数据结构/非法初始拓扑/未知问题。分配失败掩码是合成前提，不模拟真实malloc概率。所有输出是抽象模板语义证据，不是实际C执行、任意内存安全证明或已发布课程。

T067必须先用手算独立期望覆盖每个变体、非空初始链、重复值、混合分配失败、全部失败；再做长度/值重命名/失败不改变头等变形检查。期望不得调用被测引擎生成。任意实际C执行须另行安全契约，不在本提案内。
