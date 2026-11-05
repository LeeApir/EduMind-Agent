# T109 r01 真实规划独立语义核对

2026-11-05，评估者 `/root/head_goal_independent`。**准确规划pass，可进入正文；不是正文／课程教学pass。** 准确摘要及basis见同目录plan-review.json。评估者未调用Provider，未读凭据／终端／私有vault／raw.key，未补写模型规划或教学。

独立读取安全导出context、request、完整raw、wire输出、mapping及binding。原始响应7290字节／SHA `31f6111a4cc8ce891674fc2053ffd0dd39a65314e68c9105e2e9cfe376d52e50` 独立重算一致；同版实际planning_body、原适配输出、wire→local mapping及content_payload与保存值精确相等，材料与冻结B材料相同。

两个目标分别准确引用原要求“理解新节点如何连接旧链表”和“为什么调用者需要接收函数返回值”，场景覆盖两目标且包含讲解、代码、演示、练习。自述C指针／struct／NULL／返回值仅为先备自述，未伪称测得掌握度；其余画像未知。

所选明确为指定head-new-B：初始[-8]，按6、0顺序插入，两次成功分配作为本示例假设。函数接口与程序一致；函数形参head是main caller_head的指针值副本，局部p分配新节点，p->next=head保存旧头，return p返回新头，未捏造head=p或把局部与调用者混同。

独立手算：接收第一次返回后t0{6,i0}、caller=t0；第二次t1{0,t0}、caller=t1，最终0→6→-8→NULL。忽略两次返回时每次head均i0，新t0／t1各next=i0，caller始终i0，仍可达[-8]且仅两个新动态节点不可达。规划描述、约定和术语均符合此结论，没有把原链入口说成丢失。

规划职责为本次指定B的真实目标／教学组织，不代表验证了自由选例能力。15分钟是教学安排估计，不是实际学习时长证据。真实malloc失败／初始化细节／生命周期及完整13帧／四题是否正确清楚，须在后续正文独立审核，不由本规划pass预先签署。
