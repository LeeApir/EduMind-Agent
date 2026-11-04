# T108 r03 真实规划独立语义核对

2026-11-04；评估者：独立评估助手 `/root/head_goal_independent`。对象为安全导出的模型wire原稿、local mapping及实际同版payload。

**结论：pass，仅真实规划语义核验通过。** plan_digest：`b6cc3d5304b87673c343a9cf31f11ae2cf8b44d4f12a07e852795ac71d4e4991`。准确planning_basis_binding已原样写入plan-review.json；没有改写模型规划或补正文。

原始目标与request_1两项引文相符，自述C指针/struct/NULL/返回值保留为自述，未冒称已测掌握。规划选head-new-A，初始i0(12)、依次插4/7，一个场景四种形式；学习目标及purpose覆盖连接旧链表与调用者接收返回值，未把场景打包要求冒作学习目标。

本稿明确区分insert参数head与main的caller_head；步骤为p->next=head及return p，未插入head=p或另造实现。接收返回值时调用者保存新地址；忽略返回值时caller_head仍为旧入口，新分配节点从该入口不可达，未重复r02的“旧入口消失”表述。术语、代码选择和教学顺序与同版依据一致，当前目标没有必须澄清的未知材料。

独立手算：第一次local head=i0，t0.data=4、t0.next=i0，返回t0；接收后caller=t0，[4,12]。第二次local head=t0，t1.data=7、t1.next=t0，返回t1；接收后caller=t1，[7,4,12]。若两次均忽略返回值，则两次参数head均i0，caller仍i0、可读[12]，t0/t1不可从该入口到达。这与提供的代码和receive/ignore依据相符。假定malloc实际成功、不执行C、未演示释放/失败的边界保留。

独立核对wire单计划、local值、payload.plan逐对象相等；选例materials_digest与评估binding一致。仅读取安全导出与程序资料；未读Key、终端、私有raw.key，未调用Provider。

这不是完整课程或教学效果pass。按本批协议可继续一次完整正文生成；正文仍须独立核对逐段/逐帧/四题、答案不泄露、范围/生命周期等。最终还需实际应用学习与刷新评估，不能沿用本规划pass代替。r01/r02原失败保持，窗口/额度不扩展。
